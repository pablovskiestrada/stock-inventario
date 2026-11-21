from fastapi.testclient import TestClient


def _create(client: TestClient, name: str) -> dict:
    response = client.post("/api/categories", json={"name": name})
    assert response.status_code == 201
    return response.json()


def test_create_returns_201_with_trimmed_name(client: TestClient) -> None:
    created = _create(client, "  Ropa  ")
    assert created["name"] == "Ropa"
    assert created["id"] > 0


def test_create_blank_name_returns_422(client: TestClient) -> None:
    assert client.post("/api/categories", json={"name": "   "}).status_code == 422


def test_create_too_long_name_returns_422(client: TestClient) -> None:
    assert client.post("/api/categories", json={"name": "x" * 101}).status_code == 422


def test_create_duplicate_returns_409_case_insensitive(client: TestClient) -> None:
    _create(client, "Ropa")
    response = client.post("/api/categories", json={"name": "ropa"})
    assert response.status_code == 409


def test_list_returns_categories(client: TestClient) -> None:
    _create(client, "Ropa")
    _create(client, "Bazar")
    names = [c["name"] for c in client.get("/api/categories").json()]
    assert names == ["Bazar", "Ropa"]


def test_get_unknown_returns_404(client: TestClient) -> None:
    assert client.get("/api/categories/999").status_code == 404


def test_rename_returns_updated_category(client: TestClient) -> None:
    created = _create(client, "Ropa")
    response = client.put(f"/api/categories/{created['id']}", json={"name": "Indumentaria"})
    assert response.status_code == 200
    assert response.json()["name"] == "Indumentaria"


def test_rename_to_existing_returns_409(client: TestClient) -> None:
    _create(client, "Ropa")
    other = _create(client, "Bazar")
    response = client.put(f"/api/categories/{other['id']}", json={"name": "RoPa"})
    assert response.status_code == 409


def test_rename_unknown_returns_404(client: TestClient) -> None:
    assert client.put("/api/categories/999", json={"name": "X"}).status_code == 404


def test_delete_returns_204_then_404(client: TestClient) -> None:
    created = _create(client, "Ropa")
    assert client.delete(f"/api/categories/{created['id']}").status_code == 204
    assert client.get(f"/api/categories/{created['id']}").status_code == 404


def test_delete_unknown_returns_404(client: TestClient) -> None:
    assert client.delete("/api/categories/999").status_code == 404
