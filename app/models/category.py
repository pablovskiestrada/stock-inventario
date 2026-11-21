from sqlalchemy import CheckConstraint, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin


class Category(TimestampMixin, Base):
    __tablename__ = "categories"
    __table_args__ = (CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)


# RN11: unicidad sin distinguir mayúsculas/minúsculas (índice funcional).
Index("uq_categories_name_lower", func.lower(Category.name), unique=True)
