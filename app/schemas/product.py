from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _strip(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


Sku = Annotated[str, BeforeValidator(_strip), Field(min_length=1, max_length=50)]
ProductName = Annotated[str, BeforeValidator(_strip), Field(min_length=1, max_length=150)]
Price = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
MinStock = Annotated[int, Field(ge=0)]


class ProductBase(BaseModel):
    sku: Sku
    name: ProductName
    category_id: int
    cost_price: Price
    sale_price: Price
    min_stock: MinStock = 0


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
    min_stock: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
