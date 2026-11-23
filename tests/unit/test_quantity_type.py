from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import Column, Engine, Integer, MetaData, Table, func, insert, select, text
from sqlalchemy.exc import StatementError

from app.db import Quantity

# Tabla propia del test: no forma parte del esquema de la aplicación.
_metadata = MetaData()
probe = Table(
    "quantity_probe",
    _metadata,
    Column("id", Integer, primary_key=True),
    Column("amount", Quantity, nullable=False),
)


@pytest.fixture
def probe_engine(engine: Engine) -> Engine:
    _metadata.create_all(engine)
    return engine


def _store(engine: Engine, *amounts: Any) -> None:
    with engine.begin() as connection:
        for amount in amounts:
            connection.execute(insert(probe).values(amount=amount))


def _stored_raw(engine: Engine) -> list[int]:
    with engine.connect() as connection:
        return [row[0] for row in connection.execute(text("SELECT amount FROM quantity_probe"))]


@pytest.mark.parametrize("amount", [Decimal("1.500"), Decimal("0.001")])
def test_round_trip_is_exact(probe_engine: Engine, amount: Decimal) -> None:
    _store(probe_engine, amount)

    with probe_engine.connect() as connection:
        loaded = connection.execute(select(probe.c.amount)).scalar_one()

    assert loaded == amount
    assert loaded.as_tuple() == amount.as_tuple()  # 3 decimales fijos: Decimal("1.500"), no "1.5"
    assert isinstance(loaded, Decimal)


def test_stored_as_integer_thousandths(probe_engine: Engine) -> None:
    _store(probe_engine, Decimal("1.5"), Decimal("0.001"), Decimal("12"))

    assert _stored_raw(probe_engine) == [1500, 1, 12000]


def test_sum_in_sql_is_exact(probe_engine: Engine) -> None:
    _store(probe_engine, Decimal("1.3"), Decimal("0.2"), Decimal("-1.5"))

    with probe_engine.connect() as connection:
        total = connection.execute(select(func.sum(probe.c.amount))).scalar_one()

    assert total == Decimal("0")
    assert isinstance(total, Decimal)


def test_comparison_in_sql_uses_the_same_scale(probe_engine: Engine) -> None:
    _store(probe_engine, Decimal("1.5"), Decimal("2.25"))

    with probe_engine.connect() as connection:
        found = (
            connection.execute(select(probe.c.amount).where(probe.c.amount > Decimal("1.5")))
            .scalars()
            .all()
        )

    assert found == [Decimal("2.250")]


def test_null_is_preserved(engine: Engine) -> None:
    meta = MetaData()
    nullable = Table(
        "quantity_nullable", meta, Column("id", Integer, primary_key=True), Column("q", Quantity)
    )
    meta.create_all(engine)
    with engine.begin() as connection:
        connection.execute(insert(nullable).values(q=None))
        assert connection.execute(select(nullable.c.q)).scalar_one() is None


@pytest.mark.parametrize(
    ("accepted", "expected_milli"),
    [
        (Decimal("1.5"), 1500),  # Decimal
        (3, 3000),  # int
        ("1.5", 1500),  # str numérico
        ("0.001", 1),
        ("1.5000", 1500),  # ceros sobrantes: sigue siendo exacto
        ("2", 2000),
    ],
)
def test_accepts_decimal_int_and_numeric_str(
    probe_engine: Engine, accepted: Decimal | int | str, expected_milli: int
) -> None:
    _store(probe_engine, accepted)

    assert _stored_raw(probe_engine) == [expected_milli]


@pytest.mark.parametrize(
    "rejected",
    [
        1.5,  # float
        True,  # bool
        False,
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("0.0001"),  # más de 3 decimales
        "abc",  # str no numérico
        "",
        "1,5",  # la coma solo existe en la capa de entrada (RN20)
        Decimal(2**63),  # no entra en la base
    ],
)
def test_rejects_invalid_values(probe_engine: Engine, rejected: Any) -> None:
    with pytest.raises((StatementError, TypeError, ValueError)):
        _store(probe_engine, rejected)

    assert _stored_raw(probe_engine) == []
