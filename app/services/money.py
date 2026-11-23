"""Regla pura de importes (RN8, RN22): `Numeric(12, 2)`, nunca float."""
from decimal import Decimal

from app.services.errors import InvalidPriceError

_CENT = Decimal("0.01")
_MAX_PRICE = Decimal(10) ** 10  # Numeric(12, 2): 10 dígitos enteros


def validate_price(value: Decimal, label: str) -> Decimal:
    """Importe >= 0 con hasta 2 decimales; lo devuelve con exactamente 2 decimales."""
    if isinstance(value, bool) or not isinstance(value, Decimal | int):
        raise InvalidPriceError(label)
    amount = Decimal(value)
    if not amount.is_finite() or amount < 0 or amount >= _MAX_PRICE:
        raise InvalidPriceError(label)
    if amount != amount.quantize(_CENT):  # más de 2 decimales
        raise InvalidPriceError(label)
    return amount.quantize(_CENT)
