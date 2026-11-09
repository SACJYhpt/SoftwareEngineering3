"""Provisional unit ownership rules shared with the event creation API."""
from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.database import build_database
from app.models import Event, EventType, Registration, Unit, UnitManager, User
from app.services import can_manage_unit, require_manage_unit, utc_now


def test_assigned_user_can_manage_multiple_units(application):
    with application.state.sessions() as db:
        assert can_manage_unit(db, 3, 1)
        assert can_manage_unit(db, 3, 2)
        assert require_manage_unit(db, 3, 1) is None


@pytest.mark.parametrize("user_id,unit_id", [(3, 3), (1, 1), (4, 1), (999, 1), (3, 999)])
def test_unassigned_user_is_forbidden(application, user_id, unit_id):
    # An admin role alone deliberately grants no global management privilege.
    with application.state.sessions() as db:
        assert not can_manage_unit(db, user_id, unit_id)
        with pytest.raises(HTTPException) as error:
            require_manage_unit(db, user_id, unit_id)
        assert error.value.status_code == 403
        assert error.value.detail == {"code": "UNIT_FORBIDDEN", "message": "權限不足"}


def test_same_unit_managers_do_not_depend_on_event_creator(application):
    now = utc_now()
    with application.state.sessions.begin() as db:
        event = Event(unit_id=1, owner_id=3, name="單位活動", category="講座", location="海大", description="測試", contact_information="events@test.invalid",
                      starts_at=now + timedelta(days=3), ends_at=now + timedelta(days=4),
                      registration_opens_at=now - timedelta(days=1), registration_closes_at=now + timedelta(days=1))
        db.add(event)
        db.flush()
        assert event.owner_id == 3
        assert can_manage_unit(db, 3, event.unit_id)
        assert can_manage_unit(db, 5, event.unit_id)
        # Removing a creator's grant removes access; owner_id grants no fallback.
        db.delete(db.get(UnitManager, (3, 1)))
        db.flush()
        assert not can_manage_unit(db, event.owner_id, event.unit_id)
        with pytest.raises(HTTPException) as error:
            require_manage_unit(db, event.owner_id, event.unit_id)
        assert error.value.status_code == 403
        assert can_manage_unit(db, 5, event.unit_id)


def test_management_grant_is_independent_of_role_label(application):
    with application.state.sessions.begin() as db:
        db.add(UnitManager(user_id=4, unit_id=2))
        db.flush()
        assert can_manage_unit(db, 4, 2)
        # Assigned access comes from the relation, not a second role check.
        db.get(User, 3).role = "member"
        db.flush()
        assert can_manage_unit(db, 3, 1)


def test_inactive_user_cannot_manage_assigned_unit(application):
    with application.state.sessions.begin() as db:
        db.get(User, 3).is_active = False
        db.flush()
        assert not can_manage_unit(db, 3, 1)
        with pytest.raises(HTTPException) as error:
            require_manage_unit(db, 3, 1)
        assert error.value.status_code == 403


def test_duplicate_management_grant_is_rejected(application):
    with pytest.raises(IntegrityError):
        with application.state.sessions.begin() as db:
            db.add(UnitManager(user_id=3, unit_id=1))


def test_event_must_reference_existing_unit(application):
    now = utc_now()
    with pytest.raises(IntegrityError):
        with application.state.sessions.begin() as db:
            db.add(Event(unit_id=999, owner_id=3, name="無效單位活動", category="講座", location="海大", description="測試", contact_information="events@test.invalid",
                         starts_at=now + timedelta(days=3), ends_at=now + timedelta(days=4),
                         registration_opens_at=now - timedelta(days=1), registration_closes_at=now + timedelta(days=1)))


def test_demo_init_supports_new_schema_without_duplicate_data(tmp_path, monkeypatch):
    from init_data import DEMO_EVENTS, DEMO_USERS, EVENT_TYPES, UNITS, main

    url = f"sqlite:///{(tmp_path / 'new-demo.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("JWT_SECRET", "test-demo-secret-" * 4)
    main(["--demo"])
    main(["--demo"])
    engine, sessions = build_database(url)
    try:
        with sessions() as db:
            assert db.scalar(select(func.count(Unit.id))) == len(UNITS)
            assert db.scalar(select(func.count(EventType.id))) == len(EVENT_TYPES)
            assert db.scalar(select(func.count(User.id))) == len(DEMO_USERS)
            assert db.scalar(select(func.count(User.id)).where(User.role == "admin")) == 1
            assert db.scalar(select(func.count(UnitManager.user_id))) == 3
            assert db.scalar(select(func.count(Event.id))) == len(DEMO_EVENTS)
            assert db.scalar(select(func.count(Registration.id))) == 1
            event = db.scalar(select(Event).limit(1))
            assert can_manage_unit(db, event.owner_id, event.unit_id)
            # FR-01-12: test accounts cover different identities, departments and grades.
            students = db.scalars(select(User).where(User.identity == "student")).all()
            assert len({u.department_id for u in students}) >= 3 and len({u.grade for u in students}) >= 3
            assert {u.identity for u in db.scalars(select(User))} == {"student", "teacher", "staff"}
            assert all(not u.password_hash.startswith("DemoOnly") for u in db.scalars(select(User)))
    finally:
        engine.dispose()


def test_base_init_creates_one_admin_and_refuses_old_schema(tmp_path, monkeypatch, capsys):
    from init_data import main

    url = f"sqlite:///{(tmp_path / 'base.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("JWT_SECRET", "test-demo-secret-" * 4)
    main([])
    assert "臨時密碼" in capsys.readouterr().out
    main([])
    assert "臨時密碼" not in capsys.readouterr().out
    engine, sessions = build_database(url)
    try:
        with sessions() as db:
            assert db.scalar(select(func.count(User.id))) == 1
            assert db.scalar(select(User)).role == "admin"
        with engine.begin() as connection:
            connection.exec_driver_sql("ALTER TABLE users DROP COLUMN grade")
    finally:
        engine.dispose()
    with pytest.raises(SystemExit):
        main([])
    main(["--reset"])


def test_demo_and_reset_are_development_only(tmp_path, monkeypatch):
    from init_data import main

    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://u:p@127.0.0.1:1/never")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "test-demo-secret-" * 4)
    for args in (["--demo"], ["--reset"]):
        with pytest.raises(SystemExit):
            main(args)
