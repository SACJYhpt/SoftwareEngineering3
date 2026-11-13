from datetime import datetime, timedelta, timezone
import hashlib
import secrets

from fastapi import HTTPException
from sqlalchemy import func, select, text, or_, update
from sqlalchemy.exc import IntegrityError

from .models import (AccountRequest, AccountToken, Event, EventType, LoginThrottle,
                     OrganizerAcknowledgement, OutgoingEmail, PublishedDocument,
                     Registration, Unit, UnitManager, User)

MAX_LOGIN_FAILURES = 5
LOCKOUT = timedelta(minutes=10)


def can_manage_unit(db, user_id: int, unit_id: int) -> bool:
    """SRD v2: active users manage units explicitly assigned to them.

    Same-unit managers have the same access regardless of who created an event.
    Neither a role name (including admin) nor Event.owner_id grants access.
    """
    return db.scalar(
        select(UnitManager.user_id)
        .join(User, User.id == UnitManager.user_id)
        .where(UnitManager.user_id == user_id, UnitManager.unit_id == unit_id,
               User.is_active.is_(True))
    ) is not None


def require_manage_unit(db, user_id: int, unit_id: int) -> None:
    """Shared 403 guard for future unit management operations.

    Call with the authenticated user's id; for an event use event.unit_id.
    """
    if not can_manage_unit(db, user_id, unit_id):
        raise HTTPException(403, {"code": "UNIT_FORBIDDEN", "message": "權限不足"})


def user_view(db, user):
    # Account context for the MVP unit selector; no unit CRUD or role shortcut.
    units = db.scalars(select(Unit).join(UnitManager, UnitManager.unit_id == Unit.id)
                       .where(UnitManager.user_id == user.id, Unit.is_active.is_(True)).order_by(Unit.id)).all()
    department = db.get(Unit, user.department_id) if user.department_id else None
    return dict(id=user.id, email=user.email, name=user.name, role=user.role,
                identity=user.identity, grade=user.grade,
                department=dict(id=department.id, name=department.name) if department else None,
                managed_units=[dict(id=unit.id, name=unit.name) for unit in units])


def lockout_remaining(db, email, now):
    """Minutes left on an active lockout for this email, or None."""
    throttle = db.get(LoginThrottle, email)
    if throttle is None or throttle.locked_until is None or now >= throttle.locked_until:
        return None
    return max(1, -(-int((throttle.locked_until - now).total_seconds()) // 60))


def record_login_result(db, email, success, now):
    """Reset on success; lock for LOCKOUT after MAX_LOGIN_FAILURES in a row."""
    throttle = db.get(LoginThrottle, email)
    if success:
        if throttle is not None:
            db.delete(throttle)
        db.commit()
        return
    if throttle is None:
        throttle = LoginThrottle(email=email, failed_count=0)
        db.add(throttle)
    if throttle.locked_until is not None and now >= throttle.locked_until:
        throttle.failed_count, throttle.locked_until = 0, None
    throttle.failed_count += 1
    if throttle.failed_count >= MAX_LOGIN_FAILURES:
        throttle.locked_until = now + LOCKOUT
    db.commit()


def list_event_types(db):
    return db.scalars(select(EventType).where(EventType.is_active.is_(True)).order_by(EventType.id)).all()


def utc_now():
    """Database stores naive UTC; API returns explicitly UTC timestamps."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def as_utc(value):
    return value.replace(tzinfo=timezone.utc)


def count_registrations(db, event_id):
    return db.scalar(select(func.count(Registration.id)).where(Registration.event_id == event_id,
                                                             Registration.status == "registered"))


def find_registration(db, event_id, user_id, active_only=True):
    query = select(Registration).where(Registration.event_id == event_id, Registration.user_id == user_id)
    if active_only:
        query = query.where(Registration.status == "registered")
    return db.scalar(query)


def event_status(event, count, now):
    if event.is_cancelled:
        return "已取消"
    if now >= event.ends_at:
        return "已結束"
    if now >= event.starts_at:
        return "進行中"
    if now < event.registration_opens_at:
        return "報名未開始"
    if now >= event.registration_closes_at:
        return "已截止"
    if event.capacity is not None and count >= event.capacity:
        return "已額滿"
    return "開放中"


def event_view(db, event, user, count=None, registered=None, unit=None, my_status=None, now=None):
    """Build the API view; list_events passes prefetched values to avoid per-event queries."""
    if count is None:
        count = count_registrations(db, event.id)
    if registered is None:
        registered = user is not None and find_registration(db, event.id, user.id) is not None
    status = event_status(event, count, now if now is not None else utc_now())
    unit = unit or db.get(Unit, event.unit_id)
    starts_at, ends_at = as_utc(event.starts_at), as_utc(event.ends_at)
    opens_at, closes_at = as_utc(event.registration_opens_at), as_utc(event.registration_closes_at)
    mine = ("已報名" if registered else "未報名") if user else None
    if my_status is not None:
        mine = my_status
    elif user and not registered and find_registration(db, event.id, user.id, False) is not None:
        mine = "已取消"
    return dict(id=event.id, name=event.name, category=event.category,
                type=event.category, unit_id=event.unit_id, unit=dict(id=unit.id, name=unit.name),
                contact_information=event.contact_information,
                start_time=starts_at, end_time=ends_at,
                registration_start=opens_at,
                registration_deadline=closes_at, registration_count=count,
                location=event.location, description=event.description, notes=event.notes,
                starts_at=starts_at, ends_at=ends_at,
                registration_opens_at=opens_at,
                registration_closes_at=closes_at,
                capacity=event.capacity, registered_count=count, waitlist_count=0,
                status=status, my_registration_status=mine, cancellation_reason=event.cancellation_reason,
                # SRD v2: manager/admin retain ordinary registration ability.
                can_register=user is not None and user.is_active and not registered and status == "開放中")


def create_event(db, payload, user_id):
    if db.get(Unit, payload.unit_id) is None:
        raise HTTPException(404, {"code": "UNIT_NOT_FOUND", "message": "找不到單位"})
    require_manage_unit(db, user_id, payload.unit_id)
    if not db.get(Unit, payload.unit_id).is_active:
        raise HTTPException(409, {"code": "UNIT_INACTIVE", "message": "單位已停用"})
    require_organizer_acknowledgement(db, user_id)
    if payload.type not in {item.name for item in list_event_types(db)}:
        raise HTTPException(422, {"code": "EVENT_TYPE_INVALID", "message": "請從清單選擇活動類型"})
    start =payload.start_time.astimezone(timezone.utc).replace(tzinfo=None)
    if start < utc_now():
        raise HTTPException(422, {"code": "EVENT_START_IN_PAST", "message": "活動開始時間不得早於現在"})
    event = Event(unit_id=payload.unit_id, owner_id=user_id, name=payload.name, category=payload.type,
                  description=payload.description, location=payload.location,
                  contact_information=payload.contact_information, notes=payload.notes,
                  starts_at=start, ends_at=payload.end_time.astimezone(timezone.utc).replace(tzinfo=None),
                  registration_opens_at=payload.registration_start.astimezone(timezone.utc).replace(tzinfo=None),
                  registration_closes_at=payload.registration_deadline.astimezone(timezone.utc).replace(tzinfo=None),
                  capacity=payload.capacity)
    try:
        db.add(event)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return event


def get_public_event(db, event_id):
    event = db.get(Event, event_id)
    if event is None or not event.is_public:
        raise HTTPException(404, {"code": "EVENT_NOT_FOUND", "message": "找不到活動"})
    return event


def escape_like(text_value):
    return text_value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def keyword_conditions(keyword):
    """B04: every space-separated term must match the event's name, description, location
    or type, or its organizer. Organizer names also match abbreviations whose characters
    appear in order, so 「資工」 finds 資訊工程學系 and 「航管」 finds 航運管理學系."""
    conditions = []
    for term in keyword.split():
        in_order = "%" + "%".join(escape_like(char) for char in term) + "%"
        organizer = select(Unit.id).where(Unit.name.like(in_order, escape="\\"))
        conditions.append(or_(Event.name.icontains(term, autoescape=True),
                              Event.description.icontains(term, autoescape=True),
                              Event.location.icontains(term, autoescape=True),
                              Event.category.icontains(term, autoescape=True),
                              Event.unit_id.in_(organizer)))
    return conditions


def list_events(db, user, keyword=None, event_type=None, date_from=None, date_to=None, limit=30, offset=0):
    """One page of matching upcoming events and the total match count (NFR-01-02)."""
    now = utc_now()
    query = select(Event).where(Event.is_public.is_(True), Event.is_cancelled.is_(False), Event.starts_at > now)
    if keyword:
        query = query.where(*keyword_conditions(keyword))
    if event_type:
        query = query.where(Event.category == event_type)
    taiwan = timezone(timedelta(hours=8))
    if date_from and date_from != datetime.min.date():
        query = query.where(Event.starts_at >= datetime.combine(date_from, datetime.min.time(), taiwan).astimezone(timezone.utc).replace(tzinfo=None))
    if date_to:
        query = query.where(Event.starts_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time(), taiwan).astimezone(timezone.utc).replace(tzinfo=None))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    events = db.scalars(query.order_by(Event.starts_at, Event.id).limit(limit).offset(offset)).all()
    ids = [event.id for event in events]
    if not ids:
        return [], total
    counts = dict(db.execute(select(Registration.event_id, func.count(Registration.id))
                             .where(Registration.event_id.in_(ids), Registration.status == "registered").group_by(Registration.event_id)).all())
    mine = {}
    if user is not None:
        mine = dict(db.execute(select(Registration.event_id, Registration.status)
                              .where(Registration.user_id == user.id, Registration.event_id.in_(ids))).all())
    units = {unit.id: unit for unit in db.scalars(select(Unit).where(Unit.id.in_({e.unit_id for e in events})))}
    return [event_view(db, event, user, counts.get(event.id, 0), mine.get(event.id) == "registered", units[event.unit_id],
                       ("已報名" if mine.get(event.id) == "registered" else "已取消" if event.id in mine else "未報名") if user else None, now)
            for event in events], total


def list_my_upcoming_events(db, user):
    # E01: retain ongoing events until they end, including closed registrations.
    # Ownership of the registration, rather than a managed unit, selects rows.
    now = utc_now()
    rows = db.execute(
        select(Event, Registration)
        .join(Registration, Registration.event_id == Event.id)
        .where(Registration.user_id == user.id, Registration.status == "registered", Event.ends_at > now,
               Event.is_cancelled.is_(False))
        .order_by(Event.starts_at, Event.id)
    ).all()
    return [dict(event_view(db, event, user), registration_id=record.id,
                 registered_at=as_utc(record.registered_at),
                 can_cancel_registration=now < event.registration_closes_at and now < event.starts_at)
            for event, record in rows]


def cancel_registration(session_factory, event_id, user_id):
    """E02: cancel only the caller's active registration before the deadline.

    Use the same event-first lock order as register() so a released seat cannot
    be allocated twice. Keep the cancelled status required by SRD v2 B03.
    """
    with session_factory() as db:
        try:
            if db.bind.dialect.name == "sqlite":
                db.execute(text("BEGIN IMMEDIATE"))
            event = db.scalar(select(Event).where(Event.id == event_id).with_for_update())
            if event is None:
                raise HTTPException(404, {"code": "EVENT_NOT_FOUND", "message": "找不到活動"})
            user = db.get(User, user_id)
            if user is None or not user.is_active:
                raise HTTPException(401, {"code": "AUTH_REQUIRED", "message": "請先登入"})
            record = find_registration(db, event_id, user_id)
            if record is None:
                raise HTTPException(404, {"code": "REGISTRATION_NOT_FOUND", "message": "找不到本人的有效報名"})
            now = utc_now()  # Check after acquiring the lock, just as register().
            if event.is_cancelled:
                raise HTTPException(409, {"code": "EVENT_CANCELLED", "message": "活動已取消"})
            if now >= event.starts_at:
                raise HTTPException(409, {"code": "EVENT_STARTED", "message": "活動已開始"})
            if now >= event.registration_closes_at:
                raise HTTPException(409, {"code": "REGISTRATION_CLOSED", "message": "報名已截止"})
            registration_id = record.id
            record.status = "cancelled"
            record.cancelled_at = now
            db.flush()
            result = dict(message="已取消報名", registration_id=registration_id,
                          event_id=event.id, status="cancelled",
                          registration_count=count_registrations(db, event.id), capacity=event.capacity)
            db.commit()
            return result
        except Exception:
            db.rollback()
            raise


def register(session_factory, event_id, user_id):
    """One transaction per registration; all writers must lock the event first.

    MySQL uses an InnoDB event-row lock. SQLite demo uses BEGIN IMMEDIATE
    because SQLite ignores SELECT FOR UPDATE. Authentication uses a separate
    session so no earlier read snapshot precedes the lock in this transaction.
    """
    with session_factory() as db:
        try:
            if db.bind.dialect.name == "sqlite":
                db.execute(text("BEGIN IMMEDIATE"))
            event = db.scalar(select(Event).where(Event.id == event_id).with_for_update())
            if event is None or not event.is_public:
                raise HTTPException(404, {"code": "EVENT_NOT_FOUND", "message": "找不到活動"})
            user = db.get(User, user_id)
            if user is None or not user.is_active:
                raise HTTPException(401, {"code": "AUTH_REQUIRED", "message": "請先登入"})
            # SRD v2: active users may register regardless of role name.
            # Unit management grants do not limit which events they may attend.
            if event.is_cancelled:
                raise HTTPException(409, {"code": "EVENT_CANCELLED", "message": "活動已取消"})
            existing = find_registration(db, event_id, user_id)
            count = count_registrations(db, event_id)
            if existing is not None:
                result = registration_view(existing, count, event.capacity, True)
                db.commit()
                return result
            now = utc_now()  # Evaluate after obtaining the lock, not before waiting.
            if now >= event.starts_at:
                raise HTTPException(409, {"code": "EVENT_STARTED", "message": "活動已開始"})
            if now < event.registration_opens_at:
                raise HTTPException(409, {"code": "REGISTRATION_NOT_OPEN", "message": "報名尚未開始"})
            if now >= event.registration_closes_at:
                raise HTTPException(409, {"code": "REGISTRATION_CLOSED", "message": "報名已截止"})
            if event.capacity is not None and count >= event.capacity:
                raise HTTPException(409, {"code": "EVENT_FULL", "message": "名額已滿"})
            record = find_registration(db, event_id, user_id, False)
            if record is None:
                record = Registration(user_id=user_id, event_id=event_id, registered_at=now)
                db.add(record)
            else:
                record.status = "registered"
                record.registered_at = now
                record.cancelled_at = None
            db.flush()
            result = registration_view(record, count + 1, event.capacity, False)
            db.commit()
            return result
        except Exception:
            db.rollback()
            raise


def registration_view(record, count, capacity, existing):
    return dict(message="已報名" if existing else "報名成功", registration_id=record.id,
                event_id=record.event_id, registered_at=as_utc(record.registered_at),
                registration_status="已報名", registered_count=count, capacity=capacity,
                registration_count=count, status="registered", already_registered=existing)


def fail(status, code, message):
    raise HTTPException(status, {"code": code, "message": message})


def document_view(document):
    return dict(id=document.id, kind=document.kind, version=document.version,
                content=document.content, published_at=as_utc(document.published_at))


def current_document(db, kind):
    document = db.scalar(select(PublishedDocument).where(PublishedDocument.kind == kind)
                         .order_by(PublishedDocument.version.desc()).limit(1))
    if document is None:
        fail(503, "DOCUMENT_NOT_PUBLISHED", "尚未發布所需文件，請聯絡系統管理員")
    return document


def publish_document(db, kind, content):
    # Lock the publisher's user row in the API to serialize version allocation.
    version = (db.scalar(select(func.max(PublishedDocument.version)).where(PublishedDocument.kind == kind)) or 0) + 1
    document = PublishedDocument(kind=kind, version=version, content=content, published_at=utc_now())
    db.add(document)
    db.commit()
    return document_view(document)


def require_organizer_acknowledgement(db, user_id):
    document = current_document(db, "organizer")
    if db.get(OrganizerAcknowledgement, (user_id, document.id)) is None:
        fail(409, "ORGANIZER_TERMS_REQUIRED", "請先確認目前版本的主辦規範")


def acknowledge_organizer(db, user_id, document_id):
    document = current_document(db, "organizer")
    if document.id != document_id:
        fail(409, "DOCUMENT_OUTDATED", "規範已更新，請重新閱讀")
    db.scalar(select(User).where(User.id == user_id).with_for_update())
    if db.get(OrganizerAcknowledgement, (user_id, document_id)) is None:
        db.add(OrganizerAcknowledgement(user_id=user_id, document_id=document_id, acknowledged_at=utc_now()))
    db.commit()
    return dict(document_id=document_id, version=document.version, acknowledged=True)


def queue_email(db, recipient, subject, body):
    now = utc_now()
    db.add(OutgoingEmail(recipient=recipient, subject=subject, body=body, created_at=now, next_attempt_at=now))


def new_account_token(db, user, purpose, settings):
    now = utc_now()
    db.execute(update(AccountToken).where(AccountToken.user_id == user.id, AccountToken.purpose == purpose,
                                          AccountToken.used_at.is_(None)).values(used_at=now))
    raw = secrets.token_urlsafe(32)
    expires = now + (timedelta(hours=24) if purpose == "verify" else timedelta(hours=1))
    db.add(AccountToken(user_id=user.id, purpose=purpose, token_hash=hashlib.sha256(raw.encode()).hexdigest(), expires_at=expires))
    route = "verify-email" if purpose == "verify" else "reset-password"
    label = "信箱驗證" if purpose == "verify" else "重設密碼"
    # Fragment keeps the secret out of HTTP server access logs. The frontend
    # reads it and POSTs the token to the matching API, never to a third party.
    queue_email(db, user.email, label, f"請開啟 {settings.public_base_url}/{route}#token={raw}\n"
                f"有效期限：{as_utc(expires).astimezone(timezone(timedelta(hours=8))).isoformat()}（台灣時間）")


def home_unit_kind(identity):
    """Unit kind a user of this identity belongs to (ER-US-A01)."""
    return "office" if identity == "staff" else "department"


def signup(db, payload, settings):
    from .security import hash_password
    if db.bind.dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))
    domain = payload.email.rsplit("@", 1)[1]
    if not any(domain == allowed or domain.endswith("." + allowed) for allowed in settings.school_domains):
        fail(422, "SCHOOL_EMAIL_REQUIRED", "僅限學校信箱")
    if not payload.consent:
        fail(422, "PRIVACY_CONSENT_REQUIRED", "請先同意個資告知事項")
    privacy = current_document(db, "privacy")
    if privacy.version != payload.privacy_version:
        fail(409, "PRIVACY_NOTICE_OUTDATED", "個資告知已更新，請重新確認")
    # Students and teachers belong to an academic unit; administrative staff to an office.
    expected = home_unit_kind(payload.identity)
    department = db.get(Unit, payload.department_id)
    if department is None or department.kind != expected or not department.is_active:
        fail(422, "DEPARTMENT_INVALID", "請選擇啟用中的行政單位" if expected == "office" else "請選擇啟用中的系所")
    if db.scalar(select(User.id).where(User.email == payload.email)) is not None:
        fail(409, "EMAIL_ALREADY_REGISTERED", "此信箱已註冊")
    user = User(email=payload.email, name=payload.name, password_hash=hash_password(payload.password),
                identity=payload.identity, department_id=payload.department_id,
                grade=payload.grade if payload.identity == "student" else None, role="member",
                email_verified=False, consent_at=utc_now(), privacy_version=privacy.version)
    try:
        db.add(user)
        db.flush()
        db.add(AccountRequest(email=user.email, purpose="verify", requested_at=utc_now()))
        new_account_token(db, user, "verify", settings)
        db.commit()
    except IntegrityError:
        db.rollback()
        fail(409, "EMAIL_ALREADY_REGISTERED", "此信箱已註冊")
    return dict(message="註冊成功，請完成信箱驗證", verification_required=True)


def request_account_email(db, email, purpose, settings):
    if db.bind.dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))
    now = utc_now()
    row = db.scalar(select(AccountRequest).where(AccountRequest.email == email,
                     AccountRequest.purpose == purpose).with_for_update())
    if row and now < row.requested_at + timedelta(seconds=60):
        remaining = max(1, int((row.requested_at + timedelta(seconds=60) - now).total_seconds() + .999))
        raise HTTPException(429, {"code": "EMAIL_RATE_LIMITED", "message": "請稍後再試", "retry_after_seconds": remaining})
    if row is None:
        db.add(AccountRequest(email=email, purpose=purpose, requested_at=now))
    else:
        row.requested_at = now
    user = db.scalar(select(User).where(User.email == email))
    if user and user.is_active and ((purpose == "verify" and not user.email_verified) or
                                   (purpose == "reset" and user.email_verified)):
        new_account_token(db, user, purpose, settings)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        fail(429, "EMAIL_RATE_LIMITED", "請稍後再試")
    return dict(message="若此信箱符合條件，將收到操作連結")


def consume_account_token(db, raw, purpose, password=None):
    from .security import hash_password
    if db.bind.dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))
    now = utc_now()
    token = db.scalar(select(AccountToken).where(AccountToken.token_hash == hashlib.sha256(raw.encode()).hexdigest(),
                      AccountToken.purpose == purpose).with_for_update())
    if token is None or token.used_at is not None or now >= token.expires_at:
        fail(400, "LINK_INVALID", "連結已失效")
    user = db.scalar(select(User).where(User.id == token.user_id).with_for_update())
    if user is None or not user.is_active:
        fail(400, "LINK_INVALID", "連結已失效")
    consumed = db.execute(update(AccountToken).where(AccountToken.id == token.id, AccountToken.used_at.is_(None),
                           AccountToken.expires_at > now).values(used_at=now), execution_options={"synchronize_session": False})
    if consumed.rowcount != 1:
        fail(400, "LINK_INVALID", "連結已失效")
    if purpose == "verify":
        user.email_verified = True
    else:
        user.password_hash = hash_password(password)
        user.token_version += 1
        db.execute(update(AccountToken).where(AccountToken.user_id == user.id, AccountToken.purpose == "reset",
                                              AccountToken.used_at.is_(None)).values(used_at=now))
        throttle = db.get(LoginThrottle, user.email)
        if throttle:
            db.delete(throttle)
    db.commit()
    return dict(message="信箱驗證完成" if purpose == "verify" else "密碼已重設，請重新登入")


def list_my_history(db, user):
    rows = db.execute(select(Event, Registration).join(Registration, Registration.event_id == Event.id)
                      .where(Registration.user_id == user.id, Registration.status == "registered",
                             Event.ends_at <= utc_now(), Event.is_cancelled.is_(False))
                      .order_by(Event.starts_at.desc(), Event.id.desc())).all()
    return [dict(event_view(db, event, user), registration_id=record.id,
                 registered_at=as_utc(record.registered_at),
                 attendance_status=ATTENDANCE_LABELS.get(record.attendance_status, "未記錄")) for event, record in rows]


ATTENDANCE_LABELS = {"unrecorded": "未記錄", "present": "出席", "absent": "缺席", "leave": "請假"}


def managed_event(db, event_id, user_id, lock=False):
    if lock and db.bind.dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))
    query = select(Event).where(Event.id == event_id)
    event = db.scalar(query.with_for_update() if lock else query)
    if event is None:
        fail(404, "EVENT_NOT_FOUND", "找不到活動")
    require_manage_unit(db, user_id, event.unit_id)
    return event


def manage_events(db, user):
    events = db.scalars(select(Event).join(UnitManager, UnitManager.unit_id == Event.unit_id)
                       .where(UnitManager.user_id == user.id).order_by(Event.starts_at.desc(), Event.id)).all()
    return [event_view(db, event, user) for event in events]


def registration_roster(db, event_id, user_id):
    event = managed_event(db, event_id, user_id)
    rows = db.execute(select(Registration, User).join(User, User.id == Registration.user_id)
                      .where(Registration.event_id == event_id, Registration.status == "registered")
                      .order_by(Registration.registered_at, Registration.id)).all()
    items = []
    for record, user in rows:
        department = db.get(Unit, user.department_id) if user.department_id else None
        items.append(dict(registration_id=record.id, name=user.name, email=user.email, identity=user.identity,
                          department=dict(id=department.id, name=department.name) if department else None,
                          grade=user.grade, registered_at=as_utc(record.registered_at)))
    return dict(event_id=event.id, registration_count=len(items), registrations=items)


def notify_event_registrants(db, event, subject, body):
    emails = db.scalars(select(User.email).join(Registration, Registration.user_id == User.id)
                       .where(Registration.event_id == event.id, Registration.status == "registered")).all()
    for email in emails:
        queue_email(db, email, subject, body)


# F02: only these changes notify registrants, labelled as people read them.
CHANGE_LABELS = {"start_time": "開始時間", "end_time": "結束時間", "location": "地點", "notes": "注意事項"}


def change_display(value):
    if isinstance(value, datetime):
        return as_utc(value).astimezone(timezone(timedelta(hours=8))).strftime("%Y/%m/%d %H:%M")
    return value or "無"


def edit_event(db, event_id, user_id, payload):
    from .schemas import EventCreate
    from pydantic import ValidationError
    event = managed_event(db, event_id, user_id, lock=True)
    if event.is_cancelled or utc_now() >= event.ends_at:
        fail(409, "EVENT_NOT_EDITABLE", "已取消或已結束的活動不可修改")
    values = dict(name=event.name, type=event.category, description=event.description, location=event.location,
                  contact_information=event.contact_information, start_time=as_utc(event.starts_at),
                  end_time=as_utc(event.ends_at), registration_start=as_utc(event.registration_opens_at),
                  registration_deadline=as_utc(event.registration_closes_at), capacity=event.capacity,
                  unit_id=event.unit_id, notes=event.notes)
    changes = payload.model_dump(exclude_unset=True)
    values.update(changes)
    try:
        checked = EventCreate.model_validate(values)
    except ValidationError as error:
        # Only the cross-field time rules raise at model level; anything else is a field format error.
        if any(not item["loc"] for item in error.errors()):
            fail(422, "EVENT_TIME_INVALID", "活動時間順序不正確")
        fail(422, "EVENT_FIELD_INVALID", "欄位格式不正確：" + "、".join(str(item["loc"][-1]) for item in error.errors()))
    if "start_time" in changes and checked.start_time.astimezone(timezone.utc).replace(tzinfo=None) != event.starts_at:
        if checked.start_time.astimezone(timezone.utc).replace(tzinfo=None) < utc_now():
            fail(422, "EVENT_START_IN_PAST", "活動開始時間不得早於現在")
    if checked.capacity is not None and checked.capacity < count_registrations(db, event_id):
        fail(409, "CAPACITY_BELOW_REGISTRATIONS", "名額不可低於目前正式人數")
    if "type" in changes and checked.type != event.category:
        if checked.type not in {item.name for item in list_event_types(db)}:
            fail(422, "EVENT_TYPE_INVALID", "請選擇啟用中的活動類型")
    mapping = {"type": "category", "start_time": "starts_at", "end_time": "ends_at",
               "registration_start": "registration_opens_at", "registration_deadline": "registration_closes_at"}
    differences = []
    for key, value in changes.items():
        attr = mapping.get(key, key)
        if isinstance(value, datetime):
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        before = getattr(event, attr)
        if before != value and key in CHANGE_LABELS:
            differences.append(f"{CHANGE_LABELS[key]}：{change_display(before)} → {change_display(value)}")
        setattr(event, attr, value)
    if differences:
        notify_event_registrants(db, event, f"活動異動：{event.name}", "以下為修改前後差異（台灣時間）：\n" + "\n".join(differences))
    db.commit()
    return event_view(db, event, db.get(User, user_id))


def cancel_event(db, event_id, user_id, reason):
    event = managed_event(db, event_id, user_id, lock=True)
    if event.is_cancelled or utc_now() >= event.ends_at:
        fail(409, "EVENT_NOT_EDITABLE", "已取消或已結束的活動不可取消")
    event.is_cancelled = True
    event.cancellation_reason = reason
    event.cancelled_at = utc_now()
    notify_event_registrants(db, event, f"活動取消：{event.name}", f"活動已取消。\n取消原因：{reason}")
    db.commit()
    return event_view(db, event, db.get(User, user_id))


def search_users(db, keyword, unit_id, role, page, page_size):
    query = select(User)
    if keyword:
        departments = select(Unit.id).where(Unit.name.icontains(keyword, autoescape=True))
        query = query.where(or_(User.name.icontains(keyword, autoescape=True),
                               User.email.icontains(keyword, autoescape=True), User.department_id.in_(departments)))
    if role:
        query = query.where(User.role == role)
    if unit_id:
        grants = select(UnitManager.user_id).where(UnitManager.unit_id == unit_id)
        query = query.where(User.id.in_(grants) if role == "manager" else or_(User.id.in_(grants), User.department_id == unit_id))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    users = db.scalars(query.order_by(User.id).offset((page - 1) * page_size).limit(page_size)).all()
    # Current grants per user, so the admin page can show and revoke them (I02, I12).
    grants = {}
    for grant_user, unit in db.execute(select(UnitManager.user_id, Unit).join(Unit, Unit.id == UnitManager.unit_id)
                                       .where(UnitManager.user_id.in_([u.id for u in users])).order_by(Unit.id)):
        grants.setdefault(grant_user, []).append(dict(id=unit.id, name=unit.name))
    items = []
    for user in users:
        department = db.get(Unit, user.department_id) if user.department_id else None
        items.append(dict(id=user.id, name=user.name, email=user.email, identity=user.identity, role=user.role,
                          department=dict(id=department.id, name=department.name) if department else None,
                          managed_units=grants.get(user.id, [])))
    return dict(items=items, total=total, page=page, page_size=page_size)


def change_unit_manager(db, user_id, unit_id, assign):
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    unit = db.get(Unit, unit_id)
    if user is None or unit is None:
        fail(404, "USER_OR_UNIT_NOT_FOUND", "找不到使用者或單位")
    if user.role == "admin":
        fail(403, "ADMIN_ROLE_IMMUTABLE", "不可透過此功能變更系統管理員權限")
    if assign and (not unit.is_active or not user.is_active or not user.email_verified):
        fail(409, "ASSIGNMENT_NOT_ALLOWED", "僅可指派已驗證的啟用帳號至啟用單位")
    grant = db.get(UnitManager, (user_id, unit_id))
    if assign and grant is None:
        db.add(UnitManager(user_id=user_id, unit_id=unit_id))
    elif not assign and grant is not None:
        db.delete(grant)
    db.flush()
    user.role = "manager" if db.scalar(select(UnitManager.user_id).where(UnitManager.user_id == user_id).limit(1)) else "member"
    db.commit()
    return user_view(db, user)


def maintain_unit(db, payload, unit_id=None, delete=False):
    unit = db.scalar(select(Unit).where(Unit.id == unit_id).with_for_update()) if unit_id else Unit()
    if unit is None:
        fail(404, "UNIT_NOT_FOUND", "找不到單位")
    if delete:
        used = (db.scalar(select(Event.id).where(Event.unit_id == unit_id).limit(1)) or
                db.scalar(select(User.id).where(User.department_id == unit_id).limit(1)) or
                db.scalar(select(UnitManager.user_id).where(UnitManager.unit_id == unit_id).limit(1)))
        if used:
            fail(409, "UNIT_IN_USE", "已被使用的單位不可刪除，請停用")
        db.delete(unit)
    else:
        if unit_id and unit.kind != payload.kind and db.scalar(select(User.id).where(User.department_id == unit_id).limit(1)):
            fail(409, "UNIT_IN_USE", "已作為系所使用的單位不可改變類型")
        unit.name, unit.kind, unit.is_active = payload.name, payload.kind, payload.is_active
        db.add(unit)
    db.commit()
    return dict(deleted=True) if delete else dict(id=unit.id, name=unit.name, kind=unit.kind, is_active=unit.is_active)


def maintain_event_type(db, payload, type_id=None, delete=False):
    item = db.scalar(select(EventType).where(EventType.id == type_id).with_for_update()) if type_id else EventType()
    if item is None:
        fail(404, "EVENT_TYPE_NOT_FOUND", "找不到活動類型")
    if delete:
        if db.scalar(select(Event.id).where(Event.category == item.name).limit(1)):
            fail(409, "EVENT_TYPE_IN_USE", "已被使用的類型不可刪除，請停用")
        db.delete(item)
    else:
        previous = item.name
        item.name, item.is_active = payload.name, payload.is_active
        db.add(item)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            fail(409, "EVENT_TYPE_EXISTS", "活動類型已存在")
        if type_id and previous != item.name:
            db.execute(update(Event).where(Event.category == previous).values(category=item.name))
    db.commit()
    return dict(deleted=True) if delete else dict(id=item.id, name=item.name, is_active=item.is_active)
