"""Filas crudas de `stock_movements` para probar los CHECK por INSERT directo (RN3, RN21-RN23).

Se usan contra el esquema de `create_all` y contra el de la migración: tienen que dar igual.
`quantity` va en milésimas (como se guarda en la base).
"""
from typing import Any

SQL_INSERT = (
    "INSERT INTO stock_movements (product_id, type, quantity, unit_price, reason, note) "
    "VALUES (:product_id, :type, :quantity, :unit_price, :reason, :note)"
)

_BASE: dict[str, Any] = {
    "type": "IN",
    "quantity": 1000,
    "unit_price": 10,
    "reason": None,
    "note": None,
}


def row(**overrides: Any) -> dict[str, Any]:
    return {**_BASE, **overrides}


VALID_ROWS: dict[str, dict[str, Any]] = {
    "entrada": row(),
    "entrada con precio 0": row(unit_price=0),
    "salida de una milésima": row(type="OUT", quantity=1),
    "ajuste positivo": row(type="ADJUSTMENT", quantity=500, unit_price=None, reason="CONTEO"),
    "ajuste negativo": row(type="ADJUSTMENT", quantity=-500, unit_price=None, reason="ROTURA"),
    "ajuste OTRO con nota": row(
        type="ADJUSTMENT", quantity=1, unit_price=None, reason="OTRO", note="se cayó del estante"
    ),
    "entrada con nota": row(note="remito 123"),
}

INVALID_ROWS: dict[str, dict[str, Any]] = {
    "tipo desconocido": row(type="XX"),
    "tipo en minúsculas": row(type="in"),
    "entrada con cantidad 0": row(quantity=0),
    "entrada negativa": row(quantity=-1),
    "salida con cantidad 0": row(type="OUT", quantity=0),
    "salida negativa": row(type="OUT", quantity=-1000),
    "ajuste con cantidad 0": row(type="ADJUSTMENT", quantity=0, unit_price=None, reason="CONTEO"),
    "entrada sin precio": row(unit_price=None),
    "salida sin precio": row(type="OUT", unit_price=None),
    "precio negativo": row(unit_price=-0.01),
    "ajuste con precio": row(type="ADJUSTMENT", unit_price=1, reason="CONTEO"),
    "ajuste con precio 0": row(type="ADJUSTMENT", unit_price=0, reason="CONTEO"),
    "ajuste sin motivo": row(type="ADJUSTMENT", unit_price=None, reason=None),
    "ajuste con motivo fuera de la lista": row(type="ADJUSTMENT", unit_price=None, reason="XX"),
    "motivo en minúsculas": row(type="ADJUSTMENT", unit_price=None, reason="rotura"),
    "entrada con motivo": row(reason="ROTURA"),
    "salida con motivo": row(type="OUT", reason="MERMA"),
    "OTRO sin nota": row(type="ADJUSTMENT", unit_price=None, reason="OTRO", note=None),
    "OTRO con nota en blanco": row(type="ADJUSTMENT", unit_price=None, reason="OTRO", note="   "),
}
