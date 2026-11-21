from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.category import Category
from app.services.errors import DuplicateCategoryNameError


class CategoryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, name: str) -> Category:
        category = Category(name=name)
        self._session.add(category)
        self._flush_unique(name)
        self._session.refresh(category)
        return category

    def get(self, category_id: int) -> Category | None:
        return self._session.get(Category, category_id)

    def get_by_name_ci(self, name: str) -> Category | None:
        """Busca sin distinguir mayúsculas (RN11)."""
        stmt = select(Category).where(func.lower(Category.name) == name.lower())
        return self._session.scalars(stmt).first()

    def list_all(self) -> Sequence[Category]:
        stmt = select(Category).order_by(func.lower(Category.name), Category.id)
        return self._session.scalars(stmt).all()

    def rename(self, category: Category, name: str) -> Category:
        category.name = name
        self._flush_unique(name)
        self._session.refresh(category)
        return category

    def _flush_unique(self, name: str) -> None:
        # El índice único de la base es la garantía final ante condiciones de carrera.
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise DuplicateCategoryNameError(name) from exc

    def delete(self, category: Category) -> None:
        self._session.delete(category)
        self._session.flush()

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()
