from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from app.models.movement_type import AdjustmentReason, MovementType
from app.models.stock_movement import StockMovement
from app.routers.deps import (
    CategoryServiceDep,
    ProductServiceDep,
    StockMovementServiceDep,
    http_status_for,
)
from app.routers.htmx import error_fragment
from app.routers.product_views import row_response
from app.schemas.stock_movement import StockMovementCreate
from app.services.errors import DomainError, InvalidMovementTypeError
from app.services.quantity import parse_quantity_input
from app.templating import format_quantity, templates

router = APIRouter(
    prefix="/products/{product_id}/movements", tags=["stock-movements-ui"], include_in_schema=False
)

TITLES = {
    MovementType.IN: "Entrada",
    MovementType.OUT: "Salida",
    MovementType.ADJUSTMENT: "Ajuste",
}
# Entrada y Salida son el mismo formulario con otro precio precargado (RN29).
PRICE_LABELS = {MovementType.IN: "Costo unitario", MovementType.OUT: "Precio unitario de venta"}
NOTICES = {
    MovementType.IN: "Entrada registrada",
    MovementType.OUT: "Salida registrada",
    MovementType.ADJUSTMENT: "Ajuste registrado",
}
REASON_CHOICES = [
    (AdjustmentReason.ROTURA, "Rotura"),
    (AdjustmentReason.MERMA, "Merma"),
    (AdjustmentReason.CONTEO, "Conteo"),
    (AdjustmentReason.ERROR_CARGA, "Error de carga"),
    (AdjustmentReason.OTRO, "Otro"),
]

FIELD_ERRORS = {
    "type": "Elegí un tipo de movimiento: entrada, salida o ajuste.",
    "quantity": "La cantidad no es válida: hasta 3 decimales y sin separador de miles.",
    "unit_price": "El precio unitario debe ser un importe mayor o igual a 0, con hasta 2 decimales.",
    "reason": "Elegí un motivo de la lista.",
}


class MovementForm:
    """Campos del formulario como texto; el schema Pydantic los valida y el servicio decide."""

    def __init__(
        self,
        type: Annotated[str, Form()] = "",
        quantity: Annotated[str, Form()] = "",
        unit_price: Annotated[str, Form()] = "",
        reason: Annotated[str, Form()] = "",
        note: Annotated[str, Form()] = "",
        reference: Annotated[str, Form()] = "",
    ) -> None:
        self._type = type.strip()
        self._quantity = quantity
        # Se acepta la coma decimal ("19,99") habitual en español.
        self._unit_price = unit_price.strip().replace(",", ".")
        self._reason = reason.strip()
        self._note = note
        self._reference = reference

    def parse(self) -> StockMovementCreate:
        # RN20: la coma o el punto (uno solo) es el decimal; los separadores de miles se rechazan.
        return StockMovementCreate(
            type=self._type,
            quantity=parse_quantity_input(self._quantity),
            unit_price=self._unit_price or None,
            reason=self._reason or None,
            note=self._note,
            reference=self._reference,
        )


FormDep = Annotated[MovementForm, Depends()]


def _validation_message(exc: ValidationError) -> str:
    field = str(exc.errors()[0]["loc"][0])
    return FIELD_ERRORS.get(field, "Revisá los datos del formulario.")


def _notice(movement: StockMovement, unit: str) -> str:
    quantity = format_quantity(movement.quantity, unit)
    if movement.type == MovementType.ADJUSTMENT and movement.quantity > 0:
        quantity = f"+{quantity}"
    return f"{NOTICES[MovementType(movement.type)]}: {quantity} {unit}."


@router.get("", response_class=HTMLResponse)
def history(
    request: Request, product_id: int, movements: StockMovementServiceDep
) -> HTMLResponse:
    """RN32: historial del producto, página completa y de solo lectura."""
    try:
        result = movements.history(product_id)
    except DomainError as exc:
        return templates.TemplateResponse(
            request,
            "stock_movements/history_not_found.html",
            {"message": str(exc)},
            status_code=http_status_for(exc),
        )
    context = {
        "history": result,
        "product": result.product,
        "type_labels": {kind.value: label for kind, label in TITLES.items()},
        "reason_labels": {reason.value: label for reason, label in REASON_CHOICES},
    }
    return templates.TemplateResponse(request, "stock_movements/history.html", context)


@router.get("/new", response_class=HTMLResponse)
def new(
    request: Request,
    product_id: int,
    products: ProductServiceDep,
    movements: StockMovementServiceDep,
    type: str = MovementType.IN.value,
) -> HTMLResponse:
    """Formulario manual (RN29): se abre desde el producto, sobre su fila."""
    try:
        movement_type = MovementType(type)
    except ValueError:
        return error_fragment(request, str(InvalidMovementTypeError(type)), 422, "#list-error")
    try:
        product = products.get(product_id)
        stock = movements.current_stock(product_id)
    except DomainError as exc:
        return error_fragment(request, str(exc), http_status_for(exc), "#list-error")
    default_price = product.cost_price if movement_type is MovementType.IN else product.sale_price
    context = {
        "product": product,
        "stock": stock,
        "movement_type": movement_type.value,
        "title": TITLES[movement_type],
        "price_label": PRICE_LABELS.get(movement_type, ""),
        "default_price": default_price,  # precargado y editable; en Ajuste no se usa
        "reason_choices": REASON_CHOICES,
    }
    return templates.TemplateResponse(request, "stock_movements/_form_row.html", context)


@router.post("", response_class=HTMLResponse)
def register(
    request: Request,
    product_id: int,
    form: FormDep,
    products: ProductServiceDep,
    categories: CategoryServiceDep,
    movements: StockMovementServiceDep,
) -> HTMLResponse:
    target = f"#row-error-{product_id}"
    try:
        movement = movements.register_movement(product_id=product_id, **form.parse().model_dump())
        product = products.get(product_id)
    except ValidationError as exc:
        return error_fragment(request, _validation_message(exc), 422, target)
    except DomainError as exc:
        return error_fragment(request, str(exc), http_status_for(exc), target)
    return row_response(
        request,
        categories,
        movements,
        product,
        movement_notice=_notice(movement, product.unit),
    )
