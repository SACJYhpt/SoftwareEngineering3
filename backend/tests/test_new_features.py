from datetime import timedelta

from app.models import AccountRequest, Event, OutgoingEmail, User
from sqlalchemy import select
import re
from app.security import issue_token
from app.services import utc_now


# Retained teammate scenarios, adapted to the canonical R2 consent contract,
# durable outbox, request throttle, and password-reset endpoints.
def queued_token(application, recipient):
    with application.state.sessions() as db:
        body = db.scalar(select(OutgoingEmail.body).where(OutgoingEmail.recipient == recipient)
                         .order_by(OutgoingEmail.id.desc()).limit(1))
        return re.search(r"#token=([^\s]+)", body).group(1)


def registration_payload(**overrides):
    data = {"email": "newuser@ntou.edu.tw", "name": "新使用者", "identity": "student",
            "department_id": 1, "grade": 2, "password": "abc12345", "consent": True, "privacy_version": 1}
    data.update(overrides)
    return data


def test_registration_requires_school_domain_and_valid_profile(client):
    assert client.post("/auth/register", json=registration_payload(email="abc@gmail.com")).status_code == 422
    assert client.post("/auth/register", json=registration_payload(password="12345678")).status_code == 422
    assert client.post("/auth/register", json=registration_payload(grade=None)).status_code == 422
    # SRD requires grade for students; non-student grade is normalized to null.
    assert client.post("/auth/register", json=registration_payload(email="teacher-new@ntou.edu.tw", identity="teacher", grade=2)).status_code == 201
    response = client.post("/auth/register", json=registration_payload())
    assert response.status_code == 201
    assert client.post("/auth/login", json={"email": "newuser@ntou.edu.tw", "password": "abc12345"}).status_code == 403


def test_email_verify_token_and_resend_invalidates_old(client, application):
    assert client.post("/auth/register", json=registration_payload()).status_code == 201
    old_token = queued_token(application, "newuser@ntou.edu.tw")
    assert client.post("/auth/resend-verification", json={"email": "newuser@ntou.edu.tw"}).status_code == 429
    with application.state.sessions.begin() as db:
        throttle = db.get(AccountRequest, ("newuser@ntou.edu.tw", "verify"))
        throttle.requested_at = utc_now() - timedelta(seconds=61)
    assert client.post("/auth/resend-verification", json={"email": "newuser@ntou.edu.tw"}).status_code == 202
    new_token = queued_token(application, "newuser@ntou.edu.tw")
    assert new_token != old_token
    assert client.post("/auth/verify-email", json={"token": old_token}).status_code == 400
    assert client.post("/auth/verify-email", json={"token": new_token}).status_code == 200
    assert client.post("/auth/verify-email", json={"token": new_token}).status_code == 400
    assert client.post("/auth/login", json={"email": "newuser@ntou.edu.tw", "password": "abc12345"}).status_code == 200


def test_password_reset_is_one_time_and_invalidates_existing_sessions(client, application):
    # Existing fixture user is already verified.
    token1 = issue_token(1, application.state.settings)
    assert client.post("/auth/forgot-password", json={"email": "member@test.invalid"}).status_code == 202
    raw = queued_token(application, "member@test.invalid")
    assert client.get("/auth/me", headers={"Authorization": "Bearer " + token1}).status_code == 200
    payload = {"token": raw, "password": "newpass123"}
    assert client.post("/auth/reset-password", json=payload).status_code == 200
    assert client.get("/auth/me", headers={"Authorization": "Bearer " + token1}).status_code == 401
    assert client.post("/auth/reset-password", json=payload).status_code == 400
    assert client.post("/auth/login", json={"email": "member@test.invalid", "password": "newpass123"}).status_code == 200


def test_password_reset_request_does_not_reveal_account(client, application):
    a = client.post("/auth/forgot-password", json={"email": "member@test.invalid"})
    b = client.post("/auth/forgot-password", json={"email": "nobody@ntou.edu.tw"})
    assert a.status_code == b.status_code == 202
    assert a.json() == b.json()


def test_event_search_and_combined_filters(client, application):
    now = utc_now()
    with application.state.sessions.begin() as db:
        db.add_all([
            Event(unit_id=1, owner_id=3, name="Python 工作坊", category="講座", location="海大",
                  description="學習程式設計", contact_information="x", starts_at=now+timedelta(days=2),
                  ends_at=now+timedelta(days=2,hours=1), registration_opens_at=now-timedelta(days=1),
                  registration_closes_at=now+timedelta(days=1)),
            Event(unit_id=1, owner_id=3, name="音樂活動", category="參訪", location="海大",
                  description="Python 音樂工具", contact_information="x", starts_at=now+timedelta(days=3),
                  ends_at=now+timedelta(days=3,hours=1), registration_opens_at=now-timedelta(days=1),
                  registration_closes_at=now+timedelta(days=1)),
        ])
    assert len(client.get("/events?q=Python").json()) == 2
    assert len(client.get("/events?type=講座").json()) == 1
    assert len(client.get("/events?q=Python&type=參訪").json()) == 1


def test_verification_and_reset_links_expire(client, application, monkeypatch):
    assert client.post("/auth/register", json=registration_payload()).status_code == 201
    verify_token = queued_token(application, "newuser@ntou.edu.tw")
    start = utc_now()
    monkeypatch.setattr("app.services.utc_now", lambda: start + timedelta(hours=24))
    assert client.post("/auth/verify-email", json={"token": verify_token}).status_code == 400

    monkeypatch.setattr("app.services.utc_now", lambda: start)
    assert client.post("/auth/forgot-password", json={"email": "member@test.invalid"}).status_code == 202
    reset_token = queued_token(application, "member@test.invalid")
    monkeypatch.setattr("app.services.utc_now", lambda: start + timedelta(hours=1))
    assert client.post("/auth/reset-password",
                       json={"token": reset_token, "password": "another123"}).status_code == 400
