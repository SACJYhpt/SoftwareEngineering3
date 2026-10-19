"""Explicit schema creation for a new database; not a migration tool."""
from app.config import Settings
from app.database import Base, build_database
from app import models  # noqa: F401 -- registers SQLAlchemy tables

if __name__ == "__main__":
    engine, _ = build_database(Settings.from_env().database_url)
    Base.metadata.create_all(engine)
    engine.dispose()
    print("資料表已建立。此工具不會修改既有資料表結構；後續變更請使用 migration。")
