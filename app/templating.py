from datetime import UTC, datetime, tzinfo
from decimal import Decimal
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.models.unit import Unit

BASE_DIR = Path(__file__).resolve().parent

UNIT_LABELS: dict[Unit, str] = {
    Unit.UN: "Unidades (UN)",
    Unit.KG: "Kilogramos (KG)",
    Unit.M: "Metros (M)",
    Unit.L: "Litros (L)",
}


def format_quantity(value: Decimal, unit: str) -> str:
    """UN sin decimales; el resto con los decimales significativos (máx. 3): `5`, `1.5`, `2`."""
    if not Unit(unit).allows_decimals:
        return str(int(value))
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def format_signed_quantity(value: Decimal, unit: str) -> str:
    """Cantidad con signo explícito en las positivas: `+1.5`, `-3` (el signo ya viene de SQL, RN30)."""
    text = format_quantity(value, unit)
    return f"+{text}" if value > 0 else text


# Zona en que se muestran las fechas. `None` = la zona local del sistema (el sistema es local, RN32);
# los tests la fijan para no depender de la máquina.
DISPLAY_TZ: tzinfo | None = None


def to_local(value: datetime, tz: tzinfo | None = None) -> datetime:
    """Convierte a `tz` (o a la zona local del sistema si es `None`).

    SQLite devuelve los datetimes sin zona, pero siempre son UTC (`CURRENT_TIMESTAMP`): se los
    trata como UTC antes de convertir.
    """
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value
    return aware.astimezone(tz)


def format_local_datetime(value: datetime) -> str:
    """`23/11/2026 14:05`, en la zona `DISPLAY_TZ`."""
    return to_local(value, DISPLAY_TZ).strftime("%d/%m/%Y %H:%M")


templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.filters["quantity"] = format_quantity
templates.env.filters["signed_quantity"] = format_signed_quantity
templates.env.filters["local_datetime"] = format_local_datetime
templates.env.globals["unit_choices"] = list(UNIT_LABELS.items())
