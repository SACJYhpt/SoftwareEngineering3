import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.config import Settings
from app.models import Unit, UnitManager, User
from app.security import hash_password, issue_token


@pytest.fixture
def application(tmp_path):
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}", jwt_secret="test-secret-" * 5)
    app = create_app(settings)
    with TestClient(app):
        with app.state.sessions.begin() as db:
            hashed = hash_password("TestingOnly!2026")
            db.add_all([User(id=1, email="member@test.invalid", name="測試會員", role="member", password_hash=hashed),
                        User(id=2, email="other@test.invalid", name="測試會員二", role="member", password_hash=hashed),
                        User(id=3, email="manager@test.invalid", name="測試管理者", role="manager", password_hash=hashed),
                        User(id=4, email="admin@test.invalid", name="測試管理員", role="admin", password_hash=hashed),
                        User(id=5, email="manager2@test.invalid", name="同單位管理者", role="manager", password_hash=hashed)])
            db.add_all([Unit(id=1, name="測試系所"), Unit(id=2, name="測試社團"), Unit(id=3, name="其他單位")])
            db.flush()
            db.add_all([UnitManager(user_id=3, unit_id=1), UnitManager(user_id=3, unit_id=2),
                        UnitManager(user_id=5, unit_id=1)])
        yield app


@pytest.fixture
def client(application):
    with TestClient(application) as client:
        yield client


@pytest.fixture
def headers(application):
    return {"Authorization": "Bearer " + issue_token(1, application.state.settings)}
