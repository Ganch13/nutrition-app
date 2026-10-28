#!/bin/bash
# Главный процесс службы backup: ждёт назначенного времени и каждый день запускает backup.sh.
# Если свежей копии (младше 24 часов) нет, первую делает сразу при запуске службы: так сервер не остаётся
# без защиты до первой ночи, а ошибка в настройках обнаруживается сразу.

set -u

BACKUP_TIME="${BACKUP_TIME:-03:30}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"

run_backup() {
    # Ошибка одной копии не останавливает службу: завтра попробуем снова. Сбой виден в `docker compose logs backup`
    # и в статусе unhealthy, если свежей копии нет больше суток.
    bash /backup/backup.sh || echo "[$(date '+%F %T')] ОШИБКА резервного копирования, повтор в следующее время запуска." >&2
}

if [ -z "$(find "$BACKUP_DIR" -maxdepth 1 -name 'nutrition-db-*.dump' -mmin -1440 2>/dev/null | head -n 1)" ]; then
    echo "[$(date '+%F %T')] Свежей копии нет, делаю первую сейчас."
    run_backup
fi

echo "[$(date '+%F %T')] Служба резервного копирования запущена. Копия ежедневно в $BACKUP_TIME."
while true; do
    now="$(date +%s)"
    next="$(date -d "today $BACKUP_TIME" +%s)"
    if [ "$next" -le "$now" ]; then
        next="$(date -d "tomorrow $BACKUP_TIME" +%s)"
    fi
    sleep $((next - now))
    run_backup
done
