"""Fixes made while integrating the R2 frontend: list paging, readable change mail,
edit error codes, and unit grants in the admin user search."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import OutgoingEmail
from app.security import issue_token

TW = timezone(timedelta(hours=8))


@pytest.fixture
def clock(monkeypatch):
    now = datetime(2030, 1, 10, 0, 0)
    monkeypatch.setattr("app.services.utc_now", lambda: now)
    return now


def auth(application, user_id):
    return {"Authorization": "Bearer " + issue_token(user_id, application.state.settings)}


def create(client, application, clock, **overrides):
    base = clock.replace(tzinfo=timezone.utc)
    body = dict(unit_id=1, name="活動", type="講座", description="說明", location="海大",
                contact_information="x@test.invalid", capacity=10,
                start_time=(base + timedelta(days=2)).astimezone(TW).isoformat(),
                end_time=(base + timedelta(days=2, hours=2)).astimezone(TW).isoformat(),
                registration_start=(base - timedelta(hours=1)).astimezone(TW).isoformat(),
                registration_deadline=(base + timedelta(days=1)).astimezone(TW).isoformat())
    body.update(overrides)
    response = client.post("/events", json=body, headers=auth(application, 3))
    assert response.status_code == 201, response.text
    return response.json()


def test_list_is_paged_with_total_and_card_fields_only(client, application, clock):
    for i in range(35):
        create(client, application, clock, name=f"活動 {i:02d}",
               start_time=(clock.replace(tzinfo=timezone.utc) + timedelta(days=2, minutes=i)).isoformat())
    first = client.get("/events")
    rest = client.get("/events", params={"offset": 30})
    assert first.headers["X-Total-Count"] == rest.headers["X-Total-Count"] == "35"
    assert [e["name"] for e in first.json() + rest.json()] == [f"活動 {i:02d}" for i in range(35)]
    assert "description" not in first.json()[0]
    filtered = client.get("/events", params={"q": "活動 3", "limit": 2})
    assert filtered.headers["X-Total-Count"] == "5" and len(filtered.json()) == 2
    assert client.get("/events", params={"limit": 101}).status_code == 422


def test_change_mail_uses_chinese_labels_and_taiwan_time(client, application, clock):
    event = create(client, application, clock)
    client.post(f"/events/{event['id']}/registrations", headers=auth(application, 1))
    new_start = (clock.replace(tzinfo=timezone.utc) + timedelta(days=3)).astimezone(TW)
    response = client.patch(f"/events/{event['id']}", headers=auth(application, 3), json={
        "start_time": new_start.isoformat(), "end_time": (new_start + timedelta(hours=2)).isoformat(), "location": "INS 203"})
    assert response.status_code == 200, response.text
    with application.state.sessions() as db:
        body = db.scalar(select(OutgoingEmail.body).order_by(OutgoingEmail.id.desc()).limit(1))
    assert "開始時間：2030/01/12 08:00 → 2030/01/13 08:00" in body
    assert "地點：海大 → INS 203" in body
    assert "start_time" not in body


def test_edit_field_error_is_not_reported_as_time_order(client, application, clock):
    event = create(client, application, clock)
    blank = client.patch(f"/events/{event['id']}", headers=auth(application, 3), json={"capacity": 0})
    assert blank.status_code == 422
    order = client.patch(f"/events/{event['id']}", headers=auth(application, 3),
                         json={"end_time": (clock.replace(tzinfo=timezone.utc) + timedelta(days=1)).isoformat()})
    assert order.json()["detail"]["code"] == "EVENT_TIME_INVALID"


def test_admin_user_search_lists_unit_grants(client, application):
    data = client.get("/admin/users", params={"q": "manager@test"}, headers=auth(application, 4)).json()
    manager = next(item for item in data["items"] if item["email"] == "manager@test.invalid")
    assert [unit["id"] for unit in manager["managed_units"]] == [1, 2]


@pytest.mark.parametrize("field,reference", [("end_time", "start_time"), ("registration_start", "registration_deadline")])
def test_equal_times_are_rejected_on_create_and_edit(client, application, clock, field, reference):
    """SRD C03 (strict): an event must last some time and registration must stay open for some time."""
    event = create(client, application, clock)
    response = client.patch(f"/events/{event['id']}", headers=auth(application, 3), json={field: event[reference]})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "EVENT_TIME_INVALID"
    base = clock.replace(tzinfo=timezone.utc)
    same = (base + timedelta(days=2)).astimezone(TW).isoformat()
    body = dict(unit_id=1, name="活動", type="講座", description="說明", location="海大", contact_information="x",
                start_time=same, end_time=(base + timedelta(days=2, hours=1)).astimezone(TW).isoformat(),
                registration_start=(base - timedelta(hours=1)).astimezone(TW).isoformat(),
                registration_deadline=(base + timedelta(days=1)).astimezone(TW).isoformat())
    body[field] = body[reference]
    assert client.post("/events", json=body, headers=auth(application, 3)).status_code == 422


def test_registration_may_close_exactly_when_event_starts(client, application, clock):
    event = create(client, application, clock)
    response = client.patch(f"/events/{event['id']}", headers=auth(application, 3),
                            json={"registration_deadline": event["start_time"]})
    assert response.status_code == 200
