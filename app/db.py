from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal, InvalidOperation
from sqlite3 import Connection as SQLiteConnection
from typing import Any

from sqlalchemy import BigInteger, DateTime, Dialect, Engine, MetaData, create_engine, event, func
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.config import get_settings

# Nombres de restricciones estables: migraciones reproducibles en SQLite y PostgreSQL.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


QUANTITY_SCALE = 3
QUANTITY_FACTOR = 10**QUANTITY_SCALE
_MAX_STORED = 2**63 - 1  # BigInteger firmado de 64 bits


class Quantity(TypeDecorator[Decimal]):
    """Cantidad con 3 decimales (RN19).

    En Python es `Decimal` (p. ej. `Decimal("1.500")`); en la base se guarda como entero en
    milésimas (1,5 -> 1500), así las sumas en SQL son exactas. Acepta `Decimal`, `int` y `str`
    numérico (con punto decimal); rechaza `float`, `bool`, NaN/infinito y más de 3 decimales.
    """

    impl = BigInteger
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, Decimal | int | str):
            raise TypeError(f"Quantity no acepta {type(value).__name__}: usá Decimal, int o str.")
        try:
            number = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError(f"Cantidad no numérica: {value!r}") from exc
        if not number.is_finite():
            raise ValueError(f"Cantidad no finita: {value!r}")
        milli = number * QUANTITY_FACTOR
        if milli != milli.to_integral_value():
            raise ValueError(f"La cantidad admite hasta {QUANTITY_SCALE} decimales: {value!r}")
        stored = int(milli)
        if abs(stored) > _MAX_STORED:
            raise ValueError(f"Cantidad fuera de rango: {value!r}")
        return stored

    def process_result_value(self, value: int | None, dialect: Dialect) -> Decimal | None:
        if value is None:
            return None
        return Decimal(value).scaleb(-QUANTITY_SCALE)


class CreatedAtMixin:
    """Para tablas inmutables (p. ej. stock_movements, RN5)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TimestampMixin(CreatedAtMixin):
    """Para tablas mutables."""

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


def _build_engine(database_url: str) -> Engine:
    is_sqlite = database_url.startswith("sqlite")
    connect_args = {"check_same_thread": False} if is_sqlite else {}
    return create_engine(database_url, connect_args=connect_args)


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection: Any, _connection_record: Any) -> None:
    # SQLite ignora las FK salvo que se activen en cada conexión.
    if isinstance(dbapi_connection, SQLiteConnection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


engine = _build_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
