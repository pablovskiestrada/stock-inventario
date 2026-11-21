from decimal import Decimal

import pytest
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models.category import Category
from app.models.product import Product


@pytest.fixture
def category(session: Session) -> Category:
    cat = Category(name="Ropa")
    session.add(cat)
    session.commit()
    return cat


def _product(category_id: int, **overrides: object) -> Product:
    data: dict[str, object] = {
        "sku": "A-1",
        "name": "Remera",
        "category_id": category_id,
        "cost_price": Decimal("10.00"),
        "sale_price": Decimal("20.00"),
    }
    data.update(overrides)
    return Product(**data)


@pytest.mark.filterwarnings("error::sqlalchemy.exc.SAWarning")  # Numeric en SQLite no debe avisar
def test_money_round_trips_exactly_through_the_database(
    engine: Engine, session: Session, category: Category
) -> None:
    session.add(_product(category.id, cost_price=Decimal("19.99"), sale_price=Decimal("0.10")))
    session.commit()

    with sessionmaker(bind=engine)() as fresh:  # sesión nueva: lee de la base, no del caché
        stored = fresh.query(Product).one()
        assert stored.cost_price == Decimal("19.99")
        assert stored.sale_price == Decimal("0.10")
        assert isinstance(stored.cost_price, Decimal)
        assert str(stored.sale_price) == "0.10"


def test_defaults_min_stock_zero_and_active(session: Session, category: Category) -> None:
    product = _product(category.id)
    session.add(product)
    session.commit()
    assert product.min_stock == 0
    assert product.is_active is True


@pytest.mark.parametrize(
    "overrides",
    [
        {"cost_price": Decimal("-0.01")},
        {"sale_price": Decimal("-1")},
        {"min_stock": -1},
        {"sku": "   "},
        {"name": "   "},
    ],
)
def test_database_check_constraints(
    session: Session, category: Category, overrides: dict[str, object]
) -> None:
    session.add(_product(category.id, **overrides))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_database_enforces_case_insensitive_unique_sku(
    session: Session, category: Category
) -> None:
    session.add(_product(category.id, sku="ABC-1"))
    session.commit()
    session.add(_product(category.id, sku="abc-1"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_database_rejects_unknown_category(session: Session) -> None:
    session.add(_product(999))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_foreign_key_has_no_cascade(session: Session, category: Category) -> None:
    session.add(_product(category.id))
    session.commit()
    session.delete(category)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
