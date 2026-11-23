from datetime import datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models.category import Category
from app.models.product import Product
from app.models.stock_movement import StockMovement
from tests.unit.movement_rows import INVALID_ROWS, SQL_INSERT, VALID_ROWS


@pytest.fixture
def product(session: Session) -> Product:
    category = Category(name="Ropa")
    session.add(category)
    session.flush()
    prod = Product(
        sku="A-1",
        name="Harina",
        category_id=category.id,
        cost_price=Decimal("10.00"),
        sale_price=Decimal("20.00"),
        unit="KG",
    )
    session.add(prod)
    session.commit()
    return prod


@pytest.mark.parametrize("params", VALID_ROWS.values(), ids=VALID_ROWS.keys())
def test_database_accepts_valid_combinations(
    session: Session, product: Product, params: dict[str, Any]
) -> None:
    session.execute(text(SQL_INSERT), {**params, "product_id": product.id})
    session.commit()
    assert session.execute(text("SELECT COUNT(*) FROM stock_movements")).scalar_one() == 1


@pytest.mark.parametrize("params", INVALID_ROWS.values(), ids=INVALID_ROWS.keys())
def test_database_check_constraints_reject_invalid_combinations(
    session: Session, product: Product, params: dict[str, Any]
) -> None:
    with pytest.raises(IntegrityError):
        session.execute(text(SQL_INSERT), {**params, "product_id": product.id})
    session.rollback()
    assert session.execute(text("SELECT COUNT(*) FROM stock_movements")).scalar_one() == 0


def test_database_rejects_unknown_product(session: Session) -> None:
    with pytest.raises(IntegrityError):
        session.execute(text(SQL_INSERT), {**VALID_ROWS["entrada"], "product_id": 999})
    session.rollback()


def test_foreign_key_has_no_cascade(session: Session, product: Product) -> None:
    session.execute(text(SQL_INSERT), {**VALID_ROWS["entrada"], "product_id": product.id})
    session.commit()
    with pytest.raises(IntegrityError):  # el producto no se puede borrar si tiene movimientos
        session.execute(text("DELETE FROM products WHERE id = :id"), {"id": product.id})
    session.rollback()
    assert session.execute(text("SELECT COUNT(*) FROM stock_movements")).scalar_one() == 1


def test_created_at_is_automatic_and_there_is_no_updated_at(
    engine: Engine, session: Session, product: Product
) -> None:
    movement = StockMovement(
        product_id=product.id, type="IN", quantity=Decimal("1.5"), unit_price=Decimal("10.00")
    )
    session.add(movement)
    session.commit()
    session.refresh(movement)

    assert isinstance(movement.created_at, datetime)
    columns = {column["name"] for column in inspect(engine).get_columns("stock_movements")}
    assert "created_at" in columns
    assert "updated_at" not in columns  # RN5: inmutable
    assert not hasattr(StockMovement, "updated_at")


def test_quantity_and_unit_price_round_trip_exactly(
    engine: Engine, session: Session, product: Product
) -> None:
    session.add(
        StockMovement(
            product_id=product.id,
            type="ADJUSTMENT",
            quantity=Decimal("-0.001"),
            reason="MERMA",
        )
    )
    session.add(
        StockMovement(
            product_id=product.id, type="IN", quantity=Decimal("1.300"), unit_price=Decimal("19.99")
        )
    )
    session.commit()

    with sessionmaker(bind=engine)() as fresh:  # sesión nueva: lee de la base, no del caché
        stored = {m.type: m for m in fresh.query(StockMovement)}
    assert stored["ADJUSTMENT"].quantity == Decimal("-0.001")
    assert stored["ADJUSTMENT"].unit_price is None
    assert stored["IN"].quantity == Decimal("1.300")
    assert stored["IN"].unit_price == Decimal("19.99")
    raw = session.execute(text("SELECT quantity FROM stock_movements ORDER BY id")).scalars().all()
    assert raw == [-1, 1300]  # milésimas enteras (RN19)


def test_product_id_is_indexed(engine: Engine) -> None:
    indexes = inspect(engine).get_indexes("stock_movements")
    assert any(index["column_names"] == ["product_id"] for index in indexes)
