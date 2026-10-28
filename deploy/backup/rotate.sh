#!/bin/bash
# Удаляет устаревшие резервные копии. Хранит:
#   - ежедневные копии за последние KEEP_DAILY_DAYS дней (по умолчанию 14);
#   - копии, сделанные первого числа месяца, за последние KEEP_MONTHLY_MONTHS месяцев (по умолчанию 6);
#   - три самые свежие копии всегда, даже если сервер долго не работал.
# Копия состоит из нескольких файлов с одним временем в имени (база, фото, контрольные суммы): удаляются вместе.
#
# Для проверки без удаления: ROTATE_DRY_RUN=1 ./rotate.sh
# Для тестов: BACKUP_TODAY=2026-10-27 подменяет «сегодня».

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
KEEP_DAILY_DAYS="${KEEP_DAILY_DAYS:-14}"
KEEP_MONTHLY_MONTHS="${KEEP_MONTHLY_MONTHS:-6}"
KEEP_LATEST=3
today="${BACKUP_TODAY:-$(date +%F)}"

# Недописанные файлы старше суток остались от оборвавшегося копирования
find "$BACKUP_DIR" -maxdepth 1 -name '*.partial' -mmin +1440 -delete 2>/dev/null || true

# Время каждой копии берём из имени файла базы: nutrition-db-2026-10-27_033000.dump → 2026-10-27_033000
mapfile -t stamps < <(
    find "$BACKUP_DIR" -maxdepth 1 -name 'nutrition-db-*.dump' -printf '%f\n' 2>/dev/null \
        | sed -E 's/^nutrition-db-(.*)\.dump$/\1/' | sort -r
)

today_epoch="$(date -d "$today" +%s)"
index=0
for stamp in "${stamps[@]}"; do
    index=$((index + 1))
    day="${stamp%%_*}"                                    # 2026-10-27
    day_of_month="${day##*-}"                             # 27
    age_days=$(( (today_epoch - $(date -d "$day" +%s)) / 86400 ))

    keep=0
    [ "$index" -le "$KEEP_LATEST" ] && keep=1
    [ "$age_days" -le "$KEEP_DAILY_DAYS" ] && keep=1
    if [ "$day_of_month" = "01" ] && [ "$age_days" -le $((KEEP_MONTHLY_MONTHS * 31)) ]; then keep=1; fi

    if [ "$keep" -eq 0 ]; then
        echo "Удаляется устаревшая копия $stamp (возраст $age_days дн.)"
        if [ "${ROTATE_DRY_RUN:-0}" != "1" ]; then
            rm -f "$BACKUP_DIR/nutrition-db-$stamp.dump" \
                  "$BACKUP_DIR/nutrition-photos-$stamp.tar.gz" \
                  "$BACKUP_DIR/nutrition-$stamp.sha256"
        fi
    fi
done
