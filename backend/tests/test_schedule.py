"""Тесты шага 64: расписание, серии событий, недельный вид, блоки тренировки."""

from datetime import datetime
from zoneinfo import ZoneInfo

from tests.helpers import register_and_login


def at(text: str) -> datetime:
    """Превращает строку времени из ответа сервера в момент времени.

    Сравниваем моменты, а не строки: PostgreSQL отдаёт время в часовом поясе своей сессии
    (+00:00, +03:00…), и строка "2026-10-26T09:00:00+00:00" может прийти как "...12:00:00+03:00".
    """
    return datetime.fromisoformat(text)


def make_event(client, user, **overrides) -> dict:
    """Создаёт одиночное событие; по умолчанию «Работа» 26 октября 09:00–18:00 UTC."""
    body = {
        "event_type": "work",
        "title": "Работа",
        "start_at": "2026-10-26T09:00:00+00:00",
        "end_at": "2026-10-26T18:00:00+00:00",
    }
    body.update(overrides)
    response = client.post(f"/users/{user['id']}/schedule-events", json=body, headers=user["headers"])
    assert response.status_code == 201, response.text
    return response.json()


def make_session(client, user, start="2026-10-26T22:00:00+03:00", end="2026-10-26T23:30:00+03:00", **extra) -> dict:
    """Создаёт тренировочную сессию; время по умолчанию 22:00–23:30 по Москве."""
    body = {"name": "Силовая", "start_at": start, "end_at": end, **extra}
    response = client.post(f"/users/{user['id']}/training-sessions", json=body, headers=user["headers"])
    assert response.status_code == 201, response.text
    return response.json()


def add_block(client, user, session_id, start, end, name="Блок", **extra):
    """Добавляет блок в сессию; возвращает ответ сервера без проверок."""
    body = {
        "name": name,
        "load_type": "strength",
        "planned_intensity": "moderate",
        "start_at": start,
        "end_at": end,
        **extra,
    }
    return client.post(
        f"/users/{user['id']}/training-sessions/{session_id}/workouts",
        json=body,
        headers=user["headers"],
    )


# ---------------------------------------------------------------- события


def test_update_event_changes_only_given_fields(client):
    user = register_and_login(client, "a@example.com")
    event = make_event(client, user, location="Офис")

    response = client.patch(
        f"/users/{user['id']}/schedule-events/{event['id']}",
        json={"title": "Работа из дома", "location": "Дома"},
        headers=user["headers"],
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "Работа из дома"
    assert body["location"] == "Дома"
    # Время не передавали — оно осталось прежним
    assert at(body["start_at"]) == at("2026-10-26T09:00:00+00:00")


def test_update_event_rejects_end_before_saved_start(client):
    user = register_and_login(client, "a@example.com")
    event = make_event(client, user)

    # Передаём только окончание, которое раньше сохранённого начала (09:00)
    response = client.patch(
        f"/users/{user['id']}/schedule-events/{event['id']}",
        json={"end_at": "2026-10-26T08:00:00+00:00"},
        headers=user["headers"],
    )

    assert response.status_code == 422


def test_update_event_cannot_clear_required_field(client):
    user = register_and_login(client, "a@example.com")
    event = make_event(client, user)

    response = client.patch(
        f"/users/{user['id']}/schedule-events/{event['id']}",
        json={"title": None},
        headers=user["headers"],
    )

    assert response.status_code == 422


def test_other_user_cannot_touch_my_event(client):
    owner = register_and_login(client, "owner@example.com")
    stranger = register_and_login(client, "stranger@example.com")
    event = make_event(client, owner)

    # Чужой id в адресе → 403 от проверки владельца данных
    response = client.patch(
        f"/users/{owner['id']}/schedule-events/{event['id']}",
        json={"title": "Взлом"},
        headers=stranger["headers"],
    )
    assert response.status_code == 403

    # Свой адрес, но чужое событие → 404, существование не раскрывается
    response = client.delete(
        f"/users/{stranger['id']}/schedule-events/{event['id']}",
        headers=stranger["headers"],
    )
    assert response.status_code == 404


def test_delete_event_keeps_linked_training_session(client):
    user = register_and_login(client, "a@example.com")
    event = make_event(client, user, event_type="workout", title="Зал")
    session = make_session(client, user, schedule_event_id=event["id"])
    assert session["schedule_event_id"] == event["id"]

    response = client.delete(
        f"/users/{user['id']}/schedule-events/{event['id']}", headers=user["headers"]
    )
    assert response.status_code == 204

    sessions = client.get(f"/users/{user['id']}/training-sessions", headers=user["headers"]).json()
    # Тренировка осталась, связь с удалённым событием очищена
    assert len(sessions) == 1
    assert sessions[0]["schedule_event_id"] is None


# ---------------------------------------------------------------- серии


def series_body(**overrides) -> dict:
    body = {
        "event_type": "work",
        "title": "Работа",
        "weekdays": [0, 1, 2, 3, 4],
        "start_time": "09:00",
        "end_time": "18:00",
        "from_date": "2026-10-26",
        "weeks": 2,
        "location": "Офис",
    }
    body.update(overrides)
    return body


def test_series_creates_event_for_each_matching_weekday(client):
    user = register_and_login(client, "a@example.com", timezone="Europe/Moscow")

    response = client.post(
        f"/users/{user['id']}/schedule-events/series", json=series_body(), headers=user["headers"]
    )

    assert response.status_code == 201, response.text
    body = response.json()
    # 2 недели × 5 рабочих дней
    assert len(body["events"]) == 10
    first = body["events"][0]
    assert at(first["start_at"]) == at("2026-10-26T09:00:00+03:00")
    assert at(first["end_at"]) == at("2026-10-26T18:00:00+03:00")
    assert {event["series_id"] for event in body["events"]} == {body["series_id"]}


def test_series_overnight_event_ends_next_day(client):
    user = register_and_login(client, "a@example.com", timezone="Europe/Moscow")

    response = client.post(
        f"/users/{user['id']}/schedule-events/series",
        json=series_body(
            event_type="sleep", title="Сон", weekdays=[0], start_time="23:00", end_time="07:00", weeks=1
        ),
        headers=user["headers"],
    )

    assert response.status_code == 201, response.text
    event = response.json()["events"][0]
    assert at(event["start_at"]) == at("2026-10-26T23:00:00+03:00")
    assert at(event["end_at"]) == at("2026-10-27T07:00:00+03:00")


def test_series_follows_daylight_saving_of_user_timezone(client):
    # В Берлине часы переводят назад в ночь на 25 октября 2026
    user = register_and_login(client, "a@example.com", timezone="Europe/Berlin")

    response = client.post(
        f"/users/{user['id']}/schedule-events/series",
        json=series_body(weekdays=[4, 0], from_date="2026-10-23", weeks=1),
        headers=user["headers"],
    )

    assert response.status_code == 201, response.text
    starts = [event["start_at"] for event in response.json()["events"]]
    # Пятница до перевода: +02:00. Понедельник после перевода: +01:00. Местное время одно и то же — 09:00.
    berlin = ZoneInfo("Europe/Berlin")
    assert [at(start) for start in starts] == [
        datetime(2026, 10, 23, 9, 0, tzinfo=berlin),
        datetime(2026, 10, 26, 9, 0, tzinfo=berlin),
    ]
    # Разница с UTC действительно разная: 7:00 UTC и 8:00 UTC
    assert [at(start).astimezone(ZoneInfo("UTC")).hour for start in starts] == [7, 8]


def test_series_validation(client):
    user = register_and_login(client, "a@example.com")
    url = f"/users/{user['id']}/schedule-events/series"

    for bad in (
        series_body(weekdays=[]),
        series_body(weekdays=[7]),
        series_body(weekdays=[1, 1]),
        series_body(weeks=0),
        series_body(weeks=27),
        series_body(start_time="09:00", end_time="09:00"),
    ):
        assert client.post(url, json=bad, headers=user["headers"]).status_code == 422, bad


def test_delete_following_removes_this_and_later_events_only(client):
    user = register_and_login(client, "a@example.com")
    events = client.post(
        f"/users/{user['id']}/schedule-events/series",
        json=series_body(weekdays=[0], weeks=4),
        headers=user["headers"],
    ).json()["events"]
    assert len(events) == 4

    # Удаляем «со второго понедельника и дальше»
    response = client.delete(
        f"/users/{user['id']}/schedule-events/{events[1]['id']}?scope=following",
        headers=user["headers"],
    )
    assert response.status_code == 204

    remaining = client.get(
        f"/users/{user['id']}/schedule-events",
        params={"from_at": "2026-10-01T00:00:00+00:00", "to_at": "2026-12-31T00:00:00+00:00"},
        headers=user["headers"],
    ).json()
    assert [event["id"] for event in remaining] == [events[0]["id"]]


# ---------------------------------------------------------------- неделя


def test_week_view_lists_items_and_finds_conflicts(client):
    user = register_and_login(client, "a@example.com")
    work = make_event(client, user, is_container=True)  # Работа 09:00–18:00, внутри бывают другие события
    lunch_event = make_event(
        client, user, event_type="meal", title="Обед",
        start_at="2026-10-26T13:00:00+00:00", end_at="2026-10-26T13:30:00+00:00",
    )  # обед внутри блока работы — не конфликт
    # Тренировка выходит за границы блока — конфликт
    session = make_session(client, user, start="2026-10-26T17:30:00+00:00", end="2026-10-26T19:00:00+00:00")

    response = client.get(
        f"/users/{user['id']}/schedule/week", params={"start": "2026-10-26"}, headers=user["headers"]
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["start"] == "2026-10-26"
    assert body["end"] == "2026-11-01"
    assert [item["title"] for item in body["items"]] == ["Работа", "Обед", "Силовая"]
    by_title = {item["title"]: item for item in body["items"]}
    assert by_title["Работа"]["is_container"] is True and by_title["Работа"]["parent_id"] is None
    assert by_title["Обед"]["parent_id"] == work["id"] and lunch_event["is_container"] is False
    assert by_title["Силовая"]["parent_id"] is None
    assert len(body["conflicts"]) == 1
    conflict = body["conflicts"][0]
    assert {conflict["first"]["title"], conflict["second"]["title"]} == {"Работа", "Силовая"}
    assert session["id"] in (conflict["first"]["id"], conflict["second"]["id"])


def test_week_view_ignores_cancelled_training_and_linked_pair(client):
    user = register_and_login(client, "a@example.com")
    make_event(client, user)  # Работа 09:00–18:00
    # Отменённая тренировка во время работы конфликтом не считается
    make_session(client, user, start="2026-10-26T10:00:00+00:00", end="2026-10-26T11:00:00+00:00", status="cancelled")
    # Событие «workout» и привязанная к нему тренировка — одно и то же занятие
    gym = make_event(
        client, user, event_type="workout", title="Зал",
        start_at="2026-10-26T19:00:00+00:00", end_at="2026-10-26T20:00:00+00:00",
    )
    make_session(client, user, start="2026-10-26T19:00:00+00:00", end="2026-10-26T20:00:00+00:00", schedule_event_id=gym["id"])

    body = client.get(
        f"/users/{user['id']}/schedule/week", params={"start": "2026-10-26"}, headers=user["headers"]
    ).json()

    assert body["conflicts"] == []


def test_week_view_excludes_other_weeks_and_other_users(client):
    user = register_and_login(client, "a@example.com")
    other = register_and_login(client, "b@example.com")
    make_event(client, user, title="Эта неделя")
    make_event(client, user, title="Следующая", start_at="2026-11-03T09:00:00+00:00", end_at="2026-11-03T10:00:00+00:00")
    make_event(client, other, title="Чужое")

    body = client.get(
        f"/users/{user['id']}/schedule/week", params={"start": "2026-10-26"}, headers=user["headers"]
    ).json()

    assert [item["title"] for item in body["items"]] == ["Эта неделя"]


def test_week_view_requires_own_account(client):
    owner = register_and_login(client, "owner@example.com")
    stranger = register_and_login(client, "stranger@example.com")

    response = client.get(
        f"/users/{owner['id']}/schedule/week", params={"start": "2026-10-26"}, headers=stranger["headers"]
    )
    assert response.status_code == 403

    response = client.get(f"/users/{owner['id']}/schedule/week", params={"start": "2026-10-26"})
    assert response.status_code == 401


# ---------------------------------------------------------------- блоки тренировки


def test_block_cannot_start_before_previous_block_ends(client):
    user = register_and_login(client, "a@example.com", timezone="Europe/Moscow")
    session = make_session(client, user)  # 22:00–23:30 МСК
    first = add_block(client, user, session["id"], "2026-10-26T22:30:00+03:00", "2026-10-26T22:45:00+03:00", "Жим")
    assert first.status_code == 201, first.text

    # Второй блок начинается в 22:30 — в то же время, что и первый
    clash = add_block(client, user, session["id"], "2026-10-26T22:30:00+03:00", "2026-10-26T22:50:00+03:00", "Тяга")

    assert clash.status_code == 409
    detail = clash.json()["detail"]
    # Сообщение называет конфликтующий блок и время, с которого можно начинать (по часам пользователя)
    assert "Жим" in detail
    assert "22:45" in detail
    assert "суперсет" in detail


def test_block_can_start_exactly_when_previous_ends(client):
    user = register_and_login(client, "a@example.com", timezone="Europe/Moscow")
    session = make_session(client, user)
    add_block(client, user, session["id"], "2026-10-26T22:30:00+03:00", "2026-10-26T22:45:00+03:00", "Жим")

    follow = add_block(client, user, session["id"], "2026-10-26T22:45:00+03:00", "2026-10-26T23:00:00+03:00", "Тяга")

    assert follow.status_code == 201, follow.text
    assert follow.json()["superset_group"] is None


def test_superset_allows_overlap_and_shares_group(client):
    user = register_and_login(client, "a@example.com", timezone="Europe/Moscow")
    session = make_session(client, user)
    first = add_block(client, user, session["id"], "2026-10-26T22:30:00+03:00", "2026-10-26T22:45:00+03:00", "Жим").json()

    second = add_block(
        client, user, session["id"],
        "2026-10-26T22:30:00+03:00", "2026-10-26T22:45:00+03:00", "Тяга",
        superset_with_workout_id=first["id"],
    )

    assert second.status_code == 201, second.text
    group = second.json()["superset_group"]
    assert group is not None

    # Партнёр тоже получил номер группы
    blocks = client.get(
        f"/users/{user['id']}/training-sessions/{session['id']}/workouts", headers=user["headers"]
    ).json()
    assert {block["superset_group"] for block in blocks} == {group}

    # Третий блок в том же времени без суперсета по-прежнему запрещён…
    third = add_block(client, user, session["id"], "2026-10-26T22:30:00+03:00", "2026-10-26T22:45:00+03:00", "Присед")
    assert third.status_code == 409
    # …а с указанием любого блока группы — разрешён и входит в ту же группу
    third = add_block(
        client, user, session["id"],
        "2026-10-26T22:30:00+03:00", "2026-10-26T22:45:00+03:00", "Присед",
        superset_with_workout_id=second.json()["id"],
    )
    assert third.status_code == 201, third.text
    assert third.json()["superset_group"] == group


def test_superset_does_not_excuse_overlap_with_other_blocks(client):
    user = register_and_login(client, "a@example.com", timezone="Europe/Moscow")
    session = make_session(client, user)
    a = add_block(client, user, session["id"], "2026-10-26T22:00:00+03:00", "2026-10-26T22:20:00+03:00", "A").json()
    add_block(client, user, session["id"], "2026-10-26T22:20:00+03:00", "2026-10-26T22:40:00+03:00", "B")

    # Блок C объединён с A, но заходит и на время B — это уже пересечение с чужим блоком
    clash = add_block(
        client, user, session["id"], "2026-10-26T22:10:00+03:00", "2026-10-26T22:30:00+03:00", "C",
        superset_with_workout_id=a["id"],
    )

    assert clash.status_code == 409
    assert "«B»" in clash.json()["detail"]


def test_superset_partner_must_be_in_same_session(client):
    user = register_and_login(client, "a@example.com")
    session_one = make_session(client, user)
    session_two = make_session(client, user, start="2026-10-27T22:00:00+03:00", end="2026-10-27T23:30:00+03:00")
    foreign = add_block(client, user, session_two["id"], "2026-10-27T22:00:00+03:00", "2026-10-27T22:30:00+03:00").json()

    response = add_block(
        client, user, session_one["id"], "2026-10-26T22:00:00+03:00", "2026-10-26T22:30:00+03:00",
        superset_with_workout_id=foreign["id"],
    )
    assert response.status_code == 404

    response = add_block(
        client, user, session_one["id"], "2026-10-26T22:00:00+03:00", "2026-10-26T22:30:00+03:00",
        superset_with_workout_id=999999,
    )
    assert response.status_code == 404


def patch_block(client, user, session_id, workout_id, body):
    return client.patch(
        f"/users/{user['id']}/training-sessions/{session_id}/workouts/{workout_id}",
        json=body,
        headers=user["headers"],
    )


def test_mark_block_completed_uses_planned_intensity_by_default(client):
    user = register_and_login(client, "a@example.com")
    session = make_session(client, user)
    block = add_block(
        client, user, session["id"], "2026-10-26T22:00:00+03:00", "2026-10-26T22:30:00+03:00",
        planned_intensity="high",
    ).json()
    assert block["completed_at"] is None

    response = patch_block(client, user, session["id"], block["id"], {"completed": True})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["completed_at"] is not None
    assert body["actual_intensity"] == "high"  # не выбрали вручную → как в плане

    # Повторное нажатие не меняет время отметки
    again = patch_block(client, user, session["id"], block["id"], {"completed": True}).json()
    assert again["completed_at"] == body["completed_at"]


def test_mark_block_completed_keeps_chosen_actual_intensity(client):
    user = register_and_login(client, "a@example.com")
    session = make_session(client, user)
    block = add_block(
        client, user, session["id"], "2026-10-26T22:00:00+03:00", "2026-10-26T22:30:00+03:00",
        planned_intensity="high",
    ).json()

    response = patch_block(client, user, session["id"], block["id"], {"actual_intensity": "low", "completed": True})

    body = response.json()
    assert body["actual_intensity"] == "low"
    assert body["completed_at"] is not None


def test_unmark_block_completed(client):
    user = register_and_login(client, "a@example.com")
    session = make_session(client, user)
    block = add_block(client, user, session["id"], "2026-10-26T22:00:00+03:00", "2026-10-26T22:30:00+03:00").json()
    patch_block(client, user, session["id"], block["id"], {"completed": True})

    response = patch_block(client, user, session["id"], block["id"], {"completed": False})

    assert response.json()["completed_at"] is None


# ---------------------------------------------------------------- вложенные события и пересечения


def post_event(client, user, **overrides):
    """Как make_event, но возвращает ответ сервера без проверок."""
    body = {
        "event_type": "work",
        "title": "Работа",
        "start_at": "2026-10-26T09:00:00+00:00",
        "end_at": "2026-10-26T18:00:00+00:00",
        **overrides,
    }
    return client.post(f"/users/{user['id']}/schedule-events", json=body, headers=user["headers"])


def lunch(start: str, end: str, title: str = "Обед") -> dict:
    """Событие 26 октября по UTC: lunch("14:00", "15:00") → обед 14:00–15:00."""
    return {
        "event_type": "meal",
        "title": title,
        "start_at": f"2026-10-26T{start}:00+00:00",
        "end_at": f"2026-10-26T{end}:00+00:00",
    }


def test_events_without_container_cannot_overlap(client):
    user = register_and_login(client, "plain@example.com")
    make_event(client, user)  # Работа 09:00–18:00 без отметки
    response = post_event(client, user, **lunch("14:00", "15:00"))
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "«Обед» пересекается с событием «Работа» (26.10 09:00–18:00)" in detail
    assert "Внутри этого блока могут быть другие события" in detail

    # Вплотную — не пересечение
    assert post_event(client, user, **lunch("18:00", "19:00", "Ужин")).status_code == 201
    assert post_event(client, user, **lunch("08:00", "09:00", "Завтрак")).status_code == 201


def test_nested_events_fit_inside_container_and_may_touch(client):
    user = register_and_login(client, "nest@example.com")
    make_event(client, user, is_container=True)  # Работа 09:00–18:00

    assert post_event(client, user, **lunch("14:00", "15:00")).status_code == 201
    # Подряд можно, внахлёст — нельзя
    assert post_event(client, user, **lunch("15:00", "15:30", "Кофе")).status_code == 201
    overlap = post_event(client, user, **lunch("14:30", "14:45", "Звонок"))
    assert overlap.status_code == 409 and "пересекается с событием «Обед»" in overlap.json()["detail"]

    # Выходит за границы блока
    outside = post_event(client, user, **lunch("17:00", "19:00", "Встреча"))
    assert outside.status_code == 409
    assert "выходит за границы блока «Работа»" in outside.json()["detail"]


def test_containers_cannot_overlap_each_other(client):
    user = register_and_login(client, "two@example.com")
    make_event(client, user, is_container=True)
    response = post_event(
        client, user, title="Учёба", is_container=True,
        start_at="2026-10-26T17:00:00+00:00", end_at="2026-10-26T20:00:00+00:00",
    )
    assert response.status_code == 409
    assert "Блок «Учёба» пересекается с блоком «Работа»" in response.json()["detail"]
    # Контейнер внутри контейнера тоже нельзя
    inner = post_event(
        client, user, title="Совещания", is_container=True,
        start_at="2026-10-26T10:00:00+00:00", end_at="2026-10-26T12:00:00+00:00",
    )
    assert inner.status_code == 409


def test_new_container_must_fully_cover_existing_events(client):
    user = register_and_login(client, "cover@example.com")
    make_event(client, user, **lunch("14:00", "15:00"))
    # Блок 09–18 целиком накрывает обед — можно
    assert post_event(client, user, is_container=True).status_code == 201

    other = register_and_login(client, "cover2@example.com")
    make_event(client, other, **lunch("17:00", "19:00", "Встреча"))
    partial = post_event(client, other, is_container=True)
    assert partial.status_code == 409
    assert "только частично попадает в блок «Работа»" in partial.json()["detail"]


def test_update_keeps_nesting_rules(client):
    user = register_and_login(client, "upd-nest@example.com")
    work = make_event(client, user, is_container=True)
    meal = make_event(client, user, **lunch("14:00", "15:00"))
    url = f"/users/{user['id']}/schedule-events"

    # Снять отметку контейнера, пока внутри есть обед, нельзя
    assert client.patch(f"{url}/{work['id']}", json={"is_container": False}, headers=user["headers"]).status_code == 409
    # Сократить блок так, что обед выпадет наружу, тоже нельзя
    shorter = client.patch(f"{url}/{work['id']}", json={"end_at": "2026-10-26T14:30:00+00:00"}, headers=user["headers"])
    assert shorter.status_code == 409
    # Подвинуть обед внутри блока можно; со своей старой версией событие не сравнивается
    moved = client.patch(
        f"{url}/{meal['id']}",
        json={"start_at": "2026-10-26T14:30:00+00:00", "end_at": "2026-10-26T15:30:00+00:00"},
        headers=user["headers"],
    )
    assert moved.status_code == 200, moved.text
    assert client.patch(f"{url}/{meal['id']}", json={"is_container": None}, headers=user["headers"]).status_code == 422


def test_series_respects_overlaps_and_can_be_containers(client):
    user = register_and_login(client, "series-nest@example.com")
    url = f"/users/{user['id']}/schedule-events/series"
    body = {
        "event_type": "work", "title": "Работа", "weekdays": [0, 1, 2, 3, 4],
        "start_time": "09:00", "end_time": "18:00", "from_date": "2026-10-26", "weeks": 1,
        "is_container": True,
    }
    created = client.post(url, json=body, headers=user["headers"])
    assert created.status_code == 201, created.text
    assert all(event["is_container"] for event in created.json()["events"])

    # Серия обедов внутри блоков работы
    meals = {**body, "event_type": "meal", "title": "Обед", "start_time": "13:00", "end_time": "14:00", "is_container": False}
    assert client.post(url, json=meals, headers=user["headers"]).status_code == 201
    # Вторая серия пересекается с обедами — не создаётся ни одного события
    again = client.post(url, json={**meals, "title": "Перекус", "start_time": "13:30", "end_time": "13:45"}, headers=user["headers"])
    assert again.status_code == 409
    week = client.get(f"/users/{user['id']}/schedule/week", params={"start": "2026-10-26"}, headers=user["headers"]).json()
    assert [item["title"] for item in week["items"]].count("Перекус") == 0
    assert week["conflicts"] == []
