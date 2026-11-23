from collections.abc import Collection
from decimal import Decimal
from typing import Any, NamedTuple

from sqlalchemy import ColumnElement, case, func, select, type_coerce
from sqlalchemy.orm import Session

from app.db import Quantity
from app.models.movement_type import MovementType
from app.models.stock_movement import StockMovement


def _signed_quantity() -> ColumnElement[Any]:
    """RN2: efecto de un movimiento sobre el stock: IN suma, OUT resta, ADJUSTMENT ya trae su signo.

    Es la única definición del signo: el stock actual (`_stock_sum`) y el historial la reutilizan.
    """
    return case(
        (StockMovement.type == MovementType.IN.value, StockMovement.quantity),
        (StockMovement.type == MovementType.OUT.value, -StockMovement.quantity),
        else_=StockMovement.quantity,
    )


def _stock_sum() -> ColumnElement[Decimal]:
    """RN2: `suma(IN) - suma(OUT) + suma(ADJUSTMENT)` en SQL, sobre milésimas enteras (RN24).

    Los ajustes ya traen su signo (RN3), así que suman tal cual. Sin movimientos da 0.
    """
    return type_coerce(func.coalesce(func.sum(_signed_quantity()), 0), Quantity())


class HistoryRow(NamedTuple):
    """Un movimiento del historial con lo que calcula SQL: efecto con signo, saldo y total."""

    movement: StockMovement
    signed_quantity: Decimal
    balance: Decimal
    total: int


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

    def history(self, product_id: int, limit: int) -> list[HistoryRow]:
        """RN30: los últimos `limit` movimientos del producto, del más reciente al más antiguo.

        Una sola sentencia. Las ventanas se evalúan antes del `LIMIT`, así que `balance` (stock
        resultante tras el movimiento) y `total` cubren todo el historial y no solo las filas
        devueltas. El orden es el de inserción (`id`); la fecha no interviene. El signo sale de
        `_signed_quantity()` y la coerción a `Quantity` es la de `_stock_sum()`.
        """
        signed = _signed_quantity()
        running = func.sum(signed).over(
            partition_by=StockMovement.product_id,
            order_by=StockMovement.id,
            rows=(None, 0),  # desde el primer movimiento hasta el actual
        )
        total = func.count().over(partition_by=StockMovement.product_id)
        stmt = (
            select(
                StockMovement,
                type_coerce(signed, Quantity()).label("signed_quantity"),
                type_coerce(running, Quantity()).label("balance"),
                total.label("total"),
            )
            .where(StockMovement.product_id == product_id)
            .order_by(StockMovement.id.desc())
            .limit(limit)
        )
        return [HistoryRow(*row) for row in self._session.execute(stmt)]

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()
