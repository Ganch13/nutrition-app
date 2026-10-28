#!/bin/bash
# Восстанавливает базу (и, по желанию, фото) из резервной копии. Запуск на сервере:
#   ./deploy/backup/restore.sh /var/backups/nutrition/nutrition-db-2026-10-27_033000.dump [/var/backups/nutrition/nutrition-photos-2026-10-27_033000.tar.gz]
#
# Как это работает (и почему безопасно):
#   1. Копия сначала разворачивается во ВРЕМЕННУЮ базу. Если файл повреждён, сайт и текущие данные не затрагиваются.
#   2. Делается резервная копия текущего состояния (на случай, если восстанавливать не нужно было).
#   3. Сайт останавливается, текущая база переименовывается в nutrition_before_restore_<время> (не удаляется!),
#      а восстановленная становится рабочей.
#   4. Если указан архив с фото, содержимое папки с фото заменяется им.
#   5. Сайт запускается; при старте backend сам доводит структуру базы до актуальной версии (миграции).
#
# Для тестов можно подменить: COMPOSE_CMD, DB_EXEC_CMD, DB_NAME, DB_USER, RESTORE_CONFIRM=yes.

set -euo pipefail

if [ $# -lt 1 ] || [ $# -gt 2 ]; then
    echo "Использование: $0 <файл-базы.dump> [файл-фото.tar.gz]" >&2
    exit 2
fi

cd "$(dirname "${BASH_SOURCE[0]}")/../.."

DB_FILE="$1"
PHOTOS_FILE="${2:-}"
DB_NAME="${DB_NAME:-nutrition}"
DB_USER="${DB_USER:-nutrition}"

if [ -n "${COMPOSE_CMD:-}" ]; then
    read -ra COMPOSE <<< "$COMPOSE_CMD"
else
    COMPOSE=(docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env)
fi

# Команда внутри контейнера базы. Пример: db_exec psql -U nutrition -c "select 1"
db_exec() {
    if [ -n "${DB_EXEC_CMD+x}" ]; then
        # shellcheck disable=SC2086
        $DB_EXEC_CMD "$@"
    else
        "${COMPOSE[@]}" exec -T db "$@"
    fi
}

fail() { echo "ОШИБКА: $*" >&2; exit 1; }

[ -f "$DB_FILE" ] || fail "файл $DB_FILE не найден"
[ -z "$PHOTOS_FILE" ] || [ -f "$PHOTOS_FILE" ] || fail "файл $PHOTOS_FILE не найден"

# Контрольные суммы, если рядом лежит файл .sha256 от backup.sh
check_sum() {
    local file="$1" dir name sums
    dir="$(dirname "$file")"; name="$(basename "$file")"
    sums="$(grep -l -F "  $name" "$dir"/nutrition-*.sha256 2>/dev/null | head -n 1 || true)"
    if [ -n "$sums" ]; then
        ( cd "$dir" && grep -F "  $name" "$sums" | sha256sum -c - ) || fail "контрольная сумма $name не совпала: файл повреждён"
    else
        echo "Внимание: файла с контрольными суммами для $name нет, целостность не проверена."
    fi
}
check_sum "$DB_FILE"
[ -z "$PHOTOS_FILE" ] || check_sum "$PHOTOS_FILE"

echo
echo "Будет выполнено восстановление:"
echo "  база:  $DB_FILE"
[ -z "$PHOTOS_FILE" ] || echo "  фото:  $PHOTOS_FILE (текущие фото на сервере будут ЗАМЕНЕНЫ)"
echo "  Всё, что добавлено в приложение после создания этой копии, будет недоступно."
echo "  Текущая база будет сохранена под именем ${DB_NAME}_before_restore_<время> и не удалена."
if [ "${RESTORE_CONFIRM:-}" != "yes" ]; then
    read -r -p "Для подтверждения введите слово ВОССТАНОВИТЬ: " answer
    [ "$answer" = "ВОССТАНОВИТЬ" ] || { echo "Отменено."; exit 1; }
fi

stamp="$(date +%Y%m%d_%H%M%S)"
temp_db="${DB_NAME}_restoring"
old_db="${DB_NAME}_before_restore_${stamp}"

# 1. Временная база: проверяем, что копия вообще разворачивается
echo "[1/5] Проверка копии: восстановление во временную базу..."
db_exec psql -U "$DB_USER" -d postgres -v ON_ERROR_STOP=1 -q -c "DROP DATABASE IF EXISTS \"$temp_db\"" -c "CREATE DATABASE \"$temp_db\""
if ! db_exec pg_restore -U "$DB_USER" -d "$temp_db" --no-owner --exit-on-error < "$DB_FILE"; then
    db_exec psql -U "$DB_USER" -d postgres -q -c "DROP DATABASE IF EXISTS \"$temp_db\"" || true
    fail "копия не разворачивается (файл повреждён или не от этой программы). Рабочая база не тронута."
fi

# 2. Страховка: копия текущего состояния
echo "[2/5] Резервная копия текущего состояния..."
if "${COMPOSE[@]}" ps --status running --services 2>/dev/null | grep -qx backup; then
    "${COMPOSE[@]}" exec -T backup bash /backup/backup.sh || echo "Внимание: копию текущего состояния сделать не удалось, но старая база останется под именем $old_db."
fi

# 3. Остановка сайта и подмена базы
echo "[3/5] Остановка сайта и подмена базы..."
"${COMPOSE[@]}" stop caddy frontend backend
db_exec psql -U "$DB_USER" -d postgres -v ON_ERROR_STOP=1 -q \
    -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname IN ('$DB_NAME', '$temp_db') AND pid <> pg_backend_pid()" \
    -c "ALTER DATABASE \"$DB_NAME\" RENAME TO \"$old_db\"" \
    -c "ALTER DATABASE \"$temp_db\" RENAME TO \"$DB_NAME\"" > /dev/null

# 4. Фото
if [ -n "$PHOTOS_FILE" ]; then
    echo "[4/5] Восстановление фото..."
    # Одноразовый контейнер backend с теми же томами; запускается от пользователя приложения, поэтому права на файлы верные
    "${COMPOSE[@]}" run --rm --no-deps -T --entrypoint sh \
        -v "$(cd "$(dirname "$PHOTOS_FILE")" && pwd)/$(basename "$PHOTOS_FILE"):/restore/photos.tar.gz:ro" \
        backend -c 'find /data/uploads -mindepth 1 -delete && tar -xzf /restore/photos.tar.gz -C /data/uploads'
else
    echo "[4/5] Фото не восстанавливаются (архив не указан)."
fi

# 5. Запуск
echo "[5/5] Запуск сайта..."
"${COMPOSE[@]}" up -d --wait --wait-timeout 300

echo
echo "Готово. Откройте сайт и проверьте данные."
echo "Прежняя база сохранена как \"$old_db\". Когда убедитесь, что всё в порядке, удалите её:"
echo "  docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env exec -T db psql -U $DB_USER -d postgres -c 'DROP DATABASE \"$old_db\"'"
