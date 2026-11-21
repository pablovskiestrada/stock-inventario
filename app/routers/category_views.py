from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from app.models.category import Category
from app.routers.deps import CategoryServiceDep, http_status_for
from app.schemas.category import CategoryCreate
from app.services.errors import DomainError
from app.templating import templates

router = APIRouter(prefix="/categories", tags=["categories-ui"], include_in_schema=False)

NameForm = Annotated[str, Form()]


def _error(request: Request, message: str, status: int, target: str) -> HTMLResponse:
    """Fragmento de error: HTMX lo coloca en `target` en lugar del swap original."""
    response = templates.TemplateResponse(
        request, "categories/_error.html", {"message": message}, status_code=status
    )
    response.headers["HX-Retarget"] = target
    response.headers["HX-Reswap"] = "innerHTML"
    return response


def _list_response(request: Request, service: CategoryServiceDep) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "categories/_list_oob.html", {"categories": service.list()}
    )


def _clean_name(name: str) -> str:
    """Validación de entrada con el schema; el servicio vuelve a validar por su cuenta."""
    try:
        return CategoryCreate(name=name).name
    except ValidationError:
        return name


def _row(request: Request, category: Category, template: str = "categories/_row.html") -> HTMLResponse:
    return templates.TemplateResponse(request, template, {"category": category})


@router.get("", response_class=HTMLResponse)
def index(request: Request, service: CategoryServiceDep) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "categories/index.html", {"categories": service.list()}
    )


@router.post("", response_class=HTMLResponse)
def create(request: Request, name: NameForm, service: CategoryServiceDep) -> HTMLResponse:
    try:
        service.create(_clean_name(name))
    except DomainError as exc:
        return _error(request, str(exc), http_status_for(exc), "#form-error")
    return _list_response(request, service)


@router.get("/{category_id}", response_class=HTMLResponse)
def show(request: Request, category_id: int, service: CategoryServiceDep) -> HTMLResponse:
    try:
        return _row(request, service.get(category_id))
    except DomainError as exc:
        return _error(request, str(exc), http_status_for(exc), "#list-error")


@router.get("/{category_id}/edit", response_class=HTMLResponse)
def edit(request: Request, category_id: int, service: CategoryServiceDep) -> HTMLResponse:
    try:
        return _row(request, service.get(category_id), "categories/_row_edit.html")
    except DomainError as exc:
        return _error(request, str(exc), http_status_for(exc), "#list-error")


@router.put("/{category_id}", response_class=HTMLResponse)
def rename(
    request: Request, category_id: int, name: NameForm, service: CategoryServiceDep
) -> HTMLResponse:
    try:
        return _row(request, service.rename(category_id, _clean_name(name)))
    except DomainError as exc:
        return _error(request, str(exc), http_status_for(exc), f"#row-error-{category_id}")


@router.delete("/{category_id}", response_class=HTMLResponse)
def delete(request: Request, category_id: int, service: CategoryServiceDep) -> HTMLResponse:
    try:
        service.delete(category_id)
    except DomainError as exc:
        return _error(request, str(exc), http_status_for(exc), "#list-error")
    return HTMLResponse("")
