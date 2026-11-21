from fastapi import APIRouter, Response

from app.routers.deps import CategoryServiceDep
from app.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("", response_model=list[CategoryRead])
def list_categories(service: CategoryServiceDep) -> list[CategoryRead]:
    return [CategoryRead.model_validate(c) for c in service.list()]


@router.post("", response_model=CategoryRead, status_code=201)
def create_category(payload: CategoryCreate, service: CategoryServiceDep) -> CategoryRead:
    return CategoryRead.model_validate(service.create(payload.name))


@router.get("/{category_id}", response_model=CategoryRead)
def get_category(category_id: int, service: CategoryServiceDep) -> CategoryRead:
    return CategoryRead.model_validate(service.get(category_id))


@router.put("/{category_id}", response_model=CategoryRead)
def rename_category(
    category_id: int, payload: CategoryUpdate, service: CategoryServiceDep
) -> CategoryRead:
    return CategoryRead.model_validate(service.rename(category_id, payload.name))


@router.delete("/{category_id}", status_code=204)
def delete_category(category_id: int, service: CategoryServiceDep) -> Response:
    service.delete(category_id)
    return Response(status_code=204)
