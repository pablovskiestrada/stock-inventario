import re
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, text

from app.main import app
from tests.api.route_table import route_table

HX = {"HX-Request": "true"}


def _category(client: TestClient, name: str = "Ferretería") -> int:
    response = client.post("/api/categories", json={"name": name})
    assert response.status_code == 201
    return int(response.json()["id"])


def _product(client: TestClient, category_id: int, **overrides: Any) -> dict[str, Any]:
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


def _seed(client: TestClient, product_id: int, quantity: str = "5") -> None:
    response = client.post(
        f"/api/products/{product_id}/movements",
        json={"type": "IN", "quantity": quantity, "unit_price": "10.00"},
    )
    assert response.status_code == 201, response.text


def _form(movement_type: str, **overrides: str) -> dict[str, str]:
    data = {
        "type": movement_type,
        "quantity": "1",
        "unit_price": "10.00",
        "reason": "",
        "note": "",
        "reference": "",
    }
    data.update(overrides)
    return data


def _adjust(**overrides: str) -> dict[str, str]:
    return _form("ADJUSTMENT", unit_price="", reason="CONTEO", **overrides)


def _post(client: TestClient, product_id: int, data: dict[str, str]) -> Any:
    return client.post(f"/products/{product_id}/movements", data=data, headers=HX)


def _stock_cell(html: str, product_id: int) -> str:
    """Texto de la celda «Stock actual» de la fila del producto."""
    row = re.search(rf'<tr id="product-{product_id}".*?</tr>', html, re.S)
    assert row, "no se encontró la fila del producto"
    cell = re.search(r'<td class="stock">(.*?)</td>', row.group(0), re.S)
    assert cell, "la fila no tiene la celda de stock"
    return cell.group(1).strip()


@pytest.fixture
def cat(client: TestClient) -> int:
    return _category(client)


# --- listado: columna «Stock actual» ---


def test_listing_shows_the_stock_column_with_the_unit(client: TestClient, cat: int) -> None:
    kg = _product(client, cat, sku="K", name="Harina", unit="KG")
    un = _product(client, cat, sku="U", name="Tornillo", unit="UN")
    nothing = _product(client, cat, sku="N", name="Clavo", unit="UN")
    _seed(client, kg["id"], "2.5")
    _seed(client, un["id"], "40")

    html = client.get("/products").text

    assert "<th>Stock actual</th>" in html
    assert _stock_cell(html, kg["id"]) == "2.5 KG"
    assert _stock_cell(html, un["id"]) == "40 UN"
    assert _stock_cell(html, nothing["id"]) == "0 UN"


def test_listing_stock_is_signed_ins_minus_outs_plus_adjustments(
    client: TestClient, cat: int
) -> None:
    product = _product(client, cat)
    _seed(client, product["id"], "10")
    base = f"/api/products/{product['id']}/movements"
    client.post(base, json={"type": "OUT", "quantity": "3.25", "unit_price": "20"})
    client.post(base, json={"type": "ADJUSTMENT", "quantity": "-0.75", "reason": "MERMA"})

    assert _stock_cell(client.get("/products").text, product["id"]) == "6 KG"


def test_an_inactive_product_still_shows_its_stock(client: TestClient, cat: int) -> None:
    product = _product(client, cat)
    _seed(client, product["id"], "3")
    client.post(f"/api/products/{product['id']}/deactivate")

    html = client.get("/products?state=inactive", headers=HX).text

    assert _stock_cell(html, product["id"]) == "3 KG"


def test_listing_computes_stock_with_the_same_number_of_queries_whatever_its_size(
    client: TestClient, engine: Engine, cat: int
) -> None:
    def statements_for_listing() -> int:
        seen: list[str] = []
        listener = lambda _c, _cur, stmt, *_a: seen.append(stmt)  # noqa: E731
        event.listen(engine, "before_cursor_execute", listener)
        try:
            assert client.get("/products?state=all", headers=HX).status_code == 200
        finally:
            event.remove(engine, "before_cursor_execute", listener)
        return len(seen)

    first = _product(client, cat, sku="P-0", name="Producto 0")
    _seed(client, first["id"], "1")
    few = statements_for_listing()
    for n in range(1, 25):
        extra = _product(client, cat, sku=f"P-{n}", name=f"Producto {n}")
        _seed(client, extra["id"], "1")
    many = statements_for_listing()

    assert few == many  # sin N+1


# --- botones por fila ---


def test_active_rows_offer_entry_exit_and_adjustment_buttons(client: TestClient, cat: int) -> None:
    product = _product(client, cat)
    html = client.get("/products").text
    for kind, label in (("IN", "Entrada"), ("OUT", "Salida"), ("ADJUSTMENT", "Ajuste")):
        assert f'hx-get="/products/{product["id"]}/movements/new?type={kind}"' in html
        assert f">{label}</button>" in html


def test_inactive_rows_have_no_movement_buttons(client: TestClient, cat: int) -> None:
    product = _product(client, cat)
    client.post(f"/api/products/{product['id']}/deactivate")

    html = client.get("/products?state=inactive", headers=HX).text

    assert "Reactivar" in html
    assert "/movements/new" not in html


# --- formularios ---


def test_the_entry_form_preloads_the_cost_price_and_is_editable(
    client: TestClient, cat: int
) -> None:
    product = _product(client, cat, cost_price="12.50", sale_price="30.00")
    _seed(client, product["id"], "2")

    response = client.get(f"/products/{product['id']}/movements/new?type=IN", headers=HX)

    assert response.status_code == 200
    text_ = response.text
    assert 'name="type" value="IN"' in text_
    assert "Costo unitario" in text_
    assert 'name="unit_price"' in text_ and 'value="12.50"' in text_
    assert "readonly" not in text_ and "disabled" not in text_
    assert "Stock actual: 2 KG" in text_
    assert 'name="reference"' in text_ and 'name="note"' in text_
    assert 'name="reason"' not in text_
    assert "<html" not in text_
    assert f'hx-post="/products/{product["id"]}/movements"' in text_


def test_the_exit_form_is_the_entry_variant_with_the_sale_price_preloaded(
    client: TestClient, cat: int
) -> None:
    product = _product(client, cat, cost_price="12.50", sale_price="30.00")

    response = client.get(f"/products/{product['id']}/movements/new?type=OUT", headers=HX)

    assert response.status_code == 200
    assert 'name="type" value="OUT"' in response.text
    assert "Precio unitario de venta" in response.text
    assert 'value="30.00"' in response.text and 'value="12.50"' not in response.text
    assert 'name="reason"' not in response.text
    assert "<strong>Salida</strong>" in response.text


def test_the_adjustment_form_asks_for_a_signed_quantity_and_a_reason(
    client: TestClient, cat: int
) -> None:
    product = _product(client, cat)

    response = client.get(f"/products/{product['id']}/movements/new?type=ADJUSTMENT", headers=HX)

    assert response.status_code == 200
    html = response.text
    assert 'name="type" value="ADJUSTMENT"' in html
    assert "positiva suma, negativa resta" in html
    for code in ("ROTURA", "MERMA", "CONTEO", "ERROR_CARGA", "OTRO"):
        assert f'<option value="{code}">' in html
    assert 'name="unit_price"' not in html  # RN22: un ajuste no lleva precio
    quantity = re.search(r'<input[^>]*name="quantity"[^>]*>', html)
    assert quantity and "inputmode" not in quantity.group(0)  # el teclado necesita el signo «−»


def test_the_form_defaults_to_entry_and_rejects_unknown_types(client: TestClient, cat: int) -> None:
    product = _product(client, cat)

    default = client.get(f"/products/{product['id']}/movements/new", headers=HX)
    assert 'name="type" value="IN"' in default.text

    bad = client.get(f"/products/{product['id']}/movements/new?type=XX", headers=HX)
    assert bad.status_code == 422
    assert bad.headers["HX-Retarget"] == "#list-error"


def test_the_form_for_an_unknown_product_is_a_404_fragment(client: TestClient) -> None:
    response = client.get("/products/999/movements/new?type=IN", headers=HX)
    assert response.status_code == 404
    assert response.headers["HX-Retarget"] == "#list-error"


def test_cancel_goes_back_to_the_row(client: TestClient, cat: int) -> None:
    product = _product(client, cat)
    form = client.get(f"/products/{product['id']}/movements/new?type=IN", headers=HX).text
    assert f'hx-get="/products/{product["id"]}"' in form  # reutiliza GET /products/{id}
    assert "<td>H-1</td>" in client.get(f"/products/{product['id']}", headers=HX).text


# --- registrar desde la pantalla ---


def test_registering_an_entry_refreshes_the_row_with_the_new_stock(
    client: TestClient, cat: int
) -> None:
    product = _product(client, cat)

    response = _post(client, product["id"], _form("IN", quantity="1,5", unit_price="19,9"))

    assert response.status_code == 200
    assert "<html" not in response.text
    assert f'<tr id="product-{product["id"]}"' in response.text
    assert _stock_cell(response.text, product["id"]) == "1.5 KG"
    assert "Entrada registrada: 1.5 KG." in response.text


def test_registering_an_exit_uses_the_edited_price_and_subtracts(
    client: TestClient, engine: Engine, cat: int
) -> None:
    product = _product(client, cat)
    _seed(client, product["id"], "5")

    response = _post(client, product["id"], _form("OUT", quantity="2", unit_price="25"))

    assert response.status_code == 200
    assert _stock_cell(response.text, product["id"]) == "3 KG"
    assert "Salida registrada: 2 KG." in response.text
    with engine.connect() as connection:
        price = connection.execute(
            text("SELECT unit_price FROM stock_movements WHERE type='OUT'")
        ).scalar_one()
    assert float(price) == 25.0


def test_an_exit_of_exactly_the_stock_leaves_zero_and_one_thousandth_more_is_refused(
    client: TestClient, cat: int
) -> None:
    product = _product(client, cat)
    _seed(client, product["id"], "1.5")

    over = _post(client, product["id"], _form("OUT", quantity="1,501"))
    assert over.status_code == 409
    assert "Stock insuficiente" in over.text
    assert over.headers["HX-Retarget"] == f"#row-error-{product['id']}"

    exact = _post(client, product["id"], _form("OUT", quantity="1,5"))
    assert exact.status_code == 200
    assert _stock_cell(exact.text, product["id"]) == "0 KG"


def test_adjustments_take_the_sign_of_the_typed_quantity(client: TestClient, cat: int) -> None:
    product = _product(client, cat)
    _seed(client, product["id"], "5")

    down = _post(client, product["id"], _adjust(quantity="-1,5"))
    assert "Ajuste registrado: -1.5 KG." in down.text
    assert _stock_cell(down.text, product["id"]) == "3.5 KG"

    up = _post(client, product["id"], _adjust(quantity="+2"))
    assert "Ajuste registrado: +2 KG." in up.text
    assert _stock_cell(up.text, product["id"]) == "5.5 KG"


def test_a_negative_adjustment_below_zero_is_refused(client: TestClient, cat: int) -> None:
    product = _product(client, cat)
    _seed(client, product["id"], "1")

    response = _post(client, product["id"], _adjust(quantity="-1,001"))

    assert response.status_code == 409
    assert response.headers["HX-Retarget"] == f"#row-error-{product['id']}"


@pytest.mark.parametrize(
    "overrides,message",
    [
        ({"unit_price": ""}, "Falta el costo unitario"),
        ({"unit_price": "-1"}, "precio unitario"),
        ({"unit_price": "abc"}, "precio unitario"),
        ({"quantity": ""}, "mayor a 0"),
        ({"quantity": "0"}, "mayor a 0"),
        ({"quantity": "-1"}, "mayor a 0"),
        ({"quantity": "abc"}, "no es un número válido"),
        ({"reason": "ROTURA"}, "Solo los ajustes llevan motivo"),
        ({"type": "XX"}, "Elegí un tipo de movimiento"),
    ],
)
def test_invalid_entry_forms_show_the_message_in_the_row(
    client: TestClient, cat: int, overrides: dict[str, str], message: str
) -> None:
    product = _product(client, cat)

    response = _post(client, product["id"], _form("IN", **overrides))

    assert response.status_code == 422
    assert message in response.text
    assert response.headers["HX-Retarget"] == f"#row-error-{product['id']}"
    assert _stock_cell(client.get("/products").text, product["id"]) == "0 KG"


@pytest.mark.parametrize(
    "overrides,message",
    [
        ({"reason": ""}, "necesita un motivo"),
        ({"reason": "XX"}, "Elegí un motivo"),
        ({"reason": "OTRO"}, "la nota es obligatoria"),
        ({"reason": "OTRO", "note": "   "}, "la nota es obligatoria"),
        ({"quantity": "0"}, "cantidad 0"),
        ({"unit_price": "5"}, "no lleva precio unitario"),
    ],
)
def test_invalid_adjustment_forms_show_the_message_in_the_row(
    client: TestClient, cat: int, overrides: dict[str, str], message: str
) -> None:
    product = _product(client, cat)
    data = _adjust(**{"quantity": "1"})
    data.update(overrides)

    response = _post(client, product["id"], data)

    assert response.status_code == 422, response.text
    assert message in response.text
    assert response.headers["HX-Retarget"] == f"#row-error-{product['id']}"


def test_reason_otro_with_a_note_is_accepted(client: TestClient, cat: int) -> None:
    product = _product(client, cat)

    response = _post(
        client, product["id"], {**_adjust(quantity="2"), "reason": "OTRO", "note": "regalo"}
    )

    assert response.status_code == 200
    assert _stock_cell(response.text, product["id"]) == "2 KG"


@pytest.mark.parametrize("typed", ["1,5", "1.5", " 1,5 "])
def test_a_single_separator_is_the_decimal(client: TestClient, cat: int, typed: str) -> None:
    product = _product(client, cat)

    response = _post(client, product["id"], _form("IN", quantity=typed))

    assert response.status_code == 200
    assert _stock_cell(response.text, product["id"]) == "1.5 KG"


@pytest.mark.parametrize("typed", ["1.500,5", "1,500.5", "1.2.3"])
def test_thousands_separators_are_rejected_with_a_clear_message(
    client: TestClient, cat: int, typed: str
) -> None:
    product = _product(client, cat)

    response = _post(client, product["id"], _form("IN", quantity=typed))

    assert response.status_code == 422
    assert "sin separador de miles" in response.text
    assert response.headers["HX-Retarget"] == f"#row-error-{product['id']}"
    assert _stock_cell(client.get("/products").text, product["id"]) == "0 KG"


def test_decimals_are_refused_for_a_un_product(client: TestClient, cat: int) -> None:
    product = _product(client, cat, sku="U-1", unit="UN")

    entry = _post(client, product["id"], _form("IN", quantity="1,5"))
    assert entry.status_code == 422 and "solo admite cantidades enteras" in entry.text
    adjust = _post(client, product["id"], _adjust(quantity="-0,5"))
    assert adjust.status_code == 422 and "solo admite cantidades enteras" in adjust.text

    ok = _post(client, product["id"], _form("IN", quantity="3"))
    assert _stock_cell(ok.text, product["id"]) == "3 UN"


def test_an_inactive_product_refuses_movements_from_the_screen(
    client: TestClient, cat: int
) -> None:
    product = _product(client, cat)
    _seed(client, product["id"], "2")
    client.post(f"/api/products/{product['id']}/deactivate")

    for data in (_form("IN"), _form("OUT"), _adjust(quantity="1")):
        response = _post(client, product["id"], data)
        assert response.status_code == 409, data
        assert "inactivo" in response.text
        assert response.headers["HX-Retarget"] == f"#row-error-{product['id']}"
    assert _stock_cell(client.get("/products?state=inactive", headers=HX).text, product["id"]) == "2 KG"


def test_registering_for_an_unknown_product_is_a_404_fragment(client: TestClient) -> None:
    response = _post(client, 999, _form("IN"))
    assert response.status_code == 404
    assert response.headers["HX-Retarget"] == "#row-error-999"


def test_registering_from_the_screen_does_not_change_the_product_prices(
    client: TestClient, cat: int
) -> None:
    product = _product(client, cat)
    _post(client, product["id"], _form("IN", unit_price="99"))
    _seed(client, product["id"], "5")
    _post(client, product["id"], _form("OUT", unit_price="1"))

    stored = client.get(f"/api/products/{product['id']}").json()
    assert (stored["cost_price"], stored["sale_price"]) == ("10.00", "20.00")


def test_the_edit_form_row_spans_the_new_column(client: TestClient, cat: int) -> None:
    product = _product(client, cat)
    html = client.get(f"/products/{product['id']}/edit", headers=HX).text
    assert 'colspan="10"' in html


# --- inmutabilidad en la UI (RN5) ---


def test_the_screens_have_no_way_to_edit_or_delete_a_movement(client: TestClient, cat: int) -> None:
    product = _product(client, cat)
    _seed(client, product["id"])
    base = f"/products/{product['id']}/movements"

    for method in ("PUT", "PATCH", "DELETE"):
        assert client.request(method, base, headers=HX).status_code == 405
        assert client.request(method, f"{base}/1", headers=HX).status_code in (404, 405)

    ui_routes = [(p, m) for p, m in route_table(app) if p.startswith("/products") and "movements" in p]
    assert ui_routes
    for path, methods in ui_routes:
        assert not methods & {"PUT", "PATCH", "DELETE"}, (path, methods)
