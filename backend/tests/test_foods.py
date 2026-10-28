"""Тесты шага 65: справочник продуктов, свои и семейные продукты, добавление еды из справочника."""

from decimal import Decimal

from food_seed import BUILTIN_FOODS
from tests.helpers import new_household, register_and_login


def search(client, user, **params) -> dict:
    """GET /foods с параметрами поиска; возвращает {"items": [...], "total": N}."""
    response = client.get("/foods", params=params, headers=user["headers"])
    assert response.status_code == 200, response.text
    return response.json()


def names(result: dict) -> list[str]:
    return [item["name"] for item in result["items"]]


def create_food(client, user, **overrides):
    """Создаёт свой продукт (по умолчанию «Мой творог»); возвращает ответ целиком."""
    body = {
        "name": "Мой творог",
        "category": "dairy",
        "calories_per_100g": 121,
        "protein_per_100g": 17,
        "fat_per_100g": 5,
        "carbs_per_100g": 1.8,
        "serving_name": "1 пачка",
        "serving_grams": 200,
    }
    body.update(overrides)
    return client.post("/foods", json=body, headers=user["headers"])


# ---------------------------------------------------------------- данные справочника


def test_builtin_seed_values_are_plausible():
    # Защита от опечаток при правке food_seed.py: энергия должна сходиться с БЖУ
    # по формуле Этуотера (4·Б + 9·Ж + 4·У) с допуском на клетчатку и округления.
    assert len(BUILTIN_FOODS) >= 90
    assert len({food[0] for food in BUILTIN_FOODS}) == len(BUILTIN_FOODS), "названия повторяются"
    for name, category, kcal, protein, fat, carbs, serving_name, serving_grams in BUILTIN_FOODS:
        assert protein + fat + carbs <= 100.5, name
        estimate = 4 * protein + 9 * fat + 4 * carbs
        assert abs(estimate - kcal) <= max(25, 0.2 * kcal), f"{name}: {kcal} ккал против {estimate:.0f} по БЖУ"
        assert (serving_name is None) == (serving_grams is None), name


# ---------------------------------------------------------------- чтение и поиск


def test_foods_require_token(client):
    assert client.get("/foods").status_code == 401


def test_first_request_loads_builtin_foods_once(client):
    user = register_and_login(client, "a@example.com")

    first = search(client, user, limit=200)
    second = search(client, user, limit=200)

    assert first["total"] == len(BUILTIN_FOODS)
    assert second["total"] == len(BUILTIN_FOODS)
    assert all(item["source"] == "builtin" and item["can_edit"] is False for item in first["items"])


def test_search_ignores_case_and_yo(client):
    user = register_and_login(client, "a@example.com")

    # В справочнике «Свёкла», ищем без «ё» и в другом регистре
    assert "Свёкла" in names(search(client, user, q="СВЕКЛА"))


def test_search_requires_all_words_and_ranks_prefix_first(client):
    user = register_and_login(client, "a@example.com")

    result = search(client, user, q="творог 5")
    assert names(result) == ["Творог 5%"]

    # «Яйцо» — начало названия, поэтому «Яйцо куриное…» выше, чем «Яичный белок» (его вообще не находит)
    result = search(client, user, q="яйцо")
    assert names(result)[0].startswith("Яйцо")


def test_search_treats_percent_literally(client):
    user = register_and_login(client, "a@example.com")

    # «%» — не подстановочный знак: находятся только названия с символом процента
    result = search(client, user, q="%")
    assert result["total"] > 0
    assert all("%" in name for name in names(result))
    assert search(client, user, q="_")["total"] == 0


def test_category_filter_and_pagination(client):
    user = register_and_login(client, "a@example.com")

    fish = search(client, user, category="fish")
    assert fish["total"] == len([food for food in BUILTIN_FOODS if food[1] == "fish"])
    assert all(item["category"] == "fish" for item in fish["items"])

    page = search(client, user, limit=5, offset=0)
    next_page = search(client, user, limit=5, offset=5)
    assert len(page["items"]) == 5
    assert page["total"] == len(BUILTIN_FOODS)
    assert set(names(page)).isdisjoint(names(next_page))

    assert client.get("/foods", params={"limit": 500}, headers=user["headers"]).status_code == 422


# ---------------------------------------------------------------- свои продукты


def test_user_creates_edits_and_deletes_own_food(client):
    user = register_and_login(client, "a@example.com")

    created = create_food(client, user)
    assert created.status_code == 201, created.text
    food = created.json()
    assert food["source"] == "personal"
    assert food["can_edit"] is True
    assert Decimal(food["calories_per_100g"]) == Decimal("121")

    edited = client.patch(
        f"/foods/{food['id']}", json={"calories_per_100g": 125, "serving_grams": 180}, headers=user["headers"]
    )
    assert edited.status_code == 200, edited.text
    assert Decimal(edited.json()["calories_per_100g"]) == Decimal("125")
    assert Decimal(edited.json()["serving_grams"]) == Decimal("180")

    assert client.delete(f"/foods/{food['id']}", headers=user["headers"]).status_code == 204
    assert "Мой творог" not in names(search(client, user, q="мой"))


def test_personal_food_is_private(client):
    owner = register_and_login(client, "owner@example.com")
    other = register_and_login(client, "other@example.com")
    food = create_food(client, owner).json()

    assert "Мой творог" in names(search(client, owner, q="мой"))
    assert "Мой творог" not in names(search(client, other, q="мой"))
    # Чужой продукт для остальных выглядит как несуществующий
    assert client.patch(f"/foods/{food['id']}", json={"name": "Взлом"}, headers=other["headers"]).status_code == 404
    assert client.delete(f"/foods/{food['id']}", headers=other["headers"]).status_code == 404
    assert client.get(f"/foods/{food['id']}/nutrition", params={"amount_g": 100}, headers=other["headers"]).status_code == 404


def test_duplicate_name_is_rejected_case_insensitively(client):
    user = register_and_login(client, "a@example.com")
    assert create_food(client, user, name="Мой творог").status_code == 201

    assert create_food(client, user, name="  МОЙ ТВОРОГ ").status_code == 409

    other = register_and_login(client, "b@example.com")
    # У другого пользователя такое же название допустимо
    assert create_food(client, other, name="Мой творог").status_code == 201


def test_food_validation(client):
    user = register_and_login(client, "a@example.com")

    # Сумма БЖУ больше 100 г
    assert create_food(client, user, protein_per_100g=60, fat_per_100g=30, carbs_per_100g=20).status_code == 422
    # Порция без массы
    assert create_food(client, user, serving_name="1 шт.", serving_grams=None).status_code == 422
    # Отрицательные и слишком большие значения
    assert create_food(client, user, calories_per_100g=-1).status_code == 422
    assert create_food(client, user, calories_per_100g=1000).status_code == 422
    assert create_food(client, user, category="space-food").status_code == 422
    assert create_food(client, user, name="").status_code == 422


def test_patch_validates_combined_values(client):
    user = register_and_login(client, "a@example.com")
    food = create_food(client, user, protein_per_100g=17, fat_per_100g=5, carbs_per_100g=1.8).json()

    # Белки 90 г вместе с жирами 5 г и углеводами 1,8 г дают больше 100 г
    response = client.patch(f"/foods/{food['id']}", json={"protein_per_100g": 95}, headers=user["headers"])
    assert response.status_code == 422

    # Очистить обязательное поле нельзя
    response = client.patch(f"/foods/{food['id']}", json={"name": None}, headers=user["headers"])
    assert response.status_code == 422


def test_builtin_food_is_read_only(client):
    user = register_and_login(client, "a@example.com")
    builtin = search(client, user, q="гречка")["items"][0]

    assert client.patch(f"/foods/{builtin['id']}", json={"name": "Х"}, headers=user["headers"]).status_code == 403
    assert client.delete(f"/foods/{builtin['id']}", headers=user["headers"]).status_code == 403


# ---------------------------------------------------------------- семейные продукты


def test_household_food_is_shared_with_members_only(client):
    danya = register_and_login(client, "danya@example.com")
    lesya = register_and_login(client, "lesya@example.com")
    stranger = register_and_login(client, "stranger@example.com")
    household_id = new_household(client, danya, lesya)

    created = create_food(client, lesya, name="Наш йогурт", household_id=household_id)
    assert created.status_code == 201, created.text
    assert created.json()["source"] == "household"

    assert "Наш йогурт" in names(search(client, danya, q="наш"))
    assert "Наш йогурт" in names(search(client, lesya, q="наш"))
    assert "Наш йогурт" not in names(search(client, stranger, q="наш"))


def test_cannot_create_food_for_foreign_household(client):
    danya = register_and_login(client, "danya@example.com")
    stranger = register_and_login(client, "stranger@example.com")
    household_id = new_household(client, danya)

    response = create_food(client, stranger, household_id=household_id)

    assert response.status_code == 403


def test_household_food_edit_rights(client):
    danya = register_and_login(client, "danya@example.com")  # владелец
    lesya = register_and_login(client, "lesya@example.com")  # участник
    mama = register_and_login(client, "mama@example.com")  # участник
    household_id = new_household(client, danya, lesya, mama)
    food = create_food(client, lesya, name="Наш йогурт", household_id=household_id).json()

    # Обычный участник чужой семейный продукт видит, но менять не может
    visible = next(item for item in search(client, mama, q="наш")["items"] if item["id"] == food["id"])
    assert visible["can_edit"] is False
    assert client.patch(f"/foods/{food['id']}", json={"calories_per_100g": 60}, headers=mama["headers"]).status_code == 403
    assert client.delete(f"/foods/{food['id']}", headers=mama["headers"]).status_code == 403

    # Автор и владелец семьи могут
    assert client.patch(f"/foods/{food['id']}", json={"calories_per_100g": 60}, headers=lesya["headers"]).status_code == 200
    assert client.delete(f"/foods/{food['id']}", headers=danya["headers"]).status_code == 204


# ---------------------------------------------------------------- расчёт и дневник


def test_nutrition_for_grams_and_servings(client):
    user = register_and_login(client, "a@example.com")
    egg = search(client, user, q="яйцо куриное сырое")["items"][0]  # 143 ккал на 100 г, порция 55 г

    by_grams = client.get(f"/foods/{egg['id']}/nutrition", params={"amount_g": 110}, headers=user["headers"])
    assert by_grams.status_code == 200, by_grams.text
    assert Decimal(by_grams.json()["calories"]) == Decimal("157.30")  # 143 × 1,1
    assert Decimal(by_grams.json()["protein_g"]) == Decimal("13.86")

    by_servings = client.get(f"/foods/{egg['id']}/nutrition", params={"servings": 2}, headers=user["headers"])
    assert Decimal(by_servings.json()["amount_g"]) == Decimal("110.00")
    assert by_servings.json()["calories"] == by_grams.json()["calories"]


def test_nutrition_parameter_errors(client):
    user = register_and_login(client, "a@example.com")
    egg = search(client, user, q="яйцо куриное сырое")["items"][0]
    flour = search(client, user, q="майонез")["items"][0]
    no_serving = create_food(client, user, name="Без порции", serving_name=None, serving_grams=None).json()
    url = "/foods/{}/nutrition"

    # Нужен ровно один из параметров
    assert client.get(url.format(egg["id"]), headers=user["headers"]).status_code == 422
    assert client.get(url.format(egg["id"]), params={"amount_g": 100, "servings": 1}, headers=user["headers"]).status_code == 422
    # Нулевая и огромная масса
    assert client.get(url.format(egg["id"]), params={"amount_g": 0}, headers=user["headers"]).status_code == 422
    assert client.get(url.format(egg["id"]), params={"amount_g": 20000}, headers=user["headers"]).status_code == 422
    # Порции у продукта без порции
    assert client.get(url.format(no_serving["id"]), params={"servings": 1}, headers=user["headers"]).status_code == 422
    assert flour["name"] == "Майонез"


def meal_from_food(client, user, **overrides):
    body = {
        "food_id": None,
        "amount_g": 150,
        "eaten_at": "2026-10-27T12:00:00+03:00",
        "meal_type": "lunch",
    }
    body.update(overrides)
    return client.post(f"/users/{user['id']}/meal-entries/from-food", json=body, headers=user["headers"])


def test_meal_from_food_stores_snapshot_and_feeds_daily_summary(client):
    user = register_and_login(client, "a@example.com", timezone="Europe/Moscow")
    food = create_food(client, user).json()  # 121 ккал, Б 17, Ж 5, У 1,8 на 100 г

    response = meal_from_food(client, user, food_id=food["id"], amount_g=150)

    assert response.status_code == 201, response.text
    entry = response.json()
    assert Decimal(entry["calories"]) == Decimal("181.50")
    assert Decimal(entry["protein_g"]) == Decimal("25.50")
    assert entry["food_id"] == food["id"]
    assert Decimal(entry["amount_g"]) == Decimal("150.00")
    assert entry["description"] == "Мой творог — 150 г"

    summary = client.get(
        f"/users/{user['id']}/nutrition/daily-summary", params={"target_date": "2026-10-27"}, headers=user["headers"]
    ).json()
    assert Decimal(summary["calories"]) == Decimal("181.50")


def test_history_keeps_snapshot_when_food_changes_or_is_deleted(client):
    user = register_and_login(client, "a@example.com", timezone="Europe/Moscow")
    food = create_food(client, user).json()
    meal_from_food(client, user, food_id=food["id"], amount_g=100)

    # Меняем калорийность продукта — старая запись не должна измениться
    client.patch(f"/foods/{food['id']}", json={"calories_per_100g": 300}, headers=user["headers"])
    entries = client.get(
        f"/users/{user['id']}/nutrition/daily-entries", params={"target_date": "2026-10-27"}, headers=user["headers"]
    ).json()
    assert Decimal(entries[0]["calories"]) == Decimal("121.00")

    # Удаляем продукт — запись остаётся, связь пропадает
    assert client.delete(f"/foods/{food['id']}", headers=user["headers"]).status_code == 204
    entries = client.get(
        f"/users/{user['id']}/nutrition/daily-entries", params={"target_date": "2026-10-27"}, headers=user["headers"]
    ).json()
    assert len(entries) == 1
    assert entries[0]["food_id"] is None
    assert Decimal(entries[0]["calories"]) == Decimal("121.00")


def test_meal_from_food_with_servings_and_errors(client):
    user = register_and_login(client, "a@example.com", timezone="Europe/Moscow")
    other = register_and_login(client, "b@example.com")
    egg = search(client, user, q="яйцо куриное сырое")["items"][0]
    private = create_food(client, other, name="Чужой продукт").json()

    ok = meal_from_food(client, user, food_id=egg["id"], amount_g=None, servings=3)
    assert ok.status_code == 201, ok.text
    assert Decimal(ok.json()["amount_g"]) == Decimal("165.00")

    # Нужен ровно один из параметров
    assert meal_from_food(client, user, food_id=egg["id"], amount_g=None).status_code == 422
    assert meal_from_food(client, user, food_id=egg["id"], servings=1).status_code == 422
    # Чужой личный продукт недоступен
    assert meal_from_food(client, user, food_id=private["id"]).status_code == 404
    # Время без часового пояса
    assert meal_from_food(client, user, food_id=egg["id"], eaten_at="2026-10-27T12:00:00").status_code == 422
    # Чужой user_id в адресе
    response = client.post(
        f"/users/{other['id']}/meal-entries/from-food",
        json={"food_id": egg["id"], "amount_g": 100, "eaten_at": "2026-10-27T12:00:00+03:00", "meal_type": "lunch"},
        headers=user["headers"],
    )
    assert response.status_code == 403
