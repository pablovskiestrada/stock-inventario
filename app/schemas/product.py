from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from app.models.unit import Unit


def _strip(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


Sku = Annotated[str, BeforeValidator(_strip), Field(min_length=1, max_length=50)]
ProductName = Annotated[str, BeforeValidator(_strip), Field(min_length=1, max_length=150)]
Price = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
MinStock = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=3)]


class ProductBase(BaseModel):
    sku: Sku
    name: ProductName
    category_id: int
    cost_price: Price
    sale_price: Price
    unit: Unit = Unit.UN
    min_stock: MinStock = Decimal(0)


class ProductCreate(ProductBase):
    pass


class ProductUpdate(ProductBase):
    pass


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    name: str
    category_id: int
    cost_price: Decimal
    sale_price: Decimal
    unit: Unit
    min_stock: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime
