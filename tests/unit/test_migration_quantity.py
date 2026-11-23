"""Migración d2a7c41e9b53: products.unit + min_stock en milésimas, sobre una base real en archivo."""
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.config import get_settings

ROOT = Path(__file__).resolve().parents[2]
PREVIOUS = "8e0b61370e55"
HEAD = "d2a7c41e9b53"

OLD_CHECKS = {
    "ck_products_cost_price_non_negative",
    "ck_products_sale_price_non_negative",
    "ck_products_name_not_blank",
    "ck_products_sku_not_blank",
    "ck_products_min_stock_non_negative",
}
NEW_CHECK = "ck_products_unit_valid"


@pytest.fixture
def db_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    url = f"sqlite:///{tmp_path / 'migration.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    yield url
    monkeypatch.undo()
    get_settings.cache_clear()


@pytest.fixture
def alembic_cfg(db_url: str) -> Config:
    return Config(str(ROOT / "alembic.ini"))


def _query(url: str, sql: str) -> list[tuple]:
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            return [tuple(row) for row in connection.execute(text(sql))]
    finally:
        engine.dispose()


def _execute(url: str, sql: str) -> None:
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(text(sql))
    finally:
        engine.dispose()


def _schema(url: str) -> dict[str, object]:
    """Foto de lo que importa de `products` en sqlite_master."""
    table_sql = _query(url, "SELECT sql FROM sqlite_master WHERE type='table' AND name='products'")[0][0]
    indexes = {
        name: sql
        for name, sql in _query(
            url, "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='products'"
        )
        if sql is not None  # los índices automáticos de la PK no tienen SQL
    }
    return {
        "checks": set(re.findall(r"CONSTRAINT (\w+) CHECK", table_sql)),
        "indexes": indexes,
        "foreign_keys": _query(url, "SELECT \"table\", \"from\", \"to\" FROM pragma_foreign_key_list('products')"),
        "columns": [row[1] for row in _query(url, "SELECT * FROM pragma_table_info('products')")],
    }


def _seed_products_before(url: str) -> None:
    """Productos cargados con el esquema anterior (min_stock entero)."""
    _execute(url, "INSERT INTO categories (id, name) VALUES (1, 'Ropa')")
    for sku, min_stock in (("A-1", 0), ("B-2", 5), ("C-3", 12)):
        _execute(
            url,
            "INSERT INTO products (sku, name, category_id, cost_price, sale_price, min_stock) "
            f"VALUES ('{sku}', 'Producto {sku}', 1, 10.50, 20.00, {min_stock})",
        )


def _min_stocks(url: str) -> list[int]:
    return [row[0] for row in _query(url, "SELECT min_stock FROM products ORDER BY sku")]


@pytest.fixture
def seeded_previous(alembic_cfg: Config, db_url: str) -> str:
    command.upgrade(alembic_cfg, PREVIOUS)
    _seed_products_before(db_url)
    return db_url


def test_upgrade_converts_existing_data(alembic_cfg: Config, seeded_previous: str) -> None:
    command.upgrade(alembic_cfg, "head")

    assert _min_stocks(seeded_previous) == [0, 5000, 12000]
    assert _query(seeded_previous, "SELECT DISTINCT unit FROM products") == [("UN",)]
    # el resto de los datos no se toca
    assert _query(seeded_previous, "SELECT sku, name, cost_price, sale_price FROM products ORDER BY sku")[1] == (
        "B-2",
        "Producto B-2",
        10.5,
        20,
    )


def test_upgrade_keeps_every_index_and_check_and_adds_the_unit_check(
    alembic_cfg: Config, seeded_previous: str
) -> None:
    before = _schema(seeded_previous)
    assert before["checks"] == OLD_CHECKS  # punto de partida del test

    command.upgrade(alembic_cfg, "head")
    after = _schema(seeded_previous)

    assert OLD_CHECKS <= after["checks"]
    assert NEW_CHECK in after["checks"]
    assert after["checks"] == OLD_CHECKS | {NEW_CHECK}
    assert set(before["indexes"]) <= set(after["indexes"])
    assert "uq_products_sku_lower" in after["indexes"]
    assert "lower(sku)" in after["indexes"]["uq_products_sku_lower"]
    assert "UNIQUE" in after["indexes"]["uq_products_sku_lower"].upper()
    assert after["foreign_keys"] == before["foreign_keys"]
    assert "unit" in after["columns"]
    # el batch refleja `categories` por la FK: su índice funcional no se debe tocar
    assert _query(
        seeded_previous,
        "SELECT name FROM sqlite_master WHERE type='index' AND name='uq_categories_name_lower'",
    ) == [("uq_categories_name_lower",)]


def test_unit_check_exists_for_real_in_the_migrated_database(
    alembic_cfg: Config, seeded_previous: str
) -> None:
    command.upgrade(alembic_cfg, "head")
    insert = (
        "INSERT INTO products (sku, name, category_id, cost_price, sale_price, unit) "
        "VALUES ('{sku}', 'X', 1, 1, 1, '{unit}')"
    )

    with pytest.raises(IntegrityError):
        _execute(seeded_previous, insert.format(sku="Z-9", unit="XX"))
    _execute(seeded_previous, insert.format(sku="Z-9", unit="KG"))  # una válida sí entra

    assert _query(seeded_previous, "SELECT unit FROM products WHERE sku='Z-9'") == [("KG",)]


def test_other_constraints_survive_in_the_migrated_database(
    alembic_cfg: Config, seeded_previous: str
) -> None:
    command.upgrade(alembic_cfg, "head")

    with pytest.raises(IntegrityError):  # CHECK min_stock >= 0
        _execute(
            seeded_previous,
            "INSERT INTO products (sku, name, category_id, cost_price, sale_price, min_stock) "
            "VALUES ('N-1', 'X', 1, 1, 1, -1)",
        )
    with pytest.raises(IntegrityError):  # índice único sobre lower(sku): prueba que sobrevivió
        _execute(
            seeded_previous,
            "INSERT INTO products (sku, name, category_id, cost_price, sale_price) "
            "VALUES ('a-1', 'X', 1, 1, 1)",
        )
    with pytest.raises(IntegrityError):  # FK a categories
        _execute(
            seeded_previous,
            "INSERT INTO products (sku, name, category_id, cost_price, sale_price) "
            "VALUES ('F-1', 'X', 999, 1, 1)",
        )


def test_downgrade_round_trip_restores_integers_and_schema(
    alembic_cfg: Config, seeded_previous: str
) -> None:
    before = _schema(seeded_previous)

    command.upgrade(alembic_cfg, "head")
    command.downgrade(alembic_cfg, PREVIOUS)
    after = _schema(seeded_previous)

    assert _min_stocks(seeded_previous) == [0, 5, 12]
    assert "unit" not in after["columns"]
    assert after["checks"] == before["checks"] == OLD_CHECKS
    assert set(after["indexes"]) == set(before["indexes"])
    assert after["foreign_keys"] == before["foreign_keys"]
    assert after["columns"] == before["columns"]


def test_downgrade_aborts_when_a_min_stock_has_decimals(
    alembic_cfg: Config, seeded_previous: str
) -> None:
    command.upgrade(alembic_cfg, "head")
    _execute(
        seeded_previous,
        "INSERT INTO products (sku, name, category_id, cost_price, sale_price, unit, min_stock) "
        "VALUES ('KG-1', 'Harina', 1, 1, 1, 'KG', 1500)",
    )
    snapshot = _schema(seeded_previous)

    with pytest.raises(RuntimeError, match="KG-1"):
        command.downgrade(alembic_cfg, PREVIOUS)

    # no tocó nada: mismos datos y mismo esquema
    assert _min_stocks(seeded_previous) == [0, 5000, 12000, 1500]  # A-1, B-2, C-3, KG-1
    assert _query(seeded_previous, "SELECT unit FROM products WHERE sku='KG-1'") == [("KG",)]
    assert _schema(seeded_previous) == snapshot
    assert _query(seeded_previous, "SELECT version_num FROM alembic_version") == [(HEAD,)]


def test_alembic_check_reports_no_differences_after_upgrade(alembic_cfg: Config) -> None:
    command.upgrade(alembic_cfg, "head")

    command.check(alembic_cfg)  # lanza CommandError si el modelo y la base difieren
