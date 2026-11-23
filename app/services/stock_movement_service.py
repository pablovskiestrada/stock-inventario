from collections.abc import Collection
from decimal import Decimal

from app.models.movement_type import AdjustmentReason, MovementType
from app.models.product import Product
from app.models.stock_movement import StockMovement
from app.repositories.product_repository import ProductRepository
from app.repositories.stock_movement_repository import StockMovementRepository
from app.services.errors import (
    AdjustmentReasonRequiredError,
    InactiveProductError,
    InsufficientStockError,
    InvalidAdjustmentReasonError,
    InvalidMovementTypeError,
    InvalidQuantityError,
    MovementFieldTooLongError,
    NoteRequiredError,
    ProductNotFoundError,
    ReasonNotAllowedError,
    UnitPriceNotAllowedError,
    UnitPriceRequiredError,
)
from app.services.money import validate_price
from app.services.quantity import validate_quantity

NOTE_MAX_LENGTH = 500
REFERENCE_MAX_LENGTH = 100


class StockMovementService:
    """Libro mayor del stock. `register_movement` es el único punto de escritura (RN26)."""

    def __init__(
        self, repository: StockMovementRepository, product_repository: ProductRepository
    ) -> None:
        self._repo = repository
        self._products = product_repository

    def current_stock(self, product_id: int) -> Decimal:
        """RN2: stock actual calculado desde los movimientos."""
        self._get_product(product_id)
        return self._repo.current_stock(product_id)

    def current_stock_by_product(self, product_ids: Collection[int]) -> dict[int, Decimal]:
        """RN24: una sola consulta agrupada. Los productos sin movimientos valen 0."""
        found = self._repo.current_stock_by_product(product_ids)
        return {product_id: found.get(product_id, Decimal(0)) for product_id in product_ids}

    def register_movement(
        self,
        *,
        product_id: int,
        type: MovementType | str,
        quantity: Decimal,
        unit_price: Decimal | None = None,
        reason: AdjustmentReason | str | None = None,
        note: str | None = None,
        reference: str | None = None,
    ) -> StockMovement:
        """Registra un movimiento aplicando todas las reglas (RN3, RN4, RN7, RN22, RN23).

        El cálculo del stock y el INSERT van en la misma transacción (RN25): un único
        `commit()` al final, y si algo falla antes no se persiste nada.
        """
        product = self._get_product(product_id)
        if not product.is_active:  # RN7
            raise InactiveProductError(product_id)

        movement_type = self._validated_type(type)
        clean_reason = self._validated_reason(movement_type, reason)
        clean_price = self._validated_unit_price(movement_type, unit_price)
        clean_note = self._clean_text(note, NOTE_MAX_LENGTH, "La nota")
        clean_reference = self._clean_text(reference, REFERENCE_MAX_LENGTH, "La referencia")
        if clean_reason is AdjustmentReason.OTRO and clean_note is None:
            raise NoteRequiredError()
        stored_quantity = self._validated_quantity(movement_type, product.unit, quantity)

        self._ensure_stock_stays_non_negative(product.unit, movement_type, product.id, stored_quantity)

        movement = self._repo.add(
            product_id=product.id,
            type=movement_type.value,
            quantity=stored_quantity,
            unit_price=clean_price,
            reason=clean_reason.value if clean_reason else None,
            note=clean_note,
            reference=clean_reference,
        )
        self._repo.commit()
        return movement

    def _get_product(self, product_id: int) -> Product:
        product = self._products.get(product_id)
        if product is None:
            raise ProductNotFoundError(product_id)
        return product

    def _ensure_stock_stays_non_negative(
        self, unit: str, movement_type: MovementType, product_id: int, quantity: Decimal
    ) -> None:
        """RN4: dejar el stock en exactamente 0 es válido; en negativo, no."""
        delta = -quantity if movement_type is MovementType.OUT else quantity
        available = self._repo.current_stock(product_id)
        if available + delta < 0:
            raise InsufficientStockError(available, abs(delta), unit)

    @staticmethod
    def _validated_type(value: MovementType | str) -> MovementType:
        try:
            return MovementType(value)
        except ValueError as exc:
            raise InvalidMovementTypeError(value) from exc

    @staticmethod
    def _validated_reason(
        movement_type: MovementType, reason: AdjustmentReason | str | None
    ) -> AdjustmentReason | None:
        """RN23: motivo obligatorio y de la lista fija en ADJUSTMENT; prohibido en IN/OUT."""
        if movement_type is not MovementType.ADJUSTMENT:
            if reason is not None:
                raise ReasonNotAllowedError()
            return None
        if reason is None or (isinstance(reason, str) and not reason.strip()):
            raise AdjustmentReasonRequiredError()
        try:
            return AdjustmentReason(reason)
        except ValueError as exc:
            raise InvalidAdjustmentReasonError(reason) from exc

    @staticmethod
    def _validated_unit_price(
        movement_type: MovementType, unit_price: Decimal | None
    ) -> Decimal | None:
        """RN22: obligatorio en IN/OUT, ausente (ni siquiera 0) en ADJUSTMENT."""
        if movement_type is MovementType.ADJUSTMENT:
            if unit_price is not None:
                raise UnitPriceNotAllowedError()
            return None
        if unit_price is None:
            raise UnitPriceRequiredError(movement_type.value)
        return validate_price(unit_price, "El precio unitario")

    @staticmethod
    def _clean_text(value: str | None, max_length: int, label: str) -> str | None:
        """RN23: sin espacios en los extremos; vacío vale NULL."""
        if value is None:
            return None
        clean = value.strip()
        if not clean:
            return None
        if len(clean) > max_length:
            raise MovementFieldTooLongError(label, max_length)
        return clean

    @staticmethod
    def _validated_quantity(movement_type: MovementType, unit: str, quantity: Decimal) -> Decimal:
        """RN3 + RN18: la magnitud se valida según la unidad; el signo, según el tipo.

        En ADJUSTMENT se valida el valor absoluto (`copy_abs` no redondea) y se conserva el signo.
        """
        if isinstance(quantity, bool) or not isinstance(quantity, Decimal | int):
            raise InvalidQuantityError("La cantidad debe ser un número decimal exacto.")
        value = Decimal(quantity)
        magnitude = validate_quantity(unit, value.copy_abs())  # rechaza NaN/infinito antes de comparar
        if movement_type is MovementType.ADJUSTMENT:
            if value == 0:
                raise InvalidQuantityError("Un ajuste no puede ser de cantidad 0.")
            return magnitude if value > 0 else -magnitude
        if value <= 0:
            raise InvalidQuantityError("La cantidad debe ser mayor a 0.")
        return magnitude
