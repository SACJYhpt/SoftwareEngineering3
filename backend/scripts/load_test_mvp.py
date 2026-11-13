"""Load test for ER-US-B01 / NFR-01-02: 1,000 events, 50 concurrent users, 95% within 3 s.

    venv\\Scripts\\python.exe scripts\\load_test_mvp.py
    venv\\Scripts\\python.exe scripts\\load_test_mvp.py --base-url http://127.0.0.1:8000   # existing server

Without --base-url it builds a throwaway SQLite database with 1,000 upcoming events,
starts its own uvicorn on --port, and stops it afterwards. Against MySQL or a deployed
server, pass --base-url (the database must already hold 1,000 events).

Measures the API calls a page load makes (home: GET /events, first page of 30;
detail: GET /events/{id}).
Browser rendering time is not included; check that in the deployed environment.
"""
import argparse
import os
import random
import statistics
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

import httpx

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def build_database(path, events):
    from app.database import Base, build_database as connect
    from app.models import Event, EventType, Unit, User
    from app.security import hash_password
    from app.services import utc_now

    engine, sessions = connect(f"sqlite:///{path.as_posix()}")
    Base.metadata.create_all(engine)
    now = utc_now()
    with sessions.begin() as db:
        db.add(Unit(id=1, name="資訊工程學系"))
        db.add(EventType(name="講座"))
        db.add(User(id=1, email="owner@test.invalid", name="owner", role="manager", password_hash=hash_password("x")))
        db.flush()
        db.add_all([Event(unit_id=1, owner_id=1, name=f"壓測活動 {i}", category="講座", location="海大",
                          description="壓力測試用活動說明。" * 5, contact_information="events@test.invalid",
                          starts_at=now + timedelta(days=3, minutes=i), ends_at=now + timedelta(days=3, minutes=i + 60),
                          registration_opens_at=now - timedelta(days=1), registration_closes_at=now + timedelta(days=2),
                          capacity=100) for i in range(events)])
    engine.dispose()


def wait_ready(base_url, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(base_url + "/", timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            time.sleep(0.3)
    raise SystemExit("後端沒有在時間內啟動")


def run_load(base_url, users, requests_per_user, ids):
    def user_session(_):
        timings = []
        with httpx.Client(base_url=base_url, timeout=30) as client:
            for _ in range(requests_per_user):
                path = "/events" if random.random() < 0.5 else f"/events/{random.choice(ids)}"
                started = time.perf_counter()
                response = client.get(path)
                timings.append((path == "/events", time.perf_counter() - started, response.status_code))
        return timings

    with ThreadPoolExecutor(max_workers=users) as pool:
        return [item for session in pool.map(user_session, range(users)) for item in session]


def report(name, samples):
    samples = sorted(samples)
    p95 = samples[max(0, int(len(samples) * 0.95) - 1)]
    within = sum(s <= 3 for s in samples) / len(samples)
    print(f"{name:8s} 次數 {len(samples):4d}  平均 {statistics.mean(samples):.3f}s  p95 {p95:.3f}s  "
          f"最慢 {samples[-1]:.3f}s  3 秒內 {within:.1%}")
    return within


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url")
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--events", type=int, default=1000)
    parser.add_argument("--users", type=int, default=50)
    parser.add_argument("--requests", type=int, default=10, help="每位使用者送出的請求數")
    args = parser.parse_args()

    server = None
    # Windows may hold the SQLite file briefly after the server exits; leftovers stay in %TEMP%.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        base_url = args.base_url
        if base_url is None:
            database = Path(folder) / "load.db"
            build_database(database, args.events)
            env = dict(os.environ, DATABASE_URL=f"sqlite:///{database.as_posix()}", APP_ENV="development",
                       JWT_SECRET=os.environ.get("JWT_SECRET", "load-test-secret-" * 3))
            server = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1",
                                       "--port", str(args.port), "--log-level", "warning"], cwd=BACKEND, env=env)
            base_url = f"http://127.0.0.1:{args.port}"
        try:
            wait_ready(base_url)
            # Page through the list; stop when a page adds nothing new, which also
            # covers servers that ignore limit/offset and return everything at once.
            ids, offset = [], 0
            while True:
                page = httpx.get(base_url + "/events", params={"limit": 100, "offset": offset}, timeout=60).json()
                new = [event["id"] for event in page if event["id"] not in set(ids)]
                ids += new
                offset += 100
                if len(page) < 100 or not new:
                    break
            print(f"活動數 {len(ids)}，同時使用者 {args.users}，每人 {args.requests} 次請求")
            results = run_load(base_url, args.users, args.requests, ids)
        finally:
            if server is not None:
                server.terminate()
                server.wait(timeout=10)

    errors = [code for _, _, code in results if code != 200]
    ok = min(report("首頁", [t for is_list, t, _ in results if is_list]),
             report("詳情頁", [t for is_list, t, _ in results if not is_list])) >= 0.95 and not errors
    print(f"非 200 回應：{len(errors)}")
    print("結果：" + ("通過 (95% 以上在 3 秒內)" if ok else "未通過"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
