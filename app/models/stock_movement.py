from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, CreatedAtMixin, Quantity
from app.models.movement_type import AdjustmentReason, MovementType

_TYPES = ", ".join(f"'{t.value}'" for t in MovementType)
_REASONS = ", ".join(f"'{r.value}'" for r in AdjustmentReason)
_ADJ = f"'{MovementType.ADJUSTMENT.value}'"
_OTHER = f"'{AdjustmentReason.OTRO.value}'"


class StockMovement(CreatedAtMixin, Base):
    """Libro mayor del stock (RN5): inmutable, sin `updated_at`. Los errores se corrigen con un ajuste."""

    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint(f"type IN ({_TYPES})", name="type_valid"),
        # RN3: IN/OUT > 0; ADJUSTMENT distinto de 0 (el signo es la corrección).
        CheckConstraint(
            f"(type = {_ADJ} AND quantity <> 0) OR (type <> {_ADJ} AND quantity > 0)",
            name="quantity_sign_by_type",
        ),
        CheckConstraint("unit_price IS NULL OR unit_price >= 0", name="unit_price_non_negative"),
        # RN22: obligatorio en IN/OUT, NULL en ADJUSTMENT.
        CheckConstraint(
            f"(type = {_ADJ} AND unit_price IS NULL) OR (type <> {_ADJ} AND unit_price IS NOT NULL)",
            name="unit_price_by_type",
        ),
        # RN23: motivo de la lista fija en ADJUSTMENT; NULL en IN/OUT. El `IS NOT NULL` es
        # necesario: `NULL IN (...)` es NULL y un CHECK que da NULL se acepta.
        CheckConstraint(
            f"(type = {_ADJ} AND reason IS NOT NULL AND reason IN ({_REASONS})) "
            f"OR (type <> {_ADJ} AND reason IS NULL)",
            name="reason_by_type",
        ),
        CheckConstraint(
            f"reason IS NULL OR reason <> {_OTHER} OR (note IS NOT NULL AND length(trim(note)) > 0)",
            name="note_required_for_other",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # RN21: FK sin ON DELETE CASCADE; el índice acelera el cálculo del stock (RN24).
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    # RN19: milésimas enteras en la base. Con signo solo en ADJUSTMENT.
    quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(20), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
