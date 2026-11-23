from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.product import Product
from app.repositories.category_repository import CategoryRepository
from app.repositories.product_repository import ProductRepository
from app.services.errors import (
    DuplicateSkuError,
    InvalidMinStockError,
    InvalidPriceError,
    InvalidProductCategoryError,
    InvalidUnitError,
    ProductFieldTooLongError,
    ProductNameRequiredError,
    ProductNotFoundError,
    ProductSkuRequiredError,
)
from app.services.product_service import ProductService


@pytest.fixture
def service(session: Session) -> ProductService:
    return ProductService(ProductRepository(session), CategoryRepository(session))


@pytest.fixture
def category(session: Session) -> Category:
    cat = Category(name="Ropa")
    session.add(cat)
    session.commit()
    return cat


def _data(category: Category, **overrides: object) -> dict:
    data: dict = {
        "sku": "A-1",
        "name": "Remera",
        "category_id": category.id,
        "cost_price": Decimal("10.00"),
        "sale_price": Decimal("20.00"),
    }
    data.update(overrides)
    return data


def test_create_trims_sku_and_name_and_applies_defaults(
    service: ProductService, category: Category
) -> None:
    product = service.create(**_data(category, sku="  A-1 ", name=" Remera  "))
    assert (product.sku, product.name) == ("A-1", "Remera")
    assert product.min_stock == 0
    assert product.unit == "UN"
    assert product.is_active is True


@pytest.mark.parametrize("sku", ["", "   "])
def test_create_rejects_blank_sku(service: ProductService, category: Category, sku: str) -> None:
    with pytest.raises(ProductSkuRequiredError):
        service.create(**_data(category, sku=sku))


@pytest.mark.parametrize("name", ["", "  \t"])
def test_create_rejects_blank_name(service: ProductService, category: Category, name: str) -> None:
    with pytest.raises(ProductNameRequiredError):
        service.create(**_data(category, name=name))


def test_create_rejects_too_long_sku_and_name(service: ProductService, category: Category) -> None:
    with pytest.raises(ProductFieldTooLongError):
        service.create(**_data(category, sku="x" * 51))
    with pytest.raises(ProductFieldTooLongError):
        service.create(**_data(category, name="x" * 151))
    service.create(**_data(category, sku="x" * 50, name="y" * 150))


def test_create_rejects_duplicate_sku_case_insensitive(
    service: ProductService, category: Category
) -> None:
    service.create(**_data(category, sku="ABC-1"))
    with pytest.raises(DuplicateSkuError):
        service.create(**_data(category, sku=" abc-1 "))


def test_create_rejects_unknown_category(service: ProductService, category: Category) -> None:
    with pytest.raises(InvalidProductCategoryError):
        service.create(**_data(category, category_id=999))


@pytest.mark.parametrize(
    "field,value",
    [
        ("cost_price", Decimal("-0.01")),
        ("sale_price", Decimal("-1")),
        ("cost_price", Decimal("1.005")),
        ("sale_price", Decimal("NaN")),
        ("cost_price", Decimal("10000000000.00")),
    ],
)
def test_create_rejects_invalid_prices(
    service: ProductService, category: Category, field: str, value: Decimal
) -> None:
    with pytest.raises(InvalidPriceError):
        service.create(**_data(category, **{field: value}))


def test_create_accepts_zero_prices(service: ProductService, category: Category) -> None:
    product = service.create(**_data(category, cost_price=Decimal("0"), sale_price=Decimal("0")))
    assert product.cost_price == 0


@pytest.mark.parametrize("min_stock", [-1, True, 1.5, Decimal("-0.001"), Decimal("NaN")])
def test_create_rejects_invalid_min_stock(
    service: ProductService, category: Category, min_stock: object
) -> None:
    with pytest.raises(InvalidMinStockError):
        service.create(**_data(category, min_stock=min_stock))


def test_un_rejects_decimal_min_stock(service: ProductService, category: Category) -> None:
    with pytest.raises(InvalidMinStockError, match="UN solo admite cantidades enteras"):
        service.create(**_data(category, unit="UN", min_stock=Decimal("1.5")))


@pytest.mark.parametrize("unit", ["KG", "M", "L"])
def test_decimal_units_accept_decimal_min_stock(
    service: ProductService, category: Category, unit: str
) -> None:
    product = service.create(**_data(category, unit=unit, min_stock=Decimal("1.5")))
    assert (product.unit, product.min_stock) == (unit, Decimal("1.500"))


def test_rejects_more_than_three_decimals_in_min_stock(
    service: ProductService, category: Category
) -> None:
    with pytest.raises(InvalidMinStockError, match="hasta 3 decimales"):
        service.create(**_data(category, unit="KG", min_stock=Decimal("0.0001")))


@pytest.mark.parametrize("unit", ["XX", "kg", ""])
def test_rejects_unknown_unit(service: ProductService, category: Category, unit: str) -> None:
    with pytest.raises(InvalidUnitError):
        service.create(**_data(category, unit=unit))


def test_update_can_change_unit_when_min_stock_still_fits(
    service: ProductService, category: Category
) -> None:
    product = service.create(**_data(category, unit="KG", min_stock=Decimal("2")))
    updated = service.update(product.id, **_data(category, unit="UN", min_stock=Decimal("2")))
    assert (updated.unit, updated.min_stock) == ("UN", Decimal("2"))


def test_update_to_un_fails_if_min_stock_has_decimals(
    service: ProductService, category: Category
) -> None:
    product = service.create(**_data(category, unit="KG", min_stock=Decimal("1.5")))
    with pytest.raises(InvalidMinStockError):
        service.update(product.id, **_data(category, unit="UN", min_stock=Decimal("1.5")))
    assert service.get(product.id).unit == "KG"


def test_update_changes_fields(service: ProductService, category: Category) -> None:
    product = service.create(**_data(category))
    updated = service.update(
        product.id,
        **_data(category, sku="B-2", name="Camisa", sale_price=Decimal("30.50"), min_stock=3),
    )
    assert (updated.sku, updated.name, updated.sale_price, updated.min_stock) == (
        "B-2",
        "Camisa",
        Decimal("30.50"),
        3,
    )


def test_update_allows_keeping_or_recasing_own_sku(
    service: ProductService, category: Category
) -> None:
    product = service.create(**_data(category, sku="abc-1"))
    assert service.update(product.id, **_data(category, sku="abc-1")).sku == "abc-1"
    assert service.update(product.id, **_data(category, sku="ABC-1")).sku == "ABC-1"


def test_update_rejects_sku_of_another_product(
    service: ProductService, category: Category
) -> None:
    service.create(**_data(category, sku="A-1"))
    other = service.create(**_data(category, sku="B-2"))
    with pytest.raises(DuplicateSkuError):
        service.update(other.id, **_data(category, sku="a-1"))


def test_failed_update_does_not_change_the_product(
    service: ProductService, category: Category
) -> None:
    product = service.create(**_data(category))
    with pytest.raises(InvalidPriceError):
        service.update(product.id, **_data(category, name="Nuevo", cost_price=Decimal("-1")))
    assert service.get(product.id).name == "Remera"


def test_update_unknown_product_raises_not_found(
    service: ProductService, category: Category
) -> None:
    with pytest.raises(ProductNotFoundError):
        service.update(999, **_data(category))


def test_deactivate_and_activate_are_idempotent(
    service: ProductService, category: Category
) -> None:
    product = service.create(**_data(category))
    assert service.deactivate(product.id).is_active is False
    assert service.deactivate(product.id).is_active is False
    assert service.activate(product.id).is_active is True
    assert service.activate(product.id).is_active is True


def test_deactivate_unknown_product_raises_not_found(service: ProductService) -> None:
    with pytest.raises(ProductNotFoundError):
        service.deactivate(999)


def test_list_filters_by_category_and_state(
    service: ProductService, session: Session, category: Category
) -> None:
    other = Category(name="Bazar")
    session.add(other)
    session.commit()
    a = service.create(**_data(category, sku="A", name="Alfa"))
    b = service.create(**_data(category, sku="B", name="beta"))
    c = service.create(**_data(other, sku="C", name="Gamma"))
    service.deactivate(b.id)

    assert [p.id for p in service.list()] == [a.id, b.id, c.id]  # orden por nombre sin mayúsculas
    assert [p.id for p in service.list(is_active=True)] == [a.id, c.id]
    assert [p.id for p in service.list(is_active=False)] == [b.id]
    assert [p.id for p in service.list(category_id=category.id)] == [a.id, b.id]
    assert [p.id for p in service.list(category_id=category.id, is_active=True)] == [a.id]
    assert service.list(category_id=other.id, is_active=False) == []


@pytest.mark.parametrize(
    "cost,sale,expected",
    [("10.00", "9.99", True), ("10.00", "10.00", False), ("10.00", "10.01", False)],
)
def test_has_price_warning_only_when_sale_below_cost(
    cost: str, sale: str, expected: bool
) -> None:
    product = Product(cost_price=Decimal(cost), sale_price=Decimal(sale))
    assert ProductService.has_price_warning(product) is expected
