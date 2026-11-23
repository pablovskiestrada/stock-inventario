from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from app.models.product import Product
from app.models.unit import Unit
from app.repositories.category_repository import CategoryRepository
from app.repositories.product_repository import ProductRepository
from app.repositories.stock_movement_repository import StockMovementRepository
from app.services.errors import (
    DomainError,
    DuplicateSkuError,
    InvalidMinStockError,
    InvalidProductCategoryError,
    InvalidQuantityError,
    InvalidUnitError,
    ProductFieldTooLongError,
    ProductNameRequiredError,
    ProductNotFoundError,
    ProductSkuRequiredError,
    UnitChangeBlockedError,
)
from app.services.money import validate_price
from app.services.quantity import validate_quantity

SKU_MAX_LENGTH = 50
NAME_MAX_LENGTH = 150


class ProductService:
    def __init__(
        self,
        repository: ProductRepository,
        category_repository: CategoryRepository,
        movement_repository: StockMovementRepository,
    ) -> None:
        self._repo = repository
        self._categories = category_repository
        self._movements = movement_repository

    def list(
        self, *, category_id: int | None = None, is_active: bool | None = None
    ) -> Sequence[Product]:
        return self._repo.list_filtered(category_id=category_id, is_active=is_active)

    def get(self, product_id: int) -> Product:
        product = self._repo.get(product_id)
        if product is None:
            raise ProductNotFoundError(product_id)
        return product

    def create(
        self,
        *,
        sku: str,
        name: str,
        category_id: int,
        cost_price: Decimal,
        sale_price: Decimal,
        unit: str = Unit.UN,
        min_stock: Decimal = Decimal(0),
    ) -> Product:
        fields = self._validated_fields(
            sku, name, category_id, cost_price, sale_price, unit, min_stock
        )
        if self._repo.get_by_sku_ci(fields["sku"]) is not None:
            raise DuplicateSkuError(fields["sku"])
        product = self._repo.add(**fields)
        self._repo.commit()
        return product

    def update(
        self,
        product_id: int,
        *,
        sku: str,
        name: str,
        category_id: int,
        cost_price: Decimal,
        sale_price: Decimal,
        unit: str = Unit.UN,
        min_stock: Decimal = Decimal(0),
    ) -> Product:
        product = self.get(product_id)
        fields = self._validated_fields(
            sku, name, category_id, cost_price, sale_price, unit, min_stock
        )
        self._ensure_unit_change_is_allowed(product, fields["unit"])
        existing = self._repo.get_by_sku_ci(fields["sku"])
        if existing is not None and existing.id != product.id:
            raise DuplicateSkuError(fields["sku"])
        self._repo.update(product, **fields)
        self._repo.commit()
        return product

    def deactivate(self, product_id: int) -> Product:
        return self._set_active(product_id, False)

    def activate(self, product_id: int) -> Product:
        return self._set_active(product_id, True)

    @staticmethod
    def has_price_warning(product: Product) -> bool:
        """RN16: advertencia informativa; nunca bloquea el guardado."""
        return product.sale_price < product.cost_price

    def _ensure_unit_change_is_allowed(self, product: Product, new_unit: str) -> None:
        """RN27: los movimientos guardan cantidades válidas para la unidad con que se cargaron.

        Cambiar la unidad después las reinterpretaría (p. ej. 1,5 KG -> 1,5 UN, inválido), así
        que se rechaza si el producto ya tiene movimientos. El SKU no tiene esa restricción (RN28).
        """
        if new_unit != product.unit and self._movements.exists_for_product(product.id):
            raise UnitChangeBlockedError(product.id)

    def _set_active(self, product_id: int, is_active: bool) -> Product:
        product = self.get(product_id)
        if product.is_active != is_active:  # idempotente (RN6)
            self._repo.set_active(product, is_active)
            self._repo.commit()
        return product

    def _validated_fields(
        self,
        sku: str,
        name: str,
        category_id: int,
        cost_price: Decimal,
        sale_price: Decimal,
        unit: str,
        min_stock: Decimal,
    ) -> dict[str, Any]:
        if self._categories.get(category_id) is None:
            raise InvalidProductCategoryError(category_id)
        valid_unit = self._validated_unit(unit)
        return {
            "sku": self._normalize_text(sku, SKU_MAX_LENGTH, "El SKU", ProductSkuRequiredError()),
            "name": self._normalize_text(
                name, NAME_MAX_LENGTH, "El nombre", ProductNameRequiredError()
            ),
            "category_id": category_id,
            "cost_price": validate_price(cost_price, "El precio de costo"),
            "sale_price": validate_price(sale_price, "El precio de venta"),
            "unit": valid_unit.value,
            "min_stock": self._validated_min_stock(valid_unit, min_stock),
        }

    @staticmethod
    def _normalize_text(value: str, max_length: int, label: str, required: DomainError) -> str:
        clean = value.strip()
        if not clean:
            raise required
        if len(clean) > max_length:
            raise ProductFieldTooLongError(label, max_length)
        return clean

    @staticmethod
    def _validated_unit(unit: str) -> Unit:
        try:
            return Unit(unit)
        except ValueError as exc:
            raise InvalidUnitError(unit) from exc

    @staticmethod
    def _validated_min_stock(unit: Unit, value: Decimal) -> Decimal:
        """RN14/RN18: cantidad >= 0 que la unidad del producto admita (también al cambiarla)."""
        try:
            return validate_quantity(unit, value)
        except InvalidQuantityError as exc:
            raise InvalidMinStockError(exc.reason) from exc
