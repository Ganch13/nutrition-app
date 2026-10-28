#!/bin/bash
# Проверка, что резервные копии действительно восстанавливаются («учения»). Рабочая база не затрагивается:
# копия разворачивается во временную базу, показываются числа записей, после чего база удаляется.
# Запускайте раз в месяц и после любых изменений в настройках копирования:
#   ./deploy/backup/test-restore.sh                       # проверить самую свежую копию
#   ./deploy/backup/test-restore.sh /путь/к/файлу.dump    # проверить конкретную копию

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

DB_USER="${DB_USER:-nutrition}"
if [ -n "${COMPOSE_CMD:-}" ]; then
    read -ra COMPOSE <<< "$COMPOSE_CMD"
else
    COMPOSE=(docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env)
fi
db_exec() {
    if [ -n "${DB_EXEC_CMD+x}" ]; then
        # shellcheck disable=SC2086
        $DB_EXEC_CMD "$@"
    else
        "${COMPOSE[@]}" exec -T db "$@"
    fi
}

file="${1:-}"
if [ -z "$file" ]; then
    backup_dir="$(grep -E '^BACKUP_DIR=' deploy/.env 2>/dev/null | tail -n 1 | cut -d= -f2- | sed -E 's/[[:space:]]+#.*$//' || true)"
    backup_dir="${BACKUP_DIR:-${backup_dir:-/var/backups/nutrition}}"
    file="$(ls -1t "$backup_dir"/nutrition-db-*.dump 2>/dev/null | head -n 1 || true)"
    [ -n "$file" ] || { echo "ОШИБКА: в $backup_dir нет копий nutrition-db-*.dump" >&2; exit 1; }
fi
[ -f "$file" ] || { echo "ОШИБКА: файл $file не найден" >&2; exit 1; }

dir="$(dirname "$file")"; name="$(basename "$file")"
sums="$(grep -l -F "  $name" "$dir"/nutrition-*.sha256 2>/dev/null | head -n 1 || true)"
if [ -n "$sums" ]; then
    ( cd "$dir" && grep -F "  $name" "$sums" | sha256sum -c - ) || { echo "ОШИБКА: контрольная сумма не совпала" >&2; exit 1; }
fi

temp_db="restore_check_$(date +%s)"
cleanup() { db_exec psql -U "$DB_USER" -d postgres -q -c "DROP DATABASE IF EXISTS \"$temp_db\"" > /dev/null 2>&1 || true; }
trap cleanup EXIT

echo "Проверяется копия: $name ($(du -h "$file" | cut -f1)), возраст: $(( ( $(date +%s) - $(stat -c %Y "$file") ) / 3600 )) ч."
db_exec psql -U "$DB_USER" -d postgres -v ON_ERROR_STOP=1 -q -c "CREATE DATABASE \"$temp_db\""
db_exec pg_restore -U "$DB_USER" -d "$temp_db" --no-owner --exit-on-error < "$file"

tables="$(db_exec psql -U "$DB_USER" -d "$temp_db" -tA -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")"
[ "$tables" -ge 5 ] || { echo "ОШИБКА: в восстановленной базе только $tables таблиц" >&2; exit 1; }

echo "Таблиц в копии: $tables. Записей:"
for table in users households household_members weight_records meal_entries progress_photos refresh_tokens; do
    count="$(db_exec psql -U "$DB_USER" -d "$temp_db" -tA -c "SELECT count(*) FROM $table" 2>/dev/null || echo "нет таблицы")"
    printf '  %-20s %s\n' "$table" "$count"
done
echo "Версия структуры базы (alembic): $(db_exec psql -U "$DB_USER" -d "$temp_db" -tA -c "SELECT version_num FROM alembic_version" 2>/dev/null || echo "нет")"
echo "OK: копия восстанавливается."
