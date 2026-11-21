from typing import Annotated

from fastapi import Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db import get_session
from app.repositories.category_repository import CategoryRepository
from app.services.category_service import CategoryService
from app.services.errors import (
    CategoryInUseError,
    CategoryNotFoundError,
    DomainError,
    DuplicateCategoryNameError,
)


def get_category_service(session: Annotated[Session, Depends(get_session)]) -> CategoryService:
    return CategoryService(CategoryRepository(session))


CategoryServiceDep = Annotated[CategoryService, Depends(get_category_service)]


def http_status_for(exc: DomainError) -> int:
    """Traduce excepciones de dominio a códigos HTTP."""
    if isinstance(exc, CategoryNotFoundError):
        return 404
    if isinstance(exc, DuplicateCategoryNameError | CategoryInUseError):
        return 409
    return 422


def domain_error_response(exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=http_status_for(exc), content={"detail": str(exc)})
