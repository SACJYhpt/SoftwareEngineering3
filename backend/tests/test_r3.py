"""Trello iteration 3 backend acceptance: transaction, permission and time boundaries.

Each test owns its SQLite database. SMTP delivery is captured, never external.
The separate MySQL tests must not be inferred from these SQLite results.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from dataclasses import replace
import re

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app import operations, r3, services as s
from app.models import (AuditLog, CancellationRequest, Event, OutgoingEmail,
                        Registration, Unit, User)
from app.schemas import EventCreate
from app.security import issue_token


@pytest.fixture
def now(monkeypatch):
    clock={"now":datetime(2030,1,10)}
    monkeypatch.setattr(s,"utc_now",lambda:clock["now"])
    monkeypatch.setattr(operations,"utc_now",lambda:clock["now"])
    return clock


@pytest.fixture
def setup(application,now):
    with application.state.sessions.begin() as db:
        for user in db.scalars(select(User)):
            user.identity,user.department_id,user.grade="student",1,3
        db.add(Unit(id=4,name="行政單位",kind="office"))
    def event(**changes):
        t=now["now"]
        values=dict(unit_id=1,owner_id=3,name="R3 活動",category="講座",location="海大",
            description="測試",contact_information="events@test.invalid",starts_at=t+timedelta(days=3),
            ends_at=t+timedelta(days=3,hours=2),registration_opens_at=t-timedelta(days=1),
            registration_closes_at=t+timedelta(days=2),capacity=1)
        values.update(changes)
        with application.state.sessions.begin() as db:
            item=Event(**values);db.add(item);db.flush();return item.id
    return event


def auth(app,uid):
    return {"Authorization":"Bearer "+issue_token(uid,app.state.settings)}


def join(client,app,e,uid=1):
    return client.post(f"/events/{e}/registrations",headers=auth(app,uid))


def cancel(client,app,e,uid=1):
    return client.delete(f"/events/{e}/registrations/me",headers=auth(app,uid))


def payload(now,**changes):
    t=now["now"].replace(tzinfo=timezone.utc)
    result=dict(unit_id=1,name="API 活動",type="講座",description="活動描述",location="海大",
        contact_information="events@test.invalid",start_time=(t+timedelta(days=3)).isoformat(),
        end_time=(t+timedelta(days=3,hours=2)).isoformat(),registration_start=(t-timedelta(days=1)).isoformat(),
        registration_deadline=(t+timedelta(days=2)).isoformat(),capacity=5)
    result.update(changes);return result


def mails(app,kind=None):
    with app.state.sessions() as db:
        q=select(OutgoingEmail).order_by(OutgoingEmail.id)
        if kind:q=q.where(OutgoingEmail.kind==kind)
        return db.scalars(q).all()


def jobs(app):
    return r3.process_scheduled(app.state.sessions,app.state.settings)


def request(client,app,e,reason="臨時有事",uid=1):
    return client.post(f"/events/{e}/cancellation-requests",json=dict(reason=reason,confirmed=True),headers=auth(app,uid))


@pytest.mark.parametrize("capacity,expected",[(40,20),(5,3),(1,1)])
def test_c07_default_waitlist_capacity(client,application,now,setup,capacity,expected):
    response=client.post("/events",json=payload(now,capacity=capacity,waitlist_enabled=True),headers=auth(application,3))
    assert response.status_code==201,response.text
    assert response.json()["waitlist_capacity"]==expected


@pytest.mark.parametrize("changes",[
    {"capacity":None,"waitlist_enabled":True},
    {"waitlist_enabled":True,"waitlist_capacity":0},
    {"waitlist_enabled":True,"waitlist_capacity":-1},
    {"waitlist_enabled":True,"waitlist_capacity":True},
    {"waitlist_capacity":2},
    {"eligibility_department_ids":[True]},
    {"eligibility_department_ids":[999]},
    {"eligibility_department_ids":[2]}, # clubs are not a home department/office
    {"eligibility_identities":["admin"]},
    {"eligibility_grades":[0]},
])
def test_c07_c08_invalid_settings(client,application,now,setup,changes):
    response=client.post("/events",json=payload(now,**changes),headers=auth(application,3))
    assert response.status_code==422,response.text


def test_c07_c08_patch_persists_eligibility_and_custom_limit(client,application,now,setup):
    e=setup(capacity=5)
    response=client.patch(f"/events/{e}",json=dict(waitlist_enabled=True,waitlist_capacity=10,
        eligibility_identities=["student"],eligibility_department_ids=[1],eligibility_grades=[3,4]),headers=auth(application,3))
    assert response.status_code==200,response.text
    body=response.json()
    assert body["waitlist_capacity"]==10 and body["eligibility_grades"]==[3,4]
    assert "測試系所" in body["eligibility_description"]
    assert join(client,application,e).status_code==201
    with application.state.sessions.begin() as db:db.get(User,2).grade=2
    denied=join(client,application,e,2)
    assert denied.status_code==409 and "年級" in denied.json()["detail"]["message"]


def test_c11_same_unit_overlap_requires_confirmation_and_edit_checks(client,application,now,setup):
    first=setup()
    body=payload(now)
    denied=client.post("/events",json=body,headers=auth(application,3))
    assert denied.status_code==409
    assert denied.json()["detail"]["conflicts"][0]["id"]==first
    assert isinstance(denied.json()["detail"]["conflicts"][0]["start_time"],str)
    body["confirm_overlap"]=True
    second=client.post("/events",json=body,headers=auth(application,3))
    assert second.status_code==201
    # Same event excluded; changing time still sees the other event.
    changed=dict(start_time=body["start_time"],end_time=body["end_time"])
    assert client.patch(f"/events/{first}",json=changed,headers=auth(application,3)).status_code==409
    changed["confirm_overlap"]=True
    assert client.patch(f"/events/{first}",json=changed,headers=auth(application,5)).status_code==200


def test_c11_other_units_cancelled_and_touching_events_do_not_warn(client,application,now,setup):
    setup(unit_id=2)
    setup(is_cancelled=True)
    setup(starts_at=now["now"]+timedelta(days=3,hours=-1),ends_at=now["now"]+timedelta(days=3))
    response=client.post("/events",json=payload(now),headers=auth(application,3))
    assert response.status_code==201,response.text


def test_a10_profile_changes_only_future_eligibility(client,application,now,setup):
    first=setup(capacity=5,eligibility_department_ids=[1])
    assert join(client,application,first).status_code==201
    assert client.patch("/me/profile",json={"identity":"teacher","department_id":1},headers=auth(application,1)).status_code==422
    assert client.patch("/me/profile",json={"department_id":3,"grade":4},headers=auth(application,1)).status_code==200
    assert client.get(f"/events/{first}",headers=auth(application,1)).json()["my_registration_status"]=="已報名"
    second=setup(starts_at=now["now"]+timedelta(days=4),ends_at=now["now"]+timedelta(days=4,hours=2),eligibility_department_ids=[1])
    refused=join(client,application,second)
    assert refused.status_code==409 and refused.json()["detail"]["code"]=="ELIGIBILITY_MISMATCH"
    assert client.patch("/me/profile",json={"department_id":1},headers=auth(application,1)).status_code==422
    assert client.patch("/me/profile",json={"department_id":999,"grade":3},headers=auth(application,1)).status_code==422
    assert client.patch("/me/profile",json={"department_id":1,"grade":3},headers=auth(application,1)).status_code==200
    assert join(client,application,second).status_code==201


def test_d04_conflicts_are_structured_and_touching_is_allowed(client,application,now,setup):
    first=setup(name="既有活動",capacity=5)
    assert join(client,application,first).status_code==201
    overlap=setup()
    bad=join(client,application,overlap)
    assert bad.status_code==409 and bad.json()["detail"]["code"]=="TIME_CONFLICT"
    assert bad.json()["detail"]["conflicts"][0]["name"]=="既有活動"
    adjacent=setup(starts_at=now["now"]+timedelta(days=3,hours=2),ends_at=now["now"]+timedelta(days=3,hours=3))
    assert join(client,application,adjacent).status_code==201
    now["now"]+=timedelta(days=2)
    new=setup(starts_at=now["now"]+timedelta(days=1),ends_at=now["now"]+timedelta(days=1,hours=2),registration_closes_at=now["now"]+timedelta(hours=1))
    info=join(client,application,new).json()["detail"]["conflicts"][0]
    assert info["registration_closed"] and info["action"]=="request_cancellation"


def test_d05_waitlist_duplicate_status_roster_and_cancellation_rank(client,application,now,setup):
    e=setup(waitlist_enabled=True,waitlist_capacity=2)
    assert join(client,application,e).status_code==201
    second=join(client,application,e,2)
    assert second.status_code==201 and second.json()["status"]=="waitlisted" and second.json()["waitlist_position"]==1
    third=join(client,application,e,3)
    assert third.json()["waitlist_position"]==2
    repeated=join(client,application,e,2)
    assert repeated.status_code==200 and repeated.json()["registration_id"]==second.json()["registration_id"]
    assert join(client,application,e,5).json()["detail"]["code"]=="WAITLIST_FULL"
    mine=client.get("/me/events",headers=auth(application,2)).json()[0]
    assert mine["my_registration_status"]=="候補第 1 位"
    roster=client.get(f"/events/{e}/registrations",headers=auth(application,5)).json()
    assert roster["waitlist_count"]==2 and roster["registration_count"]==1
    assert cancel(client,application,e,2).status_code==200
    assert client.get(f"/events/{e}",headers=auth(application,3)).json()["waitlist_position"]==1
    assert client.get(f"/events/{e}/registrations",headers=auth(application,1)).status_code==403


def test_e05_promotion_rechecks_profile_and_skips_ineligible(client,application,now,setup):
    e=setup(waitlist_enabled=True,waitlist_capacity=4,eligibility_department_ids=[1])
    join(client,application,e,1);join(client,application,e,2);join(client,application,e,3)
    assert client.patch("/me/profile",json={"department_id":3,"grade":3},headers=auth(application,2)).status_code==200
    assert cancel(client,application,e).status_code==200
    assert client.get(f"/events/{e}",headers=auth(application,3)).json()["my_registration_status"]=="已報名"
    with application.state.sessions() as db:
        skipped=db.scalar(select(Registration).where(Registration.event_id==e,Registration.user_id==2))
        assert skipped.status=="not_promoted" and "系所" in skipped.cancellation_reason
    assert any("候補略過" in m.subject for m in mails(application))
    assert any("遞補成功" in m.subject for m in mails(application))


@pytest.mark.parametrize("source_status",["registered","waitlisted"])
def test_d11_e07_atomic_switch_success(client,application,now,setup,source_status):
    source=setup(waitlist_enabled=True,waitlist_capacity=3)
    if source_status=="waitlisted":join(client,application,source,2)
    join(client,application,source,1)
    if source_status=="registered":join(client,application,source,2)
    target=setup()
    switched=client.post(f"/events/{target}/registrations/switch",headers=auth(application,1),json={
        "source_event_ids":[source],"source_status":source_status,"confirmed":True})
    assert switched.status_code==200,switched.text
    assert switched.json()["status"]=="registered"
    assert client.get(f"/events/{source}",headers=auth(application,1)).json()["my_registration_status"]=="已取消"
    assert client.get(f"/events/{source}",headers=auth(application,2)).json()["my_registration_status"]=="已報名"


@pytest.mark.parametrize("source_status",["registered","waitlisted"])
def test_d11_e07_failed_switch_preserves_original_and_emails(client,application,now,setup,source_status):
    source=setup(waitlist_enabled=True,waitlist_capacity=2)
    if source_status=="waitlisted":join(client,application,source,2)
    original=join(client,application,source,1).json()
    target=setup(unit_id=2,waitlist_enabled=source_status=="registered",waitlist_capacity=2 if source_status=="registered" else None)
    join(client,application,target,3)
    count=len(mails(application))
    response=client.post(f"/events/{target}/registrations/switch",headers=auth(application,1),json={
        "source_event_ids":[source],"source_status":source_status,"confirmed":True})
    assert response.status_code==409,response.text
    with application.state.sessions() as db:
        assert db.get(Registration,original["registration_id"]).status==source_status
    assert len(mails(application))==count


def test_e07_waitlist_conflict_has_rank_and_stale_promotion_cannot_cancel_formal(client,application,now,setup):
    source=setup(waitlist_enabled=True,waitlist_capacity=3)
    join(client,application,source,2);join(client,application,source,1)
    target=setup()
    rejected=join(client,application,target)
    assert rejected.status_code==409 and rejected.json()["detail"]["code"]=="WAITLIST_CONFLICT"
    assert rejected.json()["detail"]["conflicts"][0]["waitlist_position"]==1
    cancel(client,application,source,2)
    response=client.post(f"/events/{target}/registrations/switch",headers=auth(application,1),json={
        "source_event_ids":[source],"source_status":"waitlisted","confirmed":True})
    assert response.status_code==409 and response.json()["detail"]["code"]=="SOURCE_STATUS_CHANGED"
    assert client.get(f"/events/{source}",headers=auth(application,1)).json()["my_registration_status"]=="已報名"


def test_d08_remove_permission_reason_notice_and_promotion(client,application,now,setup):
    e=setup(waitlist_enabled=True,waitlist_capacity=2)
    record=join(client,application,e).json();join(client,application,e,2)
    url=f"/events/{e}/registrations/{record['registration_id']}/remove"
    assert client.post(url,json={"reason":" ","confirmed":True},headers=auth(application,3)).status_code==422
    assert client.post(url,json={"reason":"資格不符","confirmed":True},headers=auth(application,1)).status_code==403
    assert client.post(url,json={"reason":"資格不符"},headers=auth(application,3)).status_code==422
    result=client.post(url,json={"reason":"資格不符","confirmed":True},headers=auth(application,5))
    assert result.status_code==200
    assert client.get(f"/events/{e}",headers=auth(application,2)).json()["my_registration_status"]=="已報名"
    assert any("已被移出名單" in m.subject and "資格不符" in m.body for m in mails(application))


def test_e06_deadline_expiration_is_idempotent_and_cancelled_waiter_excluded(client,application,now,setup):
    e=setup(waitlist_enabled=True,waitlist_capacity=3)
    join(client,application,e,1);join(client,application,e,2);join(client,application,e,3)
    cancel(client,application,e,3)
    now["now"]+=timedelta(days=2)
    assert jobs(application)["not_promoted"]==1
    count=len(mails(application))
    assert jobs(application)["not_promoted"]==0 and len(mails(application))==count
    assert len([m for m in mails(application) if "未獲遞補" in m.subject])==1
    assert client.get(f"/events/{e}",headers=auth(application,2)).json()["my_registration_status"]=="未遞補"


@pytest.mark.parametrize("decision",["approve","reject"])
def test_e11_e12_e14_request_review_permissions_and_result(client,application,now,setup,decision):
    e=setup()
    join(client,application,e)
    assert request(client,application,e).status_code==409
    now["now"]+=timedelta(days=2)
    created=request(client,application,e)
    assert created.status_code==201,created.text
    rid=created.json()["id"]
    assert request(client,application,e).status_code==409
    assert client.get(f"/events/{e}",headers=auth(application,1)).json()["my_registration_status"]=="取消申請審核中"
    assert client.get("/me/events",headers=auth(application,1)).json()[0]["cancellation_request"]["id"]==rid
    with application.state.sessions.begin() as db:db.get(Event,e).unit_id=2
    url=f"/cancellation-requests/{rid}/review"
    assert client.post(url,json={"decision":"approve"},headers=auth(application,5)).status_code==403
    assert client.post(url,json={"decision":"reject"},headers=auth(application,3)).status_code==422
    response=client.post(url,json={"decision":decision,"reason":"無法核准" if decision=="reject" else None},headers=auth(application,3))
    assert response.status_code==200,response.text
    expected="已取消" if decision=="approve" else "已報名"
    assert client.get(f"/events/{e}",headers=auth(application,1)).json()["my_registration_status"]==expected
    if decision=="reject":assert any("取消申請已拒絕" in m.subject and "無法核准" in m.body for m in mails(application))
    else:assert any("取消申請已核准" in m.subject for m in mails(application))
    assert client.post(url,json={"decision":"approve"},headers=auth(application,3)).status_code==409


@pytest.mark.parametrize("hours_to_start",[24,120])
def test_e11_e13_auto_approval_and_manager_alert_deadlines(client,application,now,setup,hours_to_start):
    e=setup(starts_at=now["now"]+timedelta(hours=hours_to_start+1),
            ends_at=now["now"]+timedelta(hours=hours_to_start+2),registration_closes_at=now["now"]+timedelta(hours=1))
    join(client,application,e)
    now["now"]+=timedelta(hours=1)
    created=request(client,application,e).json()
    notices=[m for m in mails(application) if m.subject.startswith("取消申請：")]
    assert {m.recipient for m in notices}=={"manager@test.invalid","manager2@test.invalid"}
    due=now["now"]+timedelta(hours=min(72,hours_to_start))
    now["now"]=due-timedelta(hours=24)
    assert jobs(application)["request_alerts"]==1
    assert jobs(application)["request_alerts"]==0
    now["now"]=due
    assert jobs(application)["auto_approved"]==1
    assert jobs(application)["auto_approved"]==0
    with application.state.sessions() as db:
        item=db.get(CancellationRequest,created["id"])
        assert item.status=="auto_approved" and item.active_registration_id is None
        assert db.get(Registration,item.registration_id).status=="cancelled"
    assert any("取消申請已自動核准" in m.subject for m in mails(application))


def test_e13_request_less_than_24h_before_due_has_no_second_alert(client,application,now,setup):
    e=setup(starts_at=now["now"]+timedelta(hours=12),ends_at=now["now"]+timedelta(hours=13),registration_closes_at=now["now"]+timedelta(hours=1))
    join(client,application,e);now["now"]+=timedelta(hours=2)
    assert request(client,application,e).status_code==201
    assert jobs(application)["request_alerts"]==0


def test_f03_direct_cancel_only_after_real_change_mail_delivery(client,application,now,setup):
    e=setup(waitlist_enabled=True,waitlist_capacity=2)
    join(client,application,e);join(client,application,e,2)
    now["now"]+=timedelta(days=2)
    assert client.patch(f"/events/{e}",json={"location":"新地點"},headers=auth(application,3)).status_code==200
    assert cancel(client,application,e).status_code==409 # queued != delivered
    with application.state.sessions.begin() as db:
        for mail in db.scalars(select(OutgoingEmail).where(OutgoingEmail.reschedule_notice.is_(True))):
            mail.status,mail.sent_at="sent",now["now"]
    assert cancel(client,application,e).status_code==200
    with application.state.sessions() as db:
        records=db.scalars(select(Registration).where(Registration.event_id==e)).all()
        assert [x.status for x in records]==["cancelled","waitlisted"]
        assert records[0].cancellation_reason=="改期後取消"


def test_f03_72h_window_boundary_and_notes_do_not_grant(client,application,now,setup):
    e=setup(starts_at=now["now"]+timedelta(days=8),ends_at=now["now"]+timedelta(days=8,hours=2))
    join(client,application,e);now["now"]+=timedelta(days=2)
    client.patch(f"/events/{e}",json={"notes":"新注意事項"},headers=auth(application,3))
    with application.state.sessions.begin() as db:
        for mail in db.scalars(select(OutgoingEmail).where(OutgoingEmail.kind=="event_change")):
            mail.status,mail.sent_at="sent",now["now"]
    assert cancel(client,application,e).status_code==409
    client.patch(f"/events/{e}",json={"location":"新地點"},headers=auth(application,3))
    with application.state.sessions.begin() as db:
        for mail in db.scalars(select(OutgoingEmail).where(OutgoingEmail.reschedule_notice.is_(True))):
            mail.status,mail.sent_at="sent",now["now"]
    now["now"]+=timedelta(hours=72)
    assert cancel(client,application,e).status_code==409
    assert request(client,application,e).status_code==201


@pytest.mark.parametrize("closed",[False,True])
def test_f05_capacity_increase_promotes_only_before_deadline(client,application,now,setup,closed):
    e=setup(waitlist_enabled=True,waitlist_capacity=5)
    join(client,application,e,1);join(client,application,e,2);join(client,application,e,3)
    if closed:now["now"]+=timedelta(days=2)
    response=client.patch(f"/events/{e}",json={"capacity":5},headers=auth(application,5))
    assert response.status_code==200,response.text
    assert response.json()["registration_count"]==(1 if closed else 3)
    if not closed:assert response.json()["status"]=="開放中" and response.json()["waitlist_count"]==0


def test_f04_changed_time_mail_contains_personal_conflicts_without_cancelling(client,application,now,setup):
    a=setup()
    b=setup(name="另一活動",starts_at=now["now"]+timedelta(days=4),ends_at=now["now"]+timedelta(days=4,hours=2))
    join(client,application,a);join(client,application,b)
    response=client.patch(f"/events/{a}",json={"start_time":s.as_utc(now["now"]+timedelta(days=4)).isoformat(),
        "end_time":s.as_utc(now["now"]+timedelta(days=4,hours=2)).isoformat(),"confirm_overlap":True},headers=auth(application,3))
    assert response.status_code==200,response.text
    assert "另一活動" in mails(application,"event_change")[0].body
    assert len(client.get("/me/events",headers=auth(application,1)).json())==2


def test_e08_reminder_token_is_private_read_only_and_idempotent(client,application,now,setup):
    e=setup(capacity=3,notes="請準時")
    registration=join(client,application,e).json()
    now["now"]+=timedelta(days=2)
    assert jobs(application)["reminders"]==1
    assert jobs(application)["reminders"]==0
    mail=mails(application,"event_reminder")[0]
    assert "請準時" in mail.body and "取消期限" in mail.body
    token=re.search(r"#cancel_token=(\S+)",mail.body).group(1)
    assert client.get(f"/events/{e}").status_code==200
    assert client.post("/me/cancellation-action",json={"token":token}).status_code==401
    assert client.post("/me/cancellation-action",json={"token":token},headers=auth(application,2)).status_code==400
    context=client.post("/me/cancellation-action",json={"token":token},headers=auth(application,1))
    assert context.status_code==200 and context.json()["action"]=="request_cancellation"
    with application.state.sessions() as db:assert db.get(Registration,registration["registration_id"]).status=="registered"


def test_e08_late_joiners_waiters_and_cancelled_records_do_not_receive_reminder(client,application,now,setup):
    e=setup(waitlist_enabled=True,waitlist_capacity=3)
    join(client,application,e,1);join(client,application,e,2)
    late=setup(starts_at=now["now"]+timedelta(hours=12),ends_at=now["now"]+timedelta(hours=13),
        registration_closes_at=now["now"]+timedelta(hours=10))
    join(client,application,late,3)
    assert jobs(application)["reminders"]==0
    now["now"]+=timedelta(days=2)
    assert jobs(application)["reminders"]==1
    assert {m.recipient for m in mails(application,"event_reminder")}=={"member@test.invalid"}


def test_e08_reschedule_invalidates_old_pending_reminder_and_replans(client,application,now,setup,monkeypatch):
    e=setup()
    join(client,application,e);now["now"]+=timedelta(days=2)
    jobs(application)
    old_mail=mails(application,"event_reminder")[0]
    response=client.patch(f"/events/{e}",json={"start_time":s.as_utc(now["now"]+timedelta(days=8)).isoformat(),
        "end_time":s.as_utc(now["now"]+timedelta(days=8,hours=2)).isoformat()},headers=auth(application,3))
    assert response.status_code==200,response.text
    sent=[]
    monkeypatch.setattr(operations,"smtp_send",lambda settings,to,subject,body:sent.append(subject))
    operations.process_mail(application.state.sessions,application.state.settings)
    assert not any("活動前一天提醒" in subject for subject in sent)
    with application.state.sessions() as db:assert db.get(OutgoingEmail,old_mail.id).status=="cancelled"
    now["now"]+=timedelta(days=7)
    assert jobs(application)["reminders"]==1 and jobs(application)["reminders"]==0


def test_g02_csv_bom_formula_protection_permissions_and_audit(client,application,now,setup):
    e=setup()
    with application.state.sessions.begin() as db:db.get(User,1).name="=HYPERLINK(1)"
    join(client,application,e)
    url=f"/events/{e}/registrations.csv"
    assert client.get(url,headers=auth(application,1)).status_code==403
    response=client.get(url,headers=auth(application,5))
    assert response.status_code==200 and response.content.startswith(b"\xef\xbb\xbf")
    body=response.content.decode("utf-8-sig")
    assert "姓名,身分別,系所,年級,Email" in body and "'=HYPERLINK(1)" in body
    with application.state.sessions() as db:
        record=db.scalar(select(AuditLog).where(AuditLog.action=="roster.export"))
        assert record.actor_id==5 and record.details["registration_count"]==1


def test_g04_g05_g06_check_in_selection_counts_undo_and_h01_correction(client,application,now,setup):
    e=setup(capacity=2)
    one=join(client,application,e,1).json();two=join(client,application,e,2).json()
    with application.state.sessions.begin() as db:db.get(User,2).name="測試會員"
    # Original start is three days later; cannot check in early.
    path=f"/events/{e}/registrations/{one['registration_id']}/check-in"
    assert client.post(path,headers=auth(application,3)).status_code==409
    now["now"]+=timedelta(days=3)
    roster=client.get(f"/events/{e}/registrations",params={"q":"測試會員"},headers=auth(application,3)).json()
    assert len(roster["registrations"])==2
    assert client.post(path,headers=auth(application,1)).status_code==403
    assert client.post(path,headers=auth(application,3)).json()["checked_in_count"]==1
    assert client.post(path,headers=auth(application,5)).json()["checked_in_count"]==1
    assert client.delete(path,headers=auth(application,5)).json()["checked_in_count"]==0
    assert client.post(path,headers=auth(application,3)).json()["checked_in_count"]==1
    now["now"]+=timedelta(hours=2)
    assert jobs(application)["absences"]==1
    now["now"]+=timedelta(days=3)
    url=f"/events/{e}/registrations/{two['registration_id']}/attendance"
    assert client.patch(url,json={"status":"present"},headers=auth(application,5)).status_code==200
    assert client.patch(url,json={"status":"leave"},headers=auth(application,5)).status_code==422
    now["now"]+=timedelta(days=5)
    assert client.patch(url,json={"status":"absent"},headers=auth(application,3)).status_code==409
    history=client.get("/me/events/history",headers=auth(application,2)).json()
    assert history[0]["attendance_status"]=="出席"


def test_g04_waiters_and_foreign_registration_cannot_check_in(client,application,now,setup):
    e=setup(waitlist_enabled=True,waitlist_capacity=2)
    join(client,application,e,1);waiting=join(client,application,e,2).json()
    other=setup(unit_id=2)
    foreign=join(client,application,other,3).json()
    now["now"]+=timedelta(days=3)
    for record in (waiting,foreign):
        assert client.post(f"/events/{e}/registrations/{record['registration_id']}/check-in",headers=auth(application,3)).status_code==404
    assert jobs(application)["absences"]==0 # no actual check-in means no attendance inference


def test_i07_identity_is_admin_only_clears_grade_and_audits_before_after(client,application,now,setup):
    data={"identity":"teacher","department_id":1,"grade":3}
    assert client.patch("/admin/users/1/identity",json=data,headers=auth(application,3)).status_code==403
    result=client.patch("/admin/users/1/identity",json=data,headers=auth(application,4))
    assert result.status_code==200 and result.json()["identity"]=="teacher" and result.json()["grade"] is None
    with application.state.sessions() as db:
        item=db.scalar(select(AuditLog).where(AuditLog.action=="identity.correct"))
        assert item.actor_id==4 and item.details["before"]["identity"]=="student" and item.details["after"]["grade"] is None
    assert client.patch("/admin/users/1/identity",json={"identity":"student","department_id":1},headers=auth(application,4)).status_code==422


def test_j01_audit_routes_permissions_retention_and_immutability(client,application,now,setup):
    admin=auth(application,4)
    assert client.get("/admin/users",params={"q":"測試"},headers=admin).status_code==200
    assert client.put("/admin/units/1/managers/2",headers=admin).status_code==200
    assert client.delete("/admin/units/1/managers/2",headers=admin).status_code==200
    e=setup()
    assert client.post(f"/events/{e}/cancel",json={"reason":"取消"},headers=auth(application,3)).status_code==200
    assert client.get("/admin/audit-logs",headers=auth(application,1)).status_code==403
    rows=client.get("/admin/audit-logs",headers=admin).json()
    assert {x["action"] for x in rows}>={"user.search","unit_manager.assign","unit_manager.revoke","event.cancel"}
    logid=rows[0]["id"]
    assert client.patch(f"/admin/audit-logs/{logid}",json={},headers=admin).status_code in (404,405)
    assert client.delete(f"/admin/audit-logs/{logid}",headers=admin).status_code in (404,405)
    with application.state.sessions() as db:
        row=db.get(AuditLog,logid);row.action="tamper"
        with pytest.raises(ValueError,match="append-only"):db.commit()
        db.rollback();db.delete(db.get(AuditLog,logid))
        with pytest.raises(ValueError,match="append-only"):db.commit()
        db.rollback()
    now["now"]+=timedelta(days=367)
    jobs(application)
    assert any(x["id"]==logid for x in client.get("/admin/audit-logs",headers=admin).json())


def test_r3_registration_and_mail_rollback_together(client,application,now,setup,monkeypatch):
    e=setup()
    def fail(*args,**kwargs):raise RuntimeError("outbox unavailable")
    monkeypatch.setattr(r3,"notify_registration",fail)
    with pytest.raises(RuntimeError):s.register(application.state.sessions,e,1)
    with application.state.sessions() as db:
        assert s.count_registrations(db,e)==0
        assert db.scalar(select(func.count()).select_from(OutgoingEmail))==0


def test_d05_1000_contenders_100_seats_and_900_waiters_no_duplicates(application,now,setup):
    e=setup(capacity=100,waitlist_enabled=True,waitlist_capacity=900)
    with application.state.sessions.begin() as db:
        hashed=db.get(User,1).password_hash
        users=[User(email=f"r3-{i}@test.invalid",name="併發測試",password_hash=hashed,email_verified=True) for i in range(1000)]
        db.add_all(users);db.flush();ids=[u.id for u in users]
    with ThreadPoolExecutor(max_workers=32) as executor:
        results=list(executor.map(lambda uid:s.register(application.state.sessions,e,uid),ids))
    assert sum(x["status"]=="registered" for x in results)==100
    assert sorted(x["waitlist_position"] for x in results if x["status"]=="waitlisted")==list(range(1,901))
    assert len({x["registration_id"] for x in results})==1000
    with ThreadPoolExecutor(max_workers=16) as executor:
        duplicates=list(executor.map(lambda _:s.register(application.state.sessions,e,ids[-1]),range(30)))
    assert all(x["already_registered"] for x in duplicates)
    with application.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Registration).where(Registration.event_id==e))==1000
        assert db.scalar(select(func.count()).select_from(OutgoingEmail))==1000


def test_e05_ten_simultaneous_cancellations_promote_exactly_ten(application,now,setup):
    e=setup(capacity=10,waitlist_enabled=True,waitlist_capacity=10)
    with application.state.sessions.begin() as db:
        hashed=db.get(User,1).password_hash
        users=[User(email=f"promote-{i}@test.invalid",name="遞補測試",password_hash=hashed,email_verified=True) for i in range(20)]
        db.add_all(users);db.flush();ids=[u.id for u in users]
    for uid in ids:s.register(application.state.sessions,e,uid)
    with ThreadPoolExecutor(max_workers=10) as executor:
        results=list(executor.map(lambda uid:s.cancel_registration(application.state.sessions,e,uid),ids[:10]))
    assert len(results)==10
    with application.state.sessions() as db:
        assert s.count_registrations(db,e)==10 and len(r3.waitlist(db,e))==0
        assert set(db.scalars(select(Registration.user_id).where(Registration.event_id==e,Registration.status=="registered")))==set(ids[10:])
    assert len([m for m in mails(application) if "遞補成功" in m.subject])==10
