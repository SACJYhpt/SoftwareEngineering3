"""R3 domain operations, sharing R2 sessions, permissions and durable mail outbox.

Mutations acquire the database workflow gate BEFORE event rows (ascending id).
This also serializes cross-event conflict checks and atomic switches/promotions.
The gate is intentionally coarse; it is not a Python lock or another database.
"""
from datetime import datetime, timedelta, timezone
import csv
import io

import jwt
from fastapi import HTTPException
from sqlalchemy import func, or_, select, text

from . import services as s
from .models import (AuditLog, CancellationRequest, Event, OutgoingEmail,
                     Registration, RegistrationWorkflowLock, Unit, UnitManager, User)

ACTIVE = ("registered", "waitlisted")


def workflow_lock(db):
    if db.bind.dialect.name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
        if not db.in_transaction():
            db.execute(text("BEGIN IMMEDIATE"))
        db.execute(insert(RegistrationWorkflowLock).values(id=1).on_conflict_do_nothing())
    else:
        from sqlalchemy.dialects.mysql import insert
        db.execute(insert(RegistrationWorkflowLock).values(id=1).on_duplicate_key_update(id=1))
    db.scalar(select(RegistrationWorkflowLock).where(RegistrationWorkflowLock.id == 1).with_for_update())


def lock_events(db, ids):
    workflow_lock(db)
    result = {}
    for event_id in sorted(set(ids)):
        event = db.scalar(select(Event).where(Event.id == event_id).with_for_update())
        if event is None:
            s.fail(404, "EVENT_NOT_FOUND", "找不到活動")
        result[event_id] = event
    return result


def audit(db, actor_id, action, target, **details):
    db.add(AuditLog(actor_id=actor_id, action=action, target=str(target),
                    recorded_at=s.utc_now(), details=details))


def waitlist(db, event_id):
    return db.scalars(select(Registration).where(Registration.event_id == event_id,
                      Registration.status == "waitlisted")
                      .order_by(Registration.waitlisted_at, Registration.id)).all()


def position(db, record):
    if record.status != "waitlisted":
        return None
    return next((n for n, r in enumerate(waitlist(db, record.event_id), 1) if r.id == record.id), None)


def eligibility_description(db, event):
    conditions = []
    labels = {"student": "學生", "teacher": "教師", "staff": "行政人員"}
    if event.eligibility_identities:
        conditions.append("身分別：" + "／".join(labels[x] for x in event.eligibility_identities))
    if event.eligibility_department_ids:
        names = db.scalars(select(Unit.name).where(Unit.id.in_(event.eligibility_department_ids)).order_by(Unit.id)).all()
        conditions.append("系所／單位：" + "／".join(names))
    if event.eligibility_grades:
        conditions.append("年級：" + "／".join(map(str, event.eligibility_grades)))
    return "；".join(conditions) or "不限"


def eligibility_errors(event, user):
    errors = []
    if not user.is_active or not user.email_verified:
        errors.append("帳號須已驗證且啟用")
    if event.eligibility_identities and user.identity not in event.eligibility_identities:
        errors.append("身分別不符")
    if event.eligibility_department_ids and user.department_id not in event.eligibility_department_ids:
        errors.append("系所／單位不符")
    if event.eligibility_grades and user.grade not in event.eligibility_grades:
        errors.append("年級不符")
    return errors


def validate_eligibility_settings(db, payload):
    ids = set(payload.eligibility_department_ids)
    if ids:
        actual = set(db.scalars(select(Unit.id).where(Unit.id.in_(ids), Unit.is_active.is_(True),
                                                      Unit.kind.in_(("department", "office")))))
        if ids != actual:
            s.fail(422, "ELIGIBILITY_UNIT_INVALID", "資格限制須使用啟用中的系所或行政單位")


def overlap_warning(db, unit_id, start, end, confirmed, exclude=None):
    rows = db.scalars(select(Event).where(Event.unit_id == unit_id, Event.id != (exclude or -1),
                       Event.is_cancelled.is_(False), Event.starts_at < end, Event.ends_at > start)
                       .order_by(Event.starts_at, Event.id)).all()
    if rows and not confirmed:
        raise HTTPException(409, dict(code="SCHEDULE_OVERLAP_CONFIRMATION_REQUIRED",
            message="與同單位活動時間重疊，確認後可儲存", conflicts=[dict(id=e.id, name=e.name,
                start_time=s.as_utc(e.starts_at).isoformat(), end_time=s.as_utc(e.ends_at).isoformat()) for e in rows]))


def conflicts(db, user_id, event, ignore=()):
    now = s.utc_now()
    rows = db.execute(select(Event, Registration).join(Registration, Registration.event_id == Event.id)
        .where(Registration.user_id == user_id, Registration.status.in_(ACTIVE), Event.id != event.id,
               Event.id.not_in(list(ignore)), Event.is_cancelled.is_(False),
               # Closed waitlists cannot promote, even during the worker's
               # short polling delay. Do not block another registration on one.
               or_(Registration.status != "waitlisted", Event.registration_closes_at > now),
               Event.starts_at < event.ends_at, Event.ends_at > event.starts_at)
        .order_by(Event.starts_at, Event.id)).all()
    return [dict(event_id=e.id, name=e.name, start_time=s.as_utc(e.starts_at).isoformat(), end_time=s.as_utc(e.ends_at).isoformat(),
                 status=r.status, waitlist_position=position(db, r),
                 registration_closed=now >= e.registration_closes_at,
                 action="switch" if now < e.registration_closes_at else "request_cancellation",
                 action_path=f"/events/{e.id}/" + ("registrations/me" if now < e.registration_closes_at else "cancellation-requests"))
            for e, r in rows]


def require_eligibility_and_no_conflicts(db, event, user, ignore=()):
    errors = eligibility_errors(event, user)
    if errors:
        raise HTTPException(409, dict(code="ELIGIBILITY_MISMATCH", message="；".join(errors) + "；" + eligibility_description(db, event), conditions=errors))
    overlaps = conflicts(db, user.id, event, ignore)
    if overlaps:
        code = "TIME_CONFLICT" if any(x["status"] == "registered" for x in overlaps) else "WAITLIST_CONFLICT"
        raise HTTPException(409, dict(code=code, message="與既有報名或候補活動撞期，請選擇取消本次或確認改報名", conflicts=overlaps))


def notify_registration(db, event, record, label, detail="", kind="registration", key=None):
    user = db.get(User, record.user_id)
    settings = db.info.get("settings")
    url = (settings.public_base_url if settings else "") + f"/events/{event.id}"
    body = (f"活動：{event.name}\n時間：{s.change_display(event.starts_at)} - {s.change_display(event.ends_at)}"
            f"\n地點：{event.location}\n目前狀態：{label}\n{detail}\n活動詳情：{url}")
    mail = OutgoingEmail(recipient=user.email, subject=f"{label}：{event.name}", body=body,
                         created_at=s.utc_now(), next_attempt_at=s.utc_now(), kind=kind,
                         registration_id=record.id, registration_revision=record.revision,
                         deduplication_key=key)
    db.add(mail)
    return mail


def result_view(db, record, event, existing=False):
    count = s.count_registrations(db, event.id)
    n = position(db, record)
    label = f"候補第 {n} 位" if n else "已報名"
    result = s.registration_view(record,count,event.capacity,existing)
    result.update(message=("已加入候補，目前第 " + str(n) + " 位") if n else result["message"],
                  status=record.status,registration_status=label,waitlist_position=n,
                  waitlist_count=len(waitlist(db,event.id)))
    return result


def register_in_transaction(db, event, user, *, formal_only=False):
    if not event.is_public:
        s.fail(404, "EVENT_NOT_FOUND", "找不到活動")
    if user is None or not user.is_active:
        s.fail(401, "AUTH_REQUIRED", "請先登入")
    if event.is_cancelled:
        s.fail(409, "EVENT_CANCELLED", "活動已取消")
    existing = s.find_registration(db, event.id, user.id, False)
    if existing is not None and existing.status in ACTIVE:
        return result_view(db, existing, event, True)
    now = s.utc_now()
    if now >= event.starts_at:
        s.fail(409, "EVENT_STARTED", "活動已開始")
    if now < event.registration_opens_at:
        s.fail(409, "REGISTRATION_NOT_OPEN", "報名尚未開始")
    if now >= event.registration_closes_at:
        s.fail(409, "REGISTRATION_CLOSED", "報名已截止")
    require_eligibility_and_no_conflicts(db, event, user)
    full = event.capacity is not None and s.count_registrations(db, event.id) >= event.capacity
    if full and (formal_only or not event.waitlist_enabled):
        s.fail(409, "EVENT_FULL", "名額已滿")
    if full and len(waitlist(db, event.id)) >= event.waitlist_capacity:
        s.fail(409, "WAITLIST_FULL", "名額與候補皆已額滿")
    record = existing or Registration(event_id=event.id, user_id=user.id, registered_at=now)
    if existing:
        record.revision += 1
    else:
        record.revision = 1
    record.status = "waitlisted" if full else "registered"
    record.registered_at, record.cancelled_at, record.cancellation_reason = now, None, None
    record.waitlisted_at = now if full else None
    record.attendance_status, record.checked_in_at = "unrecorded", None
    db.add(record); db.flush()
    result = result_view(db, record, event)
    notify_registration(db, event, record, result["registration_status"],
                        key=f"registration:{record.id}:{record.revision}")
    return result


def promote(db, event):
    now = s.utc_now()
    if event.is_cancelled or not event.is_public or now >= event.registration_closes_at or now >= event.starts_at:
        return []
    promoted = []
    for record in waitlist(db, event.id):
        if event.capacity is not None and s.count_registrations(db, event.id) >= event.capacity:
            break
        user = db.get(User, record.user_id)
        errors = eligibility_errors(event, user) if user else ["找不到帳號"]
        overlap = conflicts(db, record.user_id, event)
        if errors or overlap:
            record.status = "not_promoted"
            record.cancellation_reason = "；".join(errors) or "與既有報名／候補撞期"
            db.flush()
            notify_registration(db, event, record, "候補略過", record.cancellation_reason)
            continue
        record.status, record.registered_at = "registered", now
        db.flush()
        notify_registration(db, event, record, "遞補成功", f"已成為正式報名者。可於 {s.change_display(event.registration_closes_at)} 前至活動詳情取消報名。")
        promoted.append(record.id)
    return promoted


def pending_request(db, record):
    return db.scalar(select(CancellationRequest).where(CancellationRequest.active_registration_id == record.id))


def request_view(item):
    return dict(id=item.id, registration_id=item.registration_id, status=item.status, reason=item.reason,
                submitted_at=s.as_utc(item.submitted_at), auto_approve_at=s.as_utc(item.auto_approve_at),
                processed_at=s.as_utc(item.processed_at) if item.processed_at else None,
                rejection_reason=item.rejection_reason)


def direct_cancel_deadline(db, event, record, now):
    if record.status not in ACTIVE or event.is_cancelled or now >= event.starts_at:
        return None
    if now < event.registration_closes_at:
        return event.registration_closes_at
    if record.status != "registered":
        return None
    sent = db.scalar(select(func.max(OutgoingEmail.sent_at)).where(OutgoingEmail.registration_id == record.id,
        OutgoingEmail.registration_revision == record.revision, OutgoingEmail.reschedule_notice.is_(True),
        OutgoingEmail.status == "sent"))
    if sent is None:
        return None
    deadline = min(sent + timedelta(hours=72), event.starts_at)
    return deadline if now < deadline else None


def can_direct_cancel(db, event, record, now):
    return direct_cancel_deadline(db, event, record, now) is not None


def cancel_record(db, event, record, reason, allow_promotion=True, notice="已取消報名"):
    record.status, record.cancelled_at, record.cancellation_reason = "cancelled", s.utc_now(), reason
    record.attendance_status, record.checked_in_at = "unrecorded", None
    item = pending_request(db, record)
    if item:
        item.status, item.active_registration_id, item.processed_at = "approved", None, s.utc_now()
        notify_request_result(db, event, record, item)
    db.flush()
    notify_registration(db, event, record, notice, reason)
    if allow_promotion:
        promote(db, event)


def cancel_in_transaction(db, event, user_id):
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        s.fail(401, "AUTH_REQUIRED", "請先登入")
    record = s.find_registration(db, event.id, user_id, False)
    if record is None or record.status not in ACTIVE:
        s.fail(404, "REGISTRATION_NOT_FOUND", "找不到本人的有效報名或候補")
    now = s.utc_now()
    if event.is_cancelled:
        s.fail(409, "EVENT_CANCELLED", "活動已取消")
    if now >= event.starts_at:
        s.fail(409, "EVENT_STARTED", "活動已開始")
    if not can_direct_cancel(db, event, record, now):
        s.fail(409, "REGISTRATION_CLOSED", "報名已截止，請提出取消申請")
    late = now >= event.registration_closes_at
    cancel_record(db, event, record, "改期後取消" if late else "本人取消", not late)
    return dict(message="已取消報名", registration_id=record.id, event_id=event.id,
                status="cancelled", registration_count=s.count_registrations(db, event.id), capacity=event.capacity)


def switch_registration(sessions, event_id, user_id, payload):
    with sessions() as db:
        try:
            ids = set(payload.source_event_ids)
            if event_id in ids:
                s.fail(422, "SWITCH_SOURCE_INVALID", "原活動不可為新活動")
            events = lock_events(db, ids | {event_id})
            target = events[event_id]
            existing = s.find_registration(db, target.id, user_id, False)
            if existing and existing.status in ACTIVE:
                s.fail(409, "ALREADY_REGISTERED", "新活動已報名或候補，原活動未變更")
            originals = []
            for source_id in sorted(ids):
                event = events[source_id]
                record = s.find_registration(db, source_id, user_id, False)
                if not record or record.status != payload.source_status:
                    raise HTTPException(409, dict(code="SOURCE_STATUS_CHANGED", message="原報名狀態已改變，請重新確認", conflicts=conflicts(db, user_id, target)))
                if not (event.starts_at < target.ends_at and event.ends_at > target.starts_at):
                    s.fail(422, "SWITCH_SOURCE_NOT_CONFLICTING", "原活動與新活動沒有撞期")
                if not can_direct_cancel(db, event, record, s.utc_now()) or s.utc_now() >= event.registration_closes_at:
                    s.fail(409, "REGISTRATION_CLOSED", "原活動已截止，請提出取消申請")
                originals.append((event, record))
                # Temporarily release inside this transaction; any failure rolls it back.
                record.status = "cancelled"
            db.flush()
            result = register_in_transaction(db, target, db.get(User, user_id), formal_only=payload.source_status == "registered")
            for event, record in originals:
                cancel_record(db, event, record, "確認改報名", True)
            db.commit()
            return result
        except Exception:
            db.rollback(); raise


def update_profile(db, user_id, payload, actor_id=None):
    workflow_lock(db)
    user = db.get(User, user_id)
    if user is None:
        s.fail(404, "USER_NOT_FOUND", "找不到使用者")
    before = dict(identity=user.identity, department_id=user.department_id, grade=user.grade)
    identity = payload.identity if actor_id is not None else user.identity
    unit = db.get(Unit, payload.department_id)
    if identity not in ("student", "teacher", "staff"):
        s.fail(422, "IDENTITY_REQUIRED", "請聯絡系統管理員更正身分別")
    if unit is None or not unit.is_active or unit.kind != s.home_unit_kind(identity):
        s.fail(422, "DEPARTMENT_INVALID", "請選擇對應身分別的啟用系所或行政單位")
    if identity == "student" and payload.grade is None:
        s.fail(422, "GRADE_REQUIRED", "學生必須填寫年級")
    user.identity, user.department_id, user.grade = identity, unit.id, payload.grade if identity == "student" else None
    if actor_id is not None:
        audit(db, actor_id, "identity.correct", user_id, before=before,
              after=dict(identity=user.identity, department_id=user.department_id, grade=user.grade))
    db.commit()
    return s.user_view(db, user)


def managers_notify(db, event, subject, body):
    people = db.scalars(select(User).join(UnitManager, UnitManager.user_id == User.id)
        .where(UnitManager.unit_id == event.unit_id, User.is_active.is_(True), User.email_verified.is_(True))).all()
    for user in people:
        s.queue_email(db, user.email, subject, body)


def notify_request_result(db, event, record, item):
    labels = {"approved": "取消申請已核准", "rejected": "取消申請已拒絕", "auto_approved": "取消申請已自動核准"}
    notify_registration(db, event, record, labels[item.status], item.rejection_reason or "",
                        key=f"cancellation-result:{item.id}")


def submit_request(db, event_id, user_id, reason):
    event = lock_events(db, [event_id])[event_id]
    record = s.find_registration(db, event_id, user_id)
    now = s.utc_now()
    if not record:
        s.fail(404, "REGISTRATION_NOT_FOUND", "僅限本人正式報名提出申請")
    if event.is_cancelled or now < event.registration_closes_at or now >= event.starts_at:
        s.fail(409, "CANCELLATION_REQUEST_UNAVAILABLE", "僅可於截止後、活動開始前提出申請")
    if pending_request(db, record):
        s.fail(409, "CANCELLATION_REQUEST_PENDING", "已有待處理的取消申請")
    item = CancellationRequest(registration_id=record.id, active_registration_id=record.id,
         reason=reason, status="pending", submitted_at=now, auto_approve_at=min(now+timedelta(hours=72), event.starts_at))
    db.add(item); db.flush()
    managers_notify(db, event, f"取消申請：{event.name}", f"申請編號：{item.id}\n申請者：{db.get(User,user_id).name}\n原因：{reason}\n未處理將於 {s.change_display(item.auto_approve_at)} 自動核准。")
    db.commit()
    return request_view(item)


def complete_request(db, item, status, reviewer=None, reason=None):
    record = db.get(Registration, item.registration_id)
    event = db.get(Event, record.event_id)
    item.status, item.active_registration_id, item.processed_at = status, None, s.utc_now()
    item.reviewed_by, item.rejection_reason = reviewer, reason
    if status != "rejected":
        cancel_record(db, event, record, "取消申請核准", False)
    notify_request_result(db, event, record, item)
    db.flush()


def review_request(db, request_id, user_id, payload):
    workflow_lock(db)
    item = db.get(CancellationRequest, request_id)
    if item is None:
        s.fail(404, "CANCELLATION_REQUEST_NOT_FOUND", "找不到取消申請")
    record = db.get(Registration, item.registration_id)
    event = s.managed_event(db, record.event_id, user_id)
    if item.status != "pending":
        s.fail(409, "CANCELLATION_REQUEST_PROCESSED", "申請已處理")
    if s.utc_now() >= item.auto_approve_at:
        complete_request(db, item, "auto_approved"); db.commit()
        return request_view(item)
    complete_request(db, item, "approved" if payload.decision == "approve" else "rejected", user_id, payload.reason)
    db.commit()
    return request_view(item)


def remove_registrant(db, event_id, registration_id, user_id, reason):
    event = lock_events(db, [event_id])[event_id]
    s.require_manage_unit(db, user_id, event.unit_id)
    record = db.get(Registration, registration_id)
    if record is None or record.event_id != event_id or record.status not in ACTIVE:
        s.fail(404, "REGISTRATION_NOT_FOUND", "找不到該活動的有效報名")
    cancel_record(db, event, record, "管理者移出："+reason, True, notice="已被移出名單")
    audit(db, user_id, "registration.remove", record.id, event_id=event.id, reason=reason)
    db.commit()
    return dict(registration_id=record.id, status="cancelled", registration_count=s.count_registrations(db,event_id))


def attendance_counts(db, event):
    count = s.count_registrations(db, event.id)
    checked = db.scalar(select(func.count()).select_from(Registration).where(Registration.event_id == event.id,
        Registration.status == "registered", Registration.attendance_status == "present"))
    return dict(event_id=event.id, registration_count=count, checked_in_count=checked, check_in_used=event.check_in_used)


def set_attendance(db, event_id, registration_id, user_id, action):
    event = lock_events(db, [event_id])[event_id]
    s.require_manage_unit(db, user_id, event.unit_id)
    record = db.get(Registration, registration_id)
    if record is None or record.event_id != event.id or record.status != "registered":
        s.fail(404, "REGISTRATION_NOT_FOUND", "僅限該活動的正式報名者")
    now = s.utc_now()
    if event.is_cancelled:
        s.fail(409, "EVENT_CANCELLED", "活動已取消")
    if action in ("check_in", "undo"):
        taiwan = timezone(timedelta(hours=8))
        if s.as_utc(now).astimezone(taiwan).date() != s.as_utc(event.starts_at).astimezone(taiwan).date() or now >= event.ends_at:
            s.fail(409, "CHECK_IN_UNAVAILABLE", "僅能在活動當天且結束前報到或撤銷")
        if action == "check_in":
            event.check_in_used = True
            if record.attendance_status != "present":
                record.attendance_status, record.checked_in_at = "present", now
        else:
            record.attendance_status, record.checked_in_at = "unrecorded", None
    else:
        if not event.ends_at <= now < event.ends_at+timedelta(days=7):
            s.fail(409, "ATTENDANCE_CORRECTION_CLOSED", "僅可於活動結束後 7 天內修正")
        event.check_in_used = True
        record.attendance_status = action
        record.checked_in_at = now if action == "present" else None
    db.flush()
    result = dict(attendance_counts(db, event), registration_id=record.id, attendance_status=record.attendance_status)
    db.commit()
    return result


def export_roster(db, event_id, user_id):
    event = s.managed_event(db, event_id, user_id)
    rows = s.registration_roster(db, event_id, user_id)["registrations"]
    output = io.StringIO(newline="")
    writer = csv.writer(output); writer.writerow(["姓名", "身分別", "系所", "年級", "Email"])
    def safe(value):
        value = "" if value is None else str(value)
        return "'" + value if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else value
    for row in rows:
        writer.writerow([safe(row["name"]), safe({"student":"學生","teacher":"教師","staff":"行政人員"}.get(row["identity"],row["identity"])),
                         safe(row["department"]["name"] if row["department"] else ""), safe(row["grade"]), safe(row["email"])])
    audit(db, user_id, "roster.export", event.id, registration_count=len(rows))
    db.commit()
    return output.getvalue().encode("utf-8-sig")


def registration_context(db, event, user, activity_status):
    waiting = waitlist(db,event.id) if event.waitlist_enabled else []
    data = dict(waitlist_enabled=event.waitlist_enabled, waitlist_capacity=event.waitlist_capacity,
        eligibility_identities=event.eligibility_identities, eligibility_department_ids=event.eligibility_department_ids,
        eligibility_grades=event.eligibility_grades, eligibility_description=eligibility_description(db,event),
        waitlist_count=len(waiting), waitlist_position=None, cancellation_request=None,
        can_request_cancellation=False, can_cancel_registration=False, direct_cancel_deadline=None)
    if user is None:
        return data
    record = s.find_registration(db,event.id,user.id,False)
    n = position(db, record) if record else None
    request = pending_request(db,record) if record else None
    data["my_registration_status"] = ("取消申請審核中" if request else f"候補第 {n} 位" if n else
        {"registered":"已報名", "cancelled":"已取消", "not_promoted":"未遞補"}.get(record.status,"未報名") if record else "未報名")
    data["waitlist_position"] = n
    if request:
        data["cancellation_request"] = request_view(request)
    now = s.utc_now()
    deadline = direct_cancel_deadline(db,event,record,now) if record is not None else None
    data["direct_cancel_deadline"] = s.as_utc(deadline) if deadline is not None else None
    data["can_cancel_registration"] = deadline is not None
    data["can_request_cancellation"] = bool(record and record.status == "registered" and request is None
        and not event.is_cancelled and event.registration_closes_at <= now < event.starts_at)
    data["can_register"] = bool(user.is_active and (record is None or record.status not in ACTIVE) and
        (activity_status == "開放中" or (activity_status == "已額滿" and event.waitlist_enabled and len(waiting)<event.waitlist_capacity)))
    return data


def notify_event_change(db,event,differences,rescheduled):
    records = db.scalars(select(Registration).where(Registration.event_id==event.id, Registration.status.in_(ACTIVE))).all()
    for record in records:
        text_body = "以下為修改前後差異（台灣時間）：\n" + "\n".join(differences)
        overlap = [x for x in conflicts(db,record.user_id,event) if x["status"]=="registered"]
        if rescheduled and overlap:
            text_body += "\n新時間與下列已報名活動衝突（系統不自動取消）：\n"+"\n".join(
                f"{x['name']}：{s.change_display(datetime.fromisoformat(x['start_time']))} - {s.change_display(datetime.fromisoformat(x['end_time']))}" for x in overlap)
        mail = notify_registration(db,event,record,"活動異動",text_body,kind="event_change")
        mail.event_revision, mail.reschedule_notice = event.notification_revision, rescheduled


def refresh_request_deadlines(db,event):
    requests = db.scalars(select(CancellationRequest).join(Registration,Registration.id==CancellationRequest.registration_id)
        .where(Registration.event_id==event.id,CancellationRequest.status=="pending")).all()
    for item in requests:
        item.auto_approve_at=min(item.submitted_at+timedelta(hours=72),event.starts_at)


def close_requests_for_cancelled_event(db,event):
    pending=db.scalars(select(CancellationRequest).join(Registration,Registration.id==CancellationRequest.registration_id)
        .where(Registration.event_id==event.id,CancellationRequest.status=="pending")).all()
    for item in pending:
        complete_request(db,item,"auto_approved")


def cancellation_token(settings,event,record):
    return jwt.encode(dict(purpose="cancellation-action",aud="cancellation-action",sub=str(record.user_id),
        registration_id=record.id,revision=record.revision,event_id=event.id,
        exp=s.as_utc(event.starts_at)),settings.jwt_secret,algorithm="HS256")


def cancellation_action(db,user_id,raw,settings):
    # Read-only POST: receiving/scanning an email URL can never cancel a record.
    try:
        payload=jwt.decode(raw,settings.jwt_secret,algorithms=["HS256"],audience="cancellation-action")
        if payload.get("purpose")!="cancellation-action" or payload.get("sub")!=str(user_id):
            raise ValueError()
        record=db.get(Registration,payload["registration_id"])
        if (record is None or record.user_id!=user_id or record.event_id!=payload["event_id"]
            or record.revision!=payload["revision"] or record.status!="registered"):
            raise ValueError()
        event=db.get(Event,record.event_id)
        if event.is_cancelled or s.utc_now()>=event.starts_at:
            raise ValueError()
    except (jwt.InvalidTokenError,ValueError,TypeError,KeyError):
        s.fail(400,"CANCELLATION_LINK_INVALID","取消入口無效、已過期或非本人")
    direct=can_direct_cancel(db,event,record,s.utc_now())
    return dict(event_id=event.id,registration_id=record.id,action="cancel" if direct else "request_cancellation",
        confirmation_required=True,method="DELETE" if direct else "POST",
        path=f"/events/{event.id}/"+("registrations/me" if direct else "cancellation-requests"),
        message="請確認後取消" if direct else "審核期間仍保有報名義務，其他活動可能額滿")


def reminder_is_current(db,mail):
    if mail.kind!="event_reminder":
        return True
    record=db.get(Registration,mail.registration_id)
    event=db.get(Event,record.event_id) if record else None
    return bool(record and event and record.status=="registered" and record.revision==mail.registration_revision
        and not event.is_cancelled and event.starts_at==mail.event_start_at and s.utc_now()<event.starts_at)


def process_scheduled(sessions,settings):
    """Idempotent jobs; run before SMTP delivery every worker iteration."""
    totals=dict(not_promoted=0,reminders=0,auto_approved=0,request_alerts=0,absences=0)
    with sessions() as db:
        try:
            workflow_lock(db)
            now=s.utc_now()
            events=db.scalars(select(Event).where(Event.is_cancelled.is_(False),
                or_(Event.registration_closes_at<=now,Event.starts_at<=now+timedelta(hours=24))).order_by(Event.id)).all()
            for event in events:
                refresh_request_deadlines(db,event)
                requests=db.scalars(select(CancellationRequest).join(Registration,Registration.id==CancellationRequest.registration_id)
                    .where(Registration.event_id==event.id,CancellationRequest.status=="pending").order_by(CancellationRequest.id)).all()
                for item in requests:
                    if now>=item.auto_approve_at:
                        complete_request(db,item,"auto_approved"); totals["auto_approved"]+=1
                    elif (item.reminder_sent_at is None and item.auto_approve_at-item.submitted_at>=timedelta(hours=24)
                          and now>=item.auto_approve_at-timedelta(hours=24)):
                        managers_notify(db,event,f"取消申請即將自動核准：{event.name}",f"申請編號：{item.id}；未處理將於 {s.change_display(item.auto_approve_at)} 自動核准。")
                        item.reminder_sent_at=now; totals["request_alerts"]+=1
                if now>=event.registration_closes_at:
                    for record in waitlist(db,event.id):
                        record.status="not_promoted"
                        notify_registration(db,event,record,"未獲遞補","報名已截止，之後不再遞補。",
                            key=f"not-promoted:{record.id}:{record.revision}")
                        totals["not_promoted"]+=1
                if event.check_in_used and now>=event.ends_at:
                    records=db.scalars(select(Registration).where(Registration.event_id==event.id,
                        Registration.status=="registered",Registration.attendance_status=="unrecorded")).all()
                    for record in records:
                        record.attendance_status="absent";totals["absences"]+=1
                due=event.starts_at-timedelta(hours=24)
                if due<=now<event.starts_at:
                    records=db.scalars(select(Registration).where(Registration.event_id==event.id,
                        Registration.status=="registered",Registration.registered_at<=due)).all()
                    for record in records:
                        key=f"reminder:{record.id}:{record.revision}:{event.starts_at.isoformat()}"
                        if db.scalar(select(OutgoingEmail.id).where(OutgoingEmail.deduplication_key==key)):
                            continue
                        raw=cancellation_token(settings,event,record)
                        url=f"{settings.public_base_url}/events/{event.id}#cancel_token={raw}"
                        deadline=s.change_display(event.registration_closes_at)
                        mail=notify_registration(db,event,record,"活動前一天提醒",
                            f"注意事項：{event.notes or '無'}\n取消期限：{deadline}；截止後請申請取消。"
                            f"\n取消／申請入口：{url}\n須登入本人帳號並二次確認；審核期間仍保有報名義務。",
                            kind="event_reminder",key=key)
                        mail.event_start_at=event.starts_at;totals["reminders"]+=1
            db.commit()
        except Exception:
            db.rollback();raise
    return totals
