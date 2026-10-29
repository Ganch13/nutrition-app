# Управление локальным окружением проверки (local/docker-compose.yml).
#
# Запуск из корня проекта (обёртка .cmd обходит блокировку .ps1 политикой ExecutionPolicy):
#   .\local\lad-local.cmd up       — собрать образы из текущего кода и запустить (ждёт healthy)
#   .\local\lad-local.cmd seed     — заполнить базу демо-данными (demo@example.com)
#   .\local\lad-local.cmd reset    — стереть локальную базу и фото, запустить с чистого листа
#   .\local\lad-local.cmd reset -Seed — то же и сразу демо-данные
#   .\local\lad-local.cmd down     — остановить (данные сохраняются)
#   .\local\lad-local.cmd purge    — остановить и удалить всё: контейнеры, тома, образы *-local, local/.env
#   .\local\lad-local.cmd status   — состояние контейнеров
#   .\local\lad-local.cmd logs [backend|frontend|db] — журнал (Ctrl+C — выйти)
#
# Скрипт работает только с проектом lad-local и файлом local/.env: боевой сервер,
# deploy/.env и корневой .env не читаются и не меняются.

param(
    [Parameter(Position = 0)]
    [ValidateSet("up", "seed", "reset", "down", "purge", "status", "logs")]
    [string]$Command = "status",

    [Parameter(Position = 1)]
    [string]$Service = "",

    [switch]$Seed
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Here = $PSScriptRoot                                  # ...\nutrition-app\local
$ComposeFile = Join-Path $Here "docker-compose.yml"
$EnvFile = Join-Path $Here ".env"
$Images = @("lad-backend:1.4.0-local", "lad-frontend:1.4.0-local")


function New-HexSecret([int]$Bytes) {
    # Случайная строка из a-f и цифр. Пример: New-HexSecret 4 → "9f3a0c71"
    $buffer = New-Object byte[] $Bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($buffer)
    return -join ($buffer | ForEach-Object { $_.ToString("x2") })
}


function Ensure-EnvFile {
    # Создаёт local/.env с локальными случайными ключами, если файла ещё нет.
    # Содержимое на экран не выводится. Запись в UTF-8 без BOM — так его читает docker compose.
    if (Test-Path $EnvFile) { return }
    $lines = @(
        "# Создано lad-local.ps1 для локальной проверки. Не боевые значения.",
        "LOCAL_POSTGRES_PASSWORD=$(New-HexSecret 24)",
        "LOCAL_JWT_SECRET_KEY=$(New-HexSecret 32)"
    )
    [System.IO.File]::WriteAllText($EnvFile, ($lines -join "`n") + "`n", (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "Создан local/.env со случайными локальными ключами."
}


function Invoke-Compose {
    # Вызывает docker compose всегда с нашим файлом и нашими настройками.
    # Пример: Invoke-Compose ps  →  docker compose -f local\docker-compose.yml --env-file local\.env ps
    # Аргументы берутся из $args без блока param: иначе PowerShell принял бы "-d" за свой параметр.
    & docker compose -f $ComposeFile --env-file $EnvFile @args
    if ($LASTEXITCODE -ne 0) { throw "docker compose $($args -join ' ') завершился с ошибкой $LASTEXITCODE" }
}


function Start-Local {
    # Сборка из текущего кода и запуск; --wait ждёт, пока все контейнеры станут healthy.
    Ensure-EnvFile
    Write-Host "Собираю и запускаю lad-local (первая сборка занимает несколько минут)..."
    Invoke-Compose up -d --build --wait
    Write-Host ""
    Write-Host "Готово. Приложение:  http://localhost:3100"
    Write-Host "         API/Swagger: http://localhost:8100/docs"
    Write-Host "Демо-данные: .\local\lad-local.cmd seed  (вход demo@example.com / demo-password-123)"
}


function Invoke-Seed {
    # Демо-данные через API внутри контейнера backend (скрипт backend/dev_seed.py)
    Invoke-Compose exec backend python dev_seed.py
}


switch ($Command) {
    "up" {
        Start-Local
        if ($Seed) { Invoke-Seed }
    }
    "seed" {
        Ensure-EnvFile
        Invoke-Seed
    }
    "reset" {
        Ensure-EnvFile
        Write-Host "Удаляю локальную базу и фото (только проект lad-local)..."
        Invoke-Compose down --volumes --remove-orphans
        Start-Local
        if ($Seed) { Invoke-Seed }
    }
    "down" {
        Ensure-EnvFile
        Invoke-Compose down
        Write-Host "Остановлено. Данные сохранены; запуск снова: .\local\lad-local.cmd up"
    }
    "purge" {
        Ensure-EnvFile
        Invoke-Compose down --volumes --remove-orphans
        foreach ($image in $Images) {
            # Образа может не быть (ещё не собирали) — это не ошибка
            try { & docker image rm $image 2>&1 | Out-Null } catch { }
        }
        Remove-Item $EnvFile -Force
        Write-Host "Локальное окружение удалено полностью: контейнеры, тома, образы *-local и local/.env."
    }
    "status" {
        Ensure-EnvFile
        Invoke-Compose ps
    }
    "logs" {
        Ensure-EnvFile
        if ($Service) { Invoke-Compose logs -f --tail 100 $Service }
        else { Invoke-Compose logs -f --tail 100 }
    }
}
