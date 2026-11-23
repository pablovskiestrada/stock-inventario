from collections.abc import Collection
from decimal import Decimal

from sqlalchemy import ColumnElement, case, func, select, type_coerce
from sqlalchemy.orm import Session

from app.db import Quantity
from app.models.movement_type import MovementType
from app.models.stock_movement import StockMovement


def _stock_sum() -> ColumnElement[Decimal]:
    """RN2: `suma(IN) - suma(OUT) + suma(ADJUSTMENT)` en SQL, sobre milésimas enteras (RN24).

    Es la única definición de la fórmula. Los ajustes ya traen su signo (RN3), así que
    suman tal cual. Sin movimientos da 0.
    """
    signed = case(
        (StockMovement.type == MovementType.IN.value, StockMovement.quantity),
        (StockMovement.type == MovementType.OUT.value, -StockMovement.quantity),
        else_=StockMovement.quantity,
    )
    return type_coerce(func.coalesce(func.sum(signed), 0), Quantity())


class StockMovementRepository:
    """Libro mayor: solo se agregan filas y se consulta (RN5). No hay update ni delete."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(
        self,
        *,
        product_id: int,
        type: str,
        quantity: Decimal,
        unit_price: Decimal | None,
        reason: str | None,
        note: str | None,
        reference: str | None,
    ) -> StockMovement:
        movement = StockMovement(
            product_id=product_id,
            type=type,
            quantity=quantity,
            unit_price=unit_price,
            reason=reason,
            note=note,
            reference=reference,
        )
        self._session.add(movement)
        self._session.flush()
        self._session.refresh(movement)
        return movement

    def exists_for_product(self, product_id: int) -> bool:
        stmt = select(StockMovement.id).where(StockMovement.product_id == product_id).limit(1)
        return self._session.scalar(stmt) is not None

    def current_stock(self, product_id: int) -> Decimal:
        stmt = select(_stock_sum()).where(StockMovement.product_id == product_id)
        return self._session.scalar(stmt) or Decimal(0)

    def current_stock_by_product(self, product_ids: Collection[int]) -> dict[int, Decimal]:
        """Una sola consulta agrupada para todo un listado (RN24). Omite los sin movimientos."""
        if not product_ids:
            return {}
        stmt = (
            select(StockMovement.product_id, _stock_sum())
            .where(StockMovement.product_id.in_(product_ids))
            .group_by(StockMovement.product_id)
        )
        return {product_id: stock for product_id, stock in self._session.execute(stmt)}

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()
