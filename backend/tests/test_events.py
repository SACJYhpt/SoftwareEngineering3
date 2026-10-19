"""MVP create -> browse -> register API contract and validation boundaries."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.models import Event, Registration, UnitManager, User
from app.security import issue_token


@pytest.fixture
def clock(monkeypatch):
    now = datetime(2030, 1, 10, 0, 0)
    monkeypatch.setattr("app.services.utc_now", lambda: now)
    return now


@pytest.fixture
def event_payload(clock):
    def iso(delta):
        return (clock.replace(tzinfo=timezone.utc) + delta).astimezone(timezone(timedelta(hours=8))).isoformat()
    return dict(name="校園講座", type="講座", description="一起學習", location="海大",
                contact_information="events@example.edu.tw", unit_id=1, capacity=20,
                start_time=iso(timedelta(days=2)), end_time=iso(timedelta(days=2, hours=2)),
                registration_start=iso(timedelta(hours=-1)), registration_deadline=iso(timedelta(days=1)))


@pytest.fixture
def manager_headers(application):
    return {"Authorization": "Bearer " + issue_token(3, application.state.settings)}


def event_count(application):
    with application.state.sessions() as db:
        return db.scalar(select(func.count(Event.id)))


@pytest.mark.parametrize("unit_id", [1, 2])
def test_create_uses_assigned_unit_and_authenticated_creator(application, client, manager_headers, event_payload, unit_id):
    event_payload["unit_id"] = unit_id
    event_payload["name"] = "  校園講座  "
    response = client.post("/events", json=event_payload, headers=manager_headers)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["unit_id"] == unit_id == data["unit"]["id"]
    assert data["name"] == "校園講座"
    assert data["contact_information"] == event_payload["contact_information"]
    assert data["registration_count"] == data["registered_count"] == 0
    assert data["start_time"] == data["starts_at"] == "2030-01-12T00:00:00Z"
    assert data["type"] == data["category"] == "講座"
    with application.state.sessions() as db:
        event = db.get(Event, data["id"])
        assert event.owner_id == 3
        assert event.unit_id == unit_id
    assert client.get("/events").json()[0]["id"] == data["id"]
    public = client.get(f"/events/{data['id']}").json()
    assert public["my_registration_status"] is None
    assert public["can_register"] is False


def test_same_unit_manager_can_create_and_me_lists_grants(application, client, event_payload):
    auth = {"Authorization": "Bearer " + issue_token(5, application.state.settings)}
    context = client.get("/auth/me", headers=auth).json()
    assert context["managed_units"] == [{"id": 1, "name": "測試系所"}]
    result = client.post("/events", json=event_payload, headers=auth)
    assert result.status_code == 201
    with application.state.sessions() as db:
        assert db.get(Event, result.json()["id"]).owner_id == 5


def test_create_requires_login_and_unit_grant(application, client, headers, manager_headers, event_payload):
    assert client.post("/events", json=event_payload).status_code == 401
    unauthorized = client.post("/events", json=event_payload, headers=headers)
    assert unauthorized.status_code == 403
    assert unauthorized.json()["detail"]["code"] == "UNIT_FORBIDDEN"
    event_payload["unit_id"] = 3
    assert client.post("/events", json=event_payload, headers=manager_headers).status_code == 403
    assert event_count(application) == 0


def test_admin_needs_explicit_unit_grant(application, client, event_payload):
    auth = {"Authorization": "Bearer " + issue_token(4, application.state.settings)}
    assert client.post("/events", json=event_payload, headers=auth).status_code == 403
    with application.state.sessions.begin() as db:
        db.add(UnitManager(user_id=4, unit_id=1))
    assert client.post("/events", json=event_payload, headers=auth).status_code == 201


def test_missing_unit(application, client, manager_headers, event_payload):
    event_payload["unit_id"] = 999
    response = client.post("/events", json=event_payload, headers=manager_headers)
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "UNIT_NOT_FOUND"
    assert event_count(application) == 0


@pytest.mark.parametrize("field", ["name", "type", "description", "location", "contact_information", "unit_id",
                                   "start_time", "end_time", "registration_start", "registration_deadline"])
def test_missing_required_field(application, client, manager_headers, event_payload, field):
    del event_payload[field]
    response = client.post("/events", json=event_payload, headers=manager_headers)
    assert response.status_code == 422
    assert any(error["loc"] == ["body", field] for error in response.json()["detail"])
    assert event_count(application) == 0


@pytest.mark.parametrize("field", ["name", "type", "description", "location", "contact_information"])
def test_blank_required_text(application, client, manager_headers, event_payload, field):
    event_payload[field] = " \n\t "
    assert client.post("/events", json=event_payload, headers=manager_headers).status_code == 422
    assert event_count(application) == 0


@pytest.mark.parametrize("capacity", [0, -1, 1.5, "2", True])
def test_invalid_capacity(application, client, manager_headers, event_payload, capacity):
    event_payload["capacity"] = capacity
    assert client.post("/events", json=event_payload, headers=manager_headers).status_code == 422
    assert event_count(application) == 0


@pytest.mark.parametrize("capacity", [None, 1])
def test_valid_capacity(client, manager_headers, event_payload, capacity):
    event_payload["capacity"] = capacity
    result = client.post("/events", json=event_payload, headers=manager_headers)
    assert result.status_code == 201
    assert result.json()["capacity"] == capacity


@pytest.mark.parametrize("field,reference", [("end_time", "start_time"), ("registration_start", "registration_deadline")])
@pytest.mark.parametrize("offset", [0, -1])
def test_strict_time_order(application, client, manager_headers, event_payload, field, reference, offset):
    event_payload[field] = (datetime.fromisoformat(event_payload[reference]) + timedelta(seconds=offset)).isoformat()
    # Registration start must be earlier; invert the negative offset to test a reversed interval.
    if field == "registration_start" and offset:
        event_payload[field] = (datetime.fromisoformat(event_payload[reference]) + timedelta(seconds=1)).isoformat()
    assert client.post("/events", json=event_payload, headers=manager_headers).status_code == 422
    assert event_count(application) == 0


def test_registration_deadline_cannot_follow_start(application, client, manager_headers, event_payload):
    event_payload["registration_deadline"] = event_payload["end_time"]
    assert client.post("/events", json=event_payload, headers=manager_headers).status_code == 422
    assert event_count(application) == 0


def test_deadline_may_equal_start(client, manager_headers, event_payload):
    event_payload["registration_deadline"] = event_payload["start_time"]
    assert client.post("/events", json=event_payload, headers=manager_headers).status_code == 201


def test_start_in_past(application, client, manager_headers, event_payload, clock):
    def iso(days):
        return (clock.replace(tzinfo=timezone.utc) + timedelta(days=days)).isoformat()
    event_payload.update(start_time=iso(-1), end_time=iso(1), registration_start=iso(-3), registration_deadline=iso(-2))
    result = client.post("/events", json=event_payload, headers=manager_headers)
    assert result.status_code == 422
    assert result.json()["detail"]["code"] == "EVENT_START_IN_PAST"
    assert event_count(application) == 0


def test_start_at_now_is_allowed(client, manager_headers, event_payload, clock):
    event_payload["start_time"] = clock.replace(tzinfo=timezone.utc).isoformat()
    event_payload["registration_deadline"] = event_payload["start_time"]
    result = client.post("/events", json=event_payload, headers=manager_headers)
    assert result.status_code == 201
    assert result.json()["status"] == "進行中"


def test_naive_time_and_client_owner_are_rejected(client, manager_headers, event_payload):
    event_payload["owner_id"] = 4
    assert client.post("/events", json=event_payload, headers=manager_headers).status_code == 422
    del event_payload["owner_id"]
    event_payload["start_time"] = "2030-01-12T00:00:00"
    assert client.post("/events", json=event_payload, headers=manager_headers).status_code == 422


@pytest.mark.parametrize("seconds,status", [(-3601, "報名未開始"), (-3600, "開放中"), (86399, "開放中"),
    (86400, "已截止"), (172799, "已截止"), (172800, "進行中"), (179999, "進行中"), (180000, "已結束"), (180001, "已結束")])
def test_status_boundaries(client, manager_headers, event_payload, clock, monkeypatch, seconds, status):
    created = client.post("/events", json=event_payload, headers=manager_headers).json()
    monkeypatch.setattr("app.services.utc_now", lambda: clock + timedelta(seconds=seconds))
    detail = client.get(f"/events/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["status"] == status


def test_created_event_full_registration_contract(application, client, manager_headers, headers, event_payload):
    event_payload["capacity"] = 1
    created = client.post("/events", json=event_payload, headers=manager_headers).json()
    path = f"/events/{created['id']}"
    assert client.get(path, headers=headers).json()["my_registration_status"] == "未報名"
    result = client.post(path + "/registrations", headers=headers)
    assert result.status_code == 201
    record = result.json()
    assert record["status"] == "registered"
    assert record["registration_count"] == record["registered_count"] == record["capacity"] == 1
    assert record["event_id"] == created["id"]
    assert record["registered_at"].endswith("Z")
    assert client.get(path, headers=headers).json()["my_registration_status"] == "已報名"
    assert client.get(path).json()["status"] == "已額滿"
    repeated = client.post(path + "/registrations", headers=headers)
    assert repeated.status_code == 200
    assert repeated.json()["registration_id"] == record["registration_id"]


@pytest.mark.parametrize("scenario,code", [("not_open", "REGISTRATION_NOT_OPEN"), ("closed", "REGISTRATION_CLOSED"),
    ("started", "EVENT_STARTED"), ("ended", "EVENT_STARTED"), ("cancelled", "EVENT_CANCELLED"), ("full", "EVENT_FULL")])
def test_failed_registration_does_not_change_count(application, client, manager_headers, headers, event_payload, clock, monkeypatch, scenario, code):
    event_payload["capacity"] = 1
    event_id = client.post("/events", json=event_payload, headers=manager_headers).json()["id"]
    if scenario == "full":
        other = {"Authorization": "Bearer " + issue_token(2, application.state.settings)}
        assert client.post(f"/events/{event_id}/registrations", headers=other).status_code == 201
    elif scenario == "cancelled":
        with application.state.sessions.begin() as db:
            db.get(Event, event_id).is_cancelled = True
    else:
        shift = {"not_open": -3601, "closed": 86400, "started": 172800, "ended": 180000}[scenario]
        monkeypatch.setattr("app.services.utc_now", lambda: clock + timedelta(seconds=shift))
    with application.state.sessions() as db:
        before = db.scalar(select(func.count(Registration.id)))
    result = client.post(f"/events/{event_id}/registrations", headers=headers)
    assert result.status_code == 409
    assert result.json()["detail"]["code"] == code
    with application.state.sessions() as db:
        assert db.scalar(select(func.count(Registration.id))) == before


def test_cancelled_wins_over_ended_and_is_hidden(application, client, manager_headers, event_payload, clock, monkeypatch):
    event_id = client.post("/events", json=event_payload, headers=manager_headers).json()["id"]
    with application.state.sessions.begin() as db:
        db.get(Event, event_id).is_cancelled = True
    assert client.get("/events").json() == []
    monkeypatch.setattr("app.services.utc_now", lambda: clock + timedelta(days=4))
    assert client.get(f"/events/{event_id}").json()["status"] == "已取消"


def test_missing_detail_is_machine_readable(client):
    response = client.get("/events/99999")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "EVENT_NOT_FOUND"


def test_inactive_login_has_generic_error(application, client):
    with application.state.sessions.begin() as db:
        db.get(User, 1).is_active = False
    result = client.post("/auth/login", json={"email": "member@test.invalid", "password": "TestingOnly!2026"})
    assert result.status_code == 401
    assert result.json()["detail"] == {"code": "INVALID_CREDENTIALS", "message": "帳號或密碼錯誤"}
