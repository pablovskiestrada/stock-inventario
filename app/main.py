from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers import categories, category_views, health
from app.routers.deps import domain_error_response
from app.services.errors import DomainError
from app.templating import BASE_DIR


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, debug=settings.debug)
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

    @app.exception_handler(DomainError)
    def handle_domain_error(_request: Request, exc: DomainError) -> JSONResponse:
        return domain_error_response(exc)

    app.include_router(health.router)
    app.include_router(categories.router)
    app.include_router(category_views.router)
    return app


app = create_app()
