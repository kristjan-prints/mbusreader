import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["MBR_API_TOKEN"] = "test-token"

from app.api.mbus import router as mbus_router
from app.db.database import Base, get_db
import app.db.models  # noqa: F401


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.sqlite3'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    testing_session = sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        future=True,
    )

    Base.metadata.create_all(bind=engine)

    with testing_session() as session:
        yield session

    engine.dispose()


@pytest.fixture
def client(db_session):
    app = FastAPI()
    app.include_router(mbus_router)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    return TestClient(
        app,
        headers={"Authorization": "Bearer test-token"},
    )
