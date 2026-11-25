import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base, enable_sqlite_fk
from app import models  # noqa: F401  確保所有表都已註冊


@pytest.fixture()
def session():
    """每個測試使用全新的記憶體資料庫，不會動到真正的 itinerary.db"""
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_fk(engine)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as s:
        yield s
