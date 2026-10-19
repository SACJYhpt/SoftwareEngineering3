"""Add development-only sample data without deleting existing records."""
from datetime import timedelta

from sqlalchemy import select

from app.config import Settings
from app.database import Base, build_database
from app.models import Event, Registration, Unit, UnitManager, User
from app.security import hash_password
from app.services import utc_now


def main():
    settings = Settings.from_env()
    if settings.app_env != "development":
        raise SystemExit("示範帳號只能在 APP_ENV=development 建立。")
    engine, sessions = build_database(settings.database_url)
    Base.metadata.create_all(engine)
    now = utc_now()
    with sessions.begin() as db:
        people = {}
        for email, name, role in [
            ("student1@demo.ntou.edu.tw", "示範學生一", "member"),
            ("student2@demo.ntou.edu.tw", "示範學生二", "member"),
            ("manager@demo.ntou.edu.tw", "示範活動管理者", "manager"),
        ]:
            user = db.scalar(select(User).where(User.email == email))
            if user is None:
                user = User(email=email, name=name, role=role, password_hash=hash_password("DemoOnly!2026"))
                db.add(user)
                db.flush()
            people[role if role == "manager" else email] = user
        unit = db.scalar(select(Unit).where(Unit.name == "[示範] 活動主辦單位"))
        if unit is None:
            unit = Unit(name="[示範] 活動主辦單位")
            db.add(unit)
            db.flush()
        if db.get(UnitManager, (people["manager"].id, unit.id)) is None:
            db.add(UnitManager(user_id=people["manager"].id, unit_id=unit.id))
        specs = [
            ("[示範] Python 入門講座", 20, -1, 2),
            ("[示範] 最後一個名額", 1, -1, 2),
            ("[示範] 不限名額交流會", None, -1, 2),
            ("[示範] 報名尚未開始", 20, 1, 2),
            ("[示範] 報名已截止", 20, -2, -1),
            ("[示範] 已額滿參訪", 1, -1, 2),
        ]
        for name, capacity, opens_days, closes_days in specs:
            event = db.scalar(select(Event).where(Event.name == name))
            if event is None:
                event = Event(unit_id=unit.id, owner_id=people["manager"].id, name=name, category="講座",
                              location="海大資訊工程學系", description="僅供本機報名功能展示。", contact_information="events@demo.ntou.edu.tw",
                              notes="資料以建立當下的時間產生。", capacity=capacity,
                              starts_at=now + timedelta(days=3), ends_at=now + timedelta(days=3, hours=2),
                              registration_opens_at=now + timedelta(days=opens_days),
                              registration_closes_at=now + timedelta(days=closes_days))
                db.add(event)
                db.flush()
                if "已額滿" in name:
                    db.add(Registration(user_id=people["student2@demo.ntou.edu.tw"].id,
                                        event_id=event.id, registered_at=now))
            print(f"活動 {event.id}: {event.name}")
    engine.dispose()
    print("示範帳號：student1@demo.ntou.edu.tw / student2@demo.ntou.edu.tw / manager@demo.ntou.edu.tw")
    print("示範密碼：DemoOnly!2026（僅供本機；勿將含這些帳號的資料庫部署上線）")
    print("重跑不會刪除資料或清空報名，也不會重設活動日期。")


if __name__ == "__main__":
    main()
