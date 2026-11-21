"""Modelos SQLAlchemy. Importar acá cada modelo para que Alembic los detecte."""
from app.models.category import Category
from app.models.product import Product

__all__ = ["Category", "Product"]
