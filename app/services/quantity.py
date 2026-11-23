"""Reglas puras de cantidades (RN18, RN20). Sin acceso a datos: las reutiliza la rebanada 2b."""
import re
from decimal import Decimal

from app.db import QUANTITY_FACTOR, QUANTITY_SCALE
from app.models.unit import Unit
from app.services.errors import InvalidQuantityError, InvalidUnitError

MAX_QUANTITY = Decimal(10) ** 9  # tope exclusivo; en milésimas entra de sobra en BigInteger
_STEP = Decimal(1).scaleb(-QUANTITY_SCALE)
_NUMBER = re.compile(r"[+-]?(?:[0-9]+[.,]?[0-9]*|[.,][0-9]+)", re.ASCII)

THOUSANDS_MESSAGE = (
    "Escribí la cantidad sin separador de miles; usá una sola coma o punto como decimal."
)


def validate_quantity(unit: Unit | str, quantity: Decimal) -> Decimal:
    """RN18: valida la magnitud de una cantidad según la unidad y la devuelve con 3 decimales.

    El signo y el «> 0» de cada tipo de movimiento (RN3) los aplica quien la use.
    """
    try:
        unit = Unit(unit)
    except ValueError as exc:
        raise InvalidUnitError(unit) from exc
    if isinstance(quantity, bool) or not isinstance(quantity, Decimal | int):
        raise InvalidQuantityError("La cantidad debe ser un número decimal exacto.")
    value = Decimal(quantity)
    if not value.is_finite() or value < 0:
        raise InvalidQuantityError("La cantidad debe ser un número mayor o igual a 0.")
    if value >= MAX_QUANTITY:
        raise InvalidQuantityError("La cantidad es demasiado grande.")
    if value != value.quantize(_STEP):
        raise InvalidQuantityError(f"La cantidad admite hasta {QUANTITY_SCALE} decimales.")
    if not unit.allows_decimals and value != value.to_integral_value():
        raise InvalidQuantityError(f"La unidad {unit.value} solo admite cantidades enteras.")
    return value.quantize(_STEP)


def parse_quantity_input(raw: str) -> Decimal:
    """RN20: interpreta texto de un formulario. Un único separador (`,` o `.`) es el decimal.

    No hay separadores de miles: `1.500` vale 1,5 y `1.500,5` se rechaza. Vacío vale 0.
    """
    text = raw.strip()
    if not text:
        return Decimal(0)
    if sum(text.count(sep) for sep in ",.") > 1:
        raise InvalidQuantityError(THOUSANDS_MESSAGE)
    if _NUMBER.fullmatch(text) is None:
        raise InvalidQuantityError("La cantidad no es un número válido.")
    return Decimal(text.replace(",", "."))
