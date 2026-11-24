"""RN32: pantalla del historial (`GET /products/{id}/movements`) y botón «Historial»."""
import html as html_lib
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event
from sqlalchemy.orm import sessionmaker

import app.templating as templating
from app.models.stock_movement import StockMovement

ART = timezone(timedelta(hours=-3))
D = Decimal


@pytest.fixture(autouse=True)
def fixed_display_zone(monkeypatch: pytest.MonkeyPatch) -> None:
    """Las fechas se ven en UTC-3 sin importar la zona de la máquina que corre los tests."""
    monkeypatch.setattr(templating, "DISPLAY_TZ", ART)


@pytest.fixture
def cat(client: TestClient) -> int:
    response = client.post("/api/categories", json={"name": "Ferretería"})
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


def _register(client: TestClient, product_id: int, kind: str, quantity: str, **extra: Any) -> None:
    body: dict[str, Any] = {"type": kind, "quantity": quantity, **extra}
    if kind in ("IN", "OUT"):
        body.setdefault("unit_price", "10.00")
    else:
        body.setdefault("reason", "CONTEO")
    response = client.post(f"/api/products/{product_id}/movements", json=body)
    assert response.status_code == 201, response.text


def _insert(engine: Engine, *movements: StockMovement) -> None:
    with sessionmaker(bind=engine, expire_on_commit=False)() as db_session:
        db_session.add_all(movements)
        db_session.commit()


def _entry(product_id: int, quantity: str = "1", **extra: Any) -> StockMovement:
    return StockMovement(
        product_id=product_id, type="IN", quantity=D(quantity), unit_price=D("1.00"), **extra
    )


def _bulk_ins(engine: Engine, product_id: int, count: int) -> None:
    _insert(engine, *(_entry(product_id) for _ in range(count)))


def _history(client: TestClient, product_id: int) -> str:
    response = client.get(f"/products/{product_id}/movements")
    assert response.status_code == 200, response.text
    return response.text


def _rows(page: str) -> list[list[str]]:
    """Celdas (texto) de cada fila del historial, en el orden en que salen en la página."""
    rows = re.findall(r'<tr id="movement-\d+">(.*?)</tr>', page, re.S)
    return [[html_lib.unescape(c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)] for row in rows]


def _stock_cell(page: str, product_id: int) -> str:
    row = re.search(rf'<tr id="product-{product_id}".*?</tr>', page, re.S)
    assert row
    cell = re.search(r'<td class="stock">(.*?)</td>', row.group(0), re.S)
    assert cell
    return cell.group(1).strip()


# --- botón «Historial» en el listado ---


def test_every_product_row_offers_the_history_button_active_or_inactive(
    client: TestClient, cat: int
) -> None:
    active = _product(client, cat, sku="A-1", name="Activo")
    inactive = _product(client, cat, sku="I-1", name="Inactivo")
    client.post(f"/api/products/{inactive['id']}/deactivate")

    page = client.get("/products?state=all").text

    for product in (active, inactive):
        assert f'<a class="button" href="/products/{product["id"]}/movements">Historial</a>' in page


def test_the_history_button_does_not_bring_back_movement_actions_on_inactive_rows(
    client: TestClient, cat: int
) -> None:
    product = _product(client, cat)
    client.post(f"/api/products/{product['id']}/deactivate")

    page = client.get("/products?state=inactive", headers={"HX-Request": "true"}).text

    assert ">Historial</a>" in page
    assert "/movements/new" not in page  # RN7 sigue en pie


# --- contenido de la página ---


def test_the_page_has_the_spanish_columns_and_the_product_header(
    client: TestClient, cat: int
) -> None:
    product = _product(client, cat, sku="H-9", name="Harina 000")
    _register(client, product["id"], "IN", "1")

    page = _history(client, product["id"])

    assert "<!doctype html>" in page
    assert "Historial: Harina 000" in page
    assert "SKU H-9" in page and "Unidad: KG" in page
    assert "Inactivo" not in page
    assert '<a href="/products">← Volver a productos</a>' in page
    headers = re.findall(r"<th>(.*?)</th>", page)
    assert headers == [
        "Fecha y hora", "Tipo", "Cantidad", "Precio unitario", "Motivo", "Referencia", "Nota", "Saldo",
    ]


def test_each_row_shows_date_type_signed_quantity_price_reason_reference_note_and_balance(
    client: TestClient, engine: Engine, cat: int
) -> None:
    product = _product(client, cat)
    pid = product["id"]
    _insert(
        engine,
        StockMovement(  # 17:05 UTC = 14:05 en UTC-3
            product_id=pid, type="IN", quantity=D("10"), unit_price=D("10.5"),
            reference="R-1", note="lote 7", created_at=datetime(2026, 11, 23, 17, 5, 30),
        ),
        StockMovement(
            product_id=pid, type="OUT", quantity=D("3"), unit_price=D("25"),
            created_at=datetime(2026, 11, 24, 2, 30),  # 02:30 UTC = 23:30 del día anterior
        ),
        StockMovement(
            product_id=pid, type="ADJUSTMENT", quantity=D("-2"), reason="ROTURA",
            created_at=datetime(2026, 11, 24, 12, 0),
        ),
        StockMovement(
            product_id=pid, type="ADJUSTMENT", quantity=D("0.5"), reason="ERROR_CARGA",
            note="se cargó de menos", created_at=datetime(2026, 11, 24, 13, 0),
        ),
    )

    rows = _rows(_history(client, pid))

    assert rows == [  # del más reciente al más antiguo
        ["24/11/2026 10:00", "Ajuste", "+0.5 KG", "—", "Error de carga", "—", "se cargó de menos", "5.5 KG"],
        ["24/11/2026 09:00", "Ajuste", "-2 KG", "—", "Rotura", "—", "—", "5 KG"],
        ["23/11/2026 23:30", "Salida", "-3 KG", "25.00", "—", "—", "—", "7 KG"],
        ["23/11/2026 14:05", "Entrada", "+10 KG", "10.50", "—", "R-1", "lote 7", "10 KG"],
    ]


def test_every_adjustment_reason_has_its_spanish_label(
    client: TestClient, engine: Engine, cat: int
) -> None:
    product = _product(client, cat)
    _register(client, product["id"], "IN", "100")
    for reason in ("ROTURA", "MERMA", "CONTEO", "ERROR_CARGA"):
        _register(client, product["id"], "ADJUSTMENT", "-1", reason=reason)
    _register(client, product["id"], "ADJUSTMENT", "-1", reason="OTRO", note="otro motivo")

    reasons = [row[4] for row in _rows(_history(client, product["id"]))]

    assert reasons == ["Otro", "Error de carga", "Conteo", "Merma", "Rotura", "—"]


def test_rows_follow_the_insertion_order_not_the_date(
    client: TestClient, engine: Engine, cat: int
) -> None:
    product = _product(client, cat)
    _insert(
        engine,
        _entry(product["id"], "1", created_at=datetime(2026, 5, 1, 12, 0)),
        _entry(product["id"], "2", created_at=datetime(2026, 1, 1, 12, 0)),  # más vieja, insertada después
        _entry(product["id"], "4", created_at=datetime(2026, 3, 1, 12, 0)),
    )

    page = _history(client, product["id"])

    ids = [int(n) for n in re.findall(r'<tr id="movement-(\d+)">', page)]
    assert ids == sorted(ids, reverse=True) and len(ids) == 3
    assert [row[7] for row in _rows(page)] == ["7 KG", "3 KG", "1 KG"]  # el saldo sigue el id


def test_decimal_balances_are_shown_exactly(client: TestClient, cat: int) -> None:
    product = _product(client, cat)
    _register(client, product["id"], "IN", "1.3")
    _register(client, product["id"], "IN", "0.2")
    _register(client, product["id"], "OUT", "1.5")

    rows = _rows(_history(client, product["id"]))

    assert [(row[2], row[7]) for row in rows] == [
        ("-1.5 KG", "0 KG"),
        ("+0.2 KG", "1.5 KG"),
        ("+1.3 KG", "1.3 KG"),
    ]


def test_a_un_product_shows_whole_numbers(client: TestClient, cat: int) -> None:
    product = _product(client, cat, sku="U-1", unit="UN")
    _register(client, product["id"], "IN", "4")
    _register(client, product["id"], "ADJUSTMENT", "-1")

    rows = _rows(_history(client, product["id"]))

    assert [(row[2], row[7]) for row in rows] == [("-1 UN", "3 UN"), ("+4 UN", "4 UN")]


def test_the_first_row_balance_is_the_stock_shown_in_the_product_list(
    client: TestClient, cat: int
) -> None:
    product = _product(client, cat)
    for kind, quantity in (("IN", "10"), ("OUT", "3.25"), ("ADJUSTMENT", "-0.75"), ("IN", "1.5")):
        _register(client, product["id"], kind, quantity)

    first_balance = _rows(_history(client, product["id"]))[0][7]

    assert first_balance == _stock_cell(client.get("/products").text, product["id"]) == "7.5 KG"


# --- vacío, inactivo, 404 ---


def test_an_empty_history_shows_the_empty_state(client: TestClient, cat: int) -> None:
    product = _product(client, cat)

    page = _history(client, product["id"])

    assert "Este producto todavía no tiene movimientos." in page
    assert "<table" not in page and "Se muestran los últimos" not in page


def test_an_inactive_product_still_shows_its_history(client: TestClient, cat: int) -> None:
    product = _product(client, cat)
    _register(client, product["id"], "IN", "3")
    client.post(f"/api/products/{product['id']}/deactivate")

    page = _history(client, product["id"])

    assert "<strong>Inactivo</strong>" in page
    assert [row[7] for row in _rows(page)] == ["3 KG"]


def test_an_unknown_product_is_a_404_page_with_a_way_back(client: TestClient) -> None:
    response = client.get("/products/999/movements")

    assert response.status_code == 404
    assert "<!doctype html>" in response.text
    assert "no existe" in response.text
    assert '<a href="/products">← Volver a productos</a>' in response.text


# --- límite de 200 y aviso ---


def test_above_200_it_shows_the_last_200_with_the_notice_and_the_whole_history_balance(
    client: TestClient, engine: Engine, cat: int
) -> None:
    product = _product(client, cat)
    _bulk_ins(engine, product["id"], 201)

    page = _history(client, product["id"])

    rows = _rows(page)
    assert len(rows) == 200
    assert "Se muestran los últimos 200 movimientos de 201." in page
    assert "El saldo de cada fila corresponde a todo el historial." in page
    assert rows[0][7] == "201 KG"
    assert rows[-1][7] == "2 KG"  # la 2ª entrada: la primera ya no se muestra pero cuenta en el saldo


def test_with_exactly_200_there_is_no_notice(client: TestClient, engine: Engine, cat: int) -> None:
    product = _product(client, cat)
    _bulk_ins(engine, product["id"], 200)

    page = _history(client, product["id"])

    assert len(_rows(page)) == 200
    assert "Se muestran los últimos" not in page


def test_the_page_runs_the_same_number_of_statements_whatever_the_history_size(
    client: TestClient, engine: Engine, cat: int
) -> None:
    def statements_for(product_id: int) -> int:
        seen: list[str] = []
        listener = lambda _c, _cur, stmt, *_a: seen.append(stmt)  # noqa: E731
        event.listen(engine, "before_cursor_execute", listener)
        try:
            assert client.get(f"/products/{product_id}/movements").status_code == 200
        finally:
            event.remove(engine, "before_cursor_execute", listener)
        return len(seen)

    few = _product(client, cat, sku="F-1")
    many = _product(client, cat, sku="M-1")
    _bulk_ins(engine, few["id"], 3)
    _bulk_ins(engine, many["id"], 150)

    assert statements_for(few["id"]) == statements_for(many["id"])


# --- solo lectura (RN5) y escape ---


def test_the_page_offers_no_action_over_the_movements(client: TestClient, cat: int) -> None:
    product = _product(client, cat)
    _register(client, product["id"], "IN", "5")
    _register(client, product["id"], "OUT", "1")

    page = _history(client, product["id"])

    for forbidden in ("<form", "<button", "<input", "<select", "<textarea", "hx-", "/movements/new"):
        assert forbidden not in page, forbidden
    for label in ("Editar", "Eliminar", "Borrar", "Anular", "Desactivar", "Registrar"):
        assert label not in page, label


def test_the_history_route_is_get_only_for_the_page_and_never_edits_or_deletes(
    client: TestClient, cat: int
) -> None:
    product = _product(client, cat)
    _register(client, product["id"], "IN", "5")
    base = f"/products/{product['id']}/movements"

    for method in ("PUT", "PATCH", "DELETE"):
        assert client.request(method, base).status_code == 405, method
    assert client.get(f"{base}/1").status_code == 404  # tampoco hay detalle de un movimiento


def test_notes_and_references_are_escaped(client: TestClient, engine: Engine, cat: int) -> None:
    product = _product(client, cat)
    _insert(
        engine,
        _entry(product["id"], note="<script>alert(1)</script>", reference='<b onmouseover="x">R</b>'),
    )

    page = _history(client, product["id"])

    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert '<b onmouseover="x">' not in page
