from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  registra los modelos en Base.metadata
from app.db import Base, get_session
from app.main import app


@pytest.fixture
def engine() -> Iterator[Engine]:
    """SQLite en memoria con foreign keys activadas. Nunca toca stock.db."""
    test_engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    with test_engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1
    # create_all solo en tests; en la aplicación el esquema va por Alembic.
    Base.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with sessionmaker(bind=engine, expire_on_commit=False)() as db_session:
        yield db_session


@pytest.fixture
def client(engine: Engine) -> Iterator[TestClient]:
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_session() -> Iterator[Session]:
        with factory() as db_session:
            yield db_session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
