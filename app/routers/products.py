from fastapi import APIRouter

from app.routers.deps import ProductServiceDep
from app.schemas.product import ProductCreate, ProductRead, ProductUpdate

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("", response_model=list[ProductRead])
def list_products(
    service: ProductServiceDep, category_id: int | None = None, is_active: bool | None = None
) -> list[ProductRead]:
    products = service.list(category_id=category_id, is_active=is_active)
    return [ProductRead.model_validate(p) for p in products]


@router.post("", response_model=ProductRead, status_code=201)
def create_product(payload: ProductCreate, service: ProductServiceDep) -> ProductRead:
    return ProductRead.model_validate(service.create(**payload.model_dump()))


@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: int, service: ProductServiceDep) -> ProductRead:
    return ProductRead.model_validate(service.get(product_id))


@router.put("/{product_id}", response_model=ProductRead)
def update_product(
    product_id: int, payload: ProductUpdate, service: ProductServiceDep
) -> ProductRead:
    return ProductRead.model_validate(service.update(product_id, **payload.model_dump()))


@router.post("/{product_id}/deactivate", response_model=ProductRead)
def deactivate_product(product_id: int, service: ProductServiceDep) -> ProductRead:
    return ProductRead.model_validate(service.deactivate(product_id))


@router.post("/{product_id}/activate", response_model=ProductRead)
def activate_product(product_id: int, service: ProductServiceDep) -> ProductRead:
    return ProductRead.model_validate(service.activate(product_id))
