"""Тесты шага 67: рецепты и недельный план питания."""

from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from food_seed import BUILTIN_FOODS
from meal_plan_services import (
    MEAL_SLOTS,
    DayContext,
    RecipeOption,
    calibrate_scales,
    clamp_scale,
    meal_location,
    meal_role,
    pick_recipe,
    plan_meal_times,
)
from recipe_seed import BUILTIN_RECIPES
from tests.helpers import new_household, register_and_login
from tests.test_norms import add_weight, setup_profile

MONDAY = "2026-10-26"
MSK = ZoneInfo("Europe/Moscow")


def at(text: str) -> datetime:
    """Строка времени из ответа → момент времени (сравниваем моменты, а не строки)."""
    return datetime.fromisoformat(text)


def local_minutes(text: str) -> int:
    """Московское время из ответа сервера в минутах от полуночи: "...T13:30:00+00:00" → 810 + 0 (если 13:30 МСК)."""
    moment = at(text).astimezone(MSK)
    return moment.hour * 60 + moment.minute


def ready_user(client, email="a@example.com"):
    """Мужчина 30 лет, 180 см, 80 кг, часовой пояс Москвы — норма на день считается."""
    user = register_and_login(client, email, timezone="Europe/Moscow")
    setup_profile(client, user)
    add_weight(client, user, "2026-10-20", 80)
    return user


def food_id(client, user, name) -> int:
    response = client.get("/foods", params={"q": name}, headers=user["headers"])
    assert response.status_code == 200, response.text
    return next(item["id"] for item in response.json()["items"] if item["name"] == name)


def recipes(client, user, **params) -> dict:
    response = client.get("/recipes", params={"limit": 200, **params}, headers=user["headers"])
    assert response.status_code == 200, response.text
    return response.json()


def create_recipe(client, user, **overrides):
    """Создаёт рецепт «Мой завтрак»: творог 200 г и банан 100 г."""
    body = {
        "name": "Мой завтрак",
        "meal_types": ["breakfast"],
        "ingredients": [
            {"food_id": food_id(client, user, "Творог 5%"), "amount_g": 200},
            {"food_id": food_id(client, user, "Банан"), "amount_g": 100},
        ],
    }
    body.update(overrides)
    return client.post("/recipes", json=body, headers=user["headers"])


def plan_url(user) -> str:
    return f"/users/{user['id']}/meal-plan"


def generate(client, user, **overrides):
    body = {"start": MONDAY, "days": 7, **overrides}
    return client.post(f"{plan_url(user)}/generate", json=body, headers=user["headers"])


def week(client, user, start=MONDAY) -> dict:
    response = client.get(plan_url(user), params={"start": start}, headers=user["headers"])
    assert response.status_code == 200, response.text
    return response.json()


def add_work_series(client, user):
    """Работа пн–пт 09:00–18:00 (по часовому поясу пользователя)."""
    response = client.post(
        f"/users/{user['id']}/schedule-events/series",
        json={
            "event_type": "work",
            "title": "Работа",
            "weekdays": [0, 1, 2, 3, 4],
            "start_time": "09:00",
            "end_time": "18:00",
            "from_date": MONDAY,
            "weeks": 1,
        },
        headers=user["headers"],
    )
    assert response.status_code == 201, response.text


# ---------------------------------------------------------------- встроенные данные


def test_builtin_recipes_use_existing_foods_and_sane_calories():
    foods = {food[0]: food for food in BUILTIN_FOODS}
    names = [recipe[0] for recipe in BUILTIN_RECIPES]
    assert len(names) == len(set(names)), "названия рецептов повторяются"
    assert len(names) >= 30

    for name, meal_types, portable, prep, keeps, instructions, ingredients in BUILTIN_RECIPES:
        assert {item for item in meal_types.split(",")} <= {"breakfast", "lunch", "dinner", "snack"}, name
        assert 0 <= prep <= 600 and 1 <= keeps <= 7, name
        food_names = [food_name for food_name, _ in ingredients]
        assert len(food_names) == len(set(food_names)), f"{name}: продукт указан дважды"
        kcal = 0.0
        for food_name, grams in ingredients:
            assert food_name in foods, f"{name}: нет продукта «{food_name}»"
            assert grams > 0
            kcal += foods[food_name][2] * grams / 100
        assert 150 <= kcal <= 900, f"{name}: {kcal:.0f} ккал на порцию"

    # Для каждого типа приёма пищи есть и обычные, и «с собой» блюда
    for meal_type in ("breakfast", "lunch", "dinner", "snack"):
        suitable = [r for r in BUILTIN_RECIPES if meal_type in r[1].split(",")]
        assert any(r[2] for r in suitable), meal_type
        assert len(suitable) >= 4, meal_type


def test_slot_shares_sum_to_one():
    for count, slots in MEAL_SLOTS.items():
        assert len(slots) == count
        assert abs(sum(share for _, share in slots) - 1) < 1e-9
        assert slots[0][0] == "breakfast" and "dinner" in [slot_type for slot_type, _ in slots]


# ---------------------------------------------------------------- чистые функции планирования


def test_meal_times_for_ordinary_day():
    ctx = DayContext(wake=7 * 60, bed=23 * 60, work=[], training=[])

    # Завтрак через 45 минут после подъёма, ужин за 2,5 часа до сна, обед между ними
    assert plan_meal_times(["breakfast", "lunch", "dinner"], ctx) == [465, 810, 1230]
    # Перекус стоит между обедом и ужином
    assert plan_meal_times(["breakfast", "lunch", "snack", "dinner"], ctx) == [465, 810, 1020, 1230]


def test_meal_times_follow_wake_and_bed_time():
    # Подъём в 10:00, сон в 1:00 ночи: ужин не позже 22:30
    ctx = DayContext(wake=600, bed=1500, work=[], training=[])

    times = plan_meal_times(["breakfast", "lunch", "dinner"], ctx)

    assert times[0] == 645
    assert times[2] == 1350


def test_meal_inside_training_window_is_moved():
    # Тренировка 13:00–14:30 попадает на обед (13:30): обед уходит на 15:00 (через 30 минут после неё)
    ctx = DayContext(wake=420, bed=1380, work=[], training=[(780, 870)])

    times = plan_meal_times(["breakfast", "lunch", "dinner"], ctx)

    assert times == [465, 900, 1230]
    # Ни один приём пищи не попадает в «окно» за час до тренировки и во время неё
    assert all(not (720 < minute < 870) for minute in times)


def test_meals_keep_order_and_hour_gap_after_shift():
    # Тренировка вечером вытесняет ужин; интервал между приёмами всё равно не меньше часа
    ctx = DayContext(wake=420, bed=1380, work=[], training=[(1140, 1260)])

    times = plan_meal_times(["breakfast", "lunch", "snack", "dinner"], ctx)

    assert times == sorted(times)
    assert all(b - a >= 60 for a, b in zip(times, times[1:]))
    assert not any(1080 < minute < 1260 for minute in times)


def test_role_and_location_helpers():
    ctx = DayContext(wake=420, bed=1380, work=[(540, 1080)], training=[(1140, 1230)])

    assert meal_role(1000, ctx) == "pre"  # за 140 минут до тренировки
    assert meal_role(1260, ctx) == "post"  # через 30 минут после
    assert meal_role(600, ctx) is None
    assert meal_location(810, ctx) == "work"
    assert meal_location(1080, ctx) == "home"  # конец работы — уже не на работе
    assert meal_location(480, ctx) == "home"


def test_scale_is_rounded_and_limited():
    assert clamp_scale(1.337) == Decimal("1.35")
    assert clamp_scale(3.2) == Decimal("2.0")
    assert clamp_scale(0.1) == Decimal("0.5")


def test_calibration_moves_total_to_target():
    class Option:  # достаточно поля calories
        def __init__(self, calories):
            self.calories = Decimal(calories)

    picks = [(Option(500), Decimal("1")), (Option(600), Decimal("1")), (Option(400), Decimal("1"))]  # 1500 ккал

    scales = calibrate_scales(picks, 1800)

    total = sum(float(option.calories) * float(scale) for (option, _), scale in zip(picks, scales))
    assert abs(total - 1800) <= 0.03 * 1800
    assert all(Decimal("0.5") <= scale <= Decimal("2.0") for scale in scales)


def option(recipe_id, calories, *, portable=True, keeps_days=3, protein=30, fat=10, meal_types=("lunch",)):
    """Упрощённый вариант рецепта для проверки выбора без базы данных."""
    return RecipeOption(
        recipe=SimpleNamespace(id=recipe_id, portable=portable, keeps_days=keeps_days),
        rows=[],
        meal_types=set(meal_types),
        calories=Decimal(calories),
        protein_g=Decimal(protein),
        fat_g=Decimal(fat),
        carbs_g=Decimal(50),
    )


def choose(options, **overrides):
    arguments = dict(slot_type="lunch", location="home", role=None, slot_kcal=600, usage=Counter(),
                     day_used=set(), previous=None, batch_days=1, jitter=0)
    arguments.update(overrides)
    return pick_recipe(options, **arguments)


def test_pick_recipe_uses_only_portable_dishes_at_work():
    exact_but_not_portable = option(1, 600, portable=False)
    portable_but_bigger = option(2, 900)

    assert choose([exact_but_not_portable, portable_but_bigger], location="home").recipe.id == 1
    assert choose([exact_but_not_portable, portable_but_bigger], location="work").recipe.id == 2
    # Если «с собой» нет вообще, лучше любое блюдо, чем пустой слот
    assert choose([exact_but_not_portable], location="work").recipe.id == 1


def test_pick_recipe_respects_meal_type_and_day_repeats():
    lunch_only = option(1, 600)
    snack_only = option(2, 600, meal_types=("snack",))

    assert choose([lunch_only, snack_only], slot_type="snack").recipe.id == 2
    assert choose([lunch_only, snack_only], slot_type="dinner") is None
    # Уже использованный сегодня рецепт не берётся, пока есть другой
    assert choose([option(1, 600), option(2, 800)], day_used={1}).recipe.id == 2
    # ...но если другого нет, повтор лучше пустого слота
    assert choose([option(1, 600)], day_used={1}).recipe.id == 1


def test_pick_recipe_prefers_rarely_used_dishes():
    popular, fresh = option(1, 600), option(2, 600)

    assert choose([popular, fresh], usage=Counter({1: 3})).recipe.id == 2


def test_pick_recipe_batch_reuse_needs_shelf_life():
    # Блюдо на 1200 ккал плохо подходит под слот в 600 ккал, поэтому по очкам оно проигрывает
    big_dish = option(1, 1200, keeps_days=2)
    exact = option(2, 600)

    assert choose([big_dish, exact]).recipe.id == 2
    # Вчера ели это блюдо (1-й день серии), оно хранится 2 дня, серия до 2 дней → готовим «про запас»
    assert choose([big_dish, exact], previous=(big_dish, 1), batch_days=2).recipe.id == 1
    # Серия уже длится 2 дня — хватит
    assert choose([big_dish, exact], previous=(big_dish, 2), batch_days=2).recipe.id == 2
    # Блюдо хранится только 1 день — на второй день его брать нельзя
    short_shelf = option(3, 1200, keeps_days=1)
    assert choose([short_shelf, exact], previous=(short_shelf, 1), batch_days=3).recipe.id == 2
    # Перекусы и завтраки «про запас» не готовят
    big_snack = option(4, 900, meal_types=("snack",))
    small_snack = option(5, 200, meal_types=("snack",))
    chosen = choose([big_snack, small_snack], slot_type="snack", slot_kcal=200, previous=(big_snack, 1), batch_days=3)
    assert chosen.recipe.id == 5


def test_pick_recipe_pre_and_post_workout_profile():
    fatty = option(1, 600, protein=15, fat=40)  # 60 % калорий из жиров, белка мало
    lean = option(2, 600, protein=40, fat=8)

    assert choose([fatty, lean], role="pre").recipe.id == 2
    assert choose([fatty, lean], role="post").recipe.id == 2


# ---------------------------------------------------------------- рецепты


def test_recipes_require_token(client):
    assert client.get("/recipes").status_code == 401


def test_builtin_recipes_are_loaded_once_and_read_only(client):
    user = register_and_login(client, "a@example.com")

    first = recipes(client, user)
    second = recipes(client, user)

    assert first["total"] == len(BUILTIN_RECIPES) == second["total"]
    assert all(item["source"] == "builtin" and item["can_edit"] is False for item in first["items"])

    recipe_id = first["items"][0]["id"]
    forbidden = client.patch(f"/recipes/{recipe_id}", json={"portable": True}, headers=user["headers"])
    assert forbidden.status_code == 403
    assert client.delete(f"/recipes/{recipe_id}", headers=user["headers"]).status_code == 403


def test_recipe_nutrition_is_sum_of_ingredients(client):
    user = register_and_login(client, "a@example.com")

    chicken = next(r for r in recipes(client, user, q="курица греч")["items"])

    # 150 г грудки (113) + 70 г гречки (313) + 150 г брокколи (34) + 8 г масла (884)
    expected = 113 * 1.5 + 313 * 0.7 + 34 * 1.5 + 884 * 0.08
    assert chicken["name"] == "Курица с гречкой и брокколи"
    assert abs(float(chicken["calories"]) - expected) < 0.5
    assert sum(float(i["calories"]) for i in chicken["ingredients"]) == float(chicken["calories"])
    assert len(chicken["ingredients"]) == 4


def test_recipe_filters(client):
    user = register_and_login(client, "a@example.com")

    snacks = recipes(client, user, meal_type="snack")
    assert snacks["total"] >= 4
    assert all("snack" in item["meal_types"] for item in snacks["items"])

    portable = recipes(client, user, portable="true")
    assert portable["total"] > 0 and all(item["portable"] for item in portable["items"])
    not_portable = recipes(client, user, portable="false")
    assert portable["total"] + not_portable["total"] == len(BUILTIN_RECIPES)

    assert recipes(client, user, q="ГРЕЧК курица")["total"] >= 1  # регистр и порядок слов не важны
    assert recipes(client, user, q="несуществующее блюдо")["total"] == 0


def test_create_personal_recipe(client):
    user = register_and_login(client, "a@example.com")

    response = create_recipe(client, user, portable=True, prep_minutes=5, instructions="Смешать.")

    assert response.status_code == 201, response.text
    body = response.json()
    # Творог 5% 200 г = 242 ккал, банан 100 г = 89 ккал
    assert float(body["calories"]) == 242 + 89
    assert body["source"] == "personal" and body["can_edit"] is True
    assert body["meal_types"] == ["breakfast"] and body["portable"] is True
    assert [i["name"] for i in body["ingredients"]] == ["Творог 5%", "Банан"]

    # Дубль названия в той же области запрещён, без учёта регистра
    assert create_recipe(client, user, name="мой ЗАВТРАК").status_code == 409


def test_recipe_validation(client):
    user = register_and_login(client, "a@example.com")
    banana = food_id(client, user, "Банан")

    twice = create_recipe(client, user, ingredients=[{"food_id": banana, "amount_g": 100}, {"food_id": banana, "amount_g": 50}])
    assert twice.status_code == 422

    assert create_recipe(client, user, ingredients=[]).status_code == 422
    assert create_recipe(client, user, meal_types=[]).status_code == 422
    assert create_recipe(client, user, meal_types=["brunch"]).status_code == 422
    assert create_recipe(client, user, ingredients=[{"food_id": banana, "amount_g": 0}]).status_code == 422
    assert create_recipe(client, user, ingredients=[{"food_id": 999999, "amount_g": 100}]).status_code == 422
    assert create_recipe(client, user, name="   ").status_code == 422


def test_personal_recipe_is_private(client):
    owner = register_and_login(client, "a@example.com")
    stranger = register_and_login(client, "b@example.com")
    recipe_id = create_recipe(client, owner).json()["id"]

    assert client.get(f"/recipes/{recipe_id}", headers=stranger["headers"]).status_code == 404
    assert "Мой завтрак" not in [item["name"] for item in recipes(client, stranger)["items"]]
    assert client.delete(f"/recipes/{recipe_id}", headers=stranger["headers"]).status_code == 404
    # Чужой личный продукт нельзя использовать в своём рецепте
    own_food = client.post(
        "/foods",
        json={"name": "Секретный продукт", "category": "other", "calories_per_100g": 100,
              "protein_per_100g": 1, "fat_per_100g": 1, "carbs_per_100g": 1},
        headers=owner["headers"],
    ).json()["id"]
    attempt = create_recipe(client, stranger, ingredients=[{"food_id": own_food, "amount_g": 50}])
    assert attempt.status_code == 422


def test_update_recipe_replaces_ingredients(client):
    user = register_and_login(client, "a@example.com")
    recipe = create_recipe(client, user).json()
    banana = food_id(client, user, "Банан")

    response = client.patch(
        f"/recipes/{recipe['id']}",
        json={"name": "Банановый завтрак", "meal_types": ["breakfast", "snack"],
              "ingredients": [{"food_id": banana, "amount_g": 200}]},
        headers=user["headers"],
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Банановый завтрак"
    assert body["meal_types"] == ["breakfast", "snack"]
    assert [(i["name"], float(i["amount_g"])) for i in body["ingredients"]] == [("Банан", 200.0)]
    assert float(body["calories"]) == 178

    # Нельзя очистить обязательные поля
    assert client.patch(f"/recipes/{recipe['id']}", json={"name": None}, headers=user["headers"]).status_code == 422
    # Можно оставить тот же продукт при замене списка (уникальность не мешает)
    same = client.patch(
        f"/recipes/{recipe['id']}", json={"ingredients": [{"food_id": banana, "amount_g": 250}]}, headers=user["headers"]
    )
    assert same.status_code == 200, same.text


def test_household_recipe_visibility_and_permissions(client):
    owner = register_and_login(client, "a@example.com")
    member = register_and_login(client, "b@example.com")
    outsider = register_and_login(client, "c@example.com")
    household_id = new_household(client, owner, member)

    created = create_recipe(client, member, household_id=household_id, name="Семейный омлет")
    assert created.status_code == 201, created.text
    recipe_id = created.json()["id"]
    assert created.json()["source"] == "household"

    # Видят оба участника, посторонний — нет
    assert client.get(f"/recipes/{recipe_id}", headers=owner["headers"]).status_code == 200
    assert client.get(f"/recipes/{recipe_id}", headers=outsider["headers"]).status_code == 404
    # Посторонний не может создать рецепт в чужой семье
    assert create_recipe(client, outsider, household_id=household_id, name="Взлом").status_code == 403

    # Владелец семьи может изменить рецепт участника
    assert client.patch(f"/recipes/{recipe_id}", json={"portable": True}, headers=owner["headers"]).status_code == 200

    # Обычный участник не может менять рецепт, созданный владельцем
    owner_recipe = create_recipe(client, owner, household_id=household_id, name="Рецепт владельца").json()["id"]
    assert client.patch(f"/recipes/{owner_recipe}", json={"portable": True}, headers=member["headers"]).status_code == 403
    assert client.delete(f"/recipes/{owner_recipe}", headers=member["headers"]).status_code == 403


def test_household_recipe_cannot_use_personal_food(client):
    owner = register_and_login(client, "a@example.com")
    member = register_and_login(client, "b@example.com")
    household_id = new_household(client, owner, member)
    personal_food = client.post(
        "/foods",
        json={"name": "Личный сыр", "category": "dairy", "calories_per_100g": 300,
              "protein_per_100g": 20, "fat_per_100g": 20, "carbs_per_100g": 1},
        headers=owner["headers"],
    ).json()["id"]
    shared_food = client.post(
        "/foods",
        json={"name": "Семейный сыр", "category": "dairy", "calories_per_100g": 300,
              "protein_per_100g": 20, "fat_per_100g": 20, "carbs_per_100g": 1, "household_id": household_id},
        headers=owner["headers"],
    ).json()["id"]

    bad = create_recipe(
        client, owner, household_id=household_id, name="С личным", ingredients=[{"food_id": personal_food, "amount_g": 30}]
    )
    good = create_recipe(
        client, owner, household_id=household_id, name="С семейным", ingredients=[{"food_id": shared_food, "amount_g": 30}]
    )

    assert bad.status_code == 422
    assert good.status_code == 201, good.text
    # Участник семьи видит и рецепт, и его ингредиент
    assert client.get(f"/recipes/{good.json()['id']}", headers=member["headers"]).status_code == 200


def test_food_used_in_recipe_cannot_be_deleted(client):
    user = register_and_login(client, "a@example.com")
    own_food = client.post(
        "/foods",
        json={"name": "Мой творог", "category": "dairy", "calories_per_100g": 120,
              "protein_per_100g": 17, "fat_per_100g": 5, "carbs_per_100g": 2},
        headers=user["headers"],
    ).json()["id"]
    recipe = create_recipe(client, user, ingredients=[{"food_id": own_food, "amount_g": 200}]).json()

    blocked = client.delete(f"/foods/{own_food}", headers=user["headers"])
    assert blocked.status_code == 409

    client.delete(f"/recipes/{recipe['id']}", headers=user["headers"])
    assert client.delete(f"/foods/{own_food}", headers=user["headers"]).status_code == 204


# ---------------------------------------------------------------- составление плана


def test_generate_requires_weight_and_birth_date(client):
    user = register_and_login(client, "a@example.com")  # нет веса и даты рождения

    response = generate(client, user)

    assert response.status_code == 409
    assert "вес" in response.json()["detail"]
    assert week(client, user)["target_ready"] is False


def test_generate_week_covers_every_day_close_to_target(client):
    user = ready_user(client)

    response = generate(client, user)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created_meals"] == 7 * 4  # по умолчанию 4 приёма пищи
    assert body["skipped_days"] == [] and body["warnings"] == []

    result = week(client, user)
    assert result["target_ready"] is True and len(result["days"]) == 7
    for day in result["days"]:
        target = day["target"]["calories"]
        planned = float(day["planned_calories"])
        assert abs(planned / target - 1) <= 0.06, f"{day['date']}: план {planned}, норма {target}"
        assert [m["meal_type"] for m in day["meals"]] == ["breakfast", "lunch", "snack", "dinner"]
        assert day["warnings"] == []
        # Белок плана не должен сильно отставать от нормы
        assert float(day["planned_protein_g"]) >= 0.8 * day["target"]["protein_g"]


def test_generated_meals_are_consistent(client):
    user = ready_user(client)
    generate(client, user)

    for day in week(client, user)["days"]:
        previous_time = None
        for meal in day["meals"]:
            # Итог приёма пищи равен сумме его продуктов
            assert abs(sum(float(i["calories"]) for i in meal["items"]) - float(meal["calories"])) < 0.01
            assert abs(sum(float(i["protein_g"]) for i in meal["items"]) - float(meal["protein_g"])) < 0.01
            assert meal["status"] == "planned" and meal["recipe_id"] is not None
            assert Decimal("0.5") <= Decimal(meal["portion_scale"]) <= Decimal("2")
            # Время идёт по возрастанию, внутри одного дня по часовому поясу пользователя
            minutes = local_minutes(meal["planned_at"])
            assert previous_time is None or minutes >= previous_time + 60
            previous_time = minutes
            assert at(meal["planned_at"]).astimezone(MSK).date().isoformat() == day["date"]


def test_meals_during_work_hours_are_portable_and_marked_work(client):
    user = ready_user(client)
    add_work_series(client, user)
    generate(client, user, batch_days=1)
    portable_ids = {item["id"] for item in recipes(client, user, portable="true")["items"]}

    work_meals = home_meals = 0
    for index, day in enumerate(week(client, user)["days"]):
        for meal in day["meals"]:
            minutes = local_minutes(meal["planned_at"])
            in_work_hours = index < 5 and 9 * 60 <= minutes < 18 * 60
            if in_work_hours:
                work_meals += 1
                assert meal["location"] == "work", (day["date"], meal["title"], minutes)
                assert meal["recipe_id"] in portable_ids, meal["title"]
            else:
                home_meals += 1
                assert meal["location"] == "home", (day["date"], meal["title"], minutes)
    assert work_meals >= 5 and home_meals >= 5


def test_training_day_has_bigger_target_and_no_meal_before_workout(client):
    user = ready_user(client)
    # Тренировка во вторник 13:00–14:30 по Москве, с блоком нагрузки (иначе калории не учитываются)
    session = client.post(
        f"/users/{user['id']}/training-sessions",
        json={"name": "Силовая", "start_at": "2026-10-27T13:00:00+03:00", "end_at": "2026-10-27T14:30:00+03:00"},
        headers=user["headers"],
    ).json()
    block = client.post(
        f"/users/{user['id']}/training-sessions/{session['id']}/workouts",
        json={"name": "Жим", "load_type": "strength", "planned_intensity": "high",
              "start_at": "2026-10-27T13:00:00+03:00", "end_at": "2026-10-27T14:30:00+03:00"},
        headers=user["headers"],
    )
    assert block.status_code == 201, block.text

    generate(client, user)
    days = week(client, user)["days"]
    monday, tuesday = days[0], days[1]

    assert tuesday["target"]["is_training_day"] is True and tuesday["target"]["calories"] > monday["target"]["calories"]
    assert abs(float(tuesday["planned_calories"]) / tuesday["target"]["calories"] - 1) <= 0.06
    for meal in tuesday["meals"]:
        minutes = local_minutes(meal["planned_at"])
        assert not (12 * 60 < minutes < 14 * 60 + 30), f"{meal['title']} в {minutes // 60}:{minutes % 60:02d}"


def test_wake_up_time_from_sleep_schedule(client):
    user = ready_user(client)
    # Сон 02:00–10:00: завтрак не раньше 10:45
    response = client.post(
        f"/users/{user['id']}/schedule-events/series",
        json={"event_type": "sleep", "title": "Сон", "weekdays": [0, 1, 2, 3, 4, 5, 6], "start_time": "02:00",
              "end_time": "10:00", "from_date": MONDAY, "weeks": 1},
        headers=user["headers"],
    )
    assert response.status_code == 201, response.text

    generate(client, user, days=1)

    monday = week(client, user)["days"][0]
    assert local_minutes(monday["meals"][0]["planned_at"]) == 645


def test_batch_days_controls_repeats_of_lunch_and_dinner(client):
    user = ready_user(client)

    def main_meal_runs(**options):
        client.post(f"{plan_url(user)}/generate", json={"start": MONDAY, "days": 7, "overwrite": True, **options},
                    headers=user["headers"])
        days = week(client, user)["days"]
        runs = {}
        for slot in ("lunch", "dinner"):
            titles = [next(m["title"] for m in d["meals"] if m["meal_type"] == slot) for d in days]
            longest = current = 1
            for a, b in zip(titles, titles[1:]):
                current = current + 1 if a == b else 1
                longest = max(longest, current)
            runs[slot] = longest
        return runs

    assert main_meal_runs(batch_days=1) == {"lunch": 1, "dinner": 1}
    two = main_meal_runs(batch_days=2)
    assert max(two.values()) == 2
    three = main_meal_runs(batch_days=3)
    assert max(three.values()) <= 3


def test_same_recipe_not_repeated_within_a_day(client):
    user = ready_user(client)
    generate(client, user)

    for day in week(client, user)["days"]:
        titles = [m["title"] for m in day["meals"]]
        assert len(titles) == len(set(titles)), titles


def test_generate_skips_filled_days_unless_overwrite(client):
    user = ready_user(client)
    assert generate(client, user, days=3).json()["created_meals"] == 12

    again = generate(client, user, days=5)
    body = again.json()
    # Первые три дня уже заполнены и пропущены, добавлены только два новых дня
    assert body["skipped_days"] == ["2026-10-26", "2026-10-27", "2026-10-28"]
    assert body["created_meals"] == 8 and body["replaced_meals"] == 0

    redo = generate(client, user, days=3, overwrite=True).json()
    assert redo["replaced_meals"] == 12 and redo["created_meals"] == 12 and redo["skipped_days"] == []
    assert sum(len(d["meals"]) for d in week(client, user)["days"][:3]) == 12


def test_overwrite_keeps_eaten_meals_and_fills_rest_of_day(client):
    user = ready_user(client)
    generate(client, user, days=1)
    lunch = next(m for m in week(client, user)["days"][0]["meals"] if m["meal_type"] == "lunch")
    eaten = client.post(f"{plan_url(user)}/meals/{lunch['id']}/eat", headers=user["headers"])
    assert eaten.status_code == 200, eaten.text

    redo = generate(client, user, days=1, overwrite=True).json()

    monday = week(client, user)["days"][0]
    assert redo["replaced_meals"] == 3 and redo["created_meals"] == 3
    # Съеденный обед остался один, новый не добавлен
    assert [m["meal_type"] for m in monday["meals"]].count("lunch") == 1
    assert next(m for m in monday["meals"] if m["meal_type"] == "lunch")["status"] == "eaten"
    assert abs(float(monday["planned_calories"]) / monday["target"]["calories"] - 1) <= 0.06


def test_meals_per_day_setting_changes_number_of_slots(client):
    user = ready_user(client)
    saved = client.put(
        f"/users/{user['id']}/nutrition/settings",
        json={"activity_level": "sedentary", "meals_per_day": 5},
        headers=user["headers"],
    )
    assert saved.status_code == 200, saved.text

    generate(client, user, days=1)

    meals = week(client, user)["days"][0]["meals"]
    assert [m["meal_type"] for m in meals] == ["breakfast", "snack", "lunch", "snack", "dinner"]


def test_plan_is_private(client):
    owner = ready_user(client, "a@example.com")
    stranger = register_and_login(client, "b@example.com")
    generate(client, owner, days=1)
    meal_id = week(client, owner)["days"][0]["meals"][0]["id"]

    assert client.get(plan_url(owner), params={"start": MONDAY}, headers=stranger["headers"]).status_code == 403
    # Свой путь, но чужой id приёма пищи: сервер отвечает «не найдено», а не раскрывает чужие данные
    foreign = client.post(f"{plan_url(stranger)}/meals/{meal_id}/eat", headers=stranger["headers"])
    assert foreign.status_code == 404
    assert client.delete(f"{plan_url(stranger)}/meals/{meal_id}", headers=stranger["headers"]).status_code == 404
    # Прямой доступ к чужому пути запрещён
    assert client.post(f"{plan_url(owner)}/meals/{meal_id}/eat", headers=stranger["headers"]).status_code == 403
    assert client.delete(f"{plan_url(owner)}/meals/{meal_id}", headers=stranger["headers"]).status_code == 403


# ---------------------------------------------------------------- ручные изменения и «съел»


def manual_recipe_meal(client, user, **overrides):
    recipe_id = create_recipe(client, user).json()["id"]
    body = {
        "planned_at": "2026-10-28T08:00:00+03:00",
        "meal_type": "breakfast",
        "recipe_id": recipe_id,
        **overrides,
    }
    return client.post(f"{plan_url(user)}/meals", json=body, headers=user["headers"])


def test_manual_meal_from_recipe_uses_scale(client):
    user = ready_user(client)

    response = manual_recipe_meal(client, user, portion_scale=1.5, location="away")

    assert response.status_code == 201, response.text
    meal = response.json()
    # Творог 200 г и банан 100 г (331 ккал) × 1,5 = 496,5 ккал; массы тоже умножены
    assert float(meal["calories"]) == 496.5
    assert [float(i["amount_g"]) for i in meal["items"]] == [300.0, 150.0]
    assert meal["title"] == "Мой завтрак" and meal["location"] == "away"
    assert meal["plan_date"] == "2026-10-28"
    assert any(m["id"] == meal["id"] for m in week(client, user)["days"][2]["meals"])


def test_manual_meal_from_foods(client):
    user = ready_user(client)
    banana = food_id(client, user, "Банан")

    response = client.post(
        f"{plan_url(user)}/meals",
        json={"planned_at": "2026-10-28T16:00:00+03:00", "meal_type": "snack",
              "items": [{"food_id": banana, "amount_g": 250}]},
        headers=user["headers"],
    )

    assert response.status_code == 201, response.text
    meal = response.json()
    assert float(meal["calories"]) == 222.5  # 89 ккал на 100 г × 2,5
    assert meal["recipe_id"] is None and meal["title"].startswith("Из продуктов: Банан")


def test_manual_meal_validation(client):
    user = ready_user(client)
    banana = food_id(client, user, "Банан")
    url = f"{plan_url(user)}/meals"
    base = {"planned_at": "2026-10-28T16:00:00+03:00", "meal_type": "snack"}

    # Нужно что-то одно: рецепт или продукты
    assert client.post(url, json=base, headers=user["headers"]).status_code == 422
    both = {**base, "recipe_id": 1, "items": [{"food_id": banana, "amount_g": 10}]}
    assert client.post(url, json=both, headers=user["headers"]).status_code == 422
    # Время без часового пояса отклоняется
    naive = {"planned_at": "2026-10-28T16:00:00", "meal_type": "snack", "items": [{"food_id": banana, "amount_g": 10}]}
    assert client.post(url, json=naive, headers=user["headers"]).status_code == 422
    # Несуществующий рецепт и продукт
    assert client.post(url, json={**base, "recipe_id": 999999}, headers=user["headers"]).status_code == 404
    unknown_food = {**base, "items": [{"food_id": 999999, "amount_g": 10}]}
    assert client.post(url, json=unknown_food, headers=user["headers"]).status_code == 404


def test_update_meal_recalculates_from_recipe(client):
    user = ready_user(client)
    meal = manual_recipe_meal(client, user).json()
    url = f"{plan_url(user)}/meals/{meal['id']}"

    scaled = client.patch(url, json={"portion_scale": 2}, headers=user["headers"])
    assert scaled.status_code == 200, scaled.text
    assert float(scaled.json()["calories"]) == 662 and float(scaled.json()["portion_scale"]) == 2.0

    moved = client.patch(
        url,
        json={"planned_at": "2026-10-29T09:30:00+03:00", "meal_type": "lunch", "location": "work"},
        headers=user["headers"],
    )
    assert moved.status_code == 200
    assert moved.json()["plan_date"] == "2026-10-29" and moved.json()["location"] == "work"
    assert float(moved.json()["calories"]) == 662  # состав не менялся

    # Размер порции ручного набора продуктов масштабируется пропорционально
    banana = food_id(client, user, "Банан")
    manual = client.post(
        f"{plan_url(user)}/meals",
        json={"planned_at": "2026-10-29T16:00:00+03:00", "meal_type": "snack",
              "items": [{"food_id": banana, "amount_g": 100}]},
        headers=user["headers"],
    ).json()
    rescaled = client.patch(f"{plan_url(user)}/meals/{manual['id']}", json={"portion_scale": 2}, headers=user["headers"])
    assert rescaled.status_code == 200, rescaled.text
    assert float(rescaled.json()["calories"]) == 178 and float(rescaled.json()["items"][0]["amount_g"]) == 200.0

    assert client.patch(url, json={"meal_type": None}, headers=user["headers"]).status_code == 422


def test_eat_creates_meal_entry_and_reset_removes_it(client):
    user = ready_user(client)
    meal = manual_recipe_meal(client, user).json()
    base = f"{plan_url(user)}/meals/{meal['id']}"

    eaten = client.post(f"{base}/eat", json={"eaten_at": "2026-10-28T08:20:00+03:00"}, headers=user["headers"])

    assert eaten.status_code == 200, eaten.text
    body = eaten.json()
    assert body["status"] == "eaten" and body["meal_entry_id"] is not None
    entries = client.get(
        f"/users/{user['id']}/meal-entries",
        params={"from_at": "2026-10-28T00:00:00+03:00", "to_at": "2026-10-29T00:00:00+03:00"},
        headers=user["headers"],
    ).json()
    assert len(entries) == 1
    assert entries[0]["description"] == "Мой завтрак" and float(entries[0]["calories"]) == 331
    assert at(entries[0]["eaten_at"]) == at("2026-10-28T08:20:00+03:00")

    # Нельзя отметить повторно или изменить съеденное
    assert client.post(f"{base}/eat", headers=user["headers"]).status_code == 409
    assert client.patch(base, json={"portion_scale": 2}, headers=user["headers"]).status_code == 409
    assert client.post(f"{base}/skip", headers=user["headers"]).status_code == 409

    reset = client.post(f"{base}/reset", headers=user["headers"])
    assert reset.status_code == 200 and reset.json()["status"] == "planned" and reset.json()["meal_entry_id"] is None
    after = client.get(
        f"/users/{user['id']}/meal-entries",
        params={"from_at": "2026-10-28T00:00:00+03:00", "to_at": "2026-10-29T00:00:00+03:00"},
        headers=user["headers"],
    ).json()
    assert after == []
    assert client.post(f"{base}/reset", headers=user["headers"]).status_code == 409


def test_eat_without_body_uses_current_time(client):
    user = ready_user(client)
    meal = manual_recipe_meal(client, user).json()

    before = datetime.now(tz=MSK) - timedelta(seconds=5)
    response = client.post(f"{plan_url(user)}/meals/{meal['id']}/eat", headers=user["headers"])

    assert response.status_code == 200, response.text
    entries = client.get(f"/users/{user['id']}/meal-entries", headers=user["headers"]).json()
    assert len(entries) == 1 and at(entries[0]["eaten_at"]) >= before


def test_skipped_meal_not_counted_in_day_total(client):
    user = ready_user(client)
    meal = manual_recipe_meal(client, user).json()
    day = lambda: week(client, user)["days"][2]  # noqa: E731

    assert float(day()["planned_calories"]) == 331
    skipped = client.post(f"{plan_url(user)}/meals/{meal['id']}/skip", headers=user["headers"])
    assert skipped.status_code == 200 and skipped.json()["status"] == "skipped"
    assert float(day()["planned_calories"]) == 0
    assert client.post(f"{plan_url(user)}/meals/{meal['id']}/reset", headers=user["headers"]).json()["status"] == "planned"
    assert float(day()["planned_calories"]) == 331


def test_day_warning_when_plan_far_from_target(client):
    user = ready_user(client)
    manual_recipe_meal(client, user)  # 331 ккал при норме около 2100

    day = week(client, user)["days"][2]

    assert len(day["warnings"]) == 1 and "меньше" in day["warnings"][0]
    assert week(client, user)["days"][0]["warnings"] == []  # в пустом дне предупреждения нет


def test_delete_meal_and_recipe_keep_snapshot(client):
    user = ready_user(client)
    recipe_id = create_recipe(client, user).json()["id"]
    first = client.post(
        f"{plan_url(user)}/meals",
        json={"planned_at": "2026-10-28T08:00:00+03:00", "meal_type": "breakfast", "recipe_id": recipe_id},
        headers=user["headers"],
    ).json()

    # Удаление рецепта не ломает составленный план: состав сохранён, ссылка очищена
    assert client.delete(f"/recipes/{recipe_id}", headers=user["headers"]).status_code == 204
    meal = week(client, user)["days"][2]["meals"][0]
    assert meal["recipe_id"] is None and meal["title"] == "Мой завтрак" and len(meal["items"]) == 2

    assert client.delete(f"{plan_url(user)}/meals/{first['id']}", headers=user["headers"]).status_code == 204
    assert week(client, user)["days"][2]["meals"] == []
    assert client.delete(f"{plan_url(user)}/meals/{first['id']}", headers=user["headers"]).status_code == 404


def test_deleting_diary_entry_keeps_plan_meal(client):
    user = ready_user(client)
    meal = manual_recipe_meal(client, user).json()
    eaten = client.post(f"{plan_url(user)}/meals/{meal['id']}/eat", headers=user["headers"]).json()

    removed = client.delete(f"/users/{user['id']}/meal-entries/{eaten['meal_entry_id']}", headers=user["headers"])
    assert removed.status_code in (200, 204), removed.text

    current = week(client, user)["days"][2]["meals"][0]
    assert current["status"] == "eaten" and current["meal_entry_id"] is None
    # Вернуть в план всё равно можно
    reset = client.post(f"{plan_url(user)}/meals/{meal['id']}/reset", headers=user["headers"])
    assert reset.status_code == 200 and reset.json()["status"] == "planned"
