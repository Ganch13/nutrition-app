"""Тесты шага 69: семейное планирование (общий ужин, закупки и готовка)."""

from decimal import Decimal

from tests.helpers import new_household, register_and_login
from tests.test_meal_plan import (
    MONDAY,
    at,
    create_recipe,
    food_id,
    local_minutes,
    ready_user,
    week,
)
from tests.test_norms import add_weight, setup_profile

MEAL_KEYS = {"id", "planned_at", "meal_type", "location", "status", "title", "recipe_id", "portion_scale", "shared"}


def lesya_user(client, email="lesya@example.com", weight=60):
    """Женщина 30 лет, 60 кг: норма калорий заметно ниже, чем у Дани (80 кг)."""
    user = register_and_login(client, email, name="Леся", timezone="Europe/Moscow")
    setup_profile(client, user, sex="female")
    add_weight(client, user, "2026-10-20", weight)
    return user


def family(client, *, together=(True, True)):
    """Даня (владелец) и Леся в одной семье; together — кто включил «Планировать вместе».

    Результат: (даня, леся, id семьи).
    """
    danya = ready_user(client, "danya@example.com")
    # Имя нужно для списков «кто ест»
    client.patch(f"/users/{danya['id']}", json={"name": "Даня"}, headers=danya["headers"])
    lesya = lesya_user(client)
    household_id = new_household(client, danya, lesya)
    for user, flag in zip((danya, lesya), together):
        if flag:
            opt(client, household_id, user, True)
    return danya, lesya, household_id


def opt(client, household_id, user, value):
    response = client.put(
        f"/households/{household_id}/planning/me", json={"plans_together": value}, headers=user["headers"]
    )
    assert response.status_code == 200, response.text
    return response.json()


def family_generate(client, household_id, user, **overrides):
    body = {"start": MONDAY, "days": 7, **overrides}
    return client.post(f"/households/{household_id}/meal-plan/generate", json=body, headers=user["headers"])


def family_week(client, household_id, user, start=MONDAY):
    return client.get(f"/households/{household_id}/meal-plan", params={"start": start}, headers=user["headers"])


def family_shopping(client, household_id, user, start=MONDAY, days=7):
    response = client.get(
        f"/households/{household_id}/shopping-list", params={"start": start, "days": days}, headers=user["headers"]
    )
    assert response.status_code == 200, response.text
    return response.json()


def personal_shopping(client, user, start=MONDAY, days=7):
    response = client.get(
        f"/users/{user['id']}/shopping-list", params={"start": start, "days": days}, headers=user["headers"]
    )
    assert response.status_code == 200, response.text
    return response.json()


def meals_of(week_json, user_id, meal_type=None):
    """Приёмы пищи участника за неделю из семейного ответа."""
    result = []
    for day in week_json["days"]:
        for member in day["members"]:
            if member["user_id"] == user_id:
                result += [m for m in member["meals"] if meal_type in (None, m["meal_type"])]
    return result


# ---------------------------------------------------------------- согласие и доступ


def test_opt_in_is_per_member_and_visible_to_family(client):
    danya, lesya, household_id = family(client, together=(False, False))

    state = client.get(f"/households/{household_id}/planning", headers=danya["headers"]).json()
    assert state["together_count"] == 0
    assert [(m["name"], m["plans_together"], m["is_me"]) for m in state["members"]] == [
        ("Даня", False, True),
        ("Леся", False, False),
    ]

    state = opt(client, household_id, lesya, True)
    assert state["together_count"] == 1
    # Леся включила только себя; Даня видит это, но свой флаг не менялся
    assert [(m["name"], m["plans_together"], m["is_me"]) for m in state["members"]] == [
        ("Даня", False, False),
        ("Леся", True, True),
    ]
    # Выключение возможно в любой момент
    assert opt(client, household_id, lesya, False)["together_count"] == 0


def test_family_endpoints_are_for_household_members_only(client):
    danya, lesya, household_id = family(client)
    stranger = register_and_login(client, "stranger@example.com")
    base = f"/households/{household_id}"
    body = {"start": MONDAY}

    calls = [
        client.get(f"{base}/planning", headers=stranger["headers"]),
        client.put(f"{base}/planning/me", json={"plans_together": True}, headers=stranger["headers"]),
        client.get(f"{base}/meal-plan", params=body, headers=stranger["headers"]),
        client.post(f"{base}/meal-plan/generate", json=body, headers=stranger["headers"]),
        client.get(f"{base}/shopping-list", params=body, headers=stranger["headers"]),
        client.put(f"{base}/shopping-list/checks", json={**body, "key": "food:1", "checked": True}, headers=stranger["headers"]),
        client.delete(f"{base}/shopping-list/checks", params=body, headers=stranger["headers"]),
        client.get(f"{base}/cooking-plan", params=body, headers=stranger["headers"]),
    ]
    assert [call.status_code for call in calls] == [403] * 8

    # Без токена и для несуществующей семьи
    assert client.get(f"{base}/planning").status_code == 401
    assert client.get("/households/999/planning", headers=danya["headers"]).status_code == 404


def test_cannot_look_at_family_data_without_own_opt_in(client):
    danya, lesya, household_id = family(client, together=(False, True))  # включила только Леся
    base = f"/households/{household_id}"

    # Даня не включил себя — чужое ему не открывается
    for call in (
        client.get(f"{base}/meal-plan", params={"start": MONDAY}, headers=danya["headers"]),
        client.get(f"{base}/shopping-list", params={"start": MONDAY}, headers=danya["headers"]),
        client.get(f"{base}/cooking-plan", params={"start": MONDAY}, headers=danya["headers"]),
        family_generate(client, household_id, danya),
    ):
        assert call.status_code == 403, call.text
        assert "Планировать вместе" in call.json()["detail"]


def test_generate_needs_two_ready_members(client):
    danya, lesya, household_id = family(client, together=(True, False))

    # Включил только один — планировать вместе не с кем
    response = family_generate(client, household_id, danya)
    assert response.status_code == 409 and "минимум двое" in response.json()["detail"]

    # Леся включила, но у неё нет веса: готов тоже только один
    pavel = register_and_login(client, "pavel@example.com", name="Павел")
    household_id = new_household(client, danya, pavel, name="Другая")
    opt(client, household_id, danya, True)
    opt(client, household_id, pavel, True)
    response = family_generate(client, household_id, danya)
    assert response.status_code == 409


def test_member_without_data_gets_warning_but_others_are_planned(client):
    danya, lesya, household_id = family(client)
    pavel = register_and_login(client, "pavel@example.com", name="Павел")
    invite = client.post(f"/households/{household_id}/invites", headers=danya["headers"]).json()
    assert client.post("/households/join", json={"code": invite["code"]}, headers=pavel["headers"]).status_code == 200
    opt(client, household_id, pavel, True)

    response = family_generate(client, household_id, danya, days=2)

    assert response.status_code == 200, response.text
    body = response.json()
    assert [m["name"] for m in body["members"]] == ["Даня", "Леся"]
    assert any(w.startswith("Павел:") and "вес" in w for w in body["warnings"])
    assert week(client, pavel)["days"][0]["meals"] == []


# ---------------------------------------------------------------- общий план


def test_generate_makes_plans_for_each_with_shared_dinner(client):
    danya, lesya, household_id = family(client)

    response = family_generate(client, household_id, danya)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["shared_meals"] == 7
    assert [(m["name"], m["created_meals"], m["replaced_meals"], m["skipped_days"]) for m in body["members"]] == [
        ("Даня", 28, 0, []),
        ("Леся", 28, 0, []),
    ]
    assert body["warnings"] == []

    # Каждый день: у обоих один и тот же ужин, в одно время, дома
    result = family_week(client, household_id, lesya).json()
    danya_dinners = meals_of(result, danya["id"], "dinner")
    lesya_dinners = meals_of(result, lesya["id"], "dinner")
    assert len(danya_dinners) == len(lesya_dinners) == 7
    for his, hers in zip(danya_dinners, lesya_dinners):
        assert his["recipe_id"] == hers["recipe_id"] is not None
        assert at(his["planned_at"]) == at(hers["planned_at"])
        assert his["location"] == hers["location"] == "home"
        assert his["shared"] is True and hers["shared"] is True

    # Порции подогнаны под нормы: у Дани (80 кг) крупнее, чем у Леси (60 кг)
    assert sum(Decimal(m["portion_scale"]) for m in danya_dinners) > sum(Decimal(m["portion_scale"]) for m in lesya_dinners)

    # Остальные приёмы пищи не общие по умолчанию, но план каждого близок к его норме
    for user in (danya, lesya):
        for day in week(client, user)["days"]:
            assert abs(float(day["planned_calories"]) / day["target"]["calories"] - 1) <= 0.08, (user["id"], day["date"])


def test_shared_meal_types_can_be_changed(client):
    danya, lesya, household_id = family(client)

    none = family_generate(client, household_id, danya, shared_meal_types=[], days=3).json()
    assert none["shared_meals"] == 0
    assert [m["created_meals"] for m in none["members"]] == [12, 12]

    both = family_generate(client, household_id, danya, shared_meal_types=["lunch", "dinner", "lunch"], days=3, overwrite=True)
    assert both.status_code == 200, both.text
    assert both.json()["shared_meals"] == 6  # повтор типа в запросе не удваивает
    result = family_week(client, household_id, danya).json()
    for meal_type in ("lunch", "dinner"):
        for his, hers in zip(meals_of(result, danya["id"], meal_type), meals_of(result, lesya["id"], meal_type)):
            assert his["recipe_id"] == hers["recipe_id"] and his["shared"] and hers["shared"]
    # Завтрак при этом у каждого свой выбор: общим он становится только случайным совпадением, а не по правилу
    assert none["shared_meals"] == 0

    bad = family_generate(client, household_id, danya, shared_meal_types=["dessert"])
    assert bad.status_code == 422


def test_shared_dinner_time_is_the_later_of_two(client):
    danya, lesya, household_id = family(client)
    # Леся ложится в 02:00: её ужин 22:30; у Дани по умолчанию 20:30
    response = client.post(
        f"/users/{lesya['id']}/schedule-events/series",
        json={"event_type": "sleep", "title": "Сон", "weekdays": [0, 1, 2, 3, 4, 5, 6], "start_time": "02:00",
              "end_time": "10:00", "from_date": MONDAY, "weeks": 1},
        headers=lesya["headers"],
    )
    assert response.status_code == 201, response.text

    family_generate(client, household_id, danya, days=2)

    result = family_week(client, household_id, danya).json()
    for user in (danya, lesya):
        assert [local_minutes(m["planned_at"]) for m in meals_of(result, user["id"], "dinner")] == [1350, 1350]
    # Без общего ужина у Дани было бы 20:30
    family_generate(client, household_id, danya, days=2, shared_meal_types=[], overwrite=True)
    result = family_week(client, household_id, danya).json()
    assert [local_minutes(m["planned_at"]) for m in meals_of(result, danya["id"], "dinner")] == [1230, 1230]


def test_person_at_work_does_not_share_the_meal(client):
    danya, lesya, household_id = family(client)
    # Даня на работе пн–пт 09:00–18:00: обеденное время 13:30 он проводит не дома
    response = client.post(
        f"/users/{danya['id']}/schedule-events/series",
        json={"event_type": "work", "title": "Работа", "weekdays": [0, 1, 2, 3, 4], "start_time": "09:00",
              "end_time": "18:00", "from_date": MONDAY, "weeks": 1},
        headers=danya["headers"],
    )
    assert response.status_code == 201, response.text

    body = family_generate(client, household_id, danya, shared_meal_types=["lunch"]).json()

    # Общим остался обед только в субботу и воскресенье
    assert body["shared_meals"] == 2
    result = family_week(client, household_id, danya).json()
    his = meals_of(result, danya["id"], "lunch")
    assert [m["shared"] for m in his] == [False] * 5 + [True] * 2
    assert [m["location"] for m in his] == ["work"] * 5 + ["home"] * 2


def test_shared_recipe_is_visible_to_every_member(client):
    danya, lesya, household_id = family(client)
    # Много личных ужинов Дани: Леся их не видит, поэтому общий ужин не может быть одним из них
    # Калорийность у них разная (от ~360 до ~800 ккал), чтобы часть точно подходила под норму ужина
    curd = food_id(client, danya, "Творог 5%")
    private_ids = set()
    for number in range(30):
        response = create_recipe(
            client,
            danya,
            name=f"Мой ужин {number}",
            meal_types=["dinner"],
            ingredients=[{"food_id": curd, "amount_g": 300 + 15 * number}],
        )
        assert response.status_code == 201, response.text
        private_ids.add(response.json()["id"])

    # Контроль самого теста: Даня в одиночку такие ужины выбирает, значит они «конкурентоспособны»
    solo = client.post(
        f"/users/{danya['id']}/meal-plan/generate",
        json={"start": MONDAY, "days": 7, "shared_meal_types": []},
        headers=danya["headers"],
    )
    assert solo.status_code == 200, solo.text
    solo_dinners = {m["recipe_id"] for day in week(client, danya)["days"] for m in day["meals"] if m["meal_type"] == "dinner"}
    assert solo_dinners & private_ids, "личные ужины Дани не выбираются даже без Леси — тест ничего не проверяет"

    family_generate(client, household_id, danya, overwrite=True)

    result = family_week(client, household_id, danya).json()
    shared = {m["recipe_id"] for m in meals_of(result, lesya["id"], "dinner")}
    assert shared and not shared & private_ids
    for recipe_id in shared:
        assert client.get(f"/recipes/{recipe_id}", headers=lesya["headers"]).status_code == 200


def test_family_view_hides_calories_and_macros(client):
    danya, lesya, household_id = family(client)
    family_generate(client, household_id, danya, days=1)

    result = family_week(client, household_id, lesya).json()

    assert set(result) == {"household_id", "start", "end", "members", "days"}
    for meal in meals_of(result, danya["id"]):
        assert set(meal) == MEAL_KEYS
    assert set(result["days"][0]["members"][0]) == {"user_id", "name", "meals"}


def test_second_generation_keeps_filled_days_and_overwrite_replaces(client):
    danya, lesya, household_id = family(client)
    family_generate(client, household_id, danya)

    again = family_generate(client, household_id, lesya).json()
    assert [(m["created_meals"], len(m["skipped_days"])) for m in again["members"]] == [(0, 7), (0, 7)]
    assert again["shared_meals"] == 0

    # Даня съел завтрак в понедельник — при перезаписи он остаётся
    breakfast = week(client, danya)["days"][0]["meals"][0]
    assert client.post(
        f"/users/{danya['id']}/meal-plan/meals/{breakfast['id']}/eat", headers=danya["headers"]
    ).status_code == 200

    redo = family_generate(client, household_id, lesya, overwrite=True).json()
    assert redo["members"][0]["replaced_meals"] == 27 and redo["members"][1]["replaced_meals"] == 28
    assert any(m["id"] == breakfast["id"] and m["status"] == "eaten" for m in week(client, danya)["days"][0]["meals"])


def test_day_already_planned_for_one_member_is_skipped_for_that_member_only(client):
    danya, lesya, household_id = family(client)
    # У Леси на понедельник уже есть свой приём пищи
    response = client.post(
        f"/users/{lesya['id']}/meal-plan/meals",
        json={"planned_at": "2026-10-26T12:00:00+03:00", "meal_type": "lunch",
              "items": [{"food_id": food_id(client, lesya, "Банан"), "amount_g": 100}]},
        headers=lesya["headers"],
    )
    assert response.status_code == 201, response.text

    body = family_generate(client, household_id, danya, days=2).json()

    assert body["members"][0]["skipped_days"] == [] and body["members"][0]["created_meals"] == 8
    assert body["members"][1]["skipped_days"] == [MONDAY] and body["members"][1]["created_meals"] == 4
    # В понедельник ужин общим быть не мог, во вторник — общий
    assert body["shared_meals"] == 1
    result = family_week(client, household_id, danya).json()
    assert [m["shared"] for m in meals_of(result, danya["id"], "dinner")] == [False, True]


def test_opting_out_hides_member_from_family_views(client):
    danya, lesya, household_id = family(client)
    family_generate(client, household_id, danya, days=2)

    opt(client, household_id, lesya, False)

    result = family_week(client, household_id, danya).json()
    assert [m["name"] for m in result["members"]] == ["Даня"]
    assert [member["name"] for member in result["days"][0]["members"]] == ["Даня"]
    # Общим ужин тоже больше не выглядит: второго едока в семейном виде нет
    assert all(m["shared"] is False for m in meals_of(result, danya["id"]))
    assert family_shopping(client, household_id, danya)["members"] == ["Даня"]
    # Личный план Леси остался на месте, а смотреть семейное ей теперь нельзя
    assert len(week(client, lesya)["days"][0]["meals"]) == 4
    assert family_week(client, household_id, lesya).status_code == 403


# ---------------------------------------------------------------- закупки


def test_family_shopping_list_sums_both_plans(client):
    danya, lesya, household_id = family(client)
    family_generate(client, household_id, danya)

    shared = family_shopping(client, household_id, danya)
    his = {item["key"]: item for item in personal_shopping(client, danya)["items"]}
    hers = {item["key"]: item for item in personal_shopping(client, lesya)["items"]}

    assert shared["members"] == ["Даня", "Леся"]
    assert {item["key"] for item in shared["items"]} == set(his) | set(hers)
    assert shared["meals_count"] == 56
    for item in shared["items"]:
        parts = [Decimal(source[item["key"]]["amount_g"]) for source in (his, hers) if item["key"] in source]
        # Сумма округляется вверх один раз, а не по каждому человеку отдельно
        assert sum(parts) - len(parts) + 1 <= Decimal(item["amount_g"]) <= sum(parts), item["name"]
        expected = [name for name, source in (("Даня", his), ("Леся", hers)) if item["key"] in source]
        assert item["members"] == expected
        assert item["checked"] is False and item["checked_by"] is None

    # Личные списки при этом не изменились и не знают о «кто ест»
    assert all(item["members"] == [] for item in personal_shopping(client, danya)["items"])
    assert personal_shopping(client, danya)["members"] == []


def test_family_checks_are_shared_and_show_who_bought(client):
    danya, lesya, household_id = family(client)
    family_generate(client, household_id, danya, days=3)
    key = family_shopping(client, household_id, danya, days=3)["items"][0]["key"]
    url = f"/households/{household_id}/shopping-list/checks"

    assert client.put(url, json={"start": MONDAY, "key": key, "checked": True}, headers=lesya["headers"]).status_code == 204
    # Повтор того же запроса безопасен
    assert client.put(url, json={"start": MONDAY, "key": key, "checked": True}, headers=danya["headers"]).status_code == 204

    seen = family_shopping(client, household_id, danya, days=3)
    item = next(item for item in seen["items"] if item["key"] == key)
    assert item["checked"] is True and item["checked_by"] == "Леся"
    assert seen["checked_count"] == 1
    # Личные отметки остаются отдельными
    assert personal_shopping(client, danya, days=3)["checked_count"] == 0
    # Отметки привязаны к дате начала периода
    other = family_shopping(client, household_id, danya, start="2026-10-27", days=3)
    assert other["checked_count"] == 0

    assert client.put(url, json={"start": MONDAY, "key": key, "checked": False}, headers=danya["headers"]).status_code == 204
    assert family_shopping(client, household_id, lesya, days=3)["checked_count"] == 0

    client.put(url, json={"start": MONDAY, "key": key, "checked": True}, headers=danya["headers"])
    assert client.delete(url, params={"start": MONDAY}, headers=lesya["headers"]).status_code == 204
    assert family_shopping(client, household_id, danya, days=3)["checked_count"] == 0


def test_family_check_without_opt_in_is_forbidden(client):
    danya, lesya, household_id = family(client, together=(True, False))
    url = f"/households/{household_id}/shopping-list/checks"

    response = client.put(url, json={"start": MONDAY, "key": "food:1", "checked": True}, headers=lesya["headers"])

    assert response.status_code == 403
    assert client.delete(url, params={"start": MONDAY}, headers=lesya["headers"]).status_code == 403


def test_checker_who_left_the_plan_still_has_a_name(client):
    danya, lesya, household_id = family(client)
    family_generate(client, household_id, danya, days=2)
    key = family_shopping(client, household_id, danya, days=2)["items"][0]["key"]
    client.put(
        f"/households/{household_id}/shopping-list/checks",
        json={"start": MONDAY, "key": key, "checked": True},
        headers=lesya["headers"],
    )

    opt(client, household_id, lesya, False)

    item = next(i for i in family_shopping(client, household_id, danya, days=2)["items"] if i["key"] == key)
    assert item["checked"] is True and item["checked_by"] == "Леся"


# ---------------------------------------------------------------- готовка


def test_family_cooking_plan_cooks_shared_dinner_once(client):
    danya, lesya, household_id = family(client)
    family_generate(client, household_id, danya, batch_days=1)

    plan = client.get(
        f"/households/{household_id}/cooking-plan", params={"start": MONDAY}, headers=lesya["headers"]
    ).json()

    sessions = plan["sessions"]
    assert sessions
    for session in sessions:
        # Порции подхода — сумма порций тех, кто это ест
        assert Decimal(session["portions"]) == sum(Decimal(m["portion_scale"]) for m in session["meals"])
        assert all(m["user_id"] in (danya["id"], lesya["id"]) and m["user_name"] for m in session["meals"])
        assert session["estimated_minutes"] > 0
    # Хотя бы общий ужин: в одном подходе блюда сразу двух людей
    together = [s for s in sessions if {m["user_id"] for m in s["meals"]} == {danya["id"], lesya["id"]}]
    assert len(together) >= 7
    assert sum(s["estimated_minutes"] for s in sessions) == plan["total_minutes"]
    # Подходов в семье меньше, чем если бы каждый готовил отдельно
    own = [
        client.get(f"/users/{u['id']}/cooking-plan", params={"start": MONDAY}, headers=u["headers"]).json()
        for u in (danya, lesya)
    ]
    assert len(sessions) < sum(len(p["sessions"]) for p in own)
    assert all(m["user_id"] is None for p in own for s in p["sessions"] for m in s["meals"])


def test_family_cooking_plan_requires_opt_in_and_membership(client):
    danya, lesya, household_id = family(client, together=(True, False))
    url = f"/households/{household_id}/cooking-plan"

    assert client.get(url, params={"start": MONDAY}, headers=lesya["headers"]).status_code == 403
    assert client.get(url, params={"start": MONDAY, "days": 15}, headers=danya["headers"]).status_code == 422
