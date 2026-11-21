from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.product import Product
from app.repositories.category_repository import CategoryRepository
from app.repositories.product_repository import ProductRepository
from app.services.category_service import CategoryService
from app.services.errors import (
    CategoryInUseError,
    CategoryNameRequiredError,
    CategoryNotFoundError,
    DuplicateCategoryNameError,
)


@pytest.fixture
def service(session: Session) -> CategoryService:
    return CategoryService(CategoryRepository(session), ProductRepository(session))


def _add_product(session: Session, category_id: int, *, is_active: bool = True) -> None:
    session.add(
        Product(
            sku=f"SKU-{category_id}-{is_active}",
            name="Remera",
            category_id=category_id,
            cost_price=Decimal("10.00"),
            sale_price=Decimal("20.00"),
            is_active=is_active,
        )
    )
    session.commit()


def test_create_trims_name(service: CategoryService) -> None:
    assert service.create("  Ropa ").name == "Ropa"


@pytest.mark.parametrize("name", ["", "   ", "\t\n"])
def test_service_rejects_blank_name_by_itself(service: CategoryService, name: str) -> None:
    with pytest.raises(CategoryNameRequiredError):
        service.create(name)


def test_rename_rejects_blank_name(service: CategoryService) -> None:
    category = service.create("Ropa")
    with pytest.raises(CategoryNameRequiredError):
        service.rename(category.id, "  ")


def test_create_rejects_duplicate_after_trim(service: CategoryService) -> None:
    service.create("Ropa")
    with pytest.raises(DuplicateCategoryNameError):
        service.create(" Ropa")


def test_create_rejects_duplicate_case_insensitive(service: CategoryService) -> None:
    service.create("Ropa")
    with pytest.raises(DuplicateCategoryNameError):
        service.create("ropa")


def test_rename_rejects_duplicate_case_insensitive(service: CategoryService) -> None:
    service.create("Ropa")
    other = service.create("Calzado")
    with pytest.raises(DuplicateCategoryNameError):
        service.rename(other.id, "ROPA")


def test_rename_changes_name(service: CategoryService) -> None:
    category = service.create("Ropa")
    assert service.rename(category.id, " Indumentaria ").name == "Indumentaria"


def test_rename_allows_changing_only_the_case_of_own_name(service: CategoryService) -> None:
    category = service.create("ropa")
    assert service.rename(category.id, "Ropa").name == "Ropa"


def test_rename_to_same_name_is_allowed(service: CategoryService) -> None:
    category = service.create("Ropa")
    assert service.rename(category.id, "Ropa").name == "Ropa"


def test_rename_unknown_category_raises_not_found(service: CategoryService) -> None:
    with pytest.raises(CategoryNotFoundError):
        service.rename(999, "X")


def test_delete_unknown_category_raises_not_found(service: CategoryService) -> None:
    with pytest.raises(CategoryNotFoundError):
        service.delete(999)


def test_list_is_ordered_by_name_ignoring_case(service: CategoryService) -> None:
    for name in ["calzado", "Bazar", "Ropa"]:
        service.create(name)
    assert [c.name for c in service.list()] == ["Bazar", "calzado", "Ropa"]


def test_delete_category_without_products(service: CategoryService) -> None:
    category = service.create("Ropa")
    service.delete(category.id)
    assert service.list() == []


@pytest.mark.parametrize("is_active", [True, False])
def test_delete_blocked_when_category_has_products(
    service: CategoryService, session: Session, is_active: bool
) -> None:
    """RN9: bloquea con productos activos o inactivos."""
    category = service.create("Ropa")
    _add_product(session, category.id, is_active=is_active)

    with pytest.raises(CategoryInUseError):
        service.delete(category.id)
    assert [c.name for c in service.list()] == ["Ropa"]


def test_delete_only_checks_products_of_that_category(
    service: CategoryService, session: Session
) -> None:
    used = service.create("Ropa")
    empty = service.create("Bazar")
    _add_product(session, used.id)

    service.delete(empty.id)
    assert [c.name for c in service.list()] == ["Ropa"]


def test_database_enforces_case_insensitive_uniqueness(session: Session) -> None:
    from app.models.category import Category

    session.add(Category(name="Ropa"))
    session.commit()
    session.add(Category(name="ropa"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_database_rejects_blank_name(session: Session) -> None:
    from app.models.category import Category

    session.add(Category(name="   "))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
