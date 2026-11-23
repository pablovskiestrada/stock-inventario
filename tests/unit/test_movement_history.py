"""RN30: historial de un producto con saldo calculado en SQL (repositorio + servicio)."""
import random
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import Engine, event
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.product import Product
from app.models.stock_movement import StockMovement
from app.repositories.product_repository import ProductRepository
from app.repositories.stock_movement_repository import StockMovementRepository
from app.services.errors import InsufficientStockError, ProductNotFoundError
from app.services.stock_movement_service import HISTORY_LIMIT, StockMovementService

D = Decimal
ProductFactory = Callable[..., Product]
Row = tuple[str, str]  # (tipo, cantidad con signo solo en ADJUSTMENT)


@pytest.fixture
def service(session: Session) -> StockMovementService:
    return StockMovementService(StockMovementRepository(session), ProductRepository(session))


@pytest.fixture
def make_product(session: Session) -> ProductFactory:
    category = Category(name="Ferretería")
    session.add(category)
    session.commit()
    counter = iter(range(1, 1000))

    def factory(**overrides: Any) -> Product:
        n = next(counter)
        data: dict[str, Any] = {
            "sku": f"P-{n}",
            "name": f"Producto {n}",
            "category_id": category.id,
            "cost_price": D("10.00"),
            "sale_price": D("20.00"),
            "unit": "KG",
        }
        data.update(overrides)
        product = Product(**data)
        session.add(product)
        session.commit()
        return product

    return factory


@pytest.fixture
def product(make_product: ProductFactory) -> Product:
    return make_product()


def _movement(product_id: int, kind: str, quantity: str, **extra: Any) -> StockMovement:
    is_adjustment = kind == "ADJUSTMENT"
    return StockMovement(
        product_id=product_id,
        type=kind,
        quantity=D(quantity),
        unit_price=None if is_adjustment else D("10.00"),
        reason="CONTEO" if is_adjustment else None,
        **extra,
    )


def _seed(session: Session, product: Product, rows: list[Row]) -> None:
    """Inserta directo (sin RN4) para armar historiales largos rápido."""
    session.add_all(_movement(product.id, kind, quantity) for kind, quantity in rows)
    session.commit()


def _register(service: StockMovementService, product: Product, kind: str, quantity: str) -> None:
    service.register_movement(
        product_id=product.id,
        type=kind,
        quantity=D(quantity),
        unit_price=None if kind == "ADJUSTMENT" else D("10.00"),
        reason="CONTEO" if kind == "ADJUSTMENT" else None,
    )


def _expected_balances(rows: list[Row]) -> list[Decimal]:
    """Oráculo independiente: saldo acumulado en orden de inserción, con Decimal."""
    balance = D(0)
    balances: list[Decimal] = []
    for kind, quantity in rows:
        value = D(quantity)
        balance += -value if kind == "OUT" else value
        balances.append(balance)
    return balances


# --- orden (RN30: el orden es el de inserción, `id`) ---


def test_history_is_most_recent_first_by_id_and_ignores_the_date(
    service: StockMovementService, session: Session, product: Product
) -> None:
    # La fecha está desordenada a propósito: el orden lo da el id, no `created_at`.
    dates = [datetime(2026, 3, 1, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 2, 1, tzinfo=UTC)]
    session.add_all(
        _movement(product.id, "IN", quantity, created_at=date)
        for quantity, date in zip(("1", "2", "4"), dates, strict=True)
    )
    session.commit()

    history = service.history(product.id)

    ids = [row.movement.id for row in history.entries]
    assert ids == sorted(ids, reverse=True) and len(ids) == 3
    # El saldo también sigue el orden de inserción: 1, 1+2, 1+2+4 (de más viejo a más nuevo).
    assert [row.balance for row in history.entries] == [D("7"), D("3"), D("1")]


# --- saldo ---


def test_balance_follows_ins_outs_and_negative_adjustments(
    service: StockMovementService, product: Product
) -> None:
    for kind, quantity in (("IN", "10"), ("OUT", "3"), ("ADJUSTMENT", "-2"), ("IN", "5"), ("ADJUSTMENT", "1")):
        _register(service, product, kind, quantity)

    entries = service.history(product.id).entries

    # Del más reciente al más antiguo.
    assert [row.balance for row in entries] == [D("11"), D("10"), D("5"), D("7"), D("10")]
    assert [row.signed_quantity for row in entries] == [D("1"), D("5"), D("-2"), D("-3"), D("10")]
    assert [row.movement.type for row in entries] == ["ADJUSTMENT", "IN", "ADJUSTMENT", "OUT", "IN"]


def test_balance_is_an_exact_decimal_with_three_decimals(
    service: StockMovementService, product: Product
) -> None:
    """1,3 + 0,2 - 1,5: misma coerción a `Quantity` que `_stock_sum()`, sin float."""
    _register(service, product, "IN", "1.3")
    _register(service, product, "IN", "0.2")
    _register(service, product, "OUT", "1.5")

    entries = service.history(product.id).entries

    balances = [row.balance for row in reversed(entries)]  # del más antiguo al más reciente
    assert balances == [D("1.300"), D("1.500"), D("0.000")]
    # `==` entre Decimal no distingue la escala: se verifica además el texto exacto.
    assert [str(balance) for balance in balances] == ["1.300", "1.500", "0.000"]
    assert all(isinstance(balance, Decimal) for balance in balances)

    signed = [row.signed_quantity for row in reversed(entries)]
    assert [str(value) for value in signed] == ["1.300", "0.200", "-1.500"]
    assert all(isinstance(value, Decimal) for value in signed)


def test_the_balance_of_the_most_recent_movement_is_the_current_stock(
    service: StockMovementService, product: Product
) -> None:
    for kind, quantity in (("IN", "2.5"), ("OUT", "0.75"), ("ADJUSTMENT", "-0.5"), ("IN", "1.125")):
        _register(service, product, kind, quantity)

    history = service.history(product.id)

    assert history.entries[0].balance == service.current_stock(product.id) == D("2.375")


def test_the_most_recent_balance_matches_current_stock_after_every_step_of_a_random_sequence(
    service: StockMovementService, product: Product
) -> None:
    rng = random.Random(20261123)  # semilla fija: reproducible
    registered: list[Row] = []

    for _ in range(80):
        stock = service.current_stock(product.id)
        kind = rng.choice(("IN", "OUT", "ADJUSTMENT", "ADJUSTMENT"))
        thousandths = rng.randint(1, 5000)
        if kind in ("OUT", "ADJUSTMENT") and stock == 0:
            kind = "IN"
        if kind == "OUT":
            thousandths = min(thousandths, int(stock * 1000))
        sign = 1
        if kind == "ADJUSTMENT":
            sign = rng.choice((1, -1))
            if sign < 0:
                thousandths = min(thousandths, int(stock * 1000))
        quantity = str(D(sign * thousandths).scaleb(-3))
        _register(service, product, kind, quantity)
        registered.append((kind, quantity))

        history = service.history(product.id)
        assert history.entries[0].balance == service.current_stock(product.id), (kind, quantity)

    # Y cada saldo coincide con el acumulado calculado a mano.
    shown = [row.balance for row in reversed(service.history(product.id).entries)]
    assert shown == _expected_balances(registered)


def test_a_rejected_movement_leaves_no_trace_in_the_history(
    service: StockMovementService, product: Product
) -> None:
    _register(service, product, "IN", "1")
    with pytest.raises(InsufficientStockError):
        _register(service, product, "OUT", "2")

    history = service.history(product.id)

    assert history.total == 1
    assert history.entries[0].balance == D("1")


def test_another_product_does_not_leak_into_the_balance(
    service: StockMovementService, make_product: ProductFactory
) -> None:
    a, b = make_product(), make_product()
    _register(service, a, "IN", "5")
    _register(service, b, "IN", "100")
    _register(service, a, "OUT", "2")
    _register(service, b, "OUT", "30")
    _register(service, a, "IN", "1")

    history_a, history_b = service.history(a.id), service.history(b.id)

    assert [row.balance for row in history_a.entries] == [D("4"), D("3"), D("5")]
    assert [row.balance for row in history_b.entries] == [D("70"), D("100")]
    assert (history_a.total, history_b.total) == (3, 2)
    assert {row.movement.product_id for row in history_a.entries} == {a.id}


# --- casos de borde ---


def test_an_empty_history_is_valid(service: StockMovementService, product: Product) -> None:
    history = service.history(product.id)

    assert history.entries == ()
    assert (history.total, history.limit, history.truncated) == (0, HISTORY_LIMIT, False)
    assert history.product.id == product.id


def test_an_inactive_product_keeps_a_readable_history(
    service: StockMovementService, session: Session, product: Product
) -> None:
    _register(service, product, "IN", "3")
    product.is_active = False
    session.commit()

    history = service.history(product.id)

    assert history.product.is_active is False
    assert [row.balance for row in history.entries] == [D("3")]


def test_history_of_an_unknown_product_raises_not_found(service: StockMovementService) -> None:
    with pytest.raises(ProductNotFoundError):
        service.history(999)


# --- límite de 200 ---


def test_the_limit_is_200() -> None:
    assert HISTORY_LIMIT == 200


def test_only_the_last_200_are_returned_and_their_balance_covers_the_whole_history(
    service: StockMovementService, session: Session, product: Product
) -> None:
    rows: list[Row] = [
        ("OUT", "0.125") if n % 7 == 6 else ("IN", str(D("0.125") * (n % 5 + 1))) for n in range(250)
    ]
    _seed(session, product, rows)
    expected = _expected_balances(rows)

    history = service.history(product.id)

    assert len(history.entries) == 200
    assert (history.total, history.limit, history.truncated) == (250, 200, True)
    # Las filas mostradas son las 200 más recientes, con el saldo del historial completo.
    assert [row.balance for row in history.entries] == list(reversed(expected[50:]))
    assert history.entries[0].balance == service.current_stock(product.id)
    # La fila más antigua mostrada es la 51ª: su saldo arrastra las 50 anteriores.
    oldest = history.entries[-1]
    assert oldest.balance == expected[50] != oldest.signed_quantity


@pytest.mark.parametrize(
    "count,shown,truncated", [(0, 0, False), (1, 1, False), (199, 199, False), (200, 200, False), (201, 200, True)]
)
def test_the_notice_appears_only_above_200(
    service: StockMovementService,
    session: Session,
    product: Product,
    count: int,
    shown: int,
    truncated: bool,
) -> None:
    _seed(session, product, [("IN", "1")] * count)

    history = service.history(product.id)

    assert (len(history.entries), history.total, history.truncated) == (shown, count, truncated)


# --- una sola consulta (sin N+1) ---


def test_history_runs_the_same_number_of_statements_whatever_its_size(
    service: StockMovementService, session: Session, engine: Engine, make_product: ProductFactory
) -> None:
    def statements_for(product_id: int) -> int:
        seen: list[str] = []
        listener = lambda _c, _cur, stmt, *_a: seen.append(stmt)  # noqa: E731
        event.listen(engine, "before_cursor_execute", listener)
        try:
            service.history(product_id)
        finally:
            event.remove(engine, "before_cursor_execute", listener)
        return len(seen)

    few, many = make_product(), make_product()
    _seed(session, few, [("IN", "1")] * 3)
    _seed(session, many, [("IN", "1")] * 150)

    assert statements_for(few.id) == statements_for(many.id)
    assert statements_for(many.id) <= 2  # producto (si no está en la sesión) + historial
