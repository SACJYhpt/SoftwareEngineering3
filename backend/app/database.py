from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def schema_is_current(engine):
    """Detect missing R2 columns without altering or dropping existing tables."""
    inspector = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if inspector.has_table(table.name):
            existing = {column["name"] for column in inspector.get_columns(table.name)}
            if {column.name for column in table.columns} - existing:
                return False
    return True


def build_database(url: str):
    options = {"pool_pre_ping": True}
    if make_url(url).get_backend_name() == "sqlite":
        options["connect_args"] = {"check_same_thread": False, "timeout": 30}
    engine = create_engine(url, **options)
    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def configure_sqlite(connection, _):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine, sessionmaker(bind=engine, expire_on_commit=False)
