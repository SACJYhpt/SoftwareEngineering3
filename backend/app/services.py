from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select, text

from .models import Event, Registration, Unit, UnitManager, User


def can_manage_unit(db, user_id: int, unit_id: int) -> bool:
    """PROVISIONAL: active users manage units explicitly assigned to them.

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
                       .where(UnitManager.user_id == user.id).order_by(Unit.id)).all()
    return dict(id=user.id, email=user.email, name=user.name, role=user.role,
                managed_units=[dict(id=unit.id, name=unit.name) for unit in units])


def utc_now():
    """Database stores naive UTC; API returns explicitly UTC timestamps."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def as_utc(value):
    return value.replace(tzinfo=timezone.utc)


def count_registrations(db, event_id):
    return db.scalar(select(func.count(Registration.id)).where(Registration.event_id == event_id))


def find_registration(db, event_id, user_id):
    return db.scalar(select(Registration).where(Registration.event_id == event_id, Registration.user_id == user_id))


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


def event_view(db, event, user):
    count = count_registrations(db, event.id)
    registered = user is not None and find_registration(db, event.id, user.id) is not None
    status = event_status(event, count, utc_now())
    unit = db.get(Unit, event.unit_id)
    return dict(id=event.id, name=event.name, category=event.category,
                type=event.category, unit_id=event.unit_id, unit=dict(id=unit.id, name=unit.name),
                contact_information=event.contact_information,
                start_time=as_utc(event.starts_at), end_time=as_utc(event.ends_at),
                registration_start=as_utc(event.registration_opens_at),
                registration_deadline=as_utc(event.registration_closes_at), registration_count=count,
                location=event.location, description=event.description, notes=event.notes,
                starts_at=as_utc(event.starts_at), ends_at=as_utc(event.ends_at),
                registration_opens_at=as_utc(event.registration_opens_at),
                registration_closes_at=as_utc(event.registration_closes_at),
                capacity=event.capacity, registered_count=count, waitlist_count=0,
                status=status, my_registration_status=("已報名" if registered else "未報名") if user else None,
                # PROVISIONAL: manager/admin retain ordinary registration ability.
                can_register=user is not None and user.is_active and not registered and status == "開放中")


def create_event(db, payload, user_id):
    if db.get(Unit, payload.unit_id) is None:
        raise HTTPException(404, {"code": "UNIT_NOT_FOUND", "message": "找不到單位"})
    require_manage_unit(db, user_id, payload.unit_id)
    start = payload.start_time.astimezone(timezone.utc).replace(tzinfo=None)
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


def list_events(db, user):
    events = db.scalars(select(Event).where(Event.is_public.is_(True), Event.is_cancelled.is_(False),
                                           Event.starts_at > utc_now()).order_by(Event.starts_at, Event.id)).all()
    return [event_view(db, event, user) for event in events]


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
            # PROVISIONAL: active users may register regardless of role name.
            # Unit management grants do not limit which events they may attend.
            existing = find_registration(db, event_id, user_id)
            count = count_registrations(db, event_id)
            if existing is not None:
                result = registration_view(existing, count, event.capacity, True)
                db.commit()
                return result
            now = utc_now()  # Evaluate after obtaining the lock, not before waiting.
            if event.is_cancelled:
                raise HTTPException(409, {"code": "EVENT_CANCELLED", "message": "活動已取消"})
            if now >= event.starts_at:
                raise HTTPException(409, {"code": "EVENT_STARTED", "message": "活動已開始"})
            if now < event.registration_opens_at:
                raise HTTPException(409, {"code": "REGISTRATION_NOT_OPEN", "message": "報名尚未開始"})
            if now >= event.registration_closes_at:
                raise HTTPException(409, {"code": "REGISTRATION_CLOSED", "message": "報名已截止"})
            if event.capacity is not None and count >= event.capacity:
                raise HTTPException(409, {"code": "EVENT_FULL", "message": "名額已滿"})
            record = Registration(user_id=user_id, event_id=event_id, registered_at=now)
            db.add(record)
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
