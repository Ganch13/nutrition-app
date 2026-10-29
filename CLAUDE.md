# CLAUDE.md

Этот файл содержит инструкции для Claude Code (claude.ai/code) при работе с кодом в этом репозитории.

## Язык общения

Всегда отвечай пользователю на русском языке: объяснения, вопросы, итоги работы и сообщения об ошибках. Код, имена файлов, команды и идентификаторы остаются как есть, на английском.

## О проекте

«Лад» — семейный планировщик питания, тренировок, расписания и финансов. Бэкенд: FastAPI + SQLAlchemy 2 + PostgreSQL 16 + Alembic (Python 3.12) в `backend/`. Фронтенд: Next.js 16 + React 19 + TypeScript + Tailwind 4 в `frontend/`. Развёртывание (Docker Compose + Caddy) в `deploy/`. Документация, комментарии, docstring'и, тексты интерфейса и сообщения об ошибках API пишутся на русском — сохраняй это соглашение.

## Команды

Бэкенд (запускать из `backend/`; `pytest.ini` задаёт `pythonpath = .`, поэтому модули импортируются плоско, например `from models import User`):

```powershell
uvicorn main:app --reload            # http://127.0.0.1:8000, Swagger на /docs (только в dev)
alembic upgrade head                 # применить миграции
alembic revision --autogenerate -m "..."   # новая миграция после изменения models.py
pytest -v                            # все тесты
pytest tests/test_finance.py::test_name -v # один тест
```

Для тестов нужна настоящая база PostgreSQL, имя которой заканчивается на `_test` (по умолчанию `postgresql+psycopg2://nutrition:nutrition_pass@localhost:5432/nutrition_test`, переопределяется через `TEST_DATABASE_URL`); иначе conftest отказывается их запускать.

Фронтенд (запускать из `frontend/`; нужен `.env.local` с `NEXT_PUBLIC_API_URL`, см. `.env.local.example`):

```powershell
npm run dev
npx tsc --noEmit
npm run lint
npm run build
```

Весь стек в Docker: скопировать `.env.example` → `.env` (задать `POSTGRES_PASSWORD`, `JWT_SECRET_KEY`), затем `docker compose up -d --build`.

Локальная проверка перед выкладкой (обязательна для каждой доработки, ТЗ от 29.10.2026, п. 6): отдельный проект `lad-local` в `local/` — своя база, свои случайные ключи в `local/.env`, порты 3100/8100, контейнеры `lad-local-X.Y.Z-*`. Команды из корня: `.\local\lad-local.cmd up | up -Seed | seed | reset [-Seed] | down | purge | status | logs [сервис]` (`.cmd` обходит ExecutionPolicy). Демо-данные — `backend/dev_seed.py` через API (`demo@example.com` / `demo-password-123`), при `ENVIRONMENT=production` не запускается. В конце каждой доработки — пересборка `lad-local` и раздел «Что проверить» в `local/README.md`.

Открытые задачи и технический долг — `docs/OPEN_TASKS.md` (обновлять при закрытии сессии).

## Архитектура бэкенда

Модульный монолит, один слой на файл для каждого домена (schedule, food, norms, recipe, meal_plan, shopping, family_plan, photo, household, finance, auth):

- `<domain>_routes.py` — `APIRouter` с эндпоинтами; подключается в `main.py`. Старые базовые эндпоинты (users, goals, weight, meals, training sessions, workouts) по-прежнему лежат прямо в `main.py` и опираются на `services.py`.
- `<domain>_services.py` — бизнес-логика и проверки прав. Сервисы выбрасывают собственные классы исключений, а не `HTTPException`.
- Сопоставление ошибок: каждый routes-модуль определяет словарь `{ExceptionClass: (status_code, "русский текст")}` и функцию `register_error_handlers(app)`, которая вызывает `error_handling.register_error_map`. `main.py` обязан вызвать функцию регистрации каждого модуля — при добавлении нового routes-модуля подключай и `include_router`, и регистрацию обработчиков ошибок.
- `schemas.py` — все Pydantic v2 модели запросов и ответов; `models.py` — все модели SQLAlchemy (по одному файлу, а не по файлу на домен).
- Финансы разделены дальше: `finance_services.py` (книги учёта, категории, транзакции), `finance_recurring.py`, `finance_schedule.py`, `finance_planning.py` (бюджетные циклы «от дохода до дохода», нагрузка), `finance_goals.py`; эндпоинты в `finance_routes.py` и `finance_plan_routes.py`.
- Доходы никогда не начисляются автоматически: `auto_post` разрешён только для платежей (`sync_recurring` фильтрует `kind == "expense"`), а доход подтверждается через `confirm_occurrence` по запросу `GET /finance/income-prompts` (окно ±2 дня от плановой даты, `PROMPT_WINDOW_DAYS` в `finance_recurring.py`). У доходов нет `end_on`. Общие правила проверки правила — `schemas.check_rule_schedule`, она же вызывается в `update_rule` после слияния полей.
- «Всего» (баланс-кошелёк) считает только `finance_balance.ledger_balance`: операции с датой ≤ сегодня (подтверждённые доходы, траты, автосписания — автосписание считается фактом) плюс корректировки `FinanceBalanceAdjustment` («на самом деле столько-то», `POST /finance/ledgers/{id}/balance`). Корректировки не входят в отчёты, лимиты и бюджетные периоды. Ожидаемые доходы и неоплаченные платежи в «Всего» не входят. «Свободно» и «Можно тратить в день» считает только `finance_planning.spending_plan` (источник правды для `/finance/home` и `cycles.spending`): свободно = баланс − неоплаченные обязательные платежи от сегодня до дня перед следующим неподтверждённым основным доходом, в день = свободно ÷ дни до него. Ожидаемый доход не учитывается до подтверждения. `build_cycle.available` — только прогноз периода для лент и сравнения.
- Расход на цель: связь хранится только в `FinancialGoalEntry.transaction_id` (у операции своего `goal_id` нет). Создание, правка и удаление операций — `finance_transactions.py`; запись в цели ведут `finance_goals.link_expense`/`unlink_expense` (без commit, одной транзакцией с операцией). Запись «из расхода» нельзя удалить из истории цели (409). `finance_services` не может импортировать `finance_goals` — циклический импорт.
- Сводка расходов (`finance_summaries.py`, `FinanceExpenseSummary`): строки — обычные операции с `summary_id` и датой `period_end`, поэтому баланс, отчёты и цели считают их как расходы. При пересечении с уже записанными расходами тех же категорий (без операций правил и расходов на цели) сервер без `mode` отвечает 409; `mode="add"` ничего не удаляет, `mode="replace"` удаляет только `replace_ids`, показанные при сверке (`POST .../summaries/check`). Сам сервер ничего не складывает и не удаляет.
- Границы бюджетного периода задают только правила дохода с `is_primary=True`; дополнительные входят в суммы периода. `monthly_equivalent` возвращает `None` для `biweekly` (среднее не показываем); для оценки нагрузки есть `typical_month_amount` (две выплаты в месяц).
- Расписание: два события не могут пересекаться, кроме случая «контейнер (`is_container`) + не-контейнер целиком внутри него». Правило одно для создания, изменения и серий — `schedule_services.check_overlaps`; при нарушении `ScheduleOverlapError` → 409 с текстом. Любой новый код, создающий или меняющий `ScheduleEvent`, обязан вызывать `check_overlaps`. Вложенность не хранится: `parent_id` вычисляется в недельном виде.

Контроль доступа:
- `access.py`: `require_same_user` (зависимость для маршрутов `/users/{user_id}/...`) и `require_household_member(household_id, db, user, allowed_roles)`; роли в семье: `owner`, `admin`, `member`. Роутеры импортируют из `access.py`, никогда из `main.py` (`main` импортирует роутеры).
- `visibility.py`: общие правила видимости «builtin / personal / household» для записей с `owner_user_id` + `household_id` (продукты, рецепты). Встроенные данные берутся из `food_seed.py` / `recipe_seed.py`.

Аутентификация и безопасность: короткоживущий JWT access-токен (15 минут) в `Authorization: Bearer`, плюс ротируемый refresh-токен в HttpOnly-куке (`auth_routes.py`, `auth_services.py`, `security.py`; смена пароля отзывает все сессии). `config.py` читает все настройки из переменных окружения; при `ENVIRONMENT=production` функция `validate_settings()` прерывает запуск при слабом секрете, небезопасном CORS или отсутствии allowed hosts, а документация отключается. Порядок middleware в `main.py` важен (ограничение размера тела запроса добавляется внутри CORS, чтобы ответы 413 тоже несли CORS-заголовки). В `rate_limit.py` лежат ограничения на вход и регистрацию, хранящиеся в памяти.

Быстрое добавление с iPhone (`quick_routes.py`, `quick_services.py`): личные ключи `lad_...` (в базе только SHA-256 и `key_prefix`) управляются через `/access-keys` по JWT, а работают только на `/quick/...` (своя зависимость `get_key_context`, JWT там не принимается; ключ не JWT, поэтому остальные эндпоинты отвечают 401 сами). Расход создаётся общей `finance_transactions.add_transaction` (без commit) вместе с отметкой `QuickAddRequest` (Idempotency-Key, 10 минут). Смена пароля отзывает ключи (`auth_services.change_password`), удаление аккаунта удаляет каскадом. В тестах «сегодня» для `/quick` подменяется через `quick_routes.get_quick_today`.

Тесты (`backend/tests/`): схема строится через `Base.metadata.create_all` (миграции тестами не проверяются — всё равно пиши миграцию Alembic при каждом изменении моделей). Все таблицы очищаются после каждого теста; лимиты сбрасываются, а `UPLOAD_DIR` автоматически указывает на временную папку. Используй `tests/helpers.py::register_and_login(client, email)`, чтобы получить `{"id", "headers"}` авторизованного пользователя.

## Архитектура фронтенда

- `frontend/AGENTS.md`: в этой версии Next.js есть ломающие изменения по сравнению с данными, на которых обучена модель — перед написанием кода на Next.js прочитай нужное руководство в `frontend/node_modules/next/dist/docs/`.
- Страницы за логином лежат в `app/(app)/` (общий `layout.tsx` + `components/AppShell.tsx`); `login/` и `register/` публичные.
- `lib/api.ts` — единственный HTTP-клиент: хранит access-токен в `sessionStorage`, прозрачно вызывает `/auth/refresh` при 401 (с дедупликацией) и превращает ошибки в `ApiError` с русскими сообщениями. `lib/endpoints.ts` — единственное место, где пишутся URL эндпоинтов: новые вызовы API добавляй туда, а типы — в `lib/types.ts`.
- Общие элементы интерфейса лежат в `components/ui.tsx` (`Card`, `Button`, `TextField`, `Notice`, …), иконки — в `components/icons.tsx`; используй их повторно вместо новых разовых компонентов.
- Дизайн-токены (цвета `brand-*`, `saffron`, `good-*`, шрифты Inter/Lora, отдаваемые локально из `public/fonts` из-за CSP) находятся в `app/globals.css` в `@theme`. Название приложения, правила палитры и порядок перегенерации иконок и заставок описаны в `frontend/DESIGN.md` — следуй ему при работе над интерфейсом и при переименованиях.
- PWA: `app/manifest.ts`, `public/sw.js` (увеличь версию его кэша, чтобы сбросить кэш у клиентов), `public/offline.html`. При открытии страницы sw.js ждёт сервер 20 с; при ошибке сети, тайм-ауте или 502/503/504 отдаёт `offline.html` из кэша, а она сама выбирает текст «Нет подключения к интернету» / «Сервер недоступен, попробуйте позже» по `navigator.onLine`. Те же тексты в `lib/api.ts` (`NO_INTERNET_TEXT`, `SERVER_DOWN_TEXT`); запросы к API ограничены 20 с, заставка (`SplashScreen`) сдаётся через 30 с.
- Скрытые блоки главной хранятся в профиле (`users.home_hidden_blocks`, меняются через `PATCH /users/{id}`); работать с ними через `lib/home-blocks.ts::useHomeBlocks`, а плашку «Вернуть на главную» в разделе — `components/HomeBlockReturn.tsx`. Новый блок главной = значение в `HomeBlock` (schemas.py и types.ts) + место возврата в его разделе.
- Время событий расписания вводится и показывается по часовому поясу профиля (`zonedToIso`, `dateInZone`, `formatTimeInZone`), а не устройства. Старые хелперы `localInputValue`/`toIsoFromLocal` работают по поясу устройства — для расписания их не использовать.
- Правило линтера `react-hooks/set-state-in-effect` включено: не вызывать `setState` в теле `useEffect`. Загрузку делать через `useAsyncData`, сброс состояния — через `key`, начальное значение из URL — ленивым инициализатором `useState` (если первый показ всё равно «Загрузка»).
- Событие окна `lad:finance-changed` (`FINANCE_CHANGED_EVENT` в `components/finance/IncomePromptDialog.tsx`) сообщает, что поступление подтверждено; блоки, зависящие от денег, подписываются на него и перезагружаются.

## Релиз и деплой

Версия указана в `backend/main.py`, `frontend/package.json` и `package-lock.json`, тегах `image:` в трёх compose-файлах и в `local/docker-compose.yml` (теги `lad-*:X.Y.Z-local` и имена контейнеров `lad-local-X.Y.Z-*`), корневом `README.md` (строка «Версия» и команда `docker save`) и `CHANGELOG.md`. Поднимать тег образа нужно ДО сборки на сервере: `deploy.sh` собирает под тегом из `deploy/docker-compose.prod.yml`, и с прежним тегом старые образы для отката перезаписываются. Миграции, меняющие данные, не откатываются `alembic downgrade` полностью — откат релиза = код из снимка + восстановление базы из копии (`deploy/BACKUP.md`). Чек-лист перед релизом: `RELEASE.md`; деплой, обновление и резервное копирование на сервере: `deploy/README.md`, `deploy/UPDATE.md`, `deploy/BACKUP.md`.

Файлы `test_db.py` / `test_security.py` в корне — старые ручные скрипты, не входящие в набор тестов.

## Как работать с владельцем проекта (Даня)

Проект одновременно учебный: владелец (опыт в системном администрировании, Python/FastAPI изучает) хочет понимать код, а не просто получать его. Отвечать по-русски.

### Порядок работы
- Один небольшой законченный шаг за раз. Перед изменением изучить текущий код. Следующий шаг — только после проверки предыдущего.
- Не переписывать большие файлы целиком без необходимости: точечные правки.
- В каждом ответе о правке называть точный файл и место в нём («в schemas.py, после класса X»), а не «поправьте схему».
- Объяснять, что делаем, зачем и что должно получиться. Для нетривиальных изменений — путь данных: браузер → frontend → API → сервис → БД.
- В пояснениях к коду показывать примерные значения, которые лежат в переменных в этот момент.
- У каждой функции в новом коде — подробный комментарий на русском: что делает, зачем, пример данных.
- После значимых изменений давать способ проверки: тесты, готовые JSON-тела и URL для Swagger (`/docs`, только dev), ожидаемый результат. Задача не закончена, пока не проверена.
- Указывать «Шаг N», этап и что осталось до цели.
- Не делать коммиты, ветки и прочие действия с Git без прямой просьбы («без гита, сосредоточься на коде»).

### Формат объяснения команд терминала
Для каждой команды: (1) где запускать («на вашем компьютере в PowerShell» / «на сервере»); (2) сама команда; (3) что делает простыми словами; (4) зачем нужна для следующих шагов; (5) что должно быть до неё; (6) что будет после и какой вывод ожидать. Кратко, но без пропуска команд.

### Безопасность
- Не читать и не выводить содержимое `.env`, `deploy/.env`, `.env.local`, токены, пароли, JWT. Не просить пользователя присылать секреты.
- Имена эндпоинтов сверять с реальным кодом/Swagger, а не угадывать.
- Данные конкретных людей (расписание, цели, вес) не зашивать в код: всё настраивается через профиль и данные.
- Не добавлять Redis, очереди и микросервисы: модульный монолит. БД — источник истины, ИИ только поверх детерминированных расчётов.

### Окружение
- Windows 11, PyCharm, PowerShell; путь проекта `C:\Users\user\PycharmProjects\nutrition-app`.
- PostgreSQL для разработки — в контейнере Docker Desktop `nutrition-postgres` (тестовая БД `nutrition_test`). Если тесты падают с `Connection refused` на 5432 — контейнер остановлен: `docker start nutrition-postgres`. Проверять миграции на копии: `CREATE DATABASE nutrition_migcheck TEMPLATE nutrition;` в этом контейнере, `DATABASE_URL=...nutrition_migcheck`, затем `DROP DATABASE`.
- `tests/test_hardening.py` (4 варианта) и `tests/test_sessions.py` (3 теста) падают и без изменений: кодировка консоли и старая проблема окна refresh. Описание в `docs/OPEN_TASKS.md`; новые падения сравнивать с этими 7.
- Python-скрипты с кириллицей и путями Windows не передавать через Bash-heredoc: `\U` в `C:\Users` ломает строку («truncated \UXXXXXXXX escape»). Сохранять скрипт файлом в scratchpad и запускать `python -I файл`.
- Продакшен: арендованный сервер Ubuntu (1 ядро, 2 ГБ), Docker Compose + Caddy, домен через Cloudflare, доступ по SSH. Резервные копии — `deploy/BACKUP.md`.
- PowerShell блокирует `.venv\Scripts\Activate.ps1` (ExecutionPolicy). Без активации: `.venv\Scripts\python.exe -m pytest` / `-m alembic` / `-m uvicorn`; либо `Set-ExecutionPolicy -Scope Process Bypass` на время окна.
- Длинные heredoc с кириллицей в Bash-инструменте ломаются; патч-скрипты сохранять файлом в scratchpad и запускать оттуда.
- Устаревший `frontend/.next/dev/types` может ссылаться на удалённые маршруты и ломать `npm run build`; эта папка генерируется `next dev`, её можно удалить.
- Папка копий на сервере `/var/backups/nutrition` принадлежит uid 10001 (режим 750): читать через `sudo ls` или `docker compose ... exec backup ls /backups`.
- На сервере работает fail2ban: несколько неудачных SSH-подключений подряд блокируют IP (симптом `kex_exchange_identification: Connection closed`); снять — через консоль провайдера `sudo fail2ban-client set sshd unbanip IP`.
