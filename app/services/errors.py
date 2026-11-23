from decimal import Decimal


class DomainError(Exception):
    """Base de las excepciones de dominio. Los routers las traducen a HTTP."""


class CategoryNotFoundError(DomainError):
    def __init__(self, category_id: int) -> None:
        super().__init__(f"La categoría {category_id} no existe.")
        self.category_id = category_id


class CategoryNameRequiredError(DomainError):
    def __init__(self) -> None:
        super().__init__("El nombre de la categoría es obligatorio.")


class DuplicateCategoryNameError(DomainError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Ya existe una categoría llamada «{name}».")
        self.name = name


class CategoryInUseError(DomainError):
    def __init__(self, category_id: int) -> None:
        super().__init__("No se puede eliminar una categoría que tiene productos.")
        self.category_id = category_id


class ProductNotFoundError(DomainError):
    def __init__(self, product_id: int) -> None:
        super().__init__(f"El producto {product_id} no existe.")
        self.product_id = product_id


class ProductSkuRequiredError(DomainError):
    def __init__(self) -> None:
        super().__init__("El SKU es obligatorio.")


class ProductNameRequiredError(DomainError):
    def __init__(self) -> None:
        super().__init__("El nombre del producto es obligatorio.")


class ProductFieldTooLongError(DomainError):
    def __init__(self, label: str, max_length: int) -> None:
        super().__init__(f"{label} no puede superar los {max_length} caracteres.")
        self.max_length = max_length


class DuplicateSkuError(DomainError):
    def __init__(self, sku: str) -> None:
        super().__init__(f"Ya existe un producto con el SKU «{sku}».")
        self.sku = sku


class InvalidProductCategoryError(DomainError):
    def __init__(self, category_id: int) -> None:
        super().__init__(f"La categoría {category_id} no existe.")
        self.category_id = category_id


class InvalidPriceError(DomainError):
    def __init__(self, label: str) -> None:
        super().__init__(f"{label} debe ser un importe mayor o igual a 0, con hasta 2 decimales.")


class InvalidMinStockError(DomainError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"El stock mínimo no es válido. {reason}")
        self.reason = reason


class InvalidUnitError(DomainError):
    def __init__(self, unit: object) -> None:
        super().__init__(f"La unidad «{unit}» no es válida. Usá UN, KG, M o L.")
        self.unit = unit


class InvalidQuantityError(DomainError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class InactiveProductError(DomainError):
    """RN7: un producto inactivo no admite movimientos nuevos."""

    def __init__(self, product_id: int) -> None:
        super().__init__("El producto está inactivo: reactivalo para registrar movimientos.")
        self.product_id = product_id


def _plain(value: Decimal) -> str:
    """`Decimal("1.500")` -> `1.5`; `Decimal("5.000")` -> `5` (para los mensajes)."""
    return format(value.normalize(), "f")


class InsufficientStockError(DomainError):
    """RN4: el movimiento dejaría el stock en negativo."""

    def __init__(self, available: Decimal, requested: Decimal, unit: str) -> None:
        super().__init__(
            f"Stock insuficiente: hay {_plain(available)} {unit} y el movimiento resta "
            f"{_plain(requested)} {unit}."
        )
        self.available = available
        self.requested = requested
        self.unit = unit


class UnitChangeBlockedError(DomainError):
    """RN27: no se cambia la unidad de un producto que ya tiene movimientos."""

    def __init__(self, product_id: int) -> None:
        super().__init__(
            "No se puede cambiar la unidad de un producto que ya tiene movimientos de stock."
        )
        self.product_id = product_id


class InvalidMovementTypeError(DomainError):
    def __init__(self, movement_type: object) -> None:
        super().__init__(f"El tipo de movimiento «{movement_type}» no es válido. Usá IN, OUT o ADJUSTMENT.")
        self.movement_type = movement_type


class AdjustmentReasonRequiredError(DomainError):
    def __init__(self) -> None:
        super().__init__("El ajuste necesita un motivo: ROTURA, MERMA, CONTEO, ERROR_CARGA u OTRO.")


class ReasonNotAllowedError(DomainError):
    def __init__(self) -> None:
        super().__init__("Solo los ajustes llevan motivo: en una entrada o una salida no se informa.")


class InvalidAdjustmentReasonError(DomainError):
    def __init__(self, reason: object) -> None:
        super().__init__(
            f"El motivo «{reason}» no es válido. Usá ROTURA, MERMA, CONTEO, ERROR_CARGA u OTRO."
        )
        self.reason = reason


class NoteRequiredError(DomainError):
    def __init__(self) -> None:
        super().__init__("Con el motivo OTRO la nota es obligatoria: explicá qué pasó.")


class UnitPriceRequiredError(DomainError):
    def __init__(self, movement_type: str) -> None:
        label = "el costo unitario" if movement_type == "IN" else "el precio unitario de venta"
        super().__init__(f"Falta {label}: es obligatorio en este movimiento.")
        self.movement_type = movement_type


class UnitPriceNotAllowedError(DomainError):
    def __init__(self) -> None:
        super().__init__("Un ajuste no lleva precio unitario.")


class MovementFieldTooLongError(DomainError):
    def __init__(self, label: str, max_length: int) -> None:
        super().__init__(f"{label} no puede superar los {max_length} caracteres.")
        self.max_length = max_length
