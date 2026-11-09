"""System initialization (SRD FR-01-12): first admin, units, event types.

    python init_data.py                 # base data; admin password from INIT_ADMIN_PASSWORD or generated
    python init_data.py --demo          # also MVP test accounts and sample events (development only)
    python init_data.py --demo --reset  # drop and recreate all tables first (development only)

Re-running never duplicates rows and never changes existing passwords or event dates.
"""
import argparse
import os
import secrets
from datetime import timedelta

from sqlalchemy import inspect, select

from app.config import Settings
from app.database import Base, build_database
from app.models import Event, EventType, Registration, Unit, UnitManager, User
from app.security import hash_password
from app.services import utc_now

UNITS = [
    ("資訊工程學系", "department"), ("電機工程學系", "department"), ("機械與機電工程學系", "department"),
    ("航運管理學系", "department"), ("海洋生物研究所", "department"),
    ("學生事務處課外活動指導組", "office"), ("圖書暨資訊處", "office"),
    ("吉他社", "club"), ("熱舞社", "club"), ("學生會", "club"),
]
EVENT_TYPES = ["講座", "工作坊", "參訪", "比賽", "迎新", "社團活動", "志工服務", "其他"]
DEMO_PASSWORD = "DemoOnly!2026"
# email, name, role, identity, department, grade, managed units
DEMO_USERS = [
    ("admin@demo.ntou.edu.tw", "示範系統管理員", "admin", "staff", "圖書暨資訊處", None, []),
    ("manager@demo.ntou.edu.tw", "示範管理者 (資工系)", "manager", "teacher", "資訊工程學系", None, ["資訊工程學系"]),
    ("multi@demo.ntou.edu.tw", "示範管理者 (兩個社團)", "manager", "student", "資訊工程學系", 3, ["吉他社", "學生會"]),
    ("student1@demo.ntou.edu.tw", "示範學生一", "member", "student", "資訊工程學系", 1, []),
    ("student2@demo.ntou.edu.tw", "示範學生二", "member", "student", "電機工程學系", 3, []),
    ("student3@demo.ntou.edu.tw", "示範學生三", "member", "student", "航運管理學系", 4, []),
    ("grad@demo.ntou.edu.tw", "示範研究生", "member", "student", "海洋生物研究所", 5, []),
    ("teacher@demo.ntou.edu.tw", "示範教師", "member", "teacher", "機械與機電工程學系", None, []),
    ("staff@demo.ntou.edu.tw", "示範行政人員", "member", "staff", "學生事務處課外活動指導組", None, []),
]
# name, unit, capacity, registration opens (days from now), closes (days from now)
DEMO_EVENTS = [
    ("[示範] Python 入門講座", "資訊工程學系", 20, -1, 2),
    ("[示範] 最後一個名額", "資訊工程學系", 1, -1, 2),
    ("[示範] 不限名額交流會", "資訊工程學系", None, -1, 2),
    ("[示範] 報名尚未開始", "資訊工程學系", 20, 1, 2),
    ("[示範] 報名已截止", "資訊工程學系", 20, -2, -1),
    ("[示範] 已額滿參訪", "資訊工程學系", 1, -1, 2),
    ("[示範] 吉他社迎新茶會", "吉他社", 30, -1, 2),
]


def schema_is_current(engine):
    """True when every model column exists; create_all() never alters old tables."""
    inspector = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing = {column["name"] for column in inspector.get_columns(table.name)}
        if {column.name for column in table.columns} - existing:
            return False
    return True


def ensure_units(db):
    units = {}
    for name, kind in UNITS:
        unit = db.scalar(select(Unit).where(Unit.name == name))
        if unit is None:
            unit = Unit(name=name, kind=kind)
            db.add(unit)
            db.flush()
        units[name] = unit
    return units


def ensure_base(db, admin_email, admin_password):
    ensure_units(db)
    for name in EVENT_TYPES:
        if db.scalar(select(EventType).where(EventType.name == name)) is None:
            db.add(EventType(name=name))
    if db.scalar(select(User).where(User.role == "admin")) is None:
        generated = admin_password is None
        password = admin_password or secrets.token_urlsafe(12)
        db.add(User(email=admin_email, name="系統管理員", role="admin", identity="staff",
                    password_hash=hash_password(password)))
        if generated:
            print(f"已建立系統管理員 {admin_email}，臨時密碼：{password}（只顯示這一次，請妥善保存）")
        else:
            print(f"已建立系統管理員 {admin_email}")


def ensure_demo(db, units):
    now = utc_now()
    people = {}
    for email, name, role, identity, department, grade, managed in DEMO_USERS:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, name=name, role=role, identity=identity, grade=grade,
                        department_id=units[department].id, password_hash=hash_password(DEMO_PASSWORD))
            db.add(user)
            db.flush()
        people[email] = user
        for unit_name in managed:
            if db.get(UnitManager, (user.id, units[unit_name].id)) is None:
                db.add(UnitManager(user_id=user.id, unit_id=units[unit_name].id))
    owner = {"資訊工程學系": people["manager@demo.ntou.edu.tw"], "吉他社": people["multi@demo.ntou.edu.tw"]}
    for name, unit_name, capacity, opens_days, closes_days in DEMO_EVENTS:
        event = db.scalar(select(Event).where(Event.name == name))
        if event is None:
            event = Event(unit_id=units[unit_name].id, owner_id=owner[unit_name].id, name=name,
                          category="迎新" if "迎新" in name else "講座", location="海大資訊工程學系館",
                          description="僅供本機報名功能展示。", contact_information="events@demo.ntou.edu.tw",
                          notes="資料以建立當下的時間產生。", capacity=capacity,
                          starts_at=now + timedelta(days=3), ends_at=now + timedelta(days=3, hours=2),
                          registration_opens_at=now + timedelta(days=opens_days),
                          registration_closes_at=now + timedelta(days=closes_days))
            db.add(event)
            db.flush()
            if "已額滿" in name:
                db.add(Registration(user_id=people["student2@demo.ntou.edu.tw"].id, event_id=event.id, registered_at=now))
        print(f"活動 {event.id}: {event.name}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="初始化系統資料 (FR-01-12)")
    parser.add_argument("--demo", action="store_true", help="另建立 MVP 驗收用的測試帳號與示範活動 (僅限 development)")
    parser.add_argument("--reset", action="store_true", help="先刪除並重建所有資料表 (僅限 development)")
    args = parser.parse_args(argv)
    settings = Settings.from_env()
    if (args.demo or args.reset) and settings.app_env != "development":
        raise SystemExit("--demo 與 --reset 只能在 APP_ENV=development 使用。")
    engine, sessions = build_database(settings.database_url)
    try:
        if args.reset:
            Base.metadata.drop_all(engine)
        elif not schema_is_current(engine):
            raise SystemExit("資料庫的資料表結構是舊版。開發環境請加上 --reset 重建；正式環境請先執行 migration。")
        Base.metadata.create_all(engine)
        admin_email = os.getenv("INIT_ADMIN_EMAIL", "admin@ntou.edu.tw").strip().lower()
        with sessions.begin() as db:
            if args.demo:
                # Demo accounts first: the base step then finds the demo admin and creates no second admin.
                ensure_demo(db, ensure_units(db))
            ensure_base(db, admin_email, os.getenv("INIT_ADMIN_PASSWORD"))
    finally:
        engine.dispose()
    print("初始化完成。重跑不會刪除或重複建立資料。")
    if args.demo:
        print("示範帳號密碼皆為 " + DEMO_PASSWORD + "（僅供本機；勿將含示範帳號的資料庫部署上線）")


if __name__ == "__main__":
    main()
