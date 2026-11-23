"""Tabla de rutas de la app (path, métodos), incluidas las que no salen en OpenAPI."""
from fastapi import FastAPI


def route_table(app: FastAPI) -> list[tuple[str, set[str]]]:
    table: list[tuple[str, set[str]]] = []
    for route in app.routes:
        if hasattr(route, "effective_route_contexts"):  # FastAPI agrupa los routers incluidos
            table.extend((ctx.path, set(ctx.methods or ())) for ctx in route.effective_route_contexts())
        elif hasattr(route, "path"):
            table.append((route.path, set(getattr(route, "methods", None) or ())))
    return table
