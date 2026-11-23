from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models.movement_type import AdjustmentReason, MovementType
from app.schemas.product import Price

# Con signo: solo el servicio sabe si es válido según el tipo (RN3). Acá solo la forma.
MovementQuantity = Annotated[Decimal, Field(max_digits=12, decimal_places=3)]


class StockMovementCreate(BaseModel):
    """Forma de entrada; las reglas cruzadas (RN3, RN4, RN7, RN22, RN23) viven en el servicio."""

    type: MovementType
    quantity: MovementQuantity
    unit_price: Price | None = None
    reason: AdjustmentReason | None = None
    note: str | None = None
    reference: str | None = None


class StockMovementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    type: MovementType
    quantity: Decimal
    unit_price: Decimal | None
    reason: AdjustmentReason | None
    note: str | None
    reference: str | None
    created_at: datetime
