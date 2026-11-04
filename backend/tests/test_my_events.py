"""R2 E01/E02: personal upcoming events and cancellation, without waitlists."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.models import Event, Registration, User
from app.security import issue_token
from app.services import cancel_registration, register, utc_now
from test_registration import add_event


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    now = datetime(2030, 1, 10)
    monkeypatch.setattr('app.services.utc_now', lambda: now)
    monkeypatch.setattr('test_registration.utc_now', lambda: now)
    monkeypatch.setattr(__name__ + '.utc_now', lambda: now)


def auth(app, user_id):
    return {"Authorization": "Bearer " + issue_token(user_id, app.state.settings)}


def cancellation_path(event_id):
    return f"/events/{event_id}/registrations/me"


def test_personal_endpoints_require_authentication(application, client):
    event_id = add_event(application)
    for headers in ({}, {"Authorization": "Bearer invalid"}):
        assert client.get('/me/events', headers=headers).status_code == 401
        assert client.delete(cancellation_path(event_id), headers=headers).status_code == 401
    register(application.state.sessions, event_id, 1)
    with application.state.sessions.begin() as db:
        db.get(User, 1).is_active = False
    headers = auth(application, 1)
    assert client.get('/me/events', headers=headers).status_code == 401
    assert client.delete(cancellation_path(event_id), headers=headers).status_code == 401


def test_my_events_are_private_sorted_and_include_closed_and_ongoing(application, client, headers, monkeypatch):
    now = utc_now()
    monkeypatch.setattr('app.services.utc_now', lambda: now)
    assert client.get('/me/events', headers=headers).json() == []
    later = add_event(application)
    sooner = add_event(application, starts_at=now + timedelta(days=2), ends_at=now + timedelta(days=2, hours=1))
    hidden = add_event(application)
    register(application.state.sessions, later, 1)
    register(application.state.sessions, sooner, 1)
    register(application.state.sessions, hidden, 2)
    first = client.get('/me/events', headers=headers)
    assert first.status_code == 200
    assert [row['id'] for row in first.json()] == [sooner, later]
    assert all(row['my_registration_status'] == '已報名' for row in first.json())
    assert all(row['can_cancel_registration'] for row in first.json())
    assert all(row['registered_at'].endswith('Z') and row['registration_id'] > 0 for row in first.json())
    assert [row['id'] for row in client.get('/me/events', headers=auth(application, 2)).json()] == [hidden]
    monkeypatch.setattr('app.services.utc_now', lambda: now + timedelta(days=1))
    closed = client.get('/me/events', headers=headers).json()
    assert all(row['status'] == '已截止' and not row['can_cancel_registration'] for row in closed)
    monkeypatch.setattr('app.services.utc_now', lambda: now + timedelta(days=3))
    ongoing = client.get('/me/events', headers=headers).json()
    assert [row['id'] for row in ongoing] == [later]
    assert ongoing[0]['status'] == '進行中'
    assert not ongoing[0]['can_cancel_registration']
    monkeypatch.setattr('app.services.utc_now', lambda: now + timedelta(days=3, hours=1))
    assert client.get('/me/events', headers=headers).json() == []


def test_cancelled_events_are_not_upcoming(application, client, headers):
    event_id = add_event(application)
    register(application.state.sessions, event_id, 1)
    with application.state.sessions.begin() as db:
        db.get(Event, event_id).is_cancelled = True
    assert client.get('/me/events', headers=headers).json() == []
    response = client.delete(cancellation_path(event_id), headers=headers)
    assert response.status_code == 409
    assert response.json()['detail']['code'] == 'EVENT_CANCELLED'
    with application.state.sessions() as db:
        assert db.scalar(select(func.count(Registration.id)).where(Registration.status == "registered")) == 1


@pytest.mark.parametrize('capacity', [1, None])
def test_cancel_updates_views_and_allows_reregistration(application, client, headers, capacity):
    event_id = add_event(application, capacity=capacity)
    before = client.post(f'/events/{event_id}/registrations', headers=headers).json()
    response = client.delete(cancellation_path(event_id), headers=headers)
    assert response.status_code == 200
    assert response.json() == dict(message='已取消報名', registration_id=before['registration_id'],
                                   event_id=event_id, status='cancelled', registration_count=0, capacity=capacity)
    assert client.get('/me/events', headers=headers).json() == []
    detail = client.get(f'/events/{event_id}', headers=headers).json()
    assert detail['registration_count'] == detail['registered_count'] == 0
    assert detail['my_registration_status'] == '已取消' and detail['can_register']
    listed = client.get('/events').json()[0]
    assert listed['registration_count'] == 0 and listed['status'] == '開放中'
    repeated = client.delete(cancellation_path(event_id), headers=headers)
    assert repeated.status_code == 404
    assert repeated.json()['detail']['code'] == 'REGISTRATION_NOT_FOUND'
    again = client.post(f'/events/{event_id}/registrations', headers=headers)
    assert again.status_code == 201
    assert again.json()['registration_count'] == 1
    assert not again.json()['already_registered']


@pytest.mark.parametrize('user_id', [2, 3, 4])
def test_cannot_cancel_someone_elses_registration(application, client, user_id):
    event_id = add_event(application)
    original = register(application.state.sessions, event_id, 1)
    response = client.delete(cancellation_path(event_id), headers=auth(application, user_id))
    assert response.status_code == 404
    assert response.json()['detail']['code'] == 'REGISTRATION_NOT_FOUND'
    with application.state.sessions() as db:
        assert db.get(Registration, original['registration_id']).user_id == 1
        assert db.scalar(select(func.count(Registration.id)).where(Registration.status == "registered")) == 1


@pytest.mark.parametrize('user_id', [3, 4])
def test_manager_and_admin_can_cancel_their_own_registration(application, client, user_id):
    event_id = add_event(application, unit_id=3)
    register(application.state.sessions, event_id, user_id)
    response = client.delete(cancellation_path(event_id), headers=auth(application, user_id))
    assert response.status_code == 200
    assert response.json()['registration_count'] == 0


def test_cancellation_deadline_is_exclusive(application, client, headers, monkeypatch):
    now = utc_now()
    deadline = now + timedelta(hours=1)
    event_id = add_event(application, registration_closes_at=deadline)
    register(application.state.sessions, event_id, 1)
    monkeypatch.setattr('app.services.utc_now', lambda: deadline - timedelta(microseconds=1))
    assert client.get('/me/events', headers=headers).json()[0]['can_cancel_registration']
    assert client.delete(cancellation_path(event_id), headers=headers).status_code == 200
    assert client.post(f'/events/{event_id}/registrations', headers=headers).status_code == 201
    for instant in (deadline, deadline + timedelta(microseconds=1)):
        monkeypatch.setattr('app.services.utc_now', lambda: instant)
        assert not client.get('/me/events', headers=headers).json()[0]['can_cancel_registration']
        response = client.delete(cancellation_path(event_id), headers=headers)
        assert response.status_code == 409
        assert response.json()['detail']['code'] == 'REGISTRATION_CLOSED'
    with application.state.sessions() as db:
        assert db.scalar(select(func.count(Registration.id)).where(Registration.status == "registered")) == 1


def test_started_event_rejects_cancellation(application, client, headers, monkeypatch):
    now = utc_now()
    event_id = add_event(application)
    register(application.state.sessions, event_id, 1)
    monkeypatch.setattr('app.services.utc_now', lambda: now + timedelta(days=3))
    response = client.delete(cancellation_path(event_id), headers=headers)
    assert response.status_code == 409
    assert response.json()['detail']['code'] == 'EVENT_STARTED'
    with application.state.sessions() as db:
        assert db.scalar(select(func.count(Registration.id)).where(Registration.status == "registered")) == 1


def test_missing_event_and_registration(application, client, headers):
    missing = client.delete(cancellation_path(999999), headers=headers)
    assert missing.status_code == 404
    assert missing.json()['detail']['code'] == 'EVENT_NOT_FOUND'
    event_id = add_event(application)
    absent = client.delete(cancellation_path(event_id), headers=headers)
    assert absent.status_code == 404
    assert absent.json()['detail']['code'] == 'REGISTRATION_NOT_FOUND'


def test_cancellation_cors_preflight(client):
    response = client.options('/events/1/registrations/me', headers={
        'Origin': 'http://localhost:5173', 'Access-Control-Request-Method': 'DELETE',
        'Access-Control-Request-Headers': 'authorization'})
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == 'http://localhost:5173'
    assert 'DELETE' in response.headers['access-control-allow-methods']


def test_parallel_cancellations_release_one_seat(application):
    event_id = add_event(application, capacity=1)
    register(application.state.sessions, event_id, 1)

    def attempt(_):
        try:
            return cancel_registration(application.state.sessions, event_id, 1)
        except HTTPException as error:
            assert error.status_code == 404 and error.detail['code'] == 'REGISTRATION_NOT_FOUND'
            return None

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(attempt, range(16)))
    assert sum(row is not None for row in results) == 1
    with application.state.sessions() as db:
        assert db.scalar(select(func.count(Registration.id)).where(Registration.status == "registered")) == 0


def test_concurrent_cancellation_and_competing_registrations_do_not_overbook(application):
    event_id = add_event(application, capacity=1)
    register(application.state.sessions, event_id, 1)
    barrier = Barrier(4)

    def attempt(user_id):
        barrier.wait(timeout=10)
        if user_id == 1:
            return cancel_registration(application.state.sessions, event_id, user_id)
        try:
            return register(application.state.sessions, event_id, user_id)
        except HTTPException as error:
            assert error.status_code == 409 and error.detail['code'] == 'EVENT_FULL'
            return None

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(attempt, [1, 2, 3, 4]))
    assert results[0]['status'] == 'cancelled'
    successes = [row for row in results[1:] if row is not None]
    assert len(successes) <= 1
    # If every contender ran before the cancellation, the released seat remains
    # available; otherwise exactly one contender owns it. Both orders are valid.
    if not successes:
        assert register(application.state.sessions, event_id, 2)['registration_count'] == 1
    with application.state.sessions() as db:
        records = db.scalars(select(Registration).where(Registration.event_id == event_id, Registration.status == "registered")).all()
        assert len(records) == 1
        assert records[0].user_id in (2, 3, 4)


def test_team_logout_revocation_applies_to_both_r2_endpoints(application, client):
    login_body = dict(email='member@test.invalid', password='TestingOnly!2026')
    first = client.post('/auth/login', json=login_body)
    assert first.status_code == 200
    revoked = {'Authorization': 'Bearer ' + first.json()['access_token']}
    second = client.post('/auth/login', json=login_body)
    assert second.status_code == 200
    active = {'Authorization': 'Bearer ' + second.json()['access_token']}
    event_id = add_event(application, capacity=1)
    assert client.post(f'/events/{event_id}/registrations', headers=revoked).status_code == 201
    assert client.get('/me/events', headers=revoked).json()[0]['id'] == event_id
    assert client.post('/auth/logout', headers=revoked).status_code == 204
    for response in (client.get('/me/events', headers=revoked),
                     client.delete(cancellation_path(event_id), headers=revoked)):
        assert response.status_code == 401
        assert response.json()['detail']['code'] == 'INVALID_TOKEN'
    # Rejected cancellations must leave the seat intact; the other login still works.
    assert client.get('/me/events', headers=active).json()[0]['registration_count'] == 1
    assert client.delete(cancellation_path(event_id), headers=active).status_code == 200
    assert client.get('/me/events', headers=active).json() == []
