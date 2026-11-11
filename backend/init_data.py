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

from sqlalchemy import select

from app.config import Settings
from app.database import Base, build_database, schema_is_current
from app.models import (Event, EventType, OrganizerAcknowledgement, PublishedDocument,
                        Registration, Unit, UnitManager, User)
from app.security import hash_password
from app.services import utc_now

# Academic units by college, as listed on https://www.ntou.edu.tw/academics (學術單位一覽表).
# Registration lists them in this order, so units of one college stay together.
ACADEMIC_UNITS = [
    # 海運暨管理學院
    "商船學系", "航運管理學系", "運輸科學系", "輪機工程學系", "海洋觀光管理學士學位學程",
    "海洋經營管理學士學位學程", "永續發展碩士在職學位學程",
    # 生命科學院
    "食品科學系", "水產養殖學系", "生命科學暨生物科技學系", "海洋生物研究所", "食品安全與風險管理研究所",
    "海洋生物科技博士學位學程", "海洋生物科技學士學位學程",
    # 海洋科學與資源學院
    "環境生物與漁業科學學系", "海洋環境資訊系", "地球科學研究所", "海洋事務與資源管理研究所",
    "海洋環境與生態研究所", "海洋資源與環境變遷博士學位學程",
    # 工學院
    "機械與機電工程學系", "系統工程暨造船學系", "河海工程學系", "海洋工程科技博士學位學程", "海洋工程科技學士學位學程",
    # 電機資訊學院
    "電機工程學系", "資訊工程學系", "通訊與導航工程學系", "光電與材料科技學系",
    # 人文社會科學院
    "應用經濟研究所", "教育研究所", "海洋文化研究所", "應用英語研究所", "海洋文創設計產業學士學位學程",
    "師資培育中心", "華語中心",
    # 海洋法律與政策學院
    "海洋法律研究所", "海洋法政學士學位學程", "海洋政策碩士學位學程",
    # 國際學院
    "海洋生物科技及環境生態永續國際碩士學位學程", "應用人工智慧國際碩士學位學程",
    # 共同教育中心 (語文、博雅、體育教育組的教師)
    "共同教育中心",
]
# Administrative units, as listed in the school's 分層負責明細表 (人事室).
OFFICES = [
    "教務處", "研究發展處", "學生事務處", "總務處", "圖書暨資訊處", "國際事務處", "秘書室", "人事室",
    "主計室", "體育室", "職業安全衛生中心", "產學營運總中心", "馬祖行政處", "社會責任實踐與永續發展中心",
]
# Clubs are created by the system administrator as needed; these exist for the demo.
DEMO_CLUBS = ["吉他社", "熱舞社", "學生會"]
UNITS = ([(name, "department") for name in ACADEMIC_UNITS] + [(name, "office") for name in OFFICES]
         + [(name, "club") for name in DEMO_CLUBS])
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
    ("staff@demo.ntou.edu.tw", "示範行政人員", "member", "staff", "學生事務處", None, []),
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


def ensure_units(db, demo=False):
    units = {}
    for name, kind in UNITS:
        if kind == "club" and not demo:
            continue
        unit = db.scalar(select(Unit).where(Unit.name == name))
        if unit is None:
            unit = Unit(name=name, kind=kind)
            db.add(unit)
            db.flush()
        units[name] = unit
    return units


def ensure_base(db, admin_email, admin_password, development=False):
    ensure_units(db)
    if development:
        ensure_documents(db)
    for name in EVENT_TYPES:
        if db.scalar(select(EventType).where(EventType.name == name)) is None:
            db.add(EventType(name=name))
    if db.scalar(select(User).where(User.role == "admin")) is None:
        generated = admin_password is None
        password = admin_password or secrets.token_urlsafe(12)
        db.add(User(email=admin_email, name="系統管理員", role="admin", identity="staff",
                    password_hash=hash_password(password), email_verified=True))
        if generated:
            print(f"已建立系統管理員 {admin_email}，臨時密碼：{password}（只顯示這一次，請妥善保存）")
        else:
            print(f"已建立系統管理員 {admin_email}")


def ensure_documents(db):
    # Development drafts describe actual R2 behavior; the team must approve and
    # publish its own privacy notice and organizer terms before a real release.
    contents = {
        "privacy": "[開發草案，正式上線前須團隊確認] 蒐集姓名、學校信箱、身分別、系所、學生年級，用於帳號驗證及活動報名。"
                   "報名資料可由活動所屬單位的所有活動管理者查看。R2 目前保留帳號與報名資料，尚無自動到期刪除；"
                   "個資保存期限、刪除申請方式及適用法規須由團隊查證後公布，不承諾尚未實作的自動刪除。",
        "organizer": "[開發草案，正式上線前須團隊確認] 主辦單位應確認活動資訊正確，僅為辦理活動使用報名資料，"
                     "妥善保護名單；異動與取消須透過系統通知參加者，不得任意散布個人資料。",
        "faq": "R2：以學校信箱註冊並驗證後登入；可搜尋、篩選活動及報名。截止前可取消並重新報名，截止當下起不可取消。"
               "密碼忘記可申請重設；活動異動與取消會排入通知佇列。候補、截止後取消申請及報到尚未釋出。",
    }
    for kind, content in contents.items():
        if db.scalar(select(PublishedDocument.id).where(PublishedDocument.kind == kind).limit(1)) is None:
            db.add(PublishedDocument(kind=kind, version=1, content=content, published_at=utc_now()))
    db.flush()


def ensure_demo(db, units):
    now = utc_now()
    people = {}
    for email, name, role, identity, department, grade, managed in DEMO_USERS:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, name=name, role=role, identity=identity, grade=grade,
                        department_id=units[department].id, password_hash=hash_password(DEMO_PASSWORD), email_verified=True)
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
                ensure_demo(db, ensure_units(db, demo=True))
            ensure_base(db, admin_email, os.getenv("INIT_ADMIN_PASSWORD"), settings.app_env == "development")
            if args.demo:
                document = db.scalar(select(PublishedDocument).where(PublishedDocument.kind == "organizer")
                                     .order_by(PublishedDocument.version.desc()).limit(1))
                # Only simulated demo accounts get seeded acknowledgements.
                for email, *_ in DEMO_USERS:
                    user = db.scalar(select(User).where(User.email == email))
                    if db.get(OrganizerAcknowledgement, (user.id, document.id)) is None:
                        db.add(OrganizerAcknowledgement(user_id=user.id, document_id=document.id, acknowledged_at=utc_now()))
    finally:
        engine.dispose()
    print("初始化完成。重跑不會刪除或重複建立資料。")
    if args.demo:
        print("示範帳號密碼皆為 " + DEMO_PASSWORD + "（僅供本機；勿將含示範帳號的資料庫部署上線）")


if __name__ == "__main__":
    main()
