#!/bin/bash
# Проверяет deploy/.env перед запуском на сервере: найдёт пустые значения, заглушки и слабые секреты.
# Ничего не меняет. Запуск:  ./deploy/check-env.sh        Код возврата 0 — всё в порядке, 1 — есть ошибки.

set -u

ENV_FILE="${ENV_FILE:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.env}"
errors=()
warnings=()

if [ ! -f "$ENV_FILE" ]; then
    echo "Не найден файл $ENV_FILE" >&2
    echo "Создайте его:  cp deploy/.env.example deploy/.env  и заполните." >&2
    exit 1
fi

# Значение переменной из файла. Файл не выполняется как программа (source) — только читается построчно.
# Пример: get DOMAIN → nutrition.example.org
get() {
    local line
    line="$(grep -E "^[[:space:]]*$1=" "$ENV_FILE" | tail -n 1 || true)"
    line="${line#*=}"
    line="${line%%#*}"                      # комментарий в конце строки
    line="$(echo "$line" | sed -E 's/^[[:space:]]+|[[:space:]]+$//g; s/^"(.*)"$/\1/; s/^'"'"'(.*)'"'"'$/\1/')"
    printf '%s' "$line"
}

# Права доступа: секреты не должны читаться другими пользователями сервера
mode="$(stat -c %a "$ENV_FILE" 2>/dev/null || echo "?")"
if [ "$mode" != "600" ] && [ "$mode" != "400" ]; then
    errors+=("права файла .env: $mode. Исправьте: chmod 600 $ENV_FILE")
fi

domain="$(get DOMAIN)"
domain_ok=0
if [ -z "$domain" ]; then
    errors+=("DOMAIN не задан")
elif [[ "$domain" == *example.com || "$domain" == *example.org || "$domain" == localhost* ]]; then
    errors+=("DOMAIN=$domain — это пример. Укажите свой домен")
elif [[ "$domain" == *"/"* || "$domain" == *":"* ]]; then
    errors+=("DOMAIN должен быть только именем сайта, без https:// и без пути: nutrition.mydomain.ru")
elif ! [[ "$domain" =~ ^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?)+$ ]]; then
    errors+=("DOMAIN=$domain не похож на доменное имя")
else
    domain_ok=1
fi

email="$(get ACME_EMAIL)"
if [ -z "$email" ] || [ "$email" = "you@example.com" ] || ! [[ "$email" =~ ^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$ ]]; then
    errors+=("ACME_EMAIL не задан или не похож на адрес почты")
fi

pg="$(get POSTGRES_PASSWORD)"
if [ -z "$pg" ] || [ "$pg" = "ЗАМЕНИТЕ" ]; then
    errors+=("POSTGRES_PASSWORD не задан. Создайте: openssl rand -hex 24")
elif [ "${#pg}" -lt 24 ]; then
    errors+=("POSTGRES_PASSWORD короче 24 символов")
elif ! [[ "$pg" =~ ^[A-Za-z0-9]+$ ]]; then
    errors+=("POSTGRES_PASSWORD должен состоять только из латинских букв и цифр (иначе ломается адрес подключения к базе). Создайте: openssl rand -hex 24")
fi

jwt="$(get JWT_SECRET_KEY)"
if [ -z "$jwt" ] || [ "$jwt" = "ЗАМЕНИТЕ" ]; then
    errors+=("JWT_SECRET_KEY не задан. Создайте: openssl rand -hex 32")
elif [ "${#jwt}" -lt 32 ]; then
    errors+=("JWT_SECRET_KEY короче 32 символов")
else
    lower="$(echo "$jwt" | tr '[:upper:]' '[:lower:]')"
    for marker in change example secret password test default your; do
        if [[ "$lower" == *"$marker"* ]]; then
            errors+=("JWT_SECRET_KEY похож на пример (содержит «$marker»). Создайте случайный: openssl rand -hex 32")
            break
        fi
    done
fi
if [ -n "$jwt" ] && [ "$jwt" != "ЗАМЕНИТЕ" ] && [ "$jwt" = "$pg" ]; then
    errors+=("JWT_SECRET_KEY и POSTGRES_PASSWORD совпадают: нужны два разных секрета")
fi

backup_time="$(get BACKUP_TIME)"
if [ -n "$backup_time" ] && ! [[ "$backup_time" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]]; then
    errors+=("BACKUP_TIME=$backup_time: нужен формат ЧЧ:ММ, например 03:30")
fi

backup_dir="$(get BACKUP_DIR)"
backup_dir="${backup_dir:-/var/backups/nutrition}"
if [ ! -d "$backup_dir" ]; then
    warnings+=("папки для копий $backup_dir ещё нет (её создаёт deploy.sh или:  sudo install -d -o 10001 -g 10001 -m 750 $backup_dir )")
elif [ "$(stat -c %u "$backup_dir")" != "10001" ]; then
    errors+=("папка копий $backup_dir принадлежит не пользователю 10001, служба backup не сможет в неё писать. Исправьте: sudo chown 10001:10001 $backup_dir && sudo chmod 750 $backup_dir")
fi

registration="$(get REGISTRATION_OPEN)"
if [ -z "$registration" ] || [ "$registration" = "true" ]; then
    warnings+=("регистрация открыта для всех. Когда заведёте аккаунты семьи, поставьте REGISTRATION_OPEN=false и перезапустите ./deploy/deploy.sh")
fi

# DNS: сертификат Let's Encrypt выдаётся, только если домен указывает на этот сервер
if [ "$domain_ok" -eq 1 ] && command -v getent > /dev/null 2>&1; then
    if ! getent hosts "$domain" > /dev/null 2>&1; then
        warnings+=("домен $domain пока не найден в DNS: Caddy не сможет получить сертификат, пока A-запись не указывает на этот сервер")
    fi
fi

for warning in "${warnings[@]+"${warnings[@]}"}"; do
    echo "Внимание: $warning"
done

if [ "${#errors[@]}" -gt 0 ]; then
    echo >&2
    echo "Найдены ошибки в $ENV_FILE:" >&2
    for error in "${errors[@]}"; do
        echo "  ✗ $error" >&2
    done
    exit 1
fi

echo "Настройки в порядке: домен $domain, секреты заданы, права файла $mode."
