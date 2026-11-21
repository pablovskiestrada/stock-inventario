from collections.abc import Sequence

from app.models.category import Category
from app.repositories.category_repository import CategoryRepository
from app.repositories.product_repository import ProductRepository
from app.services.errors import (
    CategoryInUseError,
    CategoryNameRequiredError,
    CategoryNotFoundError,
    DuplicateCategoryNameError,
)


class CategoryService:
    def __init__(
        self, repository: CategoryRepository, product_repository: ProductRepository
    ) -> None:
        self._repo = repository
        self._products = product_repository

    def list(self) -> Sequence[Category]:
        return self._repo.list_all()

    def get(self, category_id: int) -> Category:
        category = self._repo.get(category_id)
        if category is None:
            raise CategoryNotFoundError(category_id)
        return category

    def create(self, name: str) -> Category:
        clean = self._normalize_name(name)
        if self._repo.get_by_name_ci(clean) is not None:
            raise DuplicateCategoryNameError(clean)
        category = self._repo.add(clean)
        self._repo.commit()
        return category

    def rename(self, category_id: int, name: str) -> Category:
        category = self.get(category_id)
        clean = self._normalize_name(name)
        existing = self._repo.get_by_name_ci(clean)
        if existing is not None and existing.id != category.id:
            raise DuplicateCategoryNameError(clean)
        if category.name != clean:
            self._repo.rename(category, clean)
            self._repo.commit()
        return category

    def delete(self, category_id: int) -> None:
        category = self.get(category_id)
        self._ensure_has_no_products(category.id)
        self._repo.delete(category)
        self._repo.commit()

    def _ensure_has_no_products(self, category_id: int) -> None:
        """RN9: una categoría con productos (activos o inactivos) no se puede eliminar.

        La FK ``products.category_id`` (sin ON DELETE CASCADE) es la segunda defensa.
        """
        if self._products.count_by_category(category_id) > 0:
            raise CategoryInUseError(category_id)

    @staticmethod
    def _normalize_name(name: str) -> str:
        clean = name.strip()
        if not clean:
            raise CategoryNameRequiredError()
        return clean
