from fastapi import APIRouter

from app.routers.deps import StockMovementServiceDep
from app.schemas.stock_movement import StockMovementCreate, StockMovementRead

# Solo POST: los movimientos son inmutables (RN5). El GET del historial llega en la rebanada 3.
router = APIRouter(prefix="/api/products/{product_id}/movements", tags=["stock-movements"])


@router.post("", response_model=StockMovementRead, status_code=201)
def register_movement(
    product_id: int, payload: StockMovementCreate, service: StockMovementServiceDep
) -> StockMovementRead:
    movement = service.register_movement(product_id=product_id, **payload.model_dump())
    return StockMovementRead.model_validate(movement)
