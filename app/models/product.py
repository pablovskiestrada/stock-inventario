from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, Numeric, String, func, text, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin


class Product(TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("length(trim(sku)) > 0", name="sku_not_blank"),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint("cost_price >= 0", name="cost_price_non_negative"),
        CheckConstraint("sale_price >= 0", name="sale_price_non_negative"),
        CheckConstraint("min_stock >= 0", name="min_stock_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    # RN13: FK sin ON DELETE CASCADE; el índice acelera el filtro por categoría y RN9.
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id"), nullable=False, index=True
    )
    cost_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    sale_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    min_stock: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )


# RN1: unicidad del SKU sin distinguir mayúsculas/minúsculas (índice funcional).
Index("uq_products_sku_lower", func.lower(Product.sku), unique=True)
