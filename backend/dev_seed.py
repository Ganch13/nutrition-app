"""Тестовые данные для локальной проверки (local/docker-compose.yml).

Скрипт работает как обычный пользователь: регистрирует демо-аккаунты и заполняет их
через настоящий API (те же проверки, что и в браузере). Ничего не пишет в базу напрямую.

Запуск внутри локального контейнера (это делает .\\local\\lad-local.cmd seed):
    python dev_seed.py                      # API по умолчанию http://127.0.0.1:8000
    python dev_seed.py --api http://localhost:8100

Защита:
- при ENVIRONMENT=production скрипт сразу завершается: на боевом сервере демо-данным не место;
- если демо-пользователь уже есть (вход удался), второй раз ничего не создаётся.

Что получится (даты считаются от сегодняшнего дня):
    demo@example.com / demo-password-123   — «Демо», владелец семьи «Демо-семья»
    demo2@example.com / demo-password-123  — «Демо-2», участник семьи
    Личная книга «Демо»: зарплата (подтверждена), аренда (без автосписания),
    подписка (с автосписанием), десяток расходов, цели «Отпуск» и «Долг Ивану».
    Семейная книга: зарплата «Демо-2», продукты, общая цель «Ремонт кухни».
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

PASSWORD = "demo-password-123"
TIMEZONE = "Europe/Moscow"


class Api:
    """Мини-клиент HTTP на стандартной библиотеке (в образе нет лишних пакетов).

    Пример: Api("http://127.0.0.1:8000").post("/auth/login", {...}) → (200, {"access_token": "eyJ..."})
    """

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")  # "http://127.0.0.1:8000"
        self.token: str | None = None          # access-токен после входа

    def request(self, method: str, path: str, body: dict | None = None) -> tuple[int, object]:
        """Отправляет запрос и возвращает (код ответа, JSON или None).

        Пример: request("POST", "/households", {"name": "Демо-семья"}) → (201, {"id": 1, ...})
        Ошибки HTTP (4xx/5xx) не выбрасываются, а возвращаются кодом: решает вызывающий.
        """
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                raw = response.read()
                return response.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as error:
            raw = error.read()
            try:
                return error.code, json.loads(raw)
            except ValueError:
                return error.code, raw.decode("utf-8", "replace")

    def post(self, path: str, body: dict | None = None, expect: int = 201):
        """POST с проверкой кода. При неожиданном коде печатает ответ сервера и останавливает скрипт."""
        status, payload = self.request("POST", path, body)
        if status != expect:
            sys.exit(f"Ошибка {status} на POST {path}: {payload}")
        return payload

    def get(self, path: str):
        """GET с проверкой кода 200. Пример: get("/finance/ledgers") → [{"id": 1, "kind": "personal", ...}]"""
        status, payload = self.request("GET", path)
        if status != 200:
            sys.exit(f"Ошибка {status} на GET {path}: {payload}")
        return payload


def login(api: Api, email: str) -> bool:
    """Входит под демо-пользователем. True — вход удался (токен сохранён в api.token)."""
    status, payload = api.request("POST", "/auth/login", {"email": email, "password": PASSWORD})
    if status == 200:
        api.token = payload["access_token"]
        return True
    return False


def register(api: Api, email: str, name: str) -> None:
    """Регистрирует пользователя и сразу входит. Пример: register(api, "demo@example.com", "Демо")."""
    api.token = None
    api.post("/auth/register", {
        "name": name, "email": email, "password": PASSWORD,
        "height_cm": 175, "timezone": TIMEZONE,
    })
    if not login(api, email):
        sys.exit(f"Не удалось войти под {email} сразу после регистрации")


def last_monthly_due(today: date, day: int) -> date:
    """Последняя дата «каждое day-е число» не позже сегодня.

    Пример: today=2026-10-29, day=5 → 2026-10-05; today=2026-10-03, day=5 → 2026-09-05.
    day берём до 28, чтобы дата была в любом месяце.
    """
    this_month = today.replace(day=day)
    if this_month <= today:
        return this_month
    previous = today.replace(day=1) - timedelta(days=1)  # последний день прошлого месяца
    return previous.replace(day=day)


def months_back(value: date, months: int) -> date:
    """Та же дата на months месяцев раньше (день ≤ 28). Пример: (2026-10-05, 2) → 2026-08-05."""
    month_index = value.year * 12 + (value.month - 1) - months
    return value.replace(year=month_index // 12, month=month_index % 12 + 1)


def categories(api: Api, ledger_id: int) -> dict[str, int]:
    """Категории книги: {"Продукты": 3, "Зарплата": 10, ...} (создаются вместе с книгой)."""
    return {item["name"]: item["id"] for item in api.get(f"/finance/ledgers/{ledger_id}/categories")}


def spend(api: Api, ledger_id: int, category_id: int, amount: int, day: date, description: str) -> None:
    """Обычный расход. Пример: spend(api, 1, 3, 1850, 2026-10-27, "Пятёрочка")."""
    api.post(f"/finance/ledgers/{ledger_id}/transactions", {
        "category_id": category_id, "amount": amount,
        "occurred_on": day.isoformat(), "description": description,
    })


def seed(api: Api) -> None:
    """Создаёт весь набор демо-данных (см. описание модуля)."""
    today = date.today()

    # --- Пользователи и семья ---
    register(api, "demo2@example.com", "Демо-2")
    demo2_token = api.token
    register(api, "demo@example.com", "Демо")
    demo_token = api.token

    household = api.post("/households", {"name": "Демо-семья"})
    invite = api.post(f"/households/{household['id']}/invites")
    api.token = demo2_token
    api.post("/households/join", {"code": invite["code"]}, expect=200)

    # --- Книги: личные у обоих и одна семейная ---
    api.post("/finance/ledgers", {"kind": "personal", "currency": "RUB"})
    api.token = demo_token
    personal = api.post("/finance/ledgers", {"kind": "personal", "currency": "RUB"})
    family = api.post("/finance/ledgers", {
        "kind": "household", "household_id": household["id"], "currency": "RUB",
    })

    # --- Личная книга «Демо» ---
    pid = personal["id"]
    cats = categories(api, pid)
    salary_due = last_monthly_due(today, 5)  # например 2026-10-05
    salary = api.post(f"/finance/ledgers/{pid}/recurring", {
        "kind": "income", "name": "Зарплата", "amount": 90000, "frequency": "monthly",
        "start_on": months_back(salary_due, 2).isoformat(), "day_of_month": 5,
    })
    # Подтверждаем только последнюю выплату: две прошлые остаются неподтверждёнными
    # и в «Всего» не попадают (проверка пункта 1 ТЗ)
    api.post(f"/finance/ledgers/{pid}/recurring/{salary['id']}/occurrences/{salary_due.isoformat()}/confirm")

    api.post(f"/finance/ledgers/{pid}/recurring", {
        "kind": "expense", "name": "Аренда", "amount": 35000, "frequency": "monthly",
        "start_on": (today + timedelta(days=3)).isoformat(),
    })
    api.post(f"/finance/ledgers/{pid}/recurring", {
        "kind": "expense", "name": "Подписка на музыку", "amount": 299, "frequency": "monthly",
        "start_on": last_monthly_due(today, 1).isoformat(), "day_of_month": 1, "auto_post": True,
    })

    purchases = [
        ("Продукты", 1850, 1, "Пятёрочка"),
        ("Продукты", 3200, 3, "Закупка на неделю"),
        ("Транспорт", 450, 2, "Такси"),
        ("Транспорт", 1500, 9, "Проездной"),
        ("Развлечения", 1200, 4, "Кино"),
        ("Здоровье", 870, 6, "Аптека"),
        ("Одежда", 4300, 12, "Кроссовки"),
        ("Продукты", 2600, 10, "Рынок"),
        ("Спорт", 2500, 15, "Абонемент в бассейн"),
        ("Другое", 600, 0, "Подарок коллеге"),
    ]
    for name, amount, days_ago, description in purchases:
        spend(api, pid, cats[name], amount, today - timedelta(days=days_ago), description)

    api.post(f"/finance/ledgers/{pid}/goals", {
        "kind": "savings", "name": "Отпуск", "target_amount": 200000, "start_amount": 15000,
    })
    api.post(f"/finance/ledgers/{pid}/goals", {
        "kind": "debt", "name": "Долг Ивану", "target_amount": 30000, "start_amount": 5000,
    })

    # --- Семейная книга ---
    fid = family["id"]
    fcats = categories(api, fid)
    api.token = demo2_token
    family_salary = api.post(f"/finance/ledgers/{fid}/recurring", {
        "kind": "income", "name": "Зарплата Демо-2", "amount": 70000, "frequency": "monthly",
        "start_on": months_back(last_monthly_due(today, 10), 1).isoformat(), "day_of_month": 10,
    })
    api.post(
        f"/finance/ledgers/{fid}/recurring/{family_salary['id']}"
        f"/occurrences/{last_monthly_due(today, 10).isoformat()}/confirm"
    )
    spend(api, fid, fcats["Продукты"], 5400, today - timedelta(days=2), "Гипермаркет")
    spend(api, fid, fcats["Жильё и коммунальные"], 6800, today - timedelta(days=8), "Коммуналка")
    api.token = demo_token
    api.post(f"/finance/ledgers/{fid}/goals", {
        "kind": "savings", "name": "Ремонт кухни", "target_amount": 300000, "start_amount": 40000,
    })


def main() -> None:
    """Точка входа: проверки безопасности, затем заполнение."""
    parser = argparse.ArgumentParser(description="Демо-данные для локальной проверки «Лада»")
    parser.add_argument("--api", default="http://127.0.0.1:8000", help="адрес API")
    args = parser.parse_args()

    if os.getenv("ENVIRONMENT", "development").strip().lower() == "production":
        sys.exit("ENVIRONMENT=production: демо-данные на боевом сервере не создаются")

    api = Api(args.api)
    if login(api, "demo@example.com"):
        print("Демо-данные уже есть, ничего не создаю. Для чистого старта: .\\local\\lad-local.cmd reset")
        return

    seed(api)
    print("Готово. Вход: demo@example.com / demo2@example.com, пароль " + PASSWORD)


if __name__ == "__main__":
    main()
