"""Opt-in integration check against a dedicated MySQL test database.

Set MYSQL_TEST_URL to mysql+pymysql://.../event_registration_test?charset=utf8mb4.
Only records created by this test are cleaned up; no existing tables are dropped.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.engine import make_url

from app.database import Base, build_database, schema_is_current
from app.models import EmailAttempt, Event, OutgoingEmail, Registration, Unit, User
from app.security import hash_password
from app.services import cancel_registration, register, utc_now


@pytest.mark.skipif(not os.getenv("MYSQL_TEST_URL"), reason="未設定專用 MySQL 測試資料庫；不可用 SQLite 結果代替 MySQL 驗收")
def test_mysql_concurrent_capacity_and_duplicate():
    url = make_url(os.environ["MYSQL_TEST_URL"])
    assert url.get_backend_name() == "mysql"
    assert url.database == "event_registration_test", "只允許使用專用 event_registration_test 資料庫"
    engine, sessions = build_database(url)
    assert schema_is_current(engine), "專用 MySQL 測試資料庫須先由資料庫負責人更新為 R3 結構"
    Base.metadata.create_all(engine)
    run_id = uuid4().hex
    user_ids, event_id, unit_id = [], None, None
    try:
        with sessions.begin() as db:
            hashed = hash_password("TemporaryTestOnly!2026")
            manager = User(email=f"{run_id}-manager@test.invalid", name="測試管理者", role="manager", password_hash=hashed, email_verified=True)
            db.add(manager)
            db.flush()
            user_ids.append(manager.id)
            people = [User(email=f"{run_id}-{i}@test.invalid", name="測試會員", password_hash=hashed, email_verified=True) for i in range(1000)]
            db.add_all(people)
            db.flush()
            member_ids = [user.id for user in people]
            user_ids.extend(member_ids)
            unit = Unit(name=f"測試單位 {run_id}")
            db.add(unit)
            db.flush()
            unit_id = unit.id
            now = utc_now()
            event = Event(unit_id=unit_id, owner_id=manager.id, name=f"MySQL test {run_id}", category="測試", location="測試",
                          description="自動測試資料", contact_information="events@test.invalid", starts_at=now + timedelta(days=3), ends_at=now + timedelta(days=4),
                          registration_opens_at=now - timedelta(days=1), registration_closes_at=now + timedelta(days=1), capacity=100)
            db.add(event)
            db.flush()
            event_id = event.id

        def attempt(user_id):
            try:
                return register(sessions, event_id, user_id)
            except HTTPException as error:
                assert error.status_code == 409 and error.detail["code"] == "EVENT_FULL"
                return None

        with ThreadPoolExecutor(max_workers=32) as executor:
            results = list(executor.map(attempt, member_ids))
        assert sum(item is not None for item in results) == 100
        with sessions() as db:
            assert db.scalar(select(func.count(Registration.id)).where(Registration.event_id == event_id, Registration.status == "registered")) == 100
            winner = db.scalar(select(Registration.user_id).where(Registration.event_id == event_id, Registration.status == "registered").limit(1))
        with ThreadPoolExecutor(max_workers=16) as executor:
            repeated = list(executor.map(lambda _: register(sessions, event_id, winner), range(40)))
        assert all(item["already_registered"] for item in repeated)
        assert len({item["registration_id"] for item in repeated}) == 1
        # E02 uses the same event row lock: one released seat admits one person.
        with sessions() as db:
            registered_ids = set(db.scalars(select(Registration.user_id).where(Registration.event_id == event_id, Registration.status == "registered")))
        cancelled = cancel_registration(sessions, event_id, winner)
        assert cancelled["registration_count"] == 99
        contenders = [user_id for user_id in member_ids if user_id not in registered_ids][:32]
        with ThreadPoolExecutor(max_workers=16) as executor:
            replacements = list(executor.map(attempt, contenders))
        assert sum(item is not None for item in replacements) == 1
        with sessions() as db:
            assert db.scalar(select(func.count(Registration.id)).where(Registration.event_id == event_id, Registration.status == "registered")) == 100
        # R3 exercises the same real InnoDB locks with a finite waitlist.
        with sessions.begin() as db:
            event = db.get(Event,event_id)
            event.waitlist_enabled, event.waitlist_capacity = True, 20
            current = set(db.scalars(select(Registration.user_id).where(Registration.event_id==event_id,Registration.status=="registered")))
        waiting_users=[uid for uid in member_ids if uid not in current][:20]
        with ThreadPoolExecutor(max_workers=16) as executor:
            waiting=list(executor.map(lambda uid:register(sessions,event_id,uid),waiting_users))
        assert sorted(x["waitlist_position"] for x in waiting)==list(range(1,21))
        with ThreadPoolExecutor(max_workers=10) as executor:
            list(executor.map(lambda uid:cancel_registration(sessions,event_id,uid),sorted(current)[:10]))
        with sessions() as db:
            assert db.scalar(select(func.count(Registration.id)).where(Registration.event_id==event_id,Registration.status=="registered"))==100
            assert db.scalar(select(func.count(Registration.id)).where(Registration.event_id==event_id,Registration.status=="waitlisted"))==10
    finally:
        with sessions.begin() as db:
            if event_id is not None:
                registrations=select(Registration.id).where(Registration.event_id==event_id)
                emails=select(OutgoingEmail.id).where(OutgoingEmail.registration_id.in_(registrations))
                db.execute(delete(EmailAttempt).where(EmailAttempt.email_id.in_(emails)))
                db.execute(delete(OutgoingEmail).where(OutgoingEmail.registration_id.in_(registrations)))
                db.execute(delete(Registration).where(Registration.event_id == event_id))
                db.execute(delete(Event).where(Event.id == event_id))
            if unit_id is not None:
                db.execute(delete(Unit).where(Unit.id == unit_id))
            if user_ids:
                db.execute(delete(User).where(User.id.in_(user_ids)))
        engine.dispose()
