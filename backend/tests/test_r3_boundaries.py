"""R3 cross-event races and delayed-worker boundaries beyond the story examples."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
import re

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app import r3, services as s
from app.models import Event, OutgoingEmail, Registration
from app.schemas import RegistrationSwitch
from test_r3 import auth, cancel, jobs, join, mails, now, request, setup


def test_simultaneous_different_events_cannot_bypass_user_conflict(application,now,setup):
    a,b=setup(capacity=5),setup(capacity=5)
    barrier=Barrier(2)
    def submit(e):
        barrier.wait(timeout=5)
        try:return s.register(application.state.sessions,e,1)
        except HTTPException as error:return error
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(submit,e) for e in (a,b)]
        results=[f.result(timeout=15) for f in futures]
    assert sum(isinstance(x,dict) for x in results)==1
    failure=next(x for x in results if isinstance(x,HTTPException))
    assert failure.detail["code"]=="TIME_CONFLICT"


def test_reverse_direction_switches_finish_without_deadlock(application,now,setup):
    a,b=setup(capacity=2),setup(capacity=2)
    s.register(application.state.sessions,a,1);s.register(application.state.sessions,b,2)
    barrier=Barrier(2)
    def switch(uid,source,target):
        barrier.wait(timeout=5)
        return r3.switch_registration(application.state.sessions,target,uid,
            RegistrationSwitch(source_event_ids=[source],source_status="registered",confirmed=True))
    with ThreadPoolExecutor(max_workers=2) as pool:
        one=pool.submit(switch,1,a,b);two=pool.submit(switch,2,b,a)
        assert one.result(timeout=15)["event_id"]==b
        assert two.result(timeout=15)["event_id"]==a


def test_promotion_skips_new_time_conflict_and_preserves_other_booking(client,application,now,setup):
    a=setup(waitlist_enabled=True,waitlist_capacity=3)
    join(client,application,a,1);join(client,application,a,2);join(client,application,a,3)
    b=setup(starts_at=now["now"]+timedelta(days=4),ends_at=now["now"]+timedelta(days=4,hours=2))
    join(client,application,b,2)
    moved=client.patch(f"/events/{b}",json={"start_time":s.as_utc(now["now"]+timedelta(days=3)).isoformat(),
        "end_time":s.as_utc(now["now"]+timedelta(days=3,hours=2)).isoformat(),"confirm_overlap":True},headers=auth(application,3))
    assert moved.status_code==200
    cancel(client,application,a)
    assert client.get(f"/events/{a}",headers=auth(application,3)).json()["my_registration_status"]=="已報名"
    assert client.get(f"/events/{b}",headers=auth(application,2)).json()["my_registration_status"]=="已報名"
    assert any("候補略過" in m.subject and "撞期" in m.body for m in mails(application))


def test_waitlist_to_waitlist_conflict_switch_is_atomic(client,application,now,setup):
    a=setup(waitlist_enabled=True,waitlist_capacity=2)
    b=setup(waitlist_enabled=True,waitlist_capacity=2)
    join(client,application,a,2);join(client,application,a,1)
    join(client,application,b,3)
    result=client.post(f"/events/{b}/registrations/switch",json={"source_event_ids":[a],
        "source_status":"waitlisted","confirmed":True},headers=auth(application,1))
    assert result.status_code==200 and result.json()["status"]=="waitlisted"
    assert client.get(f"/events/{a}",headers=auth(application,1)).json()["my_registration_status"]=="已取消"


def test_concurrent_worker_iterations_do_not_duplicate_due_messages(client,application,now,setup):
    e=setup(waitlist_enabled=True,waitlist_capacity=2)
    join(client,application,e);join(client,application,e,2)
    now["now"]+=timedelta(days=2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes=list(pool.map(lambda _:jobs(application),range(2)))
    assert sum(x["not_promoted"] for x in outcomes)==1
    assert sum(x["reminders"] for x in outcomes)==1


def test_reminder_action_changes_at_deadline_and_old_generation_is_invalid(client,application,now,setup):
    e=setup(registration_closes_at=now["now"]+timedelta(days=2,hours=6))
    join(client,application,e)
    now["now"]+=timedelta(days=2)
    jobs(application)
    token=re.search(r"#cancel_token=(\S+)",mails(application,"event_reminder")[0].body).group(1)
    path="/me/cancellation-action"
    assert client.post(path,json={"token":token},headers=auth(application,1)).json()["action"]=="cancel"
    assert client.get(f"/events/{e}#cancel_token={token}").status_code==200
    with application.state.sessions() as db:
        assert db.scalar(select(Registration.status).where(Registration.event_id==e))=="registered"
    assert cancel(client,application,e).status_code==200
    assert join(client,application,e).status_code==201
    assert client.post(path,json={"token":token},headers=auth(application,1)).status_code==400
    assert client.post(f"/events/{e}/registrations",headers={"Authorization":"Bearer "+token}).status_code==401


def test_cancellation_request_cleanup_when_activity_cancelled(client,application,now,setup):
    e=setup()
    join(client,application,e);now["now"]+=timedelta(days=2)
    assert request(client,application,e).status_code==201
    assert client.post(f"/events/{e}/cancel",json={"reason":"停辦"},headers=auth(application,3)).status_code==200
    rows=client.get(f"/events/{e}/cancellation-requests",headers=auth(application,3)).json()
    assert rows[0]["status"]=="auto_approved"
    assert client.get(f"/events/{e}",headers=auth(application,1)).json()["cancellation_request"] is None


def test_g05_two_managers_check_in_different_people_and_see_same_counts(client,application,now,setup):
    e=setup(capacity=2)
    one=join(client,application,e).json();two=join(client,application,e,2).json()
    now["now"]+=timedelta(days=3)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[
            pool.submit(_check_in,application,e,one["registration_id"],3),
            pool.submit(_check_in,application,e,two["registration_id"],5)]
        for f in futures:assert f.result(timeout=15)["checked_in_count"] in (1,2)
    for uid in (3,5):
        assert client.get(f"/events/{e}/attendance",headers=auth(application,uid)).json()["checked_in_count"]==2


def _check_in(application,e,rid,uid):
    with application.state.sessions() as db:return r3.set_attendance(db,e,rid,uid,"check_in")


def test_check_in_uses_taiwan_calendar_date(client,application,now,setup):
    now["now"]=now["now"].replace(hour=15,minute=59) # 23:59 Taiwan
    e=setup(starts_at=now["now"]+timedelta(hours=2),ends_at=now["now"]+timedelta(hours=4),
            registration_closes_at=now["now"]+timedelta(hours=1))
    record=join(client,application,e).json()
    url=f"/events/{e}/registrations/{record['registration_id']}/check-in"
    assert client.post(url,headers=auth(application,3)).status_code==409
    now["now"]+=timedelta(minutes=1) # midnight Taiwan, before activity starts
    assert client.post(url,headers=auth(application,3)).status_code==200


def test_g04_h01_cross_unit_denied(client,application,now,setup):
    e=setup(unit_id=2)
    record=join(client,application,e).json()
    now["now"]+=timedelta(days=3)
    base=f"/events/{e}/registrations/{record['registration_id']}"
    assert client.post(base+"/check-in",headers=auth(application,5)).status_code==403
    assert client.get(f"/events/{e}/attendance",headers=auth(application,5)).status_code==403
    now["now"]+=timedelta(days=3)
    assert client.patch(base+"/attendance",json={"status":"present"},headers=auth(application,5)).status_code==403


@pytest.mark.parametrize("change",[{"capacity":None,"waitlist_enabled":True},{"eligibility_grades":[-1]}])
def test_invalid_waitlist_or_eligibility_edit_is_not_misreported_as_time(client,application,now,setup,change):
    e=setup()
    response=client.patch(f"/events/{e}",json=change,headers=auth(application,3))
    assert response.status_code==422
    assert response.json()["detail"]["code"]=="EVENT_FIELD_INVALID"


def test_expired_waitlist_does_not_block_registration_while_worker_is_delayed(client,application,now,setup):
    old=setup(waitlist_enabled=True,waitlist_capacity=2)
    join(client,application,old,2);join(client,application,old,1)
    now["now"]+=timedelta(days=2)
    new=setup(starts_at=now["now"]+timedelta(days=1),ends_at=now["now"]+timedelta(days=1,hours=2),
              registration_closes_at=now["now"]+timedelta(hours=12))
    assert join(client,application,new,1).status_code==201
    assert jobs(application)["not_promoted"]==1
