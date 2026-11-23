from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.main import app
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


def _post(client: TestClient, product_id: int, **body: Any) -> Any:
    return client.post(f"/api/products/{product_id}/movements", json=body)


def _entrada(client: TestClient, product_id: int, quantity: str, price: str = "10.00") -> Any:
    return _post(client, product_id, type="IN", quantity=quantity, unit_price=price)


def _stock(engine: Engine, product_id: int) -> int:
    """Stock en milésimas, calculado en crudo."""
    with engine.connect() as connection:
        return connection.execute(
            text(
                "SELECT COALESCE(SUM(CASE type WHEN 'OUT' THEN -quantity ELSE quantity END), 0) "
                "FROM stock_movements WHERE product_id = :p"
            ),
            {"p": product_id},
        ).scalar_one()


# --- 201 por tipo ---


def test_register_an_in_returns_201_with_the_stored_movement(client: TestClient) -> None:
    product = _product(client)
    response = _post(
        client,
        product["id"],
        type="IN",
        quantity="1.5",
        unit_price="19.9",
        note="  lote 7 ",
        reference="R-0001-123",
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["product_id"] == product["id"]
    assert (body["type"], body["quantity"], body["unit_price"]) == ("IN", "1.500", "19.90")
    assert (body["reason"], body["note"], body["reference"]) == (None, "lote 7", "R-0001-123")
    assert body["id"] and body["created_at"]
    assert "updated_at" not in body


def test_register_an_out_returns_201(client: TestClient) -> None:
    product = _product(client)
    _entrada(client, product["id"], "5")
    response = _post(client, product["id"], type="OUT", quantity="2", unit_price="25.00")
    assert response.status_code == 201
    assert (response.json()["type"], response.json()["unit_price"]) == ("OUT", "25.00")


def test_register_adjustments_with_both_signs_returns_201(client: TestClient) -> None:
    product = _product(client)
    up = _post(client, product["id"], type="ADJUSTMENT", quantity="3", reason="CONTEO")
    down = _post(client, product["id"], type="ADJUSTMENT", quantity="-1.25", reason="ROTURA")
    assert (up.status_code, down.status_code) == (201, 201)
    assert down.json()["quantity"] == "-1.250"
    assert (down.json()["reason"], down.json()["unit_price"]) == ("ROTURA", None)


def test_in_and_out_do_not_change_the_product_prices(client: TestClient) -> None:
    product = _product(client)
    _entrada(client, product["id"], "5", price="99.00")
    _post(client, product["id"], type="OUT", quantity="1", unit_price="1.00")
    stored = client.get(f"/api/products/{product['id']}").json()
    assert (stored["cost_price"], stored["sale_price"]) == ("10.00", "20.00")


def test_one_point_three_plus_zero_point_two_minus_one_point_five_is_exactly_zero(
    client: TestClient, engine: Engine
) -> None:
    product = _product(client)
    assert _entrada(client, product["id"], "1.3").status_code == 201
    assert _entrada(client, product["id"], "0.2").status_code == 201
    assert _post(client, product["id"], type="OUT", quantity="1.5", unit_price="1").status_code == 201
    assert _stock(engine, product["id"]) == 0


# --- 404 y 409 ---


def test_unknown_product_returns_404(client: TestClient) -> None:
    response = _entrada(client, 999, "1")
    assert response.status_code == 404
    assert "no existe" in response.json()["detail"]


def test_an_out_of_exactly_the_available_stock_is_201_and_one_thousandth_more_is_409(
    client: TestClient, engine: Engine
) -> None:
    product = _product(client)
    _entrada(client, product["id"], "5")
    over = _post(client, product["id"], type="OUT", quantity="5.001", unit_price="1")
    assert over.status_code == 409
    assert "Stock insuficiente" in over.json()["detail"]
    assert _stock(engine, product["id"]) == 5000  # el rechazo no dejó nada

    exact = _post(client, product["id"], type="OUT", quantity="5", unit_price="1")
    assert exact.status_code == 201
    assert _stock(engine, product["id"]) == 0


def test_a_negative_adjustment_below_zero_is_409(client: TestClient) -> None:
    product = _product(client)
    _entrada(client, product["id"], "1")
    response = _post(client, product["id"], type="ADJUSTMENT", quantity="-1.001", reason="MERMA")
    assert response.status_code == 409


def test_an_inactive_product_returns_409(client: TestClient, engine: Engine) -> None:
    product = _product(client)
    _entrada(client, product["id"], "5")
    client.post(f"/api/products/{product['id']}/deactivate")

    for body in (
        {"type": "IN", "quantity": "1", "unit_price": "1"},
        {"type": "OUT", "quantity": "1", "unit_price": "1"},
        {"type": "ADJUSTMENT", "quantity": "1", "reason": "CONTEO"},
    ):
        response = _post(client, product["id"], **body)
        assert response.status_code == 409, body
        assert "inactivo" in response.json()["detail"]
    assert _stock(engine, product["id"]) == 5000


# --- 422 ---


@pytest.mark.parametrize(
    "body,message",
    [
        ({"type": "IN", "quantity": "1"}, "Falta el costo unitario"),
        ({"type": "OUT", "quantity": "1"}, "Falta el precio unitario de venta"),
        (
            {"type": "ADJUSTMENT", "quantity": "1", "reason": "CONTEO", "unit_price": "5"},
            "no lleva precio unitario",
        ),
        (
            {"type": "ADJUSTMENT", "quantity": "1", "reason": "CONTEO", "unit_price": "0"},
            "no lleva precio unitario",
        ),
        ({"type": "ADJUSTMENT", "quantity": "1"}, "necesita un motivo"),
        (
            {"type": "IN", "quantity": "1", "unit_price": "1", "reason": "ROTURA"},
            "Solo los ajustes llevan motivo",
        ),
        (
            {"type": "OUT", "quantity": "1", "unit_price": "1", "reason": "MERMA"},
            "Solo los ajustes llevan motivo",
        ),
        ({"type": "ADJUSTMENT", "quantity": "1", "reason": "OTRO"}, "la nota es obligatoria"),
        (
            {"type": "ADJUSTMENT", "quantity": "1", "reason": "OTRO", "note": "   "},
            "la nota es obligatoria",
        ),
        ({"type": "IN", "quantity": "0", "unit_price": "1"}, "mayor a 0"),
        ({"type": "OUT", "quantity": "-1", "unit_price": "1"}, "mayor a 0"),
        ({"type": "ADJUSTMENT", "quantity": "0", "reason": "CONTEO"}, "cantidad 0"),
        (
            {"type": "IN", "quantity": "1", "unit_price": "1", "note": "n" * 501},
            "La nota no puede superar",
        ),
        (
            {"type": "IN", "quantity": "1", "unit_price": "1", "reference": "r" * 101},
            "La referencia no puede superar",
        ),
    ],
)
def test_invalid_combinations_return_422_with_a_spanish_message(
    client: TestClient, engine: Engine, body: dict[str, Any], message: str
) -> None:
    product = _product(client)
    _entrada(client, product["id"], "5")

    response = _post(client, product["id"], **body)

    assert response.status_code == 422, response.text
    assert message in response.json()["detail"]
    assert _stock(engine, product["id"]) == 5000


def test_a_decimal_quantity_for_a_un_product_returns_422(client: TestClient) -> None:
    product = _product(client, sku="U-1", unit="UN")
    for body in (
        {"type": "IN", "quantity": "1.5", "unit_price": "1"},
        {"type": "ADJUSTMENT", "quantity": "-1.5", "reason": "CONTEO"},
    ):
        response = _post(client, product["id"], **body)
        assert response.status_code == 422
        assert "UN solo admite cantidades enteras" in response.json()["detail"]


@pytest.mark.parametrize(
    "body",
    [
        {"type": "XX", "quantity": "1", "unit_price": "1"},
        {"type": "ADJUSTMENT", "quantity": "1", "reason": "XX"},
        {"type": "IN", "quantity": "1.0001", "unit_price": "1"},  # 4 decimales
        {"type": "IN", "quantity": "abc", "unit_price": "1"},
        {"type": "IN", "quantity": "1", "unit_price": "-1"},
        {"type": "IN", "quantity": "1", "unit_price": "1.005"},
        {"type": "IN", "unit_price": "1"},  # sin cantidad
        {"quantity": "1", "unit_price": "1"},  # sin tipo
    ],
)
def test_malformed_payloads_return_422(client: TestClient, body: dict[str, Any]) -> None:
    product = _product(client)
    assert _post(client, product["id"], **body).status_code == 422


# --- RN5: inmutabilidad ---


def test_movements_expose_no_way_to_edit_or_delete(client: TestClient) -> None:
    product = _product(client)
    movement = _entrada(client, product["id"], "1").json()
    base = f"/api/products/{product['id']}/movements"

    for path in (base, f"{base}/{movement['id']}"):
        for method in ("put", "patch", "delete"):
            response = client.request(method.upper(), path, json={})
            assert response.status_code in (404, 405), (method, path)
    assert client.get(f"{base}/{movement['id']}").status_code == 404  # tampoco hay detalle


def test_no_route_of_the_app_can_edit_or_delete_a_movement() -> None:
    movement_routes = [
        (path, methods) for path, methods in route_table(app) if "movements" in path
    ]
    assert movement_routes, "no se encontró ninguna ruta de movimientos"
    for path, methods in movement_routes:
        assert not methods & {"PUT", "PATCH", "DELETE"}, (path, methods)
    assert any("POST" in methods for _, methods in movement_routes)
