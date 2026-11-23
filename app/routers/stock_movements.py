from fastapi import APIRouter

from app.routers.deps import StockMovementServiceDep
from app.schemas.stock_movement import (
    StockMovementCreate,
    StockMovementHistoryItem,
    StockMovementHistoryRead,
    StockMovementRead,
)

# Solo POST (registrar) y GET (historial, RN31): los movimientos son inmutables (RN5).
router = APIRouter(prefix="/api/products/{product_id}/movements", tags=["stock-movements"])


@router.get("", response_model=StockMovementHistoryRead)
def movement_history(
    product_id: int, service: StockMovementServiceDep
) -> StockMovementHistoryRead:
    history = service.history(product_id)
    return StockMovementHistoryRead(
        product_id=history.product.id,
        unit=history.product.unit,
        limit=history.limit,
        total=history.total,
        items=[
            StockMovementHistoryItem(
                **StockMovementRead.model_validate(row.movement).model_dump(),
                signed_quantity=row.signed_quantity,
                balance=row.balance,
            )
            for row in history.entries
        ],
    )


@router.post("", response_model=StockMovementRead, status_code=201)
def register_movement(
    product_id: int, payload: StockMovementCreate, service: StockMovementServiceDep
) -> StockMovementRead:
    movement = service.register_movement(product_id=product_id, **payload.model_dump())
    return StockMovementRead.model_validate(movement)
