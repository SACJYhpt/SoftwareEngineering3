"""MVP additions: logout (ER-US-A05), login lockout (NFR-05-04), event type list (ER-US-C01)."""
from datetime import datetime, timedelta, timezone

import pytest

PASSWORD = "TestingOnly!2026"


@pytest.fixture
def clock(monkeypatch):
    state = {"now": datetime(2030, 1, 10, 0, 0)}
    monkeypatch.setattr("app.services.utc_now", lambda: state["now"])
    return state


def login(client, email="member@test.invalid", password=PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def test_logout_revokes_token_server_side(client):
    token = login(client).json()["access_token"]
    auth = {"Authorization": "Bearer " + token}
    assert client.get("/auth/me", headers=auth).status_code == 200
    assert client.post("/auth/logout", headers=auth).status_code == 204
    # The copied token is rejected after logout, both for personal and public calls.
    for response in (client.get("/auth/me", headers=auth), client.post("/auth/logout", headers=auth),
                     client.get("/events", headers=auth)):
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "INVALID_TOKEN"


def test_logout_only_revokes_that_session(client):
    first = {"Authorization": "Bearer " + login(client).json()["access_token"]}
    second = {"Authorization": "Bearer " + login(client).json()["access_token"]}
    assert client.post("/auth/logout", headers=first).status_code == 204
    assert client.get("/auth/me", headers=second).status_code == 200


def test_logout_requires_login(client):
    assert client.post("/auth/logout").status_code == 401


def test_five_failures_lock_for_ten_minutes(client, clock):
    for _ in range(4):
        assert login(client, password="wrong").status_code == 401
    assert login(client, password="wrong").status_code == 401
    # Fifth failure locks the account: even the right password is refused.
    locked = login(client)
    assert locked.status_code == 429
    assert locked.json()["detail"]["code"] == "LOGIN_LOCKED"
    assert locked.json()["detail"]["retry_after_minutes"] == 10
    clock["now"] += timedelta(minutes=9, seconds=59)
    assert login(client).status_code == 429
    clock["now"] += timedelta(seconds=1)
    assert login(client).status_code == 200


def test_success_resets_failure_count(client, clock):
    for _ in range(4):
        login(client, password="wrong")
    assert login(client).status_code == 200
    for _ in range(4):
        assert login(client, password="wrong").status_code == 401
    assert login(client).status_code == 200


def test_unregistered_email_is_locked_the_same_way(client, clock):
    for _ in range(5):
        assert login(client, email="nobody@test.invalid", password="x").status_code == 401
    response = login(client, email="NOBODY@test.invalid", password="x")
    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "LOGIN_LOCKED"


def test_lockout_is_per_email(client, clock):
    for _ in range(5):
        login(client, password="wrong")
    assert login(client).status_code == 429
    assert login(client, email="other@test.invalid").status_code == 200


def test_me_includes_profile_fields(client):
    user = login(client).json()["user"]
    assert {"identity", "department", "grade", "managed_units"} <= user.keys()


def test_event_types_list_only_active(client):
    assert [item["name"] for item in client.get("/event-types").json()] == ["講座", "參訪"]


@pytest.mark.parametrize("value", ["不存在的類型", "停用類型"])
def test_create_rejects_unknown_or_inactive_type(client, application, value):
    from app.security import issue_token

    now = datetime.now(timezone.utc)
    payload = dict(name="活動", type=value, description="說明", location="海大", contact_information="x@test.invalid",
                   unit_id=1, start_time=(now + timedelta(days=3)).isoformat(),
                   end_time=(now + timedelta(days=3, hours=1)).isoformat(),
                   registration_start=(now + timedelta(hours=1)).isoformat(),
                   registration_deadline=(now + timedelta(days=1)).isoformat())
    auth = {"Authorization": "Bearer " + issue_token(3, application.state.settings)}
    response = client.post("/events", json=payload, headers=auth)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "EVENT_TYPE_INVALID"
