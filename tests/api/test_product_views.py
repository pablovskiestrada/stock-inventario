from typing import Any

from fastapi.testclient import TestClient

HX = {"HX-Request": "true"}
WARNING = "el precio de venta es menor al costo"


def _category(client: TestClient, name: str = "Ropa") -> int:
    response = client.post("/api/categories", json={"name": name})
    assert response.status_code == 201
    return int(response.json()["id"])


def _form(category_id: int, **overrides: str) -> dict[str, Any]:
    data: dict[str, Any] = {
        "sku": "A-1",
        "name": "Remera",
        "category_id": str(category_id),
        "cost_price": "10.00",
        "sale_price": "20.00",
        "min_stock": "0",
    }
    data.update(overrides)
    return data


def _api_create(client: TestClient, category_id: int, **overrides: Any) -> dict[str, Any]:
    payload = {
        "sku": "A-1",
        "name": "Remera",
        "category_id": category_id,
        "cost_price": "10.00",
        "sale_price": "20.00",
    }
    payload.update(overrides)
    response = client.post("/api/products", json=payload)
    assert response.status_code == 201
    return response.json()


def test_index_without_categories_asks_to_create_one(client: TestClient) -> None:
    response = client.get("/products")
    assert response.status_code == 200
    assert "creá una categoría" in response.text
    assert "Todavía no hay productos" in response.text


def test_index_shows_empty_state_and_form(client: TestClient) -> None:
    _category(client)
    response = client.get("/products")
    assert "Todavía no hay productos" in response.text
    assert 'name="sku"' in response.text


def test_index_defaults_to_active_products_only(client: TestClient) -> None:
    cat = _category(client)
    _api_create(client, cat, sku="A", name="Activo")
    off = _api_create(client, cat, sku="B", name="Apagado")
    client.post(f"/api/products/{off['id']}/deactivate")
    text = client.get("/products").text
    assert "Activo" in text
    assert "Apagado" not in text


def test_filters_by_state_and_category_return_a_fragment(client: TestClient) -> None:
    ropa, bazar = _category(client, "Ropa"), _category(client, "Bazar")
    _api_create(client, ropa, sku="A", name="Remera")
    off = _api_create(client, ropa, sku="B", name="Pantalon")
    _api_create(client, bazar, sku="C", name="Taza")
    client.post(f"/api/products/{off['id']}/deactivate")

    inactive = client.get("/products?state=inactive", headers=HX)
    assert "Pantalon" in inactive.text and "Remera" not in inactive.text
    assert "<html" not in inactive.text

    everything = client.get("/products?state=all", headers=HX).text
    assert all(name in everything for name in ("Remera", "Pantalon", "Taza"))

    by_category = client.get(f"/products?category={bazar}&state=all", headers=HX).text
    assert "Taza" in by_category and "Remera" not in by_category


def test_filter_without_matches_shows_message(client: TestClient) -> None:
    cat = _category(client)
    _api_create(client, cat)
    response = client.get("/products?state=inactive", headers=HX)
    assert "Ningún producto coincide" in response.text


def test_invalid_filters_fall_back_to_defaults(client: TestClient) -> None:
    cat = _category(client)
    _api_create(client, cat)
    response = client.get("/products?category=abc&state=zzz", headers=HX)
    assert response.status_code == 200
    assert "Remera" in response.text


def test_create_returns_list_fragment_without_warning(client: TestClient) -> None:
    cat = _category(client)
    response = client.post("/products", data=_form(cat, sku=" A-1 "), headers=HX)
    assert response.status_code == 200
    assert "<td>A-1</td>" in response.text
    assert "<html" not in response.text
    assert "Producto «Remera» guardado" in response.text
    assert WARNING not in response.text.lower()


def test_create_with_sale_below_cost_saves_and_warns_from_the_server(client: TestClient) -> None:
    cat = _category(client)
    response = client.post(
        "/products", data=_form(cat, cost_price="20.00", sale_price="10.00"), headers=HX
    )
    assert response.status_code == 200
    assert WARNING in response.text.lower()
    assert len(client.get("/api/products").json()) == 1  # RN16: no bloquea


def test_create_with_equal_prices_does_not_warn(client: TestClient) -> None:
    cat = _category(client)
    response = client.post(
        "/products", data=_form(cat, cost_price="10", sale_price="10"), headers=HX
    )
    assert WARNING not in response.text.lower()


def test_create_accepts_decimal_comma(client: TestClient) -> None:
    cat = _category(client)
    assert client.post("/products", data=_form(cat, cost_price="19,99"), headers=HX).status_code == 200
    assert client.get("/api/products").json()[0]["cost_price"] == "19.99"


def test_create_keeps_the_current_filter(client: TestClient) -> None:
    ropa, bazar = _category(client, "Ropa"), _category(client, "Bazar")
    data = {**_form(bazar, name="Taza", sku="T"), "category": str(ropa), "state": "active"}
    response = client.post("/products", data=data, headers=HX)
    assert "Taza" not in response.text.split('id="form-error"')[0]  # filtrado por Ropa
    assert len(client.get("/api/products").json()) == 1


def test_create_duplicate_sku_shows_spanish_error(client: TestClient) -> None:
    cat = _category(client)
    client.post("/products", data=_form(cat, sku="ABC"), headers=HX)
    response = client.post("/products", data=_form(cat, sku="abc"), headers=HX)
    assert response.status_code == 409
    assert "Ya existe un producto con el SKU" in response.text
    assert response.headers["HX-Retarget"] == "#form-error"


def test_create_invalid_values_show_field_messages(client: TestClient) -> None:
    cat = _category(client)
    cases = {
        "sku": ("   ", "El SKU es obligatorio"),
        "name": ("", "El nombre es obligatorio"),
        "cost_price": ("-1", "precio de costo"),
        "sale_price": ("abc", "precio de venta"),
        "min_stock": ("-3", "stock mínimo"),
    }
    for field, (value, message) in cases.items():
        response = client.post("/products", data=_form(cat, **{field: value}), headers=HX)
        assert response.status_code == 422, field
        assert message in response.text, field
        assert response.headers["HX-Retarget"] == "#form-error"
    assert client.get("/api/products").json() == []


def test_create_without_category_shows_error(client: TestClient) -> None:
    _category(client)
    response = client.post("/products", data={**_form(0), "category_id": ""}, headers=HX)
    assert response.status_code == 422
    assert "Elegí una categoría" in response.text


def test_edit_form_is_prefilled(client: TestClient) -> None:
    cat = _category(client)
    created = _api_create(client, cat, cost_price="19.99")
    response = client.get(f"/products/{created['id']}/edit", headers=HX)
    assert response.status_code == 200
    assert 'value="A-1"' in response.text
    assert 'value="19.99"' in response.text
    assert "selected" in response.text


def test_update_returns_row_and_warns_when_sale_below_cost(client: TestClient) -> None:
    cat = _category(client)
    created = _api_create(client, cat)
    ok = client.put(f"/products/{created['id']}", data=_form(cat, name="Camisa"), headers=HX)
    assert ok.status_code == 200
    assert "Camisa" in ok.text and WARNING not in ok.text.lower()

    warned = client.put(
        f"/products/{created['id']}", data=_form(cat, cost_price="30", sale_price="5"), headers=HX
    )
    assert warned.status_code == 200
    assert WARNING in warned.text.lower()
    assert client.get(f"/api/products/{created['id']}").json()["sale_price"] == "5.00"


def test_update_duplicate_sku_targets_row_error(client: TestClient) -> None:
    cat = _category(client)
    _api_create(client, cat, sku="A-1")
    other = _api_create(client, cat, sku="B-2")
    response = client.put(f"/products/{other['id']}", data=_form(cat, sku="a-1"), headers=HX)
    assert response.status_code == 409
    assert response.headers["HX-Retarget"] == f"#row-error-{other['id']}"


def test_update_invalid_price_targets_row_error(client: TestClient) -> None:
    cat = _category(client)
    created = _api_create(client, cat)
    response = client.put(
        f"/products/{created['id']}", data=_form(cat, cost_price="-5"), headers=HX
    )
    assert response.status_code == 422
    assert response.headers["HX-Retarget"] == f"#row-error-{created['id']}"


def test_show_row_and_unknown_product(client: TestClient) -> None:
    cat = _category(client)
    created = _api_create(client, cat)
    assert "<td>A-1</td>" in client.get(f"/products/{created['id']}", headers=HX).text
    missing = client.get("/products/999", headers=HX)
    assert missing.status_code == 404
    assert missing.headers["HX-Retarget"] == "#list-error"
    assert client.get("/products/999/edit", headers=HX).status_code == 404


def test_deactivate_removes_row_from_active_list_and_reactivate_restores_it(
    client: TestClient,
) -> None:
    cat = _category(client)
    created = _api_create(client, cat)
    off = client.post(f"/products/{created['id']}/deactivate", data={"state": "active"}, headers=HX)
    assert off.status_code == 200
    assert "Ningún producto coincide" in off.text  # existe, pero ya no es activo
    assert "<td>A-1</td>" not in off.text
    assert client.get(f"/api/products/{created['id']}").json()["is_active"] is False

    shown = client.get("/products?state=inactive", headers=HX).text
    assert "Inactivo" in shown and "Reactivar" in shown

    on = client.post(f"/products/{created['id']}/activate", data={"state": "inactive"}, headers=HX)
    assert on.status_code == 200
    assert client.get(f"/api/products/{created['id']}").json()["is_active"] is True


def test_toggle_unknown_product_returns_404_fragment(client: TestClient) -> None:
    response = client.post("/products/999/deactivate", headers=HX)
    assert response.status_code == 404
    assert response.headers["HX-Retarget"] == "#list-error"


def test_there_is_no_delete_route_in_the_ui(client: TestClient) -> None:
    cat = _category(client)
    created = _api_create(client, cat)
    assert client.delete(f"/products/{created['id']}", headers=HX).status_code == 405


def test_category_delete_view_shows_in_use_error_when_it_has_products(client: TestClient) -> None:
    cat = _category(client)
    _api_create(client, cat)
    response = client.delete(f"/categories/{cat}", headers=HX)
    assert response.status_code == 409
    assert "No se puede eliminar una categoría que tiene productos" in response.text
    assert response.headers["HX-Retarget"] == "#list-error"


def test_navigation_links_both_screens(client: TestClient) -> None:
    text = client.get("/products").text
    assert 'href="/products"' in text and 'href="/categories"' in text
