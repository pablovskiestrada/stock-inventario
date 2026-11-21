from fastapi.testclient import TestClient

HX = {"HX-Request": "true"}


def test_index_shows_empty_state(client: TestClient) -> None:
    response = client.get("/categories")
    assert response.status_code == 200
    assert "Todavía no hay categorías" in response.text


def test_index_lists_categories(client: TestClient) -> None:
    client.post("/api/categories", json={"name": "Ropa"})
    assert "Ropa" in client.get("/categories").text


def test_create_via_htmx_returns_list_fragment(client: TestClient) -> None:
    response = client.post("/categories", data={"name": " Ropa "}, headers=HX)
    assert response.status_code == 200
    assert "<td>Ropa</td>" in response.text
    assert "<html" not in response.text


def test_create_duplicate_shows_spanish_error(client: TestClient) -> None:
    client.post("/categories", data={"name": "Ropa"}, headers=HX)
    response = client.post("/categories", data={"name": "ropa"}, headers=HX)
    assert response.status_code == 409
    assert "Ya existe una categoría" in response.text
    assert response.headers["HX-Retarget"] == "#form-error"


def test_create_blank_shows_required_error(client: TestClient) -> None:
    response = client.post("/categories", data={"name": "   "}, headers=HX)
    assert response.status_code == 422
    assert "obligatorio" in response.text


def test_edit_and_rename_row(client: TestClient) -> None:
    created = client.post("/api/categories", json={"name": "Ropa"}).json()
    edit = client.get(f"/categories/{created['id']}/edit", headers=HX)
    assert edit.status_code == 200
    assert 'value="Ropa"' in edit.text

    renamed = client.put(f"/categories/{created['id']}", data={"name": "Bazar"}, headers=HX)
    assert renamed.status_code == 200
    assert "<td>Bazar</td>" in renamed.text


def test_rename_duplicate_targets_row_error(client: TestClient) -> None:
    client.post("/api/categories", json={"name": "Ropa"})
    other = client.post("/api/categories", json={"name": "Bazar"}).json()
    response = client.put(f"/categories/{other['id']}", data={"name": "ropa"}, headers=HX)
    assert response.status_code == 409
    assert response.headers["HX-Retarget"] == f"#row-error-{other['id']}"


def test_delete_returns_empty_fragment_and_removes_category(client: TestClient) -> None:
    created = client.post("/api/categories", json={"name": "Ropa"}).json()
    response = client.delete(f"/categories/{created['id']}", headers=HX)
    assert response.status_code == 200
    assert response.text == ""
    assert "Ropa" not in client.get("/categories").text


def test_delete_unknown_shows_error(client: TestClient) -> None:
    response = client.delete("/categories/999", headers=HX)
    assert response.status_code == 404
    assert response.headers["HX-Retarget"] == "#list-error"


def test_htmx_static_file_is_served(client: TestClient) -> None:
    assert client.get("/static/htmx.min.js").status_code == 200
