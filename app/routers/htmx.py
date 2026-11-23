"""Helpers compartidos por las vistas HTMX."""
from fastapi import Request
from fastapi.responses import HTMLResponse

from app.templating import templates


def error_fragment(request: Request, message: str, status: int, target: str) -> HTMLResponse:
    """Fragmento de error: HTMX lo coloca en `target` en lugar del swap original."""
    response = templates.TemplateResponse(
        request, "_error.html", {"message": message}, status_code=status
    )
    response.headers["HX-Retarget"] = target
    response.headers["HX-Reswap"] = "innerHTML"
    return response
