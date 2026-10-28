"""Тесты шага 68: список закупок и план готовки."""

import math
from collections import defaultdict
from datetime import date
from decimal import Decimal

from tests.helpers import register_and_login
from tests.test_meal_plan import (
    MONDAY,
    create_recipe,
    food_id,
    generate,
    plan_url,
    ready_user,
    week,
)


def shopping(client, user, start=MONDAY, days=7) -> dict:
    response = client.get(
        f"/users/{user['id']}/shopping-list", params={"start": start, "days": days}, headers=user["headers"]
    )
    assert response.status_code == 200, response.text
    return response.json()


def cooking(client, user, start=MONDAY, days=7) -> dict:
    response = client.get(
        f"/users/{user['id']}/cooking-plan", params={"start": start, "days": days}, headers=user["headers"]
    )
    assert response.status_code == 200, response.text
    return response.json()


def add_meal(client, user, planned_at, recipe_id=None, items=None, meal_type="lunch", **extra):
    body = {"planned_at": planned_at, "meal_type": meal_type, **extra}
    if recipe_id is not None:
        body["recipe_id"] = recipe_id
    if items is not None:
        body["items"] = items
    response = client.post(f"{plan_url(user)}/meals", json=body, headers=user["headers"])
    assert response.status_code == 201, response.text
    return response.json()


def all_meals(client, user) -> list[dict]:
    return [meal for day in week(client, user)["days"] for meal in day["meals"]]


# ---------------------------------------------------------------- закупки


def test_shopping_list_requires_own_account(client):
    owner = ready_user(client, "a@example.com")
    stranger = register_and_login(client, "b@example.com")

    for path in ("shopping-list", "cooking-plan"):
        url = f"/users/{owner['id']}/{path}"
        assert client.get(url, params={"start": MONDAY}, headers=stranger["headers"]).status_code == 403
        assert client.get(url, params={"start": MONDAY}).status_code == 401


def test_empty_plan_gives_empty_list(client):
    user = ready_user(client)

    result = shopping(client, user)

    assert result["items"] == [] and result["meals_count"] == 0 and result["checked_count"] == 0
    assert cooking(client, user)["sessions"] == []


def test_shopping_list_sums_products_of_the_whole_plan(client):
    user = ready_user(client)
    generate(client, user)

    result = shopping(client, user)

    # Считаем сумму по продуктам независимо — прямо из ответа плана питания
    expected = defaultdict(Decimal)
    for meal in all_meals(client, user):
        for item in meal["items"]:
            expected[item["name"]] += Decimal(item["amount_g"])
    actual = {item["name"]: Decimal(item["amount_g"]) for item in result["items"]}
    assert set(actual) == set(expected)
    for name, grams in expected.items():
        assert actual[name] == Decimal(math.ceil(grams)), name
    assert result["meals_count"] == 28
    assert result["start"] == MONDAY and result["end"] == "2026-11-01"
    # Каждая строка знает, в каких блюдах нужна, и категория проставлена
    assert all(item["used_in"] and item["category"] for item in result["items"])
    assert len({item["key"] for item in result["items"]}) == len(result["items"])


def test_shopping_list_is_ordered_by_category_then_name(client):
    user = ready_user(client)
    generate(client, user)

    categories = [item["category"] for item in shopping(client, user)["items"]]

    order = ["vegetables", "fruits", "meat", "fish", "eggs", "dairy", "bakery", "grains", "legumes",
             "nuts", "fats", "sauces", "sweets", "drinks", "supplements", "other"]
    indexes = [order.index(category) for category in categories]
    assert indexes == sorted(indexes)


def test_eaten_and_skipped_meals_are_not_bought(client):
    user = ready_user(client)
    banana = food_id(client, user, "Банан")
    eaten = add_meal(client, user, "2026-10-26T08:00:00+03:00", items=[{"food_id": banana, "amount_g": 100}], meal_type="breakfast")
    skipped = add_meal(client, user, "2026-10-26T12:00:00+03:00", items=[{"food_id": banana, "amount_g": 200}])
    add_meal(client, user, "2026-10-27T12:00:00+03:00", items=[{"food_id": banana, "amount_g": 300}])
    client.post(f"{plan_url(user)}/meals/{eaten['id']}/eat", headers=user["headers"])
    client.post(f"{plan_url(user)}/meals/{skipped['id']}/skip", headers=user["headers"])

    result = shopping(client, user)

    assert [(item["name"], item["amount_g"]) for item in result["items"]] == [("Банан", "300")]
    assert result["meals_count"] == 1


def test_period_limits_shopping_list(client):
    user = ready_user(client)
    banana = food_id(client, user, "Банан")
    for day, grams in (("26", 100), ("27", 200), ("28", 400)):
        add_meal(client, user, f"2026-10-{day}T12:00:00+03:00", items=[{"food_id": banana, "amount_g": grams}])

    assert shopping(client, user, days=1)["items"][0]["amount_g"] == "100"
    assert shopping(client, user, start="2026-10-27", days=2)["items"][0]["amount_g"] == "600"
    assert shopping(client, user, start="2026-11-10")["items"] == []
    for bad in (0, 15):
        response = client.get(
            f"/users/{user['id']}/shopping-list", params={"start": MONDAY, "days": bad}, headers=user["headers"]
        )
        assert response.status_code == 422


def test_amount_is_rounded_up_and_servings_are_counted(client):
    user = ready_user(client)
    banana = food_id(client, user, "Банан")  # порция «1 шт. (без кожуры)» = 120 г
    add_meal(client, user, "2026-10-26T12:00:00+03:00", items=[{"food_id": banana, "amount_g": 100.4}])
    add_meal(client, user, "2026-10-27T12:00:00+03:00", items=[{"food_id": banana, "amount_g": 139.6}])

    item = shopping(client, user)["items"][0]

    # 100,4 + 139,6 = 240 г ровно → 240 г и 2 порции по 120 г
    assert item["amount_g"] == "240" and Decimal(item["servings"]) == Decimal("2.0")
    assert item["serving_name"] == "1 шт. (без кожуры)" and Decimal(item["serving_grams"]) == 120
    add_meal(client, user, "2026-10-28T12:00:00+03:00", items=[{"food_id": banana, "amount_g": 0.3}])
    assert shopping(client, user)["items"][0]["amount_g"] == "241"  # 240,3 округляется вверх


def test_same_product_from_different_dishes_is_merged_with_names(client):
    user = ready_user(client)
    banana = food_id(client, user, "Банан")
    add_meal(client, user, "2026-10-26T12:00:00+03:00", items=[{"food_id": banana, "amount_g": 100}], title="Перекус А")
    add_meal(client, user, "2026-10-27T12:00:00+03:00", items=[{"food_id": banana, "amount_g": 100}], title="Перекус Б")
    add_meal(client, user, "2026-10-28T12:00:00+03:00", items=[{"food_id": banana, "amount_g": 100}], title="Перекус А")

    items = shopping(client, user)["items"]

    assert len(items) == 1 and items[0]["amount_g"] == "300"
    assert items[0]["used_in"] == ["Перекус А", "Перекус Б"]


def test_deleted_food_stays_in_list_by_name(client):
    user = ready_user(client)
    own = client.post(
        "/foods",
        json={"name": "Мой хлеб", "category": "bakery", "calories_per_100g": 250,
              "protein_per_100g": 8, "fat_per_100g": 2, "carbs_per_100g": 48},
        headers=user["headers"],
    ).json()["id"]
    add_meal(client, user, "2026-10-26T12:00:00+03:00", items=[{"food_id": own, "amount_g": 100}])
    assert client.delete(f"/foods/{own}", headers=user["headers"]).status_code == 204

    items = shopping(client, user)["items"]

    assert len(items) == 1
    assert items[0]["name"] == "Мой хлеб" and items[0]["food_id"] is None and items[0]["key"] == "name:мой хлеб"
    assert items[0]["category"] == "other" and items[0]["servings"] is None


def test_checks_are_saved_and_reset(client):
    user = ready_user(client)
    banana = food_id(client, user, "Банан")
    add_meal(client, user, "2026-10-26T12:00:00+03:00", items=[{"food_id": banana, "amount_g": 100}])
    key = shopping(client, user)["items"][0]["key"]
    url = f"/users/{user['id']}/shopping-list/checks"

    assert client.put(url, json={"start": MONDAY, "key": key, "checked": True}, headers=user["headers"]).status_code == 204
    # Повтор того же запроса безопасен
    assert client.put(url, json={"start": MONDAY, "key": key, "checked": True}, headers=user["headers"]).status_code == 204
    result = shopping(client, user)
    assert result["items"][0]["checked"] is True and result["checked_count"] == 1
    # Отметка относится к периоду: в списке, начинающемся на день позже, её нет
    assert shopping(client, user, start="2026-10-25")["items"][0]["checked"] is False

    assert client.put(url, json={"start": MONDAY, "key": key, "checked": False}, headers=user["headers"]).status_code == 204
    assert shopping(client, user)["checked_count"] == 0
    # Снятие несуществующей отметки не ошибка
    assert client.put(url, json={"start": MONDAY, "key": key, "checked": False}, headers=user["headers"]).status_code == 204

    client.put(url, json={"start": MONDAY, "key": key, "checked": True}, headers=user["headers"])
    assert client.delete(url, params={"start": MONDAY}, headers=user["headers"]).status_code == 204
    assert shopping(client, user)["checked_count"] == 0


def test_checks_are_private(client):
    owner = ready_user(client, "a@example.com")
    other = ready_user(client, "b@example.com")
    banana = food_id(client, owner, "Банан")
    for user in (owner, other):
        add_meal(client, user, "2026-10-26T12:00:00+03:00", items=[{"food_id": banana, "amount_g": 100}])
    key = shopping(client, owner)["items"][0]["key"]

    client.put(f"/users/{owner['id']}/shopping-list/checks",
               json={"start": MONDAY, "key": key, "checked": True}, headers=owner["headers"])

    assert shopping(client, owner)["items"][0]["checked"] is True
    assert shopping(client, other)["items"][0]["checked"] is False
    forbidden = client.put(f"/users/{owner['id']}/shopping-list/checks",
                           json={"start": MONDAY, "key": key, "checked": False}, headers=other["headers"])
    assert forbidden.status_code == 403
    assert client.delete(f"/users/{owner['id']}/shopping-list/checks", params={"start": MONDAY},
                         headers=other["headers"]).status_code == 403


def test_check_validation(client):
    user = ready_user(client)
    url = f"/users/{user['id']}/shopping-list/checks"

    assert client.put(url, json={"start": MONDAY, "key": "", "checked": True}, headers=user["headers"]).status_code == 422
    assert client.put(url, json={"start": MONDAY, "checked": True}, headers=user["headers"]).status_code == 422
    assert client.put(url, json={"start": "не дата", "key": "food:1", "checked": True}, headers=user["headers"]).status_code == 422


# ---------------------------------------------------------------- готовка


def recipe_with(client, user, name, keeps_days, prep_minutes=20, meal_types=("lunch",)):
    response = create_recipe(
        client, user, name=name, keeps_days=keeps_days, prep_minutes=prep_minutes, meal_types=list(meal_types)
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_dish_is_cooked_once_while_it_keeps(client):
    user = ready_user(client)
    stew = recipe_with(client, user, "Рагу", keeps_days=2, prep_minutes=30)
    for day in ("26", "27", "28"):
        add_meal(client, user, f"2026-10-{day}T13:00:00+03:00", recipe_id=stew)

    sessions = cooking(client, user)["sessions"]

    # Рагу хранится 2 дня: понедельник+вторник — один подход, среда — второй
    assert [(s["cook_date"], len(s["meals"])) for s in sessions] == [("2026-10-26", 2), ("2026-10-28", 1)]
    assert [Decimal(s["portions"]) for s in sessions] == [Decimal("2"), Decimal("1")]
    # 30 минут + 5 минут за вторую порцию; для одной порции — 30
    assert [s["estimated_minutes"] for s in sessions] == [35, 30]
    assert all(s["cook_when"] == "same_day" for s in sessions)


def test_morning_dish_is_cooked_evening_before_only_if_it_keeps(client):
    user = ready_user(client)
    keeps = recipe_with(client, user, "Овсянка с запасом", keeps_days=2, meal_types=("breakfast",))
    fresh = recipe_with(client, user, "Омлет", keeps_days=1, meal_types=("breakfast",))
    add_meal(client, user, "2026-10-27T08:00:00+03:00", recipe_id=keeps, meal_type="breakfast")
    add_meal(client, user, "2026-10-28T08:00:00+03:00", recipe_id=fresh, meal_type="breakfast")

    sessions = {s["recipe_name"]: s for s in cooking(client, user)["sessions"]}

    assert (sessions["Овсянка с запасом"]["cook_date"], sessions["Овсянка с запасом"]["cook_when"]) == ("2026-10-26", "evening_before")
    assert (sessions["Омлет"]["cook_date"], sessions["Омлет"]["cook_when"]) == ("2026-10-28", "same_day")


def test_portion_scale_adds_up_and_ingredients_are_summed(client):
    user = ready_user(client)
    recipe = recipe_with(client, user, "Творожное", keeps_days=3)  # творог 200 г + банан 100 г на порцию
    add_meal(client, user, "2026-10-26T13:00:00+03:00", recipe_id=recipe, portion_scale=1.5)
    add_meal(client, user, "2026-10-27T13:00:00+03:00", recipe_id=recipe, portion_scale=1)

    session = cooking(client, user)["sessions"][0]

    assert Decimal(session["portions"]) == Decimal("2.5")
    # 2 порции → ceil(2.5) = 3 порции: 30 − ... время = 20 + 5 × (3 − 1) = 30
    assert session["estimated_minutes"] == 30
    assert {i["name"]: i["amount_g"] for i in session["ingredients"]} == {"Творог 5%": "500", "Банан": "250"}


def test_meals_without_recipe_are_not_cooked(client):
    user = ready_user(client)
    banana = food_id(client, user, "Банан")
    add_meal(client, user, "2026-10-26T13:00:00+03:00", items=[{"food_id": banana, "amount_g": 100}])
    recipe = recipe_with(client, user, "Временный", keeps_days=1)
    add_meal(client, user, "2026-10-27T13:00:00+03:00", recipe_id=recipe)
    assert client.delete(f"/recipes/{recipe}", headers=user["headers"]).status_code == 204

    assert cooking(client, user)["sessions"] == []


def test_every_planned_meal_belongs_to_exactly_one_session(client):
    user = ready_user(client)
    generate(client, user, batch_days=3)

    plan = cooking(client, user)

    meal_ids = [meal["id"] for session in plan["sessions"] for meal in session["meals"]]
    assert sorted(meal_ids) == sorted(meal["id"] for meal in all_meals(client, user))
    assert len(plan["sessions"]) < 28  # блюда на несколько дней объединены
    assert plan["total_minutes"] == sum(s["estimated_minutes"] for s in plan["sessions"])
    # Время идёт по возрастанию дат приготовления
    dates = [s["cook_date"] for s in plan["sessions"]]
    assert dates == sorted(dates)
    # Блюдо не готовится заранее больше, чем оно хранится
    for session in plan["sessions"]:
        for meal in session["meals"]:
            days_after = (date.fromisoformat(meal["plan_date"]) - date.fromisoformat(session["cook_date"])).days
            assert 0 <= days_after < session["keeps_days"]


def test_cooking_batches_reduce_sessions(client):
    user = ready_user(client)

    generate(client, user, batch_days=1)
    separate = len(cooking(client, user)["sessions"])
    generate(client, user, batch_days=3, overwrite=True)
    batched = len(cooking(client, user)["sessions"])

    assert batched < separate
