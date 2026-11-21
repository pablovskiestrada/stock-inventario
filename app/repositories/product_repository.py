from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.product import Product
from app.services.errors import DuplicateSkuError


class ProductRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(
        self,
        *,
        sku: str,
        name: str,
        category_id: int,
        cost_price: Decimal,
        sale_price: Decimal,
        min_stock: int,
    ) -> Product:
        product = Product(
            sku=sku,
            name=name,
            category_id=category_id,
            cost_price=cost_price,
            sale_price=sale_price,
            min_stock=min_stock,
        )
        self._session.add(product)
        self._flush_unique(sku)
        self._session.refresh(product)
        return product

    def get(self, product_id: int) -> Product | None:
        return self._session.get(Product, product_id)

    def get_by_sku_ci(self, sku: str) -> Product | None:
        """Busca sin distinguir mayúsculas (RN1)."""
        stmt = select(Product).where(func.lower(Product.sku) == sku.lower())
        return self._session.scalars(stmt).first()

    def list_filtered(
        self, *, category_id: int | None = None, is_active: bool | None = None
    ) -> Sequence[Product]:
        stmt = select(Product)
        if category_id is not None:
            stmt = stmt.where(Product.category_id == category_id)
        if is_active is not None:
            stmt = stmt.where(Product.is_active == is_active)
        stmt = stmt.order_by(func.lower(Product.name), Product.id)
        return self._session.scalars(stmt).all()

    def update(
        self,
        product: Product,
        *,
        sku: str,
        name: str,
        category_id: int,
        cost_price: Decimal,
        sale_price: Decimal,
        min_stock: int,
    ) -> Product:
        product.sku = sku
        product.name = name
        product.category_id = category_id
        product.cost_price = cost_price
        product.sale_price = sale_price
        product.min_stock = min_stock
        self._flush_unique(sku)
        self._session.refresh(product)
        return product

    def set_active(self, product: Product, is_active: bool) -> Product:
        product.is_active = is_active
        self._session.flush()
        self._session.refresh(product)
        return product

    def count_by_category(self, category_id: int) -> int:
        stmt = select(func.count()).select_from(Product).where(Product.category_id == category_id)
        return self._session.scalar(stmt) or 0

    def _flush_unique(self, sku: str) -> None:
        # El índice único de la base es la garantía final ante condiciones de carrera.
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise DuplicateSkuError(sku) from exc

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()
