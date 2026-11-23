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


templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.filters["quantity"] = format_quantity
templates.env.globals["unit_choices"] = list(UNIT_LABELS.items())
