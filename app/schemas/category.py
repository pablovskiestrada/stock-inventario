from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _strip(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


CategoryName = Annotated[str, BeforeValidator(_strip), Field(min_length=1, max_length=100)]


class CategoryCreate(BaseModel):
    name: CategoryName


class CategoryUpdate(BaseModel):
    name: CategoryName


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    updated_at: datetime
