import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./itinerary.db")
engine = create_engine(DATABASE_URL)


def enable_sqlite_fk(eng):
    """SQLite 預設不檢查外鍵，要手動開啟（PostgreSQL 不需要）"""
    if eng.url.get_backend_name() == "sqlite":
        @event.listens_for(eng, "connect")
        def _fk_on(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")


enable_sqlite_fk(engine)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass
