"""RN31: GET /api/products/{id}/movements, el historial con saldo (solo lectura)."""
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, text
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.models.stock_movement import StockMovement
from tests.api.route_table import route_table


def _product(client: TestClient, **overrides: Any) -> dict[str, Any]:
    category = client.post("/api/categories", json={"name": "Ferretería"})
    category_id = category.json()["id"] if category.status_code == 201 else 1
    payload = {
        "sku": "H-1",
        "name": "Harina",
        "category_id": category_id,
        "cost_price": "10.00",
        "sale_price": "20.00",
        "unit": "KG",
    }
    payload.update(overrides)
    response = client.post("/api/products", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _register(client: TestClient, product_id: int, kind: str, quantity: str, **extra: Any) -> Any:
    body: dict[str, Any] = {"type": kind, "quantity": quantity, **extra}
    if kind in ("IN", "OUT"):
        body.setdefault("unit_price", "10.00")
    else:
        body.setdefault("reason", "CONTEO")
    response = client.post(f"/api/products/{product_id}/movements", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _history(client: TestClient, product_id: int) -> dict[str, Any]:
    response = client.get(f"/api/products/{product_id}/movements")
    assert response.status_code == 200, response.text
    return response.json()


def _bulk_ins(engine: Engine, product_id: int, count: int) -> None:
    """`count` entradas de 1 insertadas directo (sin pasar por la API) para armar historiales largos."""
    with sessionmaker(bind=engine, expire_on_commit=False)() as db_session:
        db_session.add_all(
            StockMovement(product_id=product_id, type="IN", quantity=Decimal("1"), unit_price=Decimal("1.00"))
            for _ in range(count)
        )
        db_session.commit()


def _count(engine: Engine) -> int:
    with engine.connect() as connection:
        return connection.execute(text("SELECT COUNT(*) FROM stock_movements")).scalar_one()


# --- contenido, orden y saldo ---


def test_history_lists_the_most_recent_first_with_sign_and_balance(client: TestClient) -> None:
    product = _product(client)
    _register(client, product["id"], "IN", "10", reference="R-1", note="lote 7")
    _register(client, product["id"], "OUT", "3", unit_price="25.00")
    _register(client, product["id"], "ADJUSTMENT", "-2", reason="ROTURA")

    body = _history(client, product["id"])

    assert (body["product_id"], body["unit"], body["limit"], body["total"]) == (product["id"], "KG", 200, 3)
    items = body["items"]
    assert [item["type"] for item in items] == ["ADJUSTMENT", "OUT", "IN"]
    assert [item["signed_quantity"] for item in items] == ["-2.000", "-3.000", "10.000"]
    assert [item["balance"] for item in items] == ["5.000", "7.000", "10.000"]
    ids = [item["id"] for item in items]
    assert ids == sorted(ids, reverse=True)


def test_each_item_carries_the_movement_fields_and_no_updated_at(client: TestClient) -> None:
    product = _product(client)
    _register(client, product["id"], "IN", "10", reference="R-1", note="lote 7", unit_price="19.90")
    _register(client, product["id"], "ADJUSTMENT", "-1.5", reason="MERMA")

    adjustment, entry = _history(client, product["id"])["items"]

    assert entry["product_id"] == product["id"]
    assert (entry["quantity"], entry["unit_price"]) == ("10.000", "19.90")
    assert (entry["reason"], entry["note"], entry["reference"]) == (None, "lote 7", "R-1")
    assert (adjustment["quantity"], adjustment["unit_price"], adjustment["reason"]) == ("-1.500", None, "MERMA")
    for item in (entry, adjustment):
        assert item["created_at"]
        assert "updated_at" not in item


def test_balances_are_exact_decimals_with_three_decimals(client: TestClient) -> None:
    """1,3 + 0,2 - 1,5: 1.300, 1.500 y 0.000, como texto exacto."""
    product = _product(client)
    _register(client, product["id"], "IN", "1.3")
    _register(client, product["id"], "IN", "0.2")
    _register(client, product["id"], "OUT", "1.5")

    items = _history(client, product["id"])["items"]

    assert [item["balance"] for item in reversed(items)] == ["1.300", "1.500", "0.000"]
    assert [item["signed_quantity"] for item in reversed(items)] == ["1.300", "0.200", "-1.500"]


def test_an_empty_history_is_200_with_no_items(client: TestClient) -> None:
    product = _product(client)

    body = _history(client, product["id"])

    assert (body["items"], body["total"], body["limit"]) == ([], 0, 200)


def test_an_inactive_product_still_has_a_readable_history(client: TestClient) -> None:
    product = _product(client)
    _register(client, product["id"], "IN", "4")
    client.post(f"/api/products/{product['id']}/deactivate")

    body = _history(client, product["id"])

    assert [item["balance"] for item in body["items"]] == ["4.000"]
    # Leer no reactiva ni habilita nada: seguir registrando es 409 (RN7).
    refused = client.post(
        f"/api/products/{product['id']}/movements",
        json={"type": "IN", "quantity": "1", "unit_price": "1"},
    )
    assert refused.status_code == 409


def test_unknown_product_returns_404(client: TestClient) -> None:
    response = client.get("/api/products/999/movements")

    assert response.status_code == 404
    assert "no existe" in response.json()["detail"]


def test_another_product_does_not_leak_into_the_history(client: TestClient) -> None:
    a = _product(client, sku="A-1")
    b = _product(client, sku="B-1")
    _register(client, a["id"], "IN", "5")
    _register(client, b["id"], "IN", "100")
    _register(client, a["id"], "OUT", "2")

    body = _history(client, a["id"])

    assert [item["balance"] for item in body["items"]] == ["3.000", "5.000"]
    assert {item["product_id"] for item in body["items"]} == {a["id"]}
    assert body["total"] == 2


# --- límite de 200 ---


def test_only_the_last_200_are_listed_and_the_balance_covers_the_whole_history(
    client: TestClient, engine: Engine
) -> None:
    product = _product(client)
    _bulk_ins(engine, product["id"], 205)

    body = _history(client, product["id"])

    assert (len(body["items"]), body["total"], body["limit"]) == (200, 205, 200)
    assert body["items"][0]["balance"] == "205.000"  # = stock actual
    assert body["items"][-1]["balance"] == "6.000"  # la 6ª entrada: arrastra las 5 anteriores


def test_exactly_200_movements_are_all_listed(client: TestClient, engine: Engine) -> None:
    product = _product(client)
    _bulk_ins(engine, product["id"], 200)

    body = _history(client, product["id"])

    assert (len(body["items"]), body["total"]) == (200, 200)
    assert body["items"][-1]["balance"] == "1.000"


def test_the_endpoint_runs_the_same_number_of_statements_whatever_the_history_size(
    client: TestClient, engine: Engine
) -> None:
    def statements_for(product_id: int) -> int:
        seen: list[str] = []
        listener = lambda _c, _cur, stmt, *_a: seen.append(stmt)  # noqa: E731
        event.listen(engine, "before_cursor_execute", listener)
        try:
            assert client.get(f"/api/products/{product_id}/movements").status_code == 200
        finally:
            event.remove(engine, "before_cursor_execute", listener)
        return len(seen)

    few = _product(client, sku="F-1")
    many = _product(client, sku="M-1")
    _bulk_ins(engine, few["id"], 3)
    _bulk_ins(engine, many["id"], 150)

    assert statements_for(few["id"]) == statements_for(many["id"])


# --- solo lectura (RN5) ---


def test_reading_the_history_does_not_change_the_ledger(client: TestClient, engine: Engine) -> None:
    product = _product(client)
    _register(client, product["id"], "IN", "2")
    before = _count(engine)

    first = _history(client, product["id"])
    second = _history(client, product["id"])

    assert first == second
    assert _count(engine) == before


def test_the_history_route_is_read_only(client: TestClient) -> None:
    product = _product(client)
    path = f"/api/products/{product['id']}/movements"

    for method in ("PUT", "PATCH", "DELETE"):
        assert client.request(method, path, json={}).status_code == 405, method

    api_routes: dict[str, set[str]] = {}
    for template, methods in route_table(app):
        if template.startswith("/api/") and "movements" in template:
            api_routes.setdefault(template, set()).update(methods)
    assert api_routes == {"/api/products/{product_id}/movements": {"GET", "POST"}}
