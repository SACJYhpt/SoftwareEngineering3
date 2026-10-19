from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import jwt
import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import Event, Registration, User
from app.security import issue_token
from app.services import register, utc_now


def add_event(app, **overrides):
    now = utc_now()
    values = dict(unit_id=1, owner_id=3, name="測試活動", category="講座", location="海大", description="測試", contact_information="events@test.invalid",
                  starts_at=now + timedelta(days=3), ends_at=now + timedelta(days=3, hours=1),
                  registration_opens_at=now - timedelta(days=1), registration_closes_at=now + timedelta(days=1), capacity=20)
    values.update(overrides)
    with app.state.sessions.begin() as db:
        event = Event(**values)
        db.add(event)
        db.flush()
        return event.id


def test_login_and_generic_failure(client):
    result = client.post("/auth/login", json={"email": " MEMBER@test.invalid ", "password": "TestingOnly!2026"})
    assert result.status_code == 200
    token = result.json()["access_token"]
    assert client.get("/auth/me", headers={"Authorization": "Bearer " + token}).json()["id"] == 1
    for email in ("member@test.invalid", "missing@test.invalid"):
        error = client.post("/auth/login", json={"email": email, "password": "wrong"})
        assert error.status_code == 401
        assert error.json() == {"detail": {"code": "INVALID_CREDENTIALS", "message": "帳號或密碼錯誤"}}


def test_guest_invalid_token_and_expired_token(application, client):
    event_id = add_event(application)
    path = f"/events/{event_id}/registrations"
    assert client.post(path).status_code == 401
    assert client.post(path, headers={"Authorization": "Bearer forged"}).status_code == 401
    token = jwt.encode(dict(sub="1", iat=1, exp=2, iss="ntou-events", aud="ntou-events-api"),
                       application.state.settings.jwt_secret, algorithm="HS256")
    assert client.post(path, headers={"Authorization": "Bearer " + token}).status_code == 401


def test_success_duplicate_and_personal_status(application, client, headers):
    event_id = add_event(application)
    path = f"/events/{event_id}/registrations"
    first = client.post(path, headers=headers)
    second = client.post(path, headers=headers)
    assert first.status_code == 201
    assert first.json()["message"] == "報名成功"
    assert first.json()["registered_count"] == 1
    assert second.status_code == 200
    assert second.json()["already_registered"] is True
    assert first.json()["registration_id"] == second.json()["registration_id"]
    view = client.get(f"/events/{event_id}", headers=headers).json()
    assert view["my_registration_status"] == "已報名"
    assert view["can_register"] is False
    assert client.get(f"/events/{event_id}").json()["my_registration_status"] is None


@pytest.mark.parametrize("offsets,message", [((1, 2), "報名尚未開始"), ((-2, -1), "報名已截止")])
def test_outside_registration_period(application, client, headers, offsets, message):
    now = utc_now()
    event_id = add_event(application, registration_opens_at=now + timedelta(days=offsets[0]),
                         registration_closes_at=now + timedelta(days=offsets[1]))
    response = client.post(f"/events/{event_id}/registrations", headers=headers)
    assert response.status_code == 409
    assert response.json()["detail"]["message"] == message


def test_exact_open_and_close_boundaries(application, monkeypatch):
    now = utc_now()
    event_id = add_event(application, registration_opens_at=now, registration_closes_at=now + timedelta(hours=1))
    monkeypatch.setattr("app.services.utc_now", lambda: now)
    assert register(application.state.sessions, event_id, 1)["message"] == "報名成功"
    monkeypatch.setattr("app.services.utc_now", lambda: now + timedelta(hours=1))
    with pytest.raises(HTTPException) as error:
        register(application.state.sessions, event_id, 2)
    assert error.value.detail["code"] == "REGISTRATION_CLOSED"


def test_full_and_unlimited(application, client, headers):
    limited = add_event(application, capacity=1)
    assert client.post(f"/events/{limited}/registrations", headers=headers).status_code == 201
    other = {"Authorization": "Bearer " + issue_token(2, application.state.settings)}
    response = client.post(f"/events/{limited}/registrations", headers=other)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "EVENT_FULL"
    unlimited = add_event(application, capacity=None)
    for auth in (headers, other):
        assert client.post(f"/events/{unlimited}/registrations", headers=auth).status_code == 201
    assert client.get(f"/events/{unlimited}").json()["registered_count"] == 2


def test_cancelled_missing_and_private(application, client, headers):
    cancelled = add_event(application, is_cancelled=True)
    assert client.post(f"/events/{cancelled}/registrations", headers=headers).json()["detail"]["code"] == "EVENT_CANCELLED"
    private = add_event(application, is_public=False)
    assert client.post(f"/events/{private}/registrations", headers=headers).status_code == 404
    assert client.get(f"/events/{private}").status_code == 404
    assert client.post("/events/999/registrations", headers=headers).status_code == 404


@pytest.mark.parametrize("user_id", [3, 4])
def test_manager_and_admin_can_register(application, client, user_id):
    # PROVISIONAL: manager/admin retain general-user abilities. This event is in
    # a unit neither test account manages, and neither account is its creator.
    event_id = add_event(application, unit_id=3, owner_id=5, capacity=1)
    auth = {"Authorization": "Bearer " + issue_token(user_id, application.state.settings)}
    assert client.get(f"/events/{event_id}", headers=auth).json()["can_register"] is True
    result = client.post(f"/events/{event_id}/registrations", headers=auth)
    assert result.status_code == 201
    assert result.json()["registered_count"] == 1
    assert client.get(f"/events/{event_id}", headers=auth).json()["can_register"] is False
    repeated = client.post(f"/events/{event_id}/registrations", headers=auth)
    assert repeated.status_code == 200
    assert repeated.json()["registration_id"] == result.json()["registration_id"]


@pytest.mark.parametrize("user_id", [3, 4])
def test_manager_and_admin_still_obey_registration_rules(application, client, headers, user_id):
    auth = {"Authorization": "Bearer " + issue_token(user_id, application.state.settings)}
    full_id = add_event(application, capacity=1)
    assert client.post(f"/events/{full_id}/registrations", headers=headers).status_code == 201
    full = client.post(f"/events/{full_id}/registrations", headers=auth)
    assert full.status_code == 409
    assert full.json()["detail"]["code"] == "EVENT_FULL"
    assert client.get(f"/events/{full_id}", headers=auth).json()["can_register"] is False
    future_id = add_event(application, registration_opens_at=utc_now() + timedelta(hours=1))
    future = client.post(f"/events/{future_id}/registrations", headers=auth)
    assert future.status_code == 409
    assert future.json()["detail"]["code"] == "REGISTRATION_NOT_OPEN"


def test_inactive_account_and_no_plaintext_password(application, client, headers):
    with application.state.sessions.begin() as db:
        user = db.get(User, 1)
        assert user.password_hash.startswith("$argon2id$")
        assert user.password_hash != "TestingOnly!2026"
        user.is_active = False
    assert client.get("/auth/me", headers=headers).status_code == 401
    assert client.post("/auth/login", json={"email": "member@test.invalid", "password": "TestingOnly!2026"}).status_code == 401


def test_listing_visibility_order_and_utc(application, client):
    first = add_event(application, starts_at=utc_now() + timedelta(days=2))
    second = add_event(application)
    add_event(application, is_cancelled=True)
    add_event(application, is_public=False)
    now = utc_now()
    add_event(application, starts_at=now - timedelta(days=1), ends_at=now - timedelta(hours=1),
              registration_opens_at=now - timedelta(days=3), registration_closes_at=now - timedelta(days=2))
    response = client.get("/events")
    assert [item["id"] for item in response.json()] == [first, second]
    assert response.json()[0]["starts_at"].endswith("Z")


def test_parallel_repeated_requests_create_one_record(application):
    event_id = add_event(application, capacity=1)
    with ThreadPoolExecutor(max_workers=16) as executor:
        results = list(executor.map(lambda _: register(application.state.sessions, event_id, 1), range(40)))
    assert sum(not item["already_registered"] for item in results) == 1
    assert len({item["registration_id"] for item in results}) == 1


def test_1000_attempts_do_not_exceed_100_seats(application):
    event_id = add_event(application, capacity=100)
    with application.state.sessions.begin() as db:
        hashed = db.get(User, 1).password_hash
        db.add_all([User(id=i, email=f"user{i}@test.invalid", name=f"User {i}", password_hash=hashed)
                    for i in range(10, 1010)])

    def attempt(user_id):
        try:
            return register(application.state.sessions, event_id, user_id)
        except HTTPException as error:
            assert error.status_code == 409 and error.detail["code"] == "EVENT_FULL"
            return None

    with ThreadPoolExecutor(max_workers=32) as executor:
        results = list(executor.map(attempt, range(10, 1010)))
    assert sum(item is not None for item in results) == 100
    with application.state.sessions() as db:
        assert db.scalar(select(func.count(Registration.id)).where(Registration.event_id == event_id)) == 100


def test_http_parallel_last_seat(application, client):
    event_id = add_event(application, capacity=1)
    def attempt(user_id):
        auth = {"Authorization": "Bearer " + issue_token(user_id, application.state.settings)}
        return client.post(f"/events/{event_id}/registrations", headers=auth).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, [1, 2]))
    assert sorted(results) == [201, 409]


def test_database_itself_rejects_duplicate_pair(application):
    event_id = add_event(application)
    register(application.state.sessions, event_id, 1)
    with pytest.raises(IntegrityError):
        with application.state.sessions.begin() as db:
            db.add(Registration(user_id=1, event_id=event_id, registered_at=utc_now()))
