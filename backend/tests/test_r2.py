"""SRD v2 R2 acceptance scenarios. Each test uses a new private SQLite database.

No real messages are sent: token links are read from the test database outbox.
The operations tests separately exercise SMTP retries and local backup/restore.
"""
from datetime import datetime, timedelta
from io import BytesIO
import hashlib
import re

import pytest
from PIL import Image
from sqlalchemy import func, select

from app.models import (AccountToken, Event, EventType, OrganizerAcknowledgement,
                        OutgoingEmail, PublishedDocument, Registration, Unit, UnitManager, User)
from app.security import issue_token
from app.services import utc_now
from test_registration import add_event


@pytest.fixture
def manager(application):
    return {'Authorization': 'Bearer ' + issue_token(3, application.state.settings)}


@pytest.fixture
def admin(application):
    return {'Authorization': 'Bearer ' + issue_token(4, application.state.settings)}


@pytest.fixture
def clock(monkeypatch):
    state = {'now': datetime(2030, 1, 10)}
    monkeypatch.setattr('app.services.utc_now', lambda: state['now'])
    monkeypatch.setattr('test_registration.utc_now', lambda: state['now'])
    return state


def signup_payload(**changes):
    data = dict(email='new@ntou.edu.tw', password='NewPassword123', name='新同學', identity='student',
                department_id=1, grade=1, consent=True, privacy_version=1)
    data.update(changes)
    return data


def latest_token(application, recipient):
    with application.state.sessions() as db:
        body = db.scalar(select(OutgoingEmail.body).where(OutgoingEmail.recipient == recipient)
                         .order_by(OutgoingEmail.id.desc()).limit(1))
        return re.search(r'#token=([^\s]+)', body).group(1)


def test_signup_consent_verification_and_duplicate_email(application, client, clock):
    assert client.get('/privacy-notice').json()['version'] == 1
    result = client.post('/auth/register', json=signup_payload())
    assert result.status_code == 201
    token = latest_token(application, 'new@ntou.edu.tw')
    with application.state.sessions() as db:
        user = db.scalar(select(User).where(User.email == 'new@ntou.edu.tw'))
        assert user.consent_at == clock['now'] and user.privacy_version == 1
        assert user.role == 'member' and not user.email_verified
        assert user.password_hash.startswith('$argon2id$')
        record = db.scalar(select(AccountToken).where(AccountToken.user_id == user.id))
        assert record.token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert record.expires_at == clock['now'] + timedelta(hours=24)
    assert client.post('/auth/register', json=signup_payload(email=' NEW@ntou.edu.tw ')).status_code == 409
    login = dict(email='new@ntou.edu.tw', password='NewPassword123')
    assert client.post('/auth/login', json=login).json()['detail']['code'] == 'EMAIL_NOT_VERIFIED'
    assert client.post('/auth/verify-email', json={'token': token}).status_code == 200
    assert client.post('/auth/login', json=login).status_code == 200
    assert client.post('/auth/verify-email', json={'token': token}).status_code == 400


@pytest.mark.parametrize('changes,status,code', [
    ({'email': 'new@gmail.com'}, 422, 'SCHOOL_EMAIL_REQUIRED'),
    ({'email': 'new@ntou.edu.tw.attacker.com'}, 422, 'SCHOOL_EMAIL_REQUIRED'),
    ({'consent': False}, 422, 'PRIVACY_CONSENT_REQUIRED'),
    ({'privacy_version': 2}, 409, 'PRIVACY_NOTICE_OUTDATED'),
    ({'department_id': 999}, 422, 'DEPARTMENT_INVALID'),
    ({'grade': None}, 422, None), ({'name': ' '}, 422, None),
    ({'password': 'onlyletters'}, 422, None), ({'password': '12345678'}, 422, None),
    ({'password': 'a1'}, 422, None), ({'role': 'admin'}, 422, None),
])
def test_signup_rejects_invalid_input_without_creating_account(application, client, changes, status, code):
    response = client.post('/auth/register', json=signup_payload(**changes))
    assert response.status_code == status
    if code:
        assert response.json()['detail']['code'] == code
    with application.state.sessions() as db:
        assert db.scalar(select(func.count(User.id))) == 5
        assert db.scalar(select(func.count(OutgoingEmail.id))) == 0


def test_signup_teacher_and_school_subdomain(client):
    assert client.post('/auth/register', json=signup_payload(email='teacher@mail.ntou.edu.tw', identity='teacher', grade=None)).status_code == 201


def test_verification_expiry_resend_and_uniform_throttle(application, client, clock):
    client.post('/auth/register', json=signup_payload())
    old = latest_token(application, 'new@ntou.edu.tw')
    assert client.post('/auth/resend-verification', json={'email':'new@ntou.edu.tw'}).status_code == 429
    clock['now'] += timedelta(seconds=60)
    known = client.post('/auth/resend-verification', json={'email':'new@ntou.edu.tw'})
    unknown = client.post('/auth/resend-verification', json={'email':'missing@ntou.edu.tw'})
    assert known.status_code == unknown.status_code == 202 and known.json() == unknown.json()
    new = latest_token(application, 'new@ntou.edu.tw')
    assert new != old
    assert client.post('/auth/verify-email', json={'token':old}).status_code == 400
    for email in ('new@ntou.edu.tw', 'missing@ntou.edu.tw'):
        response = client.post('/auth/resend-verification', json={'email':email})
        assert response.status_code == 429
        assert response.json()['detail']['retry_after_seconds'] == 60
    clock['now'] += timedelta(hours=24)
    expired = client.post('/auth/verify-email', json={'token':new})
    assert expired.json()['detail']['code'] == 'LINK_INVALID'


def test_password_reset_single_use_and_revokes_all_existing_logins(application, client, clock):
    login = dict(email='member@test.invalid', password='TestingOnly!2026')
    first = client.post('/auth/login', json=login).json()['access_token']
    second = client.post('/auth/login', json=login).json()['access_token']
    known = client.post('/auth/forgot-password', json={'email':login['email']})
    unknown = client.post('/auth/forgot-password', json={'email':'missing@test.invalid'})
    assert known.status_code == unknown.status_code == 202 and known.json() == unknown.json()
    token = latest_token(application, login['email'])
    # A reset token cannot be used as a verification token.
    assert client.post('/auth/verify-email', json={'token':token}).status_code == 400
    body = dict(token=token, password='ChangedPassword123')
    assert client.post('/auth/reset-password', json=body).status_code == 200
    assert client.post('/auth/reset-password', json=body).status_code == 400
    for value in (first, second):
        assert client.get('/auth/me', headers={'Authorization':'Bearer '+value}).status_code == 401
    assert client.post('/auth/login', json=login).status_code == 401
    login['password'] = 'ChangedPassword123'
    assert client.post('/auth/login', json=login).status_code == 200


def test_reset_expires_exactly_after_one_hour(application, client, clock):
    client.post('/auth/forgot-password', json={'email':'member@test.invalid'})
    token = latest_token(application, 'member@test.invalid')
    clock['now'] += timedelta(hours=1)
    assert client.post('/auth/reset-password', json=dict(token=token,password='ChangedPassword123')).status_code == 400


def test_search_filter_combination_and_taiwan_day_boundaries(application, client, clock):
    # UTC Jan 11 16:00 is Taiwan Jan 12 00:00; end-date includes the entire Taiwan day.
    match = add_event(application, name='企業參訪', starts_at=datetime(2030,1,11,16), ends_at=datetime(2030,1,12,18), category='參訪')
    add_event(application, name='企業參訪已取消', is_cancelled=True)
    add_event(application, name='企業參訪隱藏', is_public=False)
    add_event(application, name='其他講座')
    assert [x['id'] for x in client.get('/events', params={'q':'參訪','type':'參訪','date_from':'2030-01-12','date_to':'2030-01-12'}).json()] == [match]
    assert client.get('/events', params={'q':'找不到'}).json() == []
    assert client.get('/events', params={'q':"%' OR 1=1 --"}).json() == []
    assert client.get('/events', params={'date_from':'2030-02-01','date_to':'2030-01-01'}).status_code == 422


def test_history_and_cancelled_status_are_separate(application, client, headers, clock):
    event_id = add_event(application)
    client.post(f'/events/{event_id}/registrations', headers=headers)
    client.delete(f'/events/{event_id}/registrations/me', headers=headers)
    assert client.get(f'/events/{event_id}', headers=headers).json()['my_registration_status'] == '已取消'
    with application.state.sessions() as db:
        assert db.scalar(select(Registration)).status == 'cancelled'
    client.post(f'/events/{event_id}/registrations', headers=headers)
    with application.state.sessions() as db:
        assert db.scalar(select(func.count(Registration.id))) == 1
    clock['now'] += timedelta(days=3,hours=1)
    assert client.get('/me/events', headers=headers).json() == []
    history = client.get('/me/events/history', headers=headers).json()
    assert [x['id'] for x in history] == [event_id]
    assert history[0]['attendance_status'] == '未記錄'
    other = {'Authorization':'Bearer '+issue_token(2,application.state.settings)}
    assert client.get('/me/events/history', headers=other).json() == []


def test_same_unit_can_edit_roster_and_qr_but_other_units_cannot(application, client, manager, headers):
    event_id = add_event(application)
    client.post(f'/events/{event_id}/registrations', headers=headers)
    same = {'Authorization':'Bearer '+issue_token(5,application.state.settings)}
    roster = client.get(f'/events/{event_id}/registrations', headers=same)
    assert roster.status_code == 200 and roster.json()['registration_count'] == 1
    assert roster.json()['registrations'][0]['email'] == 'member@test.invalid'
    assert 'password_hash' not in str(roster.json())
    assert client.patch(f'/events/{event_id}', json={'description':'修改說明'}, headers=same).status_code == 200
    qr = client.get(f'/events/{event_id}/qr', headers=manager)
    assert qr.status_code == 200 and qr.headers['content-type']=='image/png'
    assert Image.open(BytesIO(qr.content)).format == 'PNG'
    other_event = add_event(application, unit_id=3)
    for path in (f'/events/{other_event}/registrations', f'/events/{other_event}/qr'):
        assert client.get(path, headers=manager).status_code == 403
    assert client.patch(f'/events/{other_event}', json={'name':'不允許'}, headers=manager).status_code == 403
    assert client.get(f'/events/{event_id}/registrations', headers=headers).status_code == 403


def test_qr_contains_only_stable_public_event_link(application,client,manager,monkeypatch):
    import qrcode
    event_id=add_event(application)
    original=qrcode.make
    contents=[]
    def make(data):
        contents.append(data)
        return original(data)
    monkeypatch.setattr(qrcode,'make',make)
    assert client.get(f'/events/{event_id}/qr',headers=manager).status_code==200
    assert contents==[f'http://localhost:5173/events/{event_id}']
    assert 'token' not in contents[0] and '@' not in contents[0]


def test_edit_notifications_are_transactional_and_only_for_required_fields(application, client, manager, headers, clock):
    event_id = add_event(application,capacity=2)
    client.post(f'/events/{event_id}/registrations', headers=headers)
    with application.state.sessions() as db:
        assert db.scalar(select(func.count(OutgoingEmail.id))) == 0
    assert client.patch(f'/events/{event_id}', json={'description':'不寄信'}, headers=manager).status_code == 200
    response = client.patch(f'/events/{event_id}', json={'location':'新地點','notes':'請準時'}, headers=manager)
    assert response.status_code == 200
    with application.state.sessions() as db:
        mail = db.scalar(select(OutgoingEmail))
        assert '海大 → 新地點' in mail.body and '請準時' in mail.body
        assert mail.recipient == 'member@test.invalid' and mail.status == 'pending'
    bad = client.patch(f'/events/{event_id}', json={'registration_deadline':'2030-02-01T00:00:00Z'}, headers=manager)
    assert bad.status_code == 422
    with application.state.sessions() as db:
        assert db.scalar(select(func.count(OutgoingEmail.id))) == 1
    # Cannot shrink below active registrations; cancelling a seat permits shrinking.
    other = {'Authorization':'Bearer '+issue_token(2,application.state.settings)}
    client.post(f'/events/{event_id}/registrations', headers=other)
    assert client.patch(f'/events/{event_id}', json={'capacity':1}, headers=manager).status_code == 409
    client.delete(f'/events/{event_id}/registrations/me', headers=other)
    assert client.patch(f'/events/{event_id}', json={'capacity':1}, headers=manager).status_code == 200


def test_cancel_event_stops_registration_and_notifies_active_registrants(application, client, manager, headers):
    event_id=add_event(application)
    client.post(f'/events/{event_id}/registrations',headers=headers)
    assert client.post(f'/events/{event_id}/cancel',json={'reason':'颱風取消'},headers=manager).status_code==200
    assert client.get(f'/events/{event_id}').json()['status']=='已取消'
    assert client.get('/events').json()==[]
    other={'Authorization':'Bearer '+issue_token(2,application.state.settings)}
    assert client.post(f'/events/{event_id}/registrations',headers=other).json()['detail']['code']=='EVENT_CANCELLED'
    assert client.post(f'/events/{event_id}/registrations',headers=headers).json()['detail']['code']=='EVENT_CANCELLED'
    assert client.delete(f'/events/{event_id}/registrations/me',headers=headers).status_code==409
    assert client.patch(f'/events/{event_id}',json={'name':'不可修改'},headers=manager).status_code==409
    with application.state.sessions() as db:
        assert db.scalar(select(OutgoingEmail.body)).endswith('颱風取消')
        assert db.get(Event,event_id).cancellation_reason=='颱風取消'


def test_ended_event_is_not_editable(application, client, manager, clock):
    event_id=add_event(application)
    clock['now']+=timedelta(days=4)
    assert client.patch(f'/events/{event_id}',json={'name':'結束不可改'},headers=manager).status_code==409
    assert client.post(f'/events/{event_id}/cancel',json={'reason':'不可'},headers=manager).status_code==409


def test_terms_version_changes_block_new_publication_until_ack(application, client, manager, admin):
    current=client.get('/organizer-terms').json()
    assert client.post('/admin/documents/organizer',json={'content':'新版規範'},headers=manager).status_code==403
    new=client.post('/admin/documents/organizer',json={'content':'新版規範'},headers=admin).json()
    assert new['version']==current['version']+1
    from datetime import timezone
    now=utc_now().replace(tzinfo=timezone.utc)
    payload=dict(name='新活動',type='講座',description='說明',location='海大',contact_information='x@test.invalid',unit_id=1,
                 start_time=(now+timedelta(days=3)).isoformat(),end_time=(now+timedelta(days=3,hours=1)).isoformat(),
                 registration_start=(now-timedelta(days=1)).isoformat(),registration_deadline=(now+timedelta(days=1)).isoformat())
    assert client.post('/events',json=payload,headers=manager).json()['detail']['code']=='ORGANIZER_TERMS_REQUIRED'
    assert client.post('/organizer-terms/acknowledgements',json={'document_id':current['id']},headers=manager).status_code==409
    assert client.post('/organizer-terms/acknowledgements',json={'document_id':new['id']},headers=manager).status_code==200
    assert client.post('/events',json=payload,headers=manager).status_code==201


def test_faq_is_public_but_only_admin_can_publish(client,headers,admin):
    assert client.get('/faq').status_code==200
    assert client.post('/admin/documents/faq',json={'content':'新版 FAQ'},headers=headers).status_code==403
    published=client.post('/admin/documents/faq',json={'content':'新版 FAQ'},headers=admin)
    assert published.status_code==201
    assert client.get('/faq').json()['content']=='新版 FAQ'
    assert datetime.fromisoformat(client.get('/faq').json()['published_at']).utcoffset() == timedelta(0)


def test_user_search_pagination_filters_and_no_private_secrets(application,client,admin,manager,headers):
    with application.state.sessions.begin() as db:
        db.get(User,1).name=db.get(User,2).name='同名學生'
        db.get(User,1).department_id=1
        db.get(User,2).department_id=2
    assert client.get('/admin/users',headers=headers).status_code==403
    assert client.get('/admin/users',headers=manager).status_code==403
    data=client.get('/admin/users',params={'q':'同名','page_size':1},headers=admin).json()
    assert data['total']==2 and len(data['items'])==1
    assert set(data['items'][0])=={'id','name','email','identity','department','role','managed_units'}
    second=client.get('/admin/users',params={'q':'同名','page_size':1,'page':2},headers=admin).json()
    assert data['items'][0]['email']!=second['items'][0]['email']
    filtered=client.get('/admin/users',params={'unit_id':2,'role':'manager'},headers=admin).json()
    assert [x['id'] for x in filtered['items']]==[3]
    assert client.get('/admin/users',params={'q':"%' OR 1=1 --"},headers=admin).json()['total']==0


def test_assign_revoke_multi_unit_immediate_and_admin_is_immutable(application,client,admin,headers):
    # A pre-existing login acquires and loses grants without relogging.
    assert client.put('/admin/units/1/managers/1',headers=headers).status_code==403
    for unit in (1,2):
        assert client.put(f'/admin/units/{unit}/managers/1',headers=admin).status_code==200
    assert len(client.get('/auth/me',headers=headers).json()['managed_units'])==2
    assert client.delete('/admin/units/1/managers/1',headers=admin).status_code==200
    assert client.get('/auth/me',headers=headers).json()['managed_units']==[{'id':2,'name':'測試社團'}]
    event_id=add_event(application,unit_id=1)
    assert client.get(f'/events/{event_id}/registrations',headers=headers).status_code==403
    assert client.put('/admin/units/1/managers/4',headers=admin).status_code==403
    assert client.delete('/admin/units/1/managers/4',headers=admin).status_code==403


def test_unit_maintenance_department_options_and_in_use_deletion(application,client,admin,manager):
    result=client.post('/admin/units',json={'name':'新系所','kind':'department'},headers=admin)
    assert result.status_code==201
    unit_id=result.json()['id']
    assert unit_id in [x['id'] for x in client.get('/departments').json()]
    assert client.put(f'/admin/units/{unit_id}',json={'name':'停用系所','kind':'department','is_active':False},headers=admin).status_code==200
    assert unit_id not in [x['id'] for x in client.get('/departments').json()]
    assert client.delete(f'/admin/units/{unit_id}',headers=admin).status_code==200
    add_event(application,unit_id=1)
    assert client.delete('/admin/units/1',headers=admin).json()['detail']['code']=='UNIT_IN_USE'
    assert client.put('/admin/units/1',json={'name':'已更名系所','kind':'department'},headers=admin).status_code==200
    assert client.get('/events').json()[0]['unit']['name']=='已更名系所'
    assert client.post('/admin/units',json={'name':'不可','kind':'department'},headers=manager).status_code==403


def test_types_rename_disable_and_prevent_delete_if_used(application,client,admin):
    event_id=add_event(application)
    assert client.delete('/admin/event-types/1',headers=admin).json()['detail']['code']=='EVENT_TYPE_IN_USE'
    assert client.put('/admin/event-types/1',json={'name':'更名講座','is_active':False},headers=admin).status_code==200
    assert client.get(f'/events/{event_id}').json()['type']=='更名講座'
    assert '更名講座' not in [x['name'] for x in client.get('/event-types').json()]
    created=client.post('/admin/event-types',json={'name':'新類型'},headers=admin)
    assert created.status_code==201
    assert client.delete(f"/admin/event-types/{created.json()['id']}",headers=admin).status_code==200


def test_inactive_unit_blocks_new_events_but_keeps_existing_manageable(application,client,admin,manager):
    event_id=add_event(application)
    client.put('/admin/units/1',json={'name':'停用單位','kind':'department','is_active':False},headers=admin)
    assert client.get(f'/events/{event_id}/registrations',headers=manager).status_code==200
    from datetime import timezone
    now=utc_now().replace(tzinfo=timezone.utc)
    payload=dict(name='活動',type='講座',description='說明',location='海大',contact_information='x@test.invalid',unit_id=1,
                 start_time=(now+timedelta(days=3)).isoformat(),end_time=(now+timedelta(days=3,hours=1)).isoformat(),
                 registration_start=(now-timedelta(days=1)).isoformat(),registration_deadline=(now+timedelta(days=1)).isoformat())
    assert client.post('/events',json=payload,headers=manager).json()['detail']['code']=='UNIT_INACTIVE'


def test_capacity_edit_racing_registration_cannot_overbook(application,client,manager,headers):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    event_id=add_event(application,capacity=2)
    assert client.post(f'/events/{event_id}/registrations',headers=headers).status_code==201
    barrier=Barrier(2)
    other={'Authorization':'Bearer '+issue_token(2,application.state.settings)}
    def register():
        barrier.wait(timeout=10)
        return client.post(f'/events/{event_id}/registrations',headers=other).status_code
    def shrink():
        barrier.wait(timeout=10)
        return client.patch(f'/events/{event_id}',json={'capacity':1},headers=manager).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        reg,edit=pool.submit(register),pool.submit(shrink)
        outcomes=reg.result(),edit.result()
    assert outcomes in ((201,409),(409,200))
    detail=client.get(f'/events/{event_id}').json()
    assert detail['registration_count']<=detail['capacity']


def test_password_reset_token_cannot_be_consumed_twice_concurrently(application,client):
    from concurrent.futures import ThreadPoolExecutor
    client.post('/auth/forgot-password',json={'email':'member@test.invalid'})
    token=latest_token(application,'member@test.invalid')
    def reset(_):
        return client.post('/auth/reset-password',json=dict(token=token,password='ChangedPassword123')).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reset,range(2)))==[200,400]
