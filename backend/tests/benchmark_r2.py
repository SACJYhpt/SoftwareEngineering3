"""One-off local HTTP benchmark; uses only a temporary SQLite database."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import math
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

backend = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend))
from app.database import Base, build_database
from app.models import Event, Unit, User

def main():
    with tempfile.TemporaryDirectory(prefix='r2-benchmark-') as temp:
        url = 'sqlite:///' + (Path(temp) / 'benchmark.db').as_posix()
        engine, sessions = build_database(url)
        Base.metadata.create_all(engine)
        with sessions.begin() as db:
            db.add(Unit(id=1, name='效能測試單位'))
            db.add(User(id=1, email='perf@test.invalid', name='測試', password_hash='not-a-login', email_verified=True))
            db.flush()
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            db.add_all([Event(unit_id=1, owner_id=1, name=f'參訪效能測試 {i}', category='參訪', location='海大',
                              description='參訪效能資料', contact_information='perf@test.invalid',
                              starts_at=now+timedelta(days=3), ends_at=now+timedelta(days=3, hours=1),
                              registration_opens_at=now-timedelta(days=1), registration_closes_at=now+timedelta(days=1))
                        for i in range(1000)])
        engine.dispose()
        env = os.environ.copy()
        env.update(DATABASE_URL=url, JWT_SECRET=secrets.token_urlsafe(48), APP_ENV='development', PYTHONDONTWRITEBYTECODE='1')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', str(port)],
                                   cwd=backend, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            base = f'http://127.0.0.1:{port}'
            for _ in range(80):
                try:
                    with urllib.request.urlopen(base+'/docs', timeout=1) as response:
                        if response.status == 200: break
                except OSError:
                    time.sleep(.1)
            def request(index):
                start=time.perf_counter()
                try:
                    with urllib.request.urlopen(base+'/events?q=%E5%8F%83%E8%A8%AA', timeout=30) as response:
                        data=json.load(response)
                        return (time.perf_counter()-start, response.status == 200 and len(data)==1000)
                except Exception:
                    return (time.perf_counter()-start, False)
            with ThreadPoolExecutor(max_workers=50) as pool:
                results=list(pool.map(request, range(50)))
            durations=sorted(x[0] for x in results)
            output=dict(database='temporary SQLite',events=1000,requests=50,workers=50,
                        successes=sum(x[1] for x in results),p95_seconds=round(durations[math.ceil(.95*len(durations))-1],3),
                        maximum_seconds=round(max(durations),3),scope='local API benchmark, not MySQL or browser page-load acceptance')
            print(json.dumps(output),flush=True)
        finally:
            if process.poll() is None:
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL) if os.name == 'nt' else process.terminate()
            process.wait(timeout=10)


if __name__ == "__main__":
    main()
