from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient


def _category(client: TestClient, name: str = "Ropa") -> dict[str, Any]:
    response = client.post("/api/categories", json={"name": name})
    assert response.status_code == 201
    return response.json()


def _payload(category_id: int, **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "sku": "A-1",
        "name": "Remera",
        "category_id": category_id,
        "cost_price": "19.99",
        "sale_price": "0.10",
    }
    data.update(overrides)
    return data


def _create(client: TestClient, category_id: int, **overrides: Any) -> dict[str, Any]:
    response = client.post("/api/products", json=_payload(category_id, **overrides))
    assert response.status_code == 201, response.text
    return response.json()


def test_create_returns_201_with_normalized_data(client: TestClient) -> None:
    category = _category(client)
    created = _create(client, category["id"], sku="  A-1 ", name=" Remera ")
    assert created["sku"] == "A-1"
    assert created["name"] == "Remera"
    assert created["cost_price"] == "19.99"
    assert created["sale_price"] == "0.10"
    assert created["min_stock"] == "0.000"
    assert created["unit"] == "UN"
    assert created["is_active"] is True


def test_create_with_sale_below_cost_is_not_blocked(client: TestClient) -> None:
    """RN16: la advertencia no bloquea el guardado (costo 19.99 > venta 0.10)."""
    category = _category(client)
    assert client.post("/api/products", json=_payload(category["id"])).status_code == 201


def test_create_duplicate_sku_returns_409_case_insensitive(client: TestClient) -> None:
    category = _category(client)
    _create(client, category["id"], sku="ABC-1")
    response = client.post("/api/products", json=_payload(category["id"], sku="abc-1"))
    assert response.status_code == 409


def test_create_unknown_category_returns_422(client: TestClient) -> None:
    assert client.post("/api/products", json=_payload(999)).status_code == 422


@pytest.mark.parametrize(
    "overrides",
    [
        {"sku": "   "},
        {"sku": "x" * 51},
        {"name": ""},
        {"name": "x" * 151},
        {"cost_price": "-0.01"},
        {"sale_price": "1.005"},
        {"min_stock": -1},
        {"min_stock": 1.5},  # UN (por defecto) solo admite enteros
        {"min_stock": "0.0001", "unit": "KG"},
        {"unit": "XX"},
        {"unit": "kg"},
    ],
)
def test_create_invalid_payload_returns_422(client: TestClient, overrides: dict[str, Any]) -> None:
    category = _category(client)
    response = client.post("/api/products", json=_payload(category["id"], **overrides))
    assert response.status_code == 422


@pytest.mark.parametrize("missing", ["sku", "name", "category_id", "cost_price", "sale_price"])
def test_create_requires_fields(client: TestClient, missing: str) -> None:
    category = _category(client)
    payload = _payload(category["id"])
    del payload[missing]
    assert client.post("/api/products", json=payload).status_code == 422


def test_get_and_unknown_product(client: TestClient) -> None:
    category = _category(client)
    created = _create(client, category["id"])
    assert client.get(f"/api/products/{created['id']}").json()["sku"] == "A-1"
    assert client.get("/api/products/999").status_code == 404


def test_update_product(client: TestClient) -> None:
    category = _category(client)
    created = _create(client, category["id"])
    response = client.put(
        f"/api/products/{created['id']}",
        json=_payload(category["id"], sku="B-2", name="Camisa", min_stock=4),
    )
    assert response.status_code == 200
    assert (response.json()["sku"], response.json()["min_stock"]) == ("B-2", "4.000")


def test_create_with_decimal_unit_and_min_stock(client: TestClient) -> None:
    category = _category(client)
    created = _create(client, category["id"], unit="KG", min_stock="1.5")
    assert (created["unit"], created["min_stock"]) == ("KG", "1.500")
    assert client.get(f"/api/products/{created['id']}").json()["min_stock"] == "1.500"


def test_create_decimal_min_stock_with_un_returns_422_with_message(client: TestClient) -> None:
    category = _category(client)
    response = client.post(
        "/api/products", json=_payload(category["id"], unit="UN", min_stock="1.5")
    )
    assert response.status_code == 422
    assert "solo admite cantidades enteras" in response.json()["detail"]


def test_update_changing_unit_revalidates_min_stock(client: TestClient) -> None:
    category = _category(client)
    created = _create(client, category["id"], unit="KG", min_stock="1.5")
    response = client.put(
        f"/api/products/{created['id']}",
        json=_payload(category["id"], unit="UN", min_stock="1.5"),
    )
    assert response.status_code == 422
    assert client.get(f"/api/products/{created['id']}").json()["unit"] == "KG"  # no cambió


def test_update_duplicate_sku_returns_409_and_unknown_returns_404(client: TestClient) -> None:
    category = _category(client)
    _create(client, category["id"], sku="A-1")
    other = _create(client, category["id"], sku="B-2")
    duplicate = client.put(f"/api/products/{other['id']}", json=_payload(category["id"], sku="a-1"))
    assert duplicate.status_code == 409
    assert client.put("/api/products/999", json=_payload(category["id"])).status_code == 404


def test_deactivate_and_activate(client: TestClient) -> None:
    category = _category(client)
    created = _create(client, category["id"])
    off = client.post(f"/api/products/{created['id']}/deactivate")
    assert off.status_code == 200 and off.json()["is_active"] is False
    on = client.post(f"/api/products/{created['id']}/activate")
    assert on.status_code == 200 and on.json()["is_active"] is True
    assert client.post("/api/products/999/deactivate").status_code == 404


def test_there_is_no_physical_delete(client: TestClient) -> None:
    category = _category(client)
    created = _create(client, category["id"])
    assert client.delete(f"/api/products/{created['id']}").status_code == 405


def test_list_filters_by_category_and_state(client: TestClient) -> None:
    ropa = _category(client, "Ropa")
    bazar = _category(client, "Bazar")
    a = _create(client, ropa["id"], sku="A", name="Alfa")
    b = _create(client, ropa["id"], sku="B", name="Beta")
    c = _create(client, bazar["id"], sku="C", name="Gamma")
    client.post(f"/api/products/{b['id']}/deactivate")

    def ids(query: str) -> list[int]:
        return [p["id"] for p in client.get(f"/api/products{query}").json()]

    assert ids("") == [a["id"], b["id"], c["id"]]
    assert ids("?is_active=true") == [a["id"], c["id"]]
    assert ids("?is_active=false") == [b["id"]]
    assert ids(f"?category_id={ropa['id']}") == [a["id"], b["id"]]
    assert ids(f"?category_id={ropa['id']}&is_active=true") == [a["id"]]


def test_deleting_category_with_products_returns_409(client: TestClient) -> None:
    """RN9 de punta a punta, también con un producto inactivo."""
    category = _category(client)
    created = _create(client, category["id"])
    client.post(f"/api/products/{created['id']}/deactivate")
    assert client.delete(f"/api/categories/{category['id']}").status_code == 409
    assert client.get(f"/api/categories/{category['id']}").status_code == 200


def test_update_changing_the_unit_of_a_product_with_movements_returns_409(
    client: TestClient, seed_movement: Callable[[int], None]
) -> None:
    category = _category(client)
    created = _create(client, category["id"], unit="KG")
    seed_movement(created["id"])

    response = client.put(
        f"/api/products/{created['id']}", json=_payload(category["id"], unit="UN", name="Nuevo")
    )

    assert response.status_code == 409
    assert "No se puede cambiar la unidad" in response.json()["detail"]
    stored = client.get(f"/api/products/{created['id']}").json()
    assert (stored["unit"], stored["name"]) == ("KG", "Remera")


def test_update_sku_and_other_fields_of_a_product_with_movements_returns_200(
    client: TestClient, seed_movement: Callable[[int], None]
) -> None:
    category = _category(client)
    created = _create(client, category["id"], unit="KG")
    seed_movement(created["id"])

    response = client.put(
        f"/api/products/{created['id']}",
        json=_payload(category["id"], unit="KG", sku="NEW-1", name="Harina"),
    )

    assert response.status_code == 200
    assert (response.json()["sku"], response.json()["unit"]) == ("NEW-1", "KG")
