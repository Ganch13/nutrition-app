#!/bin/bash
# Проверка на сервере: есть ли свежая резервная копия. Нужна для оповещений, чтобы сбой копирования не остался незамеченным.
#   ./deploy/backup/check-backup.sh            → печатает состояние; код возврата 0 — всё хорошо, 1 — копия устарела или её нет
#
# Оповещение на почту или в мониторинг (раз в час, crontab -e под root или пользователем с доступом к папке копий):
#   17 * * * * /home/deploy/nutrition/deploy/backup/check-backup.sh || echo "Копия Nutrition устарела" | mail -s "Nutrition: backup" you@example.com
# Либо сервис healthchecks.io: создайте проверку, скопируйте её адрес и укажите в PING_URL — адрес будет вызываться
# только когда копия свежая; если вызовов нет, сервис сам пришлёт письмо или сообщение в Telegram.
#   PING_URL=https://hc-ping.com/ваш-код ./deploy/backup/check-backup.sh
#
# Параметры: BACKUP_DIR (по умолчанию из deploy/.env или /var/backups/nutrition), MAX_AGE_HOURS (по умолчанию 26).

set -u
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

backup_dir="${BACKUP_DIR:-}"
if [ -z "$backup_dir" ] && [ -f deploy/.env ]; then
    backup_dir="$(grep -E '^BACKUP_DIR=' deploy/.env | tail -n 1 | cut -d= -f2- | sed -E 's/[[:space:]]+#.*$//; s/^"(.*)"$/\1/')"
fi
backup_dir="${backup_dir:-/var/backups/nutrition}"
max_age_hours="${MAX_AGE_HOURS:-26}"

latest="$(ls -1t "$backup_dir"/nutrition-db-*.dump 2>/dev/null | head -n 1 || true)"
if [ -z "$latest" ]; then
    echo "ПЛОХО: в $backup_dir нет ни одной копии базы (или нет доступа к папке: запустите через sudo)." >&2
    exit 1
fi

age_hours=$(( ( $(date +%s) - $(stat -c %Y "$latest") ) / 3600 ))
size="$(du -h "$latest" | cut -f1)"
if [ "$age_hours" -gt "$max_age_hours" ]; then
    echo "ПЛОХО: последняя копия $(basename "$latest") сделана $age_hours ч. назад (допустимо $max_age_hours ч.)." >&2
    exit 1
fi

echo "Хорошо: последняя копия $(basename "$latest"), $size, $age_hours ч. назад."
if [ -n "${PING_URL:-}" ]; then
    curl -fsS --max-time 10 --retry 2 -o /dev/null "$PING_URL" || echo "Внимание: не удалось вызвать PING_URL." >&2
fi
exit 0
