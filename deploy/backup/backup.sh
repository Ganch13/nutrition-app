#!/bin/bash
# Делает одну резервную копию: базу данных и фото прогресса. Удаляет устаревшие копии.
#
# Запускается автоматически службой backup (раз в сутки) и вручную:
#   docker compose -f deploy/docker-compose.prod.yml exec backup bash /backup/backup.sh
#
# Результат в папке BACKUP_DIR (по умолчанию /backups), например:
#   nutrition-db-2026-10-27_033000.dump        база (формат pg_dump custom, уже сжата)
#   nutrition-photos-2026-10-27_033000.tar.gz  фото прогресса
#   nutrition-2026-10-27_033000.sha256         контрольные суммы обоих файлов
#
# Параметры (переменные окружения): PGHOST, PGUSER, PGPASSWORD, PGDATABASE — подключение к базе;
# BACKUP_DIR, UPLOADS_DIR — папки; KEEP_DAILY_DAYS, KEEP_MONTHLY_MONTHS — сколько хранить (см. rotate.sh).

set -euo pipefail
# Файлы копий: владелец читает и пишет, его группа (на сервере это группа nutribackup, куда входит администратор)
# только читает, остальным доступа нет: в копиях все данные семьи
umask 027

BACKUP_DIR="${BACKUP_DIR:-/backups}"
UPLOADS_DIR="${UPLOADS_DIR:-/data/uploads}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

stamp="$(date +%Y-%m-%d_%H%M%S)"
db_name="nutrition-db-$stamp.dump"
photos_name="nutrition-photos-$stamp.tar.gz"
sums_name="nutrition-$stamp.sha256"

mkdir -p "$BACKUP_DIR"

# Две копии одновременно не нужны: вторая запустилась бы поверх первой.
# Блокировка старше двух часов осталась от внезапно остановленного копирования (контейнер убит) — снимаем её.
lock_dir="$BACKUP_DIR/.backup.lock"
if [ -d "$lock_dir" ] && [ -n "$(find "$lock_dir" -maxdepth 0 -mmin +120)" ]; then
    rmdir "$lock_dir" 2>/dev/null || true
fi
if ! mkdir "$lock_dir" 2>/dev/null; then
    echo "Резервное копирование уже выполняется (или прервалось неожиданно: удалите папку $lock_dir)." >&2
    exit 1
fi

partial_files=()
cleanup() {
    rm -f "${partial_files[@]}" 2>/dev/null || true
    rmdir "$lock_dir" 2>/dev/null || true
}
trap cleanup EXIT

echo "[$(date '+%F %T')] Копирование базы..."
partial_files+=("$BACKUP_DIR/$db_name.partial")
# Сначала пишем во временный файл: оборвавшаяся копия не должна выглядеть готовой
pg_dump --format=custom --no-owner --file="$BACKUP_DIR/$db_name.partial"

# Проверка: архив читается и содержит таблицы, а не пустой файл
tables="$(pg_restore --list "$BACKUP_DIR/$db_name.partial" | grep -cE ' TABLE public ' || true)"
if [ "$tables" -lt 5 ]; then
    echo "ОШИБКА: в копии базы найдено таблиц: $tables. Копия не принята." >&2
    exit 1
fi
mv "$BACKUP_DIR/$db_name.partial" "$BACKUP_DIR/$db_name"

# Фото копируем после базы: все фото, о которых знает база, к этому моменту уже на диске
files_to_sum=("$db_name")
if [ -d "$UPLOADS_DIR" ]; then
    echo "[$(date '+%F %T')] Копирование фото..."
    partial_files+=("$BACKUP_DIR/$photos_name.partial")
    tar -czf "$BACKUP_DIR/$photos_name.partial" -C "$UPLOADS_DIR" .
    tar -tzf "$BACKUP_DIR/$photos_name.partial" > /dev/null   # архив читается
    mv "$BACKUP_DIR/$photos_name.partial" "$BACKUP_DIR/$photos_name"
    files_to_sum+=("$photos_name")
fi

( cd "$BACKUP_DIR" && sha256sum "${files_to_sum[@]}" > "$sums_name" )

echo "[$(date '+%F %T')] Готово: $db_name ($(du -h "$BACKUP_DIR/$db_name" | cut -f1)), таблиц в копии: $tables"

bash "$SCRIPT_DIR/rotate.sh"
