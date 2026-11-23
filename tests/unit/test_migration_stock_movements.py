"""Migración a3f9c2d17b64: crea `stock_movements`, sobre una base real en archivo."""
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

import app.models  # noqa: F401  registra los modelos en Base.metadata
from app.config import get_settings
from app.db import Base
from tests.unit.movement_rows import INVALID_ROWS, SQL_INSERT, VALID_ROWS

ROOT = Path(__file__).resolve().parents[2]
PREVIOUS = "d2a7c41e9b53"
HEAD = "a3f9c2d17b64"

CHECKS = {
    "ck_stock_movements_type_valid",
    "ck_stock_movements_quantity_sign_by_type",
    "ck_stock_movements_unit_price_non_negative",
    "ck_stock_movements_unit_price_by_type",
    "ck_stock_movements_reason_by_type",
    "ck_stock_movements_note_required_for_other",
}
INDEX = "ix_stock_movements_product_id"


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


def _query(url: str, sql: str, params: dict[str, Any] | None = None) -> list[tuple]:
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            return [tuple(row) for row in connection.execute(text(sql), params or {})]
    finally:
        engine.dispose()


def _execute(url: str, sql: str, params: dict[str, Any] | None = None) -> None:
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(text(sql), params or {})
    finally:
        engine.dispose()


def _master(url: str, *, tables: tuple[str, ...] | None = None) -> list[tuple]:
    """Foto de `sqlite_master`: tipo, nombre, tabla y SQL de cada objeto (índices incluidos)."""
    rows = _query(url, "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name")
    return [row for row in rows if tables is None or row[2] in tables]


def _table_shape(url: str, table: str) -> dict[str, object]:
    """Lo que importa de una tabla, sin depender del orden en que se declararon las cosas."""
    table_sql = _query(
        url, "SELECT sql FROM sqlite_master WHERE type='table' AND name=:t", {"t": table}
    )[0][0]
    indexes = {
        name: sql
        for name, sql in _query(
            url,
            "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name=:t",
            {"t": table},
        )
        if sql is not None  # los índices automáticos de la PK no tienen SQL
    }
    return {
        "checks": set(re.findall(r"CONSTRAINT (\w+) CHECK", table_sql)),
        "indexes": indexes,
        "foreign_keys": _query(
            url, 'SELECT "table", "from", "to", on_delete FROM pragma_foreign_key_list(:t)', {"t": table}
        ),
        "columns": sorted(
            _query(url, "SELECT name, type, \"notnull\", dflt_value, pk FROM pragma_table_info(:t)", {"t": table})
        ),
    }


def _seed_product(url: str) -> int:
    _execute(url, "INSERT INTO categories (id, name) VALUES (1, 'Ferretería')")
    _execute(
        url,
        "INSERT INTO products (id, sku, name, category_id, cost_price, sale_price, unit) "
        "VALUES (1, 'T-1', 'Tornillo', 1, 1.50, 2.00, 'UN')",
    )
    return 1


@pytest.fixture
def previous(alembic_cfg: Config, db_url: str) -> str:
    """Base en la revisión anterior, con una categoría y un producto ya cargados."""
    command.upgrade(alembic_cfg, PREVIOUS)
    _seed_product(db_url)
    return db_url


def test_upgrade_leaves_categories_and_products_exactly_as_they_were(
    alembic_cfg: Config, previous: str
) -> None:
    tables = ("categories", "products")
    before = _master(previous, tables=tables)
    data_before = _query(previous, "SELECT * FROM products")
    assert any(name == "uq_products_sku_lower" for _, name, _, _ in before)
    assert any(name == "uq_categories_name_lower" for _, name, _, _ in before)

    command.upgrade(alembic_cfg, "head")

    # CREATE TABLE, índices (incluidos los funcionales sobre lower()) y CHECKs: idénticos
    assert _master(previous, tables=tables) == before
    assert _query(previous, "SELECT * FROM products") == data_before
    assert _query(previous, "SELECT version_num FROM alembic_version") == [(HEAD,)]


def test_upgrade_creates_the_table_its_index_and_every_check(
    alembic_cfg: Config, previous: str
) -> None:
    command.upgrade(alembic_cfg, "head")
    shape = _table_shape(previous, "stock_movements")

    assert shape["checks"] == CHECKS
    assert INDEX in shape["indexes"]
    assert shape["foreign_keys"] == [("products", "product_id", "id", "NO ACTION")]  # sin cascade
    assert "updated_at" not in [column[0] for column in shape["columns"]]  # RN5


def test_migrated_schema_matches_the_one_built_from_the_models(
    alembic_cfg: Config, previous: str, tmp_path: Path
) -> None:
    command.upgrade(alembic_cfg, "head")
    models_url = f"sqlite:///{tmp_path / 'models.db'}"
    engine = create_engine(models_url)
    Base.metadata.create_all(engine)
    engine.dispose()

    migrated = _table_shape(previous, "stock_movements")
    modeled = _table_shape(models_url, "stock_movements")

    assert migrated["checks"] == modeled["checks"] == CHECKS
    assert set(migrated["indexes"]) == set(modeled["indexes"])
    assert migrated["foreign_keys"] == modeled["foreign_keys"]
    assert migrated["columns"] == modeled["columns"]


@pytest.mark.parametrize("params", VALID_ROWS.values(), ids=VALID_ROWS.keys())
def test_migrated_database_accepts_valid_rows(
    alembic_cfg: Config, previous: str, params: dict[str, Any]
) -> None:
    command.upgrade(alembic_cfg, "head")

    _execute(previous, SQL_INSERT, {**params, "product_id": 1})

    assert _query(previous, "SELECT COUNT(*) FROM stock_movements") == [(1,)]


@pytest.mark.parametrize("params", INVALID_ROWS.values(), ids=INVALID_ROWS.keys())
def test_migrated_database_rejects_invalid_rows(
    alembic_cfg: Config, previous: str, params: dict[str, Any]
) -> None:
    command.upgrade(alembic_cfg, "head")

    with pytest.raises(IntegrityError):
        _execute(previous, SQL_INSERT, {**params, "product_id": 1})

    assert _query(previous, "SELECT COUNT(*) FROM stock_movements") == [(0,)]


def test_migrated_foreign_key_rejects_unknown_product_and_product_deletion(
    alembic_cfg: Config, previous: str
) -> None:
    command.upgrade(alembic_cfg, "head")

    with pytest.raises(IntegrityError):
        _execute(previous, SQL_INSERT, {**VALID_ROWS["entrada"], "product_id": 999})
    _execute(previous, SQL_INSERT, {**VALID_ROWS["entrada"], "product_id": 1})
    with pytest.raises(IntegrityError):  # sin ON DELETE CASCADE
        _execute(previous, "DELETE FROM products WHERE id = 1")
    assert _query(previous, "SELECT COUNT(*) FROM stock_movements") == [(1,)]


def test_downgrade_round_trip_restores_the_previous_schema(
    alembic_cfg: Config, previous: str
) -> None:
    before = _master(previous)

    command.upgrade(alembic_cfg, "head")
    assert _master(previous) != before
    command.downgrade(alembic_cfg, PREVIOUS)

    assert _master(previous) == before  # sqlite_master completo, no solo `products`
    assert _query(previous, "SELECT version_num FROM alembic_version") == [(PREVIOUS,)]
    assert _query(previous, "SELECT sku FROM products") == [("T-1",)]

    command.upgrade(alembic_cfg, "head")  # y vuelve a subir sin problemas
    assert _table_shape(previous, "stock_movements")["checks"] == CHECKS


def test_downgrade_aborts_without_touching_anything_when_there_are_movements(
    alembic_cfg: Config, previous: str
) -> None:
    command.upgrade(alembic_cfg, "head")
    _execute(previous, SQL_INSERT, {**VALID_ROWS["entrada"], "product_id": 1})
    _execute(previous, SQL_INSERT, {**VALID_ROWS["ajuste negativo"], "product_id": 1})
    master = _master(previous)

    with pytest.raises(RuntimeError, match="2 movimiento"):
        command.downgrade(alembic_cfg, PREVIOUS)

    assert _master(previous) == master
    assert _query(previous, "SELECT COUNT(*) FROM stock_movements") == [(2,)]
    assert _query(previous, "SELECT version_num FROM alembic_version") == [(HEAD,)]


def test_alembic_check_reports_no_differences_after_upgrade(alembic_cfg: Config) -> None:
    command.upgrade(alembic_cfg, "head")

    command.check(alembic_cfg)  # lanza CommandError si el modelo y la base difieren
