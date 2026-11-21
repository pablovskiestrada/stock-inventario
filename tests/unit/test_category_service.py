import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.repositories.category_repository import CategoryRepository
from app.services.category_service import CategoryService
from app.services.errors import (
    CategoryInUseError,
    CategoryNameRequiredError,
    CategoryNotFoundError,
    DuplicateCategoryNameError,
)


@pytest.fixture
def service(session: Session) -> CategoryService:
    return CategoryService(CategoryRepository(session))


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


def test_delete_blocked_when_category_has_products(
    service: CategoryService, monkeypatch: pytest.MonkeyPatch
) -> None:
    # TEMPORAL: en la rebanada 1b este test se reemplaza por uno real con Product
    # (crear un producto en la categoría y verificar que delete lanza CategoryInUseError).
    category = service.create("Ropa")

    def fake_ensure(category_id: int) -> None:
        raise CategoryInUseError(category_id)

    monkeypatch.setattr(service, "_ensure_has_no_products", fake_ensure)

    with pytest.raises(CategoryInUseError):
        service.delete(category.id)
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
