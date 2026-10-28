"""Тесты шага 66: нормы питания (BMR, активность, тренировки, цель) и прогресс целей."""

from datetime import date, timedelta
from decimal import Decimal

from models import Goal, WeightRecord
from norms_services import _progress_for_goal, _slope_per_week, calculate_age, calculate_bmr
from tests.helpers import register_and_login

DAY = "2026-10-27"


def setup_profile(client, user, birth_date="1996-10-27", sex="male"):
    """Заполняет в профиле дату рождения и пол (рост 180 см задан при регистрации)."""
    response = client.patch(
        f"/users/{user['id']}", json={"birth_date": birth_date, "sex": sex}, headers=user["headers"]
    )
    assert response.status_code == 200, response.text


def add_weight(client, user, day, kg):
    response = client.post(
        f"/users/{user['id']}/weight-records",
        json={"measurement_date": str(day), "weight_kg": kg},
        headers=user["headers"],
    )
    assert response.status_code == 201, response.text


def add_goal(client, user, **overrides):
    body = {"goal_type": "fat_loss", "priority": 1, "start_date": "2026-10-01"}
    body.update(overrides)
    response = client.post(f"/users/{user['id']}/goals", json=body, headers=user["headers"])
    assert response.status_code == 201, response.text
    return response.json()


def targets(client, user, day=DAY) -> dict:
    response = client.get(f"/users/{user['id']}/nutrition/targets", params={"target_date": day}, headers=user["headers"])
    assert response.status_code == 200, response.text
    return response.json()


def ready_user(client, email="a@example.com", **kwargs):
    """Мужчина 30 лет, 180 см, 80 кг (на 2026-10-27), часовой пояс Москвы."""
    user = register_and_login(client, email, timezone="Europe/Moscow")
    setup_profile(client, user, **kwargs)
    add_weight(client, user, "2026-10-20", 80)
    return user


# ---------------------------------------------------------------- формулы


def test_bmr_formula_matches_hand_calculation():
    # 10·80 + 6,25·180 − 5·30 + 5 = 1780
    assert calculate_bmr(80, 180, 30, "male") == 1780
    # 10·60 + 6,25·165 − 5·28 − 161 = 1330,25
    assert calculate_bmr(60, 165, 28, "female") == 1330.25
    # Среднее значение формулы: константа −78
    assert calculate_bmr(70, 170, 40, "average") == 700 + 1062.5 - 200 - 78


def test_age_counts_full_years():
    assert calculate_age(date(1996, 10, 27), date(2026, 10, 27)) == 30
    assert calculate_age(date(1996, 10, 28), date(2026, 10, 27)) == 29


# ---------------------------------------------------------------- норма на день


def test_rest_day_target_without_goal(client):
    user = ready_user(client)

    result = targets(client, user)

    assert result["ready"] is True
    assert result["bmr"] == 1780
    assert result["base_kcal"] == 2136  # 1780 × 1,2
    assert result["exercise_kcal"] == 0
    assert result["calories"] == 2136
    assert result["protein_g"] == 128  # 1,6 г/кг × 80
    assert result["fat_g"] == 64  # минимум 0,8 г/кг выше, чем 25 % калорий (59 г)
    assert result["carbs_g"] == 262  # (2136 − 128·4 − 64·9) / 4
    assert result["is_training_day"] is False
    assert result["explanation"]


def test_missing_data_is_reported_not_guessed(client):
    user = register_and_login(client, "a@example.com")  # нет ни веса, ни даты рождения

    result = targets(client, user)

    assert result["ready"] is False
    assert set(result["missing"]) == {"weight", "birth_date"}
    assert result["calories"] is None
    assert result["warnings"]


def test_unspecified_sex_uses_average_and_warns(client):
    user = ready_user(client, sex="unspecified")

    result = targets(client, user)

    assert result["sex_used"] == "average"
    assert result["bmr"] == 1780 - 5 - 78  # константа −78 вместо +5
    assert any("Пол" in warning for warning in result["warnings"])


def create_session_with_blocks(client, user, blocks, start="2026-10-27T10:00:00+03:00", end="2026-10-27T12:00:00+03:00", **extra):
    session = client.post(
        f"/users/{user['id']}/training-sessions",
        json={"name": "Зал", "start_at": start, "end_at": end, **extra},
        headers=user["headers"],
    ).json()
    created = []
    for block in blocks:
        response = client.post(
            f"/users/{user['id']}/training-sessions/{session['id']}/workouts", json=block, headers=user["headers"]
        )
        assert response.status_code == 201, response.text
        created.append(response.json())
    return session, created


def block(start, end, intensity="moderate", load_type="strength", **extra):
    return {
        "name": "Блок",
        "load_type": load_type,
        "planned_intensity": intensity,
        "start_at": start,
        "end_at": end,
        **extra,
    }


def test_training_adds_energy_by_met(client):
    user = ready_user(client)
    # Силовая средней интенсивности 60 минут: (4,5 − 1) × 80 кг × 1 ч = 280 ккал
    create_session_with_blocks(client, user, [block("2026-10-27T10:00:00+03:00", "2026-10-27T11:00:00+03:00")])

    result = targets(client, user)

    assert result["exercise_kcal"] == 280
    assert result["training_minutes"] == 60
    assert result["is_training_day"] is True
    assert result["tdee"] == 2136 + 280
    assert result["calories"] == 2416


def test_actual_intensity_overrides_planned(client):
    user = ready_user(client)
    _, blocks = create_session_with_blocks(
        client, user, [block("2026-10-27T10:00:00+03:00", "2026-10-27T11:00:00+03:00", intensity="low")]
    )
    # План «низкая»: (3 − 1)·80 = 160. Фактически «высокая»: (6 − 1)·80 = 400
    assert targets(client, user)["exercise_kcal"] == 160
    session_id = blocks[0]["training_session_id"]
    client.patch(
        f"/users/{user['id']}/training-sessions/{session_id}/workouts/{blocks[0]['id']}",
        json={"actual_intensity": "high"},
        headers=user["headers"],
    )

    assert targets(client, user)["exercise_kcal"] == 400


def test_superset_time_is_not_counted_twice(client):
    user = ready_user(client)
    first = block("2026-10-27T10:00:00+03:00", "2026-10-27T11:00:00+03:00")
    session, created = create_session_with_blocks(client, user, [first])
    # Второй блок идёт одновременно с первым, как суперсет
    response = client.post(
        f"/users/{user['id']}/training-sessions/{session['id']}/workouts",
        json=block("2026-10-27T10:00:00+03:00", "2026-10-27T11:00:00+03:00", superset_with_workout_id=created[0]["id"]),
        headers=user["headers"],
    )
    assert response.status_code == 201, response.text

    result = targets(client, user)

    # Реально прошёл один час, а не два
    assert result["training_minutes"] == 60
    assert result["exercise_kcal"] == 280


def test_session_without_blocks_uses_default_load(client):
    user = ready_user(client)
    create_session_with_blocks(client, user, [], start="2026-10-27T18:00:00+03:00", end="2026-10-27T19:30:00+03:00")

    result = targets(client, user)

    # 1,5 ч × (5 − 1) × 80 = 480
    assert result["exercise_kcal"] == 480


def test_cancelled_and_other_day_sessions_are_ignored(client):
    user = ready_user(client)
    create_session_with_blocks(client, user, [], status="cancelled")
    create_session_with_blocks(client, user, [], start="2026-10-28T10:00:00+03:00", end="2026-10-28T12:00:00+03:00")

    assert targets(client, user)["exercise_kcal"] == 0


def test_fat_loss_goal_creates_deficit(client):
    user = ready_user(client)
    add_goal(client, user, goal_type="fat_loss", target_weight_kg=75, desired_rate_kg_per_week=0.4)

    result = targets(client, user)

    # 0,4 кг в неделю × 7700 / 7 = 440 ккал в день
    assert result["goal_adjustment_kcal"] == -440
    assert result["calories"] == 2136 - 440
    assert result["goal_type"] == "fat_loss"
    # Белок ограничен 35 % калорий: 0,35 × 1696 / 4 ≈ 148 г (а не 2 г/кг = 160 г)
    assert result["protein_g"] == 148


def test_deficit_is_limited_to_a_quarter_of_expenditure(client):
    user = ready_user(client)
    # 0,5 кг в неделю = 550 ккал, но 25 % от 2136 = 534
    add_goal(client, user, goal_type="fat_loss", desired_rate_kg_per_week=0.5)

    result = targets(client, user)

    assert result["goal_adjustment_kcal"] == -534
    assert any("25" in warning for warning in result["warnings"])


def test_muscle_gain_goal_creates_surplus_with_default_rate(client):
    user = ready_user(client)
    add_goal(client, user, goal_type="muscle_gain")  # темп не задан → 0,25 кг/нед

    result = targets(client, user)

    assert result["goal_adjustment_kcal"] == 275
    assert result["calories"] == 2136 + 275


def test_deficit_is_capped_and_floor_applies(client):
    user = register_and_login(client, "lesya@example.com", timezone="Europe/Moscow")
    setup_profile(client, user, birth_date="1986-05-01", sex="female")  # 40 лет
    add_weight(client, user, "2026-10-20", 50)
    add_goal(client, user, goal_type="fat_loss", desired_rate_kg_per_week=1.5)

    result = targets(client, user)

    # BMR = 500 + 1125 − 200 − 161 = 1264; ×1,2 = 1517; дефицит ограничен 25 % → 1138 < 1200
    assert result["bmr"] == 1264
    assert result["calories"] == 1200
    assert len(result["warnings"]) >= 2


def test_reached_target_means_maintenance(client):
    user = ready_user(client)
    add_goal(client, user, goal_type="fat_loss", target_weight_kg=85)  # уже 80 ≤ 85

    result = targets(client, user)

    assert result["goal_adjustment_kcal"] == 0
    assert result["calories"] == 2136
    assert any("достигнут" in warning for warning in result["warnings"])


def test_only_highest_priority_active_goal_counts(client):
    user = ready_user(client)
    add_goal(client, user, goal_type="muscle_gain", priority=2)
    add_goal(client, user, goal_type="fat_loss", priority=1, desired_rate_kg_per_week=0.5)

    assert targets(client, user)["goal_type"] == "fat_loss"


def test_manual_settings_override_calculation(client):
    user = ready_user(client)
    response = client.put(
        f"/users/{user['id']}/nutrition/settings",
        json={"activity_level": "moderate", "meals_per_day": 5, "protein_g_per_kg": 2.2, "calorie_override": 2500},
        headers=user["headers"],
    )
    assert response.status_code == 200, response.text

    result = targets(client, user)

    assert result["base_kcal"] == 2492  # 1780 × 1,4
    assert result["calories"] == 2500
    assert result["protein_g"] == 176  # 2,2 × 80


def test_settings_defaults_roundtrip_and_validation(client):
    user = register_and_login(client, "a@example.com")
    url = f"/users/{user['id']}/nutrition/settings"

    default = client.get(url, headers=user["headers"]).json()
    assert default["activity_level"] == "sedentary"
    assert default["meals_per_day"] == 4

    for bad in (
        {"activity_level": "extreme"},
        {"meals_per_day": 2},
        {"meals_per_day": 7},
        {"protein_g_per_kg": 5},
        {"calorie_override": 300},
    ):
        assert client.put(url, json=bad, headers=user["headers"]).status_code == 422, bad

    assert client.put(url, json={"activity_level": "light", "meals_per_day": 3}, headers=user["headers"]).status_code == 200
    saved = client.get(url, headers=user["headers"]).json()
    assert saved["activity_level"] == "light"
    assert saved["meals_per_day"] == 3


def test_norms_are_private(client):
    owner = register_and_login(client, "owner@example.com")
    stranger = register_and_login(client, "stranger@example.com")

    for path in ("nutrition/settings", "nutrition/targets", "goals/progress"):
        response = client.get(f"/users/{owner['id']}/{path}", headers=stranger["headers"])
        assert response.status_code == 403, path
        assert client.get(f"/users/{owner['id']}/{path}").status_code == 401, path
    assert client.put(f"/users/{owner['id']}/nutrition/settings", json={}, headers=stranger["headers"]).status_code == 403


# ---------------------------------------------------------------- прогресс целей


def make_goal(goal_type="fat_loss", start=date(2026, 10, 1), target=Decimal("90"), rate=Decimal("0.5")):
    return Goal(
        id=1, user_id=1, goal_type=goal_type, priority=1, start_date=start,
        target_weight_kg=target, desired_rate_kg_per_week=rate, status="active",
    )


def weights(*pairs):
    return [WeightRecord(id=i, user_id=1, measurement_date=day, weight_kg=Decimal(str(kg))) for i, (day, kg) in enumerate(pairs, 1)]


def test_slope_is_per_week_and_needs_a_week_of_data():
    points = [(date(2026, 10, 1), Decimal("100")), (date(2026, 10, 8), Decimal("99.5")), (date(2026, 10, 15), Decimal("99"))]
    assert _slope_per_week(points) == Decimal("-0.5")
    assert _slope_per_week(points[:1]) is None
    assert _slope_per_week([(date(2026, 10, 1), Decimal("100")), (date(2026, 10, 5), Decimal("99"))]) is None


def test_progress_on_track_with_eta():
    records = weights((date(2026, 10, 1), 100), (date(2026, 10, 8), 99.5), (date(2026, 10, 15), 99), (date(2026, 10, 22), 98.5))
    progress = _progress_for_goal(make_goal(), records, today=date(2026, 10, 27))

    assert progress.status == "on_track"
    assert progress.start_weight_kg == Decimal("100")
    assert progress.current_weight_kg == Decimal("98.5")
    assert progress.change_kg == Decimal("-1.5")
    assert progress.remaining_kg == Decimal("-8.5")
    assert progress.progress_percent == 15  # 1,5 из 10 кг
    assert progress.actual_rate_kg_per_week == Decimal("-0.50")
    # 8,5 кг при 0,5 кг в неделю = 17 недель = 119 дней
    assert progress.eta_date == date(2026, 10, 27) + timedelta(days=119)


def test_progress_statuses():
    today = date(2026, 10, 27)

    def status(*pairs, goal=None):
        return _progress_for_goal(goal or make_goal(), weights(*pairs), today).status

    # Быстрее желаемого (−1 кг в неделю при желаемых 0,5)
    assert status((date(2026, 10, 1), 100), (date(2026, 10, 8), 99), (date(2026, 10, 15), 98)) == "faster"
    # Медленнее (−0,2 в неделю)
    assert status((date(2026, 10, 1), 100), (date(2026, 10, 15), 99.6), (date(2026, 10, 22), 99.4)) == "slower"
    # Вес растёт при цели снижения
    assert status((date(2026, 10, 1), 100), (date(2026, 10, 15), 101)) == "wrong_direction"
    # Стоит на месте
    assert status((date(2026, 10, 1), 100), (date(2026, 10, 15), 100)) == "stalled"
    # Достигнута
    assert status((date(2026, 10, 1), 100), (date(2026, 10, 20), 89.5)) == "reached"
    # Мало данных: одна точка и две точки в пределах недели
    assert status((date(2026, 10, 25), 100)) == "no_data"
    assert status((date(2026, 10, 24), 100), (date(2026, 10, 27), 99)) == "no_data"


def test_progress_for_muscle_gain_counts_growth_as_progress():
    goal = make_goal("muscle_gain", target=Decimal("85"), rate=Decimal("0.25"))
    records = weights((date(2026, 10, 1), 80), (date(2026, 10, 15), 80.5), (date(2026, 10, 22), 80.75))

    progress = _progress_for_goal(goal, records, date(2026, 10, 27))

    assert progress.status == "on_track"
    assert progress.actual_rate_kg_per_week > 0


def test_progress_without_weights_and_endpoint(client):
    user = register_and_login(client, "a@example.com")
    add_goal(client, user, target_weight_kg=90)

    empty = client.get(f"/users/{user['id']}/goals/progress", headers=user["headers"]).json()
    assert len(empty) == 1
    assert empty[0]["status"] == "no_data"

    today = date.today()
    add_weight(client, user, today - timedelta(days=14), 100)
    add_weight(client, user, today - timedelta(days=7), 99.5)
    add_weight(client, user, today, 99)
    data = client.get(f"/users/{user['id']}/goals/progress", headers=user["headers"]).json()
    assert data[0]["status"] in ("on_track", "slower")
    assert Decimal(data[0]["current_weight_kg"]) == Decimal("99")
    assert data[0]["eta_date"] is not None
