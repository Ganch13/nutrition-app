#!/bin/bash
# Сборка и запуск (или обновление) приложения на сервере. Запускать из любой папки:  ./deploy/deploy.sh
# Безопасно повторять: при обновлении сначала делается резервная копия, потом пересборка и перезапуск.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
COMPOSE=(docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env)

if [ ! -f deploy/.env ]; then
    echo "Нет файла deploy/.env. Создайте его:  cp deploy/.env.example deploy/.env  и заполните (см. deploy/README.md)." >&2
    exit 1
fi

# 1. Папка для резервных копий (владелец 10001 — пользователь службы backup)
backup_dir="$(grep -E '^BACKUP_DIR=' deploy/.env | tail -n 1 | cut -d= -f2- | sed -E 's/[[:space:]]+#.*$//; s/^"(.*)"$/\1/')"
backup_dir="${backup_dir:-/var/backups/nutrition}"
if [ ! -d "$backup_dir" ]; then
    echo "Создаю папку для резервных копий $backup_dir"
    if [ "$(id -u)" -eq 0 ]; then
        install -d -o 10001 -g 10001 -m 750 "$backup_dir"
    else
        sudo install -d -o 10001 -g 10001 -m 750 "$backup_dir"
    fi
fi

# 2. Проверка настроек
bash ./deploy/check-env.sh

# 3. При обновлении работающего приложения — копия «на всякий случай»
if "${COMPOSE[@]}" ps --status running --services 2>/dev/null | grep -qx backup; then
    echo "Приложение уже запущено. Делаю резервную копию перед обновлением..."
    "${COMPOSE[@]}" exec -T backup bash /backup/backup.sh
fi

# 4. Сборка образов (--pull подтягивает свежие исправления безопасности базовых образов) и запуск.
# --wait ждёт, пока все службы станут здоровыми; не дождался за 5 минут — ошибка.
# Образы собираются по одному: на сервере с 2 ГБ памяти две сборки сразу (Python и Next.js) могут не поместиться.
for service in backend frontend; do
    "${COMPOSE[@]}" build --pull "$service"
done
"${COMPOSE[@]}" up -d --remove-orphans --wait --wait-timeout 300

echo
"${COMPOSE[@]}" ps
domain="$(grep -E '^DOMAIN=' deploy/.env | tail -n 1 | cut -d= -f2- | sed -E 's/[[:space:]]+#.*$//')"
echo
echo "Готово. Сайт: https://$domain"
echo "Первый запуск: сертификат выпускается около минуты, до этого браузер может показать ошибку соединения."
echo "Журнал:  docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env logs -f --tail 100"
