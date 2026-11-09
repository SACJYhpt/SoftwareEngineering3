from datetime import timedelta
from urllib.parse import urlparse, parse_qs

from app.models import User, EmailVerificationToken, PasswordResetToken, Event
from app.security import decode_token, issue_token, hash_password
from app.services import utc_now


def registration_payload(**overrides):
    data = {"email": "newuser@ntou.edu.tw", "name": "新使用者", "identity": "student",
            "department_id": 1, "grade": 2, "password": "abc12345"}
    data.update(overrides)
    return data


def test_registration_requires_school_domain_and_valid_profile(client):
    assert client.post("/auth/register", json=registration_payload(email="abc@gmail.com")).status_code == 422
    assert client.post("/auth/register", json=registration_payload(password="12345678")).status_code == 422
    assert client.post("/auth/register", json=registration_payload(grade=None)).status_code == 422
    assert client.post("/auth/register", json=registration_payload(identity="teacher", grade=2)).status_code == 422
    response = client.post("/auth/register", json=registration_payload())
    assert response.status_code == 201
    assert client.post("/auth/login", json={"email": "newuser@ntou.edu.tw", "password": "abc12345"}).status_code == 403


def test_email_verify_token_and_resend_invalidates_old(client, application):
    assert client.post("/auth/register", json=registration_payload()).status_code == 201
    old_body = application.state.email_outbox[-1]["body"]
    old_token = old_body.split("token=", 1)[1].strip()
    assert client.post("/auth/resend-verification", json={"email": "newuser@ntou.edu.tw"}).status_code == 429
    with application.state.sessions.begin() as db:
        user = db.query(User).filter_by(email="newuser@ntou.edu.tw").one()
        user.verification_sent_at = utc_now() - timedelta(seconds=61)
    assert client.post("/auth/resend-verification", json={"email": "newuser@ntou.edu.tw"}).status_code == 200
    new_token = application.state.email_outbox[-1]["body"].split("token=", 1)[1].strip()
    assert new_token != old_token
    assert client.post("/auth/verify-email", json={"token": old_token}).status_code == 400
    assert client.post("/auth/verify-email", json={"token": new_token}).status_code == 200
    assert client.post("/auth/verify-email", json={"token": new_token}).status_code == 400
    assert client.post("/auth/login", json={"email": "newuser@ntou.edu.tw", "password": "abc12345"}).status_code == 200


def test_password_reset_is_one_time_and_invalidates_existing_sessions(client, application):
    # Existing fixture user is already verified.
    token1 = issue_token(1, application.state.settings)
    assert client.post("/auth/password-reset/request", json={"email": "member@test.invalid"}).status_code == 200
    raw = application.state.email_outbox[-1]["body"].split("token=", 1)[1].strip()
    assert client.get("/auth/me", headers={"Authorization": "Bearer " + token1}).status_code == 200
    payload = {"token": raw, "password": "newpass123"}
    assert client.post("/auth/password-reset/confirm", json=payload).status_code == 200
    assert client.get("/auth/me", headers={"Authorization": "Bearer " + token1}).status_code == 401
    assert client.post("/auth/password-reset/confirm", json=payload).status_code == 400
    assert client.post("/auth/login", json={"email": "member@test.invalid", "password": "newpass123"}).status_code == 200


def test_password_reset_request_does_not_reveal_account(client, application):
    a = client.post("/auth/password-reset/request", json={"email": "member@test.invalid"})
    b = client.post("/auth/password-reset/request", json={"email": "nobody@ntou.edu.tw"})
    assert a.status_code == b.status_code == 200
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
    verify_token = application.state.email_outbox[-1]["body"].split("token=", 1)[1].strip()
    start = utc_now()
    monkeypatch.setattr("app.services.utc_now", lambda: start + timedelta(hours=24))
    assert client.post("/auth/verify-email", json={"token": verify_token}).status_code == 400

    monkeypatch.setattr("app.services.utc_now", lambda: start)
    assert client.post("/auth/password-reset/request", json={"email": "member@test.invalid"}).status_code == 200
    reset_token = application.state.email_outbox[-1]["body"].split("token=", 1)[1].strip()
    monkeypatch.setattr("app.services.utc_now", lambda: start + timedelta(hours=1))
    assert client.post("/auth/password-reset/confirm",
                       json={"token": reset_token, "password": "another123"}).status_code == 400
