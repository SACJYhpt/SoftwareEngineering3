"""SRD MVP acceptance: one test per 測試方法 item that the backend can verify.

Test names carry the story id (ER-US-xxx) or requirement id so each SRD item is traceable.
UI-only items (button states, form field marking, redirects in the browser) are checked by
hand following the root README; performance (NFR-01-02) by scripts/load_test_mvp.py.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.models import Event, Registration, User
from app.security import issue_token

PASSWORD = "TestingOnly!2026"
TW = timezone(timedelta(hours=8))


@pytest.fixture
def clock(monkeypatch):
    state = {"now": datetime(2030, 1, 10, 0, 0)}
    monkeypatch.setattr("app.services.utc_now", lambda: state["now"])
    return state


def auth(application, user_id):
    return {"Authorization": "Bearer " + issue_token(user_id, application.state.settings)}


def payload(clock, **overrides):
    base = clock["now"].replace(tzinfo=timezone.utc)
    def iso(delta):
        return (base + delta).astimezone(TW).isoformat()
    values = dict(unit_id=1, name="驗收活動", type="講座", description="說明", location="海大",
                  contact_information="窗口 events@test.invalid", capacity=2,
                  start_time=iso(timedelta(days=2)), end_time=iso(timedelta(days=2, hours=2)),
                  registration_start=iso(timedelta(hours=-1)), registration_deadline=iso(timedelta(days=1)))
    values.update(overrides)
    return values


def create(client, application, clock, **overrides):
    response = client.post("/events", json=payload(clock, **overrides), headers=auth(application, 3))
    assert response.status_code == 201, response.text
    return response.json()


def registrations(application, event_id):
    with application.state.sessions() as db:
        return db.scalar(select(func.count(Registration.id)).where(Registration.event_id == event_id))


def login(client, email="member@test.invalid", password=PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


# ---- ER-US-A04 Log in ---------------------------------------------------------

def test_a04_correct_credentials_log_in(client):
    response = login(client)
    assert response.status_code == 200
    assert response.json()["user"]["email"] == "member@test.invalid"


@pytest.mark.parametrize("email,password", [("member@test.invalid", "wrong"), ("nobody@test.invalid", PASSWORD)])
def test_a04_wrong_account_or_password_show_same_message(client, email, password):
    response = login(client, email, password)
    assert response.status_code == 401
    assert response.json()["detail"]["message"] == "帳號或密碼錯誤"


def test_a04_five_wrong_passwords_block_correct_password_for_ten_minutes(client, clock):
    for _ in range(5):
        login(client, password="wrong")
    for minutes in (0, 5, 9.99):
        clock["now"] = datetime(2030, 1, 10, 0, 0) + timedelta(minutes=minutes)
        assert login(client).status_code == 429
    clock["now"] = datetime(2030, 1, 10, 0, 10)
    assert login(client).status_code == 200


# ---- ER-US-A05 Log out ----------------------------------------------------------

def test_a05_token_from_before_logout_is_rejected(client):
    headers = {"Authorization": "Bearer " + login(client).json()["access_token"]}
    assert client.post("/auth/logout", headers=headers).status_code == 204
    assert client.get("/auth/me", headers=headers).status_code == 401


# ---- ER-US-C01 Create event / FR-01-06 / NFR-05-03 ------------------------------

def test_c01_created_event_appears_on_home_page(client, application, clock):
    event = create(client, application, clock)
    assert [item["id"] for item in client.get("/events").json()] == [event["id"]]


def test_c01_member_cannot_create_via_api(client, application, clock):
    response = client.post("/events", json=payload(clock), headers=auth(application, 1))
    assert response.status_code == 403
    assert response.json()["detail"]["message"] == "權限不足"


def test_c01_member_has_no_managed_units_so_ui_hides_entry(client, application):
    # The UI shows 建立活動 only when managed_units is non-empty.
    assert client.get("/auth/me", headers=auth(application, 1)).json()["managed_units"] == []


# ---- ER-US-C02 Set capacity -----------------------------------------------------

@pytest.mark.parametrize("capacity", [0, -3, 1.5, "十", "5"])
def test_c02_invalid_capacity_rejected(client, application, clock, capacity):
    assert client.post("/events", json=payload(clock, capacity=capacity), headers=auth(application, 3)).status_code == 422


def test_c02_blank_capacity_means_unlimited_on_list_and_detail(client, application, clock):
    event = create(client, application, clock, capacity=None)
    assert client.get("/events").json()[0]["capacity"] is None
    assert client.get(f"/events/{event['id']}").json()["capacity"] is None  # UI shows 「不限」


# ---- ER-US-C03 Validate event form ----------------------------------------------

@pytest.mark.parametrize("field", ["name", "type", "description", "location", "contact_information", "unit_id",
                                   "start_time", "end_time", "registration_start", "registration_deadline"])
def test_c03_missing_required_field_rejected_and_named(client, application, clock, field):
    body = payload(clock)
    del body[field]
    response = client.post("/events", json=body, headers=auth(application, 3))
    assert response.status_code == 422
    assert any(error["loc"][-1] == field for error in response.json()["detail"])


def test_c03_end_before_start_rejected(client, application, clock):
    body = payload(clock)
    body["end_time"] = (datetime.fromisoformat(body["start_time"]) - timedelta(minutes=1)).isoformat()
    assert client.post("/events", json=body, headers=auth(application, 3)).status_code == 422


def test_c03_deadline_after_start_rejected(client, application, clock):
    body = payload(clock)
    body["registration_deadline"] = (datetime.fromisoformat(body["start_time"]) + timedelta(minutes=1)).isoformat()
    assert client.post("/events", json=body, headers=auth(application, 3)).status_code == 422


def test_c03_registration_start_after_deadline_rejected(client, application, clock):
    body = payload(clock)
    body["registration_start"] = (datetime.fromisoformat(body["registration_deadline"]) + timedelta(minutes=1)).isoformat()
    assert client.post("/events", json=body, headers=auth(application, 3)).status_code == 422


def test_c03_start_in_past_rejected(client, application, clock):
    body = payload(clock, start_time=(clock["now"].replace(tzinfo=timezone.utc) - timedelta(minutes=1)).isoformat())
    response = client.post("/events", json=body, headers=auth(application, 3))
    assert response.status_code == 422


def test_c03_bypassing_frontend_still_rejected(client, application, clock):
    # Raw API call with every rule broken at once: nothing is stored.
    body = payload(clock, name="", capacity=0, end_time=payload(clock)["registration_start"])
    assert client.post("/events", json=body, headers=auth(application, 3)).status_code == 422
    assert client.get("/events").json() == []


# ---- ER-US-C12 Create event under unit ------------------------------------------

def test_c12_unit_choices_are_only_own_units(client, application):
    assert [u["id"] for u in client.get("/auth/me", headers=auth(application, 3)).json()["managed_units"]] == [1, 2]
    assert [u["id"] for u in client.get("/auth/me", headers=auth(application, 5)).json()["managed_units"]] == [1]


def test_c12_other_unit_via_api_is_403(client, application, clock):
    response = client.post("/events", json=payload(clock, unit_id=3), headers=auth(application, 3))
    assert response.status_code == 403


# ---- ER-US-B01 Browse events ----------------------------------------------------

def test_b01_guest_sees_list_sorted_by_start(client, application, clock):
    later = create(client, application, clock, name="較晚")
    body = payload(clock, name="較早")
    body["start_time"] = (datetime.fromisoformat(body["start_time"]) - timedelta(hours=3)).isoformat()
    earlier = client.post("/events", json=body, headers=auth(application, 3)).json()
    listed = client.get("/events").json()
    assert [item["id"] for item in listed] == [earlier["id"], later["id"]]
    assert {"name", "start_time", "location", "unit", "registration_count", "capacity"} <= listed[0].keys()


def test_b01_list_is_paged_in_start_order_with_total(client, application, clock):
    base = datetime.fromisoformat(payload(clock)["start_time"])
    for i in range(35):
        body = payload(clock, name=f"活動 {i:02d}", start_time=(base + timedelta(minutes=i)).isoformat())
        assert client.post("/events", json=body, headers=auth(application, 3)).status_code == 201
    first = client.get("/events")
    second = client.get("/events", params={"offset": 30})
    assert first.headers["X-Total-Count"] == second.headers["X-Total-Count"] == "35"
    names = [item["name"] for item in first.json() + second.json()]
    assert names == [f"活動 {i:02d}" for i in range(35)]
    assert client.get("/events", params={"limit": 101}).status_code == 422


def test_b01_ended_and_started_events_not_listed(client, application, clock):
    event = create(client, application, clock)
    clock["now"] += timedelta(days=2)  # started
    assert client.get("/events").json() == []
    clock["now"] += timedelta(days=1)  # ended
    assert client.get("/events").json() == []
    assert client.get(f"/events/{event['id']}").status_code == 200


# ---- ER-US-B02 View event details / ER-US-B09 -----------------------------------

def test_b02_b09_guest_sees_details_and_contact_without_login(client, application, clock):
    event = create(client, application, clock)
    detail = client.get(f"/events/{event['id']}")
    assert detail.status_code == 200
    data = detail.json()
    for key in ("name", "description", "location", "start_time", "end_time", "registration_start",
                "registration_deadline", "capacity", "registration_count", "status"):
        assert data[key] is not None
    assert data["unit"]["name"] == "測試系所"
    assert data["contact_information"] == "窗口 events@test.invalid"
    assert data["my_registration_status"] is None


@pytest.mark.parametrize("offset,status", [
    (timedelta(hours=-2), "報名未開始"), (timedelta(0), "開放中"), (timedelta(days=1), "已截止"),
    (timedelta(days=2), "進行中"), (timedelta(days=2, hours=2), "已結束"),
])
def test_b02_status_at_each_point_in_time(client, application, clock, offset, status):
    event = create(client, application, clock)
    clock["now"] = datetime(2030, 1, 10, 0, 0) + offset
    assert client.get(f"/events/{event['id']}").json()["status"] == status


def test_b02_full_status(client, application, clock):
    event = create(client, application, clock, capacity=1)
    client.post(f"/events/{event['id']}/registrations", headers=auth(application, 1))
    assert client.get(f"/events/{event['id']}").json()["status"] == "已額滿"


# ---- ER-US-B03 View my registration status --------------------------------------

def test_b03_registered_user_sees_registered(client, application, clock):
    event = create(client, application, clock)
    assert client.get(f"/events/{event['id']}", headers=auth(application, 1)).json()["my_registration_status"] == "未報名"
    client.post(f"/events/{event['id']}/registrations", headers=auth(application, 1))
    assert client.get(f"/events/{event['id']}", headers=auth(application, 1)).json()["my_registration_status"] == "已報名"
    assert client.get(f"/events/{event['id']}", headers=auth(application, 2)).json()["my_registration_status"] == "未報名"


# ---- ER-US-D01 Register and receive a clear result / FR-04-xx -------------------

def test_d01_success_message_count_plus_one(client, application, clock):
    event = create(client, application, clock)
    response = client.post(f"/events/{event['id']}/registrations", headers=auth(application, 1))
    assert response.status_code == 201
    assert response.json()["message"] == "報名成功"
    detail = client.get(f"/events/{event['id']}", headers=auth(application, 1)).json()
    assert detail["registration_count"] == 1
    assert detail["can_register"] is False  # UI: button becomes 「已報名」 and disabled


@pytest.mark.parametrize("now,code", [(timedelta(hours=-2), "REGISTRATION_NOT_OPEN"), (timedelta(days=1), "REGISTRATION_CLOSED")])
def test_d01_outside_period_rejected_count_unchanged(client, application, clock, now, code):
    event = create(client, application, clock)
    clock["now"] = datetime(2030, 1, 10, 0, 0) + now
    view = client.get(f"/events/{event['id']}", headers=auth(application, 1)).json()
    assert view["can_register"] is False and view["registration_start"] and view["registration_deadline"]
    response = client.post(f"/events/{event['id']}/registrations", headers=auth(application, 1))
    assert response.status_code == 409 and response.json()["detail"]["code"] == code
    assert registrations(application, event["id"]) == 0


def test_d01_exactly_at_deadline_is_closed(client, application, clock):
    event = create(client, application, clock)
    clock["now"] = datetime(2030, 1, 11, 0, 0)  # registration_deadline exactly
    response = client.post(f"/events/{event['id']}/registrations", headers=auth(application, 1))
    assert response.json()["detail"] == {"code": "REGISTRATION_CLOSED", "message": "報名已截止"}
    assert registrations(application, event["id"]) == 0


def test_d01_resubmits_create_one_record(client, application, clock):
    event = create(client, application, clock)
    codes = [client.post(f"/events/{event['id']}/registrations", headers=auth(application, 1)).status_code
             for _ in range(5)]
    assert codes == [201, 200, 200, 200, 200]
    assert registrations(application, event["id"]) == 1


def test_d01_full_rejected_with_reason_count_unchanged(client, application, clock):
    event = create(client, application, clock, capacity=1)
    client.post(f"/events/{event['id']}/registrations", headers=auth(application, 1))
    response = client.post(f"/events/{event['id']}/registrations", headers=auth(application, 2))
    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "EVENT_FULL", "message": "名額已滿"}
    assert registrations(application, event["id"]) == 1


def test_d01_guest_must_log_in(client, application, clock):
    event = create(client, application, clock)
    assert client.post(f"/events/{event['id']}/registrations").json()["detail"]["code"] == "AUTH_REQUIRED"


# ---- NFR-05-02 hashed passwords --------------------------------------------------

def test_nfr0502_no_plaintext_passwords(application):
    with application.state.sessions() as db:
        for user in db.scalars(select(User)):
            assert PASSWORD not in user.password_hash
            assert user.password_hash.startswith("$argon2id$")
