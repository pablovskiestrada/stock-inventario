from decimal import Decimal

import pytest
from sqlalchemy import Engine, text
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
    assert product.min_stock == Decimal(0)
    assert product.unit == "UN"
    assert product.is_active is True


def test_unit_defaults_to_un_in_python_and_in_the_database(
    session: Session, category: Category
) -> None:
    product = _product(category.id)
    session.add(product)
    session.commit()
    assert product.unit == "UN"

    session.execute(
        text(
            "INSERT INTO products (sku, name, category_id, cost_price, sale_price) "
            f"VALUES ('RAW-1', 'Crudo', {category.id}, 1, 1)"  # sin unit: usa el server_default
        )
    )
    assert session.execute(text("SELECT unit, min_stock FROM products WHERE sku='RAW-1'")).one() == (
        "UN",
        0,
    )


@pytest.mark.parametrize("unit", ["UN", "KG", "M", "L"])
def test_every_unit_is_accepted(session: Session, category: Category, unit: str) -> None:
    session.add(_product(category.id, unit=unit))
    session.commit()


def test_min_stock_with_decimals_round_trips_exactly(
    engine: Engine, session: Session, category: Category
) -> None:
    session.add(_product(category.id, unit="KG", min_stock=Decimal("1.500")))
    session.commit()

    with sessionmaker(bind=engine)() as fresh:
        stored = fresh.query(Product).one()
        assert stored.min_stock == Decimal("1.500")
        assert stored.min_stock.as_tuple() == Decimal("1.500").as_tuple()
    assert session.execute(text("SELECT min_stock FROM products")).scalar_one() == 1500


@pytest.mark.parametrize(
    "overrides",
    [
        {"cost_price": Decimal("-0.01")},
        {"sale_price": Decimal("-1")},
        {"min_stock": -1},
        {"min_stock": Decimal("-0.001")},
        {"unit": "XX"},
        {"unit": "kg"},  # el CHECK distingue mayúsculas
        {"unit": ""},
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
