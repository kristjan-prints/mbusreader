import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("MBR_DATABASE_URL", "sqlite:///./mbr.sqlite3")

connect_args = (
    {"check_same_thread": False, "timeout": 30}
    if DATABASE_URL.startswith("sqlite")
    else {}
)

engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,  # matches your original intent
    future=True,
)

Base = declarative_base()

def init_db() -> None:
    # Import models so they register with Base.metadata
    import app.db.models  # noqa: F401  # required to register SQLAlchemy models
    Base.metadata.create_all(bind=engine)

def get_db():
    """
    FastAPI dependency: creates a Session per request and guarantees close.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if not DATABASE_URL.startswith("sqlite"):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.execute("PRAGMA busy_timeout=30000;")  # 30s
    cursor.close()