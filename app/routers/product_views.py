from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from app.models.product import Product
from app.routers.deps import CategoryServiceDep, ProductServiceDep, http_status_for
from app.routers.htmx import error_fragment
from app.schemas.product import ProductCreate
from app.services.category_service import CategoryService
from app.services.errors import DomainError
from app.services.product_service import ProductService
from app.services.quantity import parse_quantity_input
from app.templating import templates

router = APIRouter(prefix="/products", tags=["products-ui"], include_in_schema=False)

# Estado del filtro de la pantalla -> valor para el servicio (RN15).
STATES: dict[str, bool | None] = {"active": True, "inactive": False, "all": None}
DEFAULT_STATE = "active"

FIELD_ERRORS = {
    "sku": "El SKU es obligatorio y admite hasta 50 caracteres.",
    "name": "El nombre es obligatorio y admite hasta 150 caracteres.",
    "category_id": "Elegí una categoría.",
    "cost_price": "El precio de costo debe ser un importe mayor o igual a 0, con hasta 2 decimales.",
    "sale_price": "El precio de venta debe ser un importe mayor o igual a 0, con hasta 2 decimales.",
    "unit": "Elegí una unidad: UN, KG, M o L.",
    "min_stock": (
        "El stock mínimo debe ser un número mayor o igual a 0, con hasta 3 decimales "
        "(solo enteros si la unidad es UN)."
    ),
}


class ProductForm:
    """Campos del formulario como texto; el schema Pydantic los valida y convierte."""

    def __init__(
        self,
        sku: Annotated[str, Form()] = "",
        name: Annotated[str, Form()] = "",
        category_id: Annotated[str, Form()] = "",
        cost_price: Annotated[str, Form()] = "",
        sale_price: Annotated[str, Form()] = "",
        unit: Annotated[str, Form()] = "UN",
        min_stock: Annotated[str, Form()] = "",
    ) -> None:
        self.raw = {
            "sku": sku,
            "name": name,
            "category_id": category_id.strip(),
            # Se acepta la coma decimal ("19,99") habitual en español.
            "cost_price": cost_price.strip().replace(",", "."),
            "sale_price": sale_price.strip().replace(",", "."),
            "unit": unit.strip(),
        }
        self._min_stock = min_stock

    def parse(self) -> ProductCreate:
        # RN20: la coma o el punto (uno solo) es el decimal; los separadores de miles se rechazan.
        return ProductCreate(**self.raw, min_stock=parse_quantity_input(self._min_stock))


FormDep = Annotated[ProductForm, Depends()]


def _validation_message(exc: ValidationError) -> str:
    field = str(exc.errors()[0]["loc"][0])
    return FIELD_ERRORS.get(field, "Revisá los datos del formulario.")


def _parse_filters(category: str, state: str) -> tuple[int | None, str]:
    category_id = int(category) if category.strip().isdigit() else None
    return category_id, state if state in STATES else DEFAULT_STATE


def _list_context(
    products: ProductService, categories: CategoryService, category: str, state: str
) -> dict[str, Any]:
    category_id, state = _parse_filters(category, state)
    all_categories = categories.list()
    found = products.list(category_id=category_id, is_active=STATES[state])
    return {
        "products": found,
        "has_any_product": bool(found) or bool(products.list()),
        "categories": all_categories,
        "category_names": {c.id: c.name for c in all_categories},
        "filter_category": category_id,
        "filter_state": state,
    }


def _row_response(
    request: Request,
    categories: CategoryService,
    product: Product,
    template: str = "products/_row.html",
    warning: bool = False,
    saved_notice: bool = False,
) -> HTMLResponse:
    all_categories = categories.list()
    context = {
        "product": product,
        "categories": all_categories,
        "category_names": {c.id: c.name for c in all_categories},
        "warning": warning,
        "saved_notice": saved_notice,
    }
    return templates.TemplateResponse(request, template, context)


@router.get("", response_class=HTMLResponse)
def index(
    request: Request,
    products: ProductServiceDep,
    categories: CategoryServiceDep,
    category: str = "",
    state: str = DEFAULT_STATE,
) -> HTMLResponse:
    context = _list_context(products, categories, category, state)
    is_fragment = (
        "HX-Request" in request.headers and "HX-History-Restore-Request" not in request.headers
    )
    template = "products/_list.html" if is_fragment else "products/index.html"
    return templates.TemplateResponse(request, template, context)


@router.post("", response_class=HTMLResponse)
def create(
    request: Request,
    form: FormDep,
    products: ProductServiceDep,
    categories: CategoryServiceDep,
    category: Annotated[str, Form()] = "",
    state: Annotated[str, Form()] = DEFAULT_STATE,
) -> HTMLResponse:
    try:
        product = products.create(**form.parse().model_dump())
    except ValidationError as exc:
        return error_fragment(request, _validation_message(exc), 422, "#form-error")
    except DomainError as exc:
        return error_fragment(request, str(exc), http_status_for(exc), "#form-error")
    context = _list_context(products, categories, category, state)
    context.update(saved=product, warning=products.has_price_warning(product))
    return templates.TemplateResponse(request, "products/_list_oob.html", context)


@router.get("/{product_id}", response_class=HTMLResponse)
def show(
    request: Request, product_id: int, products: ProductServiceDep, categories: CategoryServiceDep
) -> HTMLResponse:
    try:
        return _row_response(request, categories, products.get(product_id))
    except DomainError as exc:
        return error_fragment(request, str(exc), http_status_for(exc), "#list-error")


@router.get("/{product_id}/edit", response_class=HTMLResponse)
def edit(
    request: Request, product_id: int, products: ProductServiceDep, categories: CategoryServiceDep
) -> HTMLResponse:
    try:
        product = products.get(product_id)
    except DomainError as exc:
        return error_fragment(request, str(exc), http_status_for(exc), "#list-error")
    return _row_response(request, categories, product, "products/_row_edit.html")


@router.put("/{product_id}", response_class=HTMLResponse)
def update(
    request: Request,
    product_id: int,
    form: FormDep,
    products: ProductServiceDep,
    categories: CategoryServiceDep,
) -> HTMLResponse:
    target = f"#row-error-{product_id}"
    try:
        product = products.update(product_id, **form.parse().model_dump())
    except ValidationError as exc:
        return error_fragment(request, _validation_message(exc), 422, target)
    except DomainError as exc:
        return error_fragment(request, str(exc), http_status_for(exc), target)
    return _row_response(
        request,
        categories,
        product,
        warning=products.has_price_warning(product),
        saved_notice=True,
    )


def _toggle_response(
    request: Request,
    products: ProductService,
    categories: CategoryService,
    product_id: int,
    activate: bool,
    category: str,
    state: str,
) -> HTMLResponse:
    try:
        if activate:
            products.activate(product_id)
        else:
            products.deactivate(product_id)
    except DomainError as exc:
        return error_fragment(request, str(exc), http_status_for(exc), "#list-error")
    context = _list_context(products, categories, category, state)
    return templates.TemplateResponse(request, "products/_list_oob.html", context)


@router.post("/{product_id}/deactivate", response_class=HTMLResponse)
def deactivate(
    request: Request,
    product_id: int,
    products: ProductServiceDep,
    categories: CategoryServiceDep,
    category: Annotated[str, Form()] = "",
    state: Annotated[str, Form()] = DEFAULT_STATE,
) -> HTMLResponse:
    return _toggle_response(request, products, categories, product_id, False, category, state)


@router.post("/{product_id}/activate", response_class=HTMLResponse)
def activate(
    request: Request,
    product_id: int,
    products: ProductServiceDep,
    categories: CategoryServiceDep,
    category: Annotated[str, Form()] = "",
    state: Annotated[str, Form()] = DEFAULT_STATE,
) -> HTMLResponse:
    return _toggle_response(request, products, categories, product_id, True, category, state)
