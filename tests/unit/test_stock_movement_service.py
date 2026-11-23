from collections.abc import Callable, Iterator
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import Engine, event, text
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.product import Product
from app.models.stock_movement import StockMovement
from app.repositories.product_repository import ProductRepository
from app.repositories.stock_movement_repository import StockMovementRepository
from app.services.errors import (
    AdjustmentReasonRequiredError,
    DomainError,
    InactiveProductError,
    InsufficientStockError,
    InvalidAdjustmentReasonError,
    InvalidMovementTypeError,
    InvalidPriceError,
    InvalidQuantityError,
    MovementFieldTooLongError,
    NoteRequiredError,
    ProductNotFoundError,
    ReasonNotAllowedError,
    UnitPriceNotAllowedError,
    UnitPriceRequiredError,
)
from app.services.stock_movement_service import StockMovementService

D = Decimal
ProductFactory = Callable[..., Product]


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


def _in(service: StockMovementService, product: Product, quantity: str, **kw: Any) -> StockMovement:
    kw.setdefault("unit_price", D("10.00"))
    return service.register_movement(
        product_id=product.id, type="IN", quantity=D(quantity), **kw
    )


def _out(service: StockMovementService, product: Product, quantity: str, **kw: Any) -> StockMovement:
    kw.setdefault("unit_price", D("20.00"))
    return service.register_movement(
        product_id=product.id, type="OUT", quantity=D(quantity), **kw
    )


def _adjust(
    service: StockMovementService, product: Product, quantity: str, **kw: Any
) -> StockMovement:
    kw.setdefault("reason", "CONTEO")
    return service.register_movement(
        product_id=product.id, type="ADJUSTMENT", quantity=D(quantity), **kw
    )


def _movement_count(session: Session) -> int:
    return session.execute(text("SELECT COUNT(*) FROM stock_movements")).scalar_one()


# --- RN2 y RN4: stock calculado y nunca negativo ---


def test_stock_of_a_product_without_movements_is_zero(
    service: StockMovementService, product: Product
) -> None:
    assert service.current_stock(product.id) == 0


def test_stock_is_in_minus_out_plus_signed_adjustments(
    service: StockMovementService, product: Product
) -> None:
    _in(service, product, "10")
    _out(service, product, "3.5")
    _adjust(service, product, "-1")
    _adjust(service, product, "0.25")
    assert service.current_stock(product.id) == D("5.750")


def test_stock_only_counts_the_movements_of_its_own_product(
    service: StockMovementService, make_product: ProductFactory
) -> None:
    a, b = make_product(), make_product()
    _in(service, a, "7")
    _in(service, b, "2")
    assert (service.current_stock(a.id), service.current_stock(b.id)) == (D("7"), D("2"))


def test_an_out_of_exactly_the_available_stock_is_valid(
    service: StockMovementService, product: Product
) -> None:
    _in(service, product, "5")
    _out(service, product, "5")
    assert service.current_stock(product.id) == 0


def test_an_out_one_thousandth_over_the_available_stock_is_rejected(
    service: StockMovementService, session: Session, product: Product
) -> None:
    _in(service, product, "5")
    with pytest.raises(InsufficientStockError, match="hay 5 KG y el movimiento resta 5.001 KG"):
        _out(service, product, "5.001")
    assert service.current_stock(product.id) == D("5")
    assert _movement_count(session) == 1  # no quedó ningún movimiento a medias


def test_an_out_without_any_stock_is_rejected(
    service: StockMovementService, product: Product
) -> None:
    with pytest.raises(InsufficientStockError):
        _out(service, product, "0.001")


def test_a_negative_adjustment_that_leaves_the_stock_negative_is_rejected(
    service: StockMovementService, session: Session, product: Product
) -> None:
    _in(service, product, "2")
    with pytest.raises(InsufficientStockError):
        _adjust(service, product, "-2.001")
    assert service.current_stock(product.id) == D("2")
    assert _movement_count(session) == 1


def test_a_negative_adjustment_down_to_exactly_zero_is_valid(
    service: StockMovementService, product: Product
) -> None:
    _in(service, product, "2")
    _adjust(service, product, "-2")
    assert service.current_stock(product.id) == 0


def test_a_positive_adjustment_works_with_no_prior_stock(
    service: StockMovementService, product: Product
) -> None:
    _adjust(service, product, "3", reason="ERROR_CARGA")
    assert service.current_stock(product.id) == D("3")


def test_exact_decimal_arithmetic_against_the_database(
    service: StockMovementService, session: Session, product: Product
) -> None:
    """1,3 + 0,2 - 1,5 = 0 exacto: la suma se hace en SQL sobre milésimas enteras."""
    _in(service, product, "1.3")
    _in(service, product, "0.2")
    _out(service, product, "1.5")  # exacto al disponible: válido

    raw = session.execute(
        text(
            "SELECT SUM(CASE type WHEN 'IN' THEN quantity WHEN 'OUT' THEN -quantity "
            "ELSE quantity END) FROM stock_movements"
        )
    ).scalar_one()
    assert raw == 0 and isinstance(raw, int)
    assert service.current_stock(product.id) == 0


# --- RN3 y RN18: cantidades ---


@pytest.mark.parametrize("quantity", ["0", "-1", "-0.001"])
@pytest.mark.parametrize("kind", ["IN", "OUT"])
def test_in_and_out_need_a_quantity_greater_than_zero(
    service: StockMovementService, product: Product, kind: str, quantity: str
) -> None:
    _in(service, product, "10")
    with pytest.raises(InvalidQuantityError):
        service.register_movement(
            product_id=product.id, type=kind, quantity=D(quantity), unit_price=D("1")
        )


def test_an_adjustment_of_zero_is_rejected(
    service: StockMovementService, product: Product
) -> None:
    with pytest.raises(InvalidQuantityError, match="cantidad 0"):
        _adjust(service, product, "0")


@pytest.mark.parametrize("quantity", ["1.5", "-1.5", "0.001"])
def test_a_decimal_quantity_is_rejected_for_a_un_product(
    service: StockMovementService, make_product: ProductFactory, quantity: str
) -> None:
    un = make_product(unit="UN")
    _in(service, un, "10")
    with pytest.raises(InvalidQuantityError, match="UN solo admite cantidades enteras"):
        _adjust(service, un, quantity)
    with pytest.raises(InvalidQuantityError, match="UN solo admite cantidades enteras"):
        _in(service, un, quantity.lstrip("-"))
    with pytest.raises(InvalidQuantityError, match="UN solo admite cantidades enteras"):
        _out(service, un, quantity.lstrip("-"))


def test_a_un_product_accepts_whole_quantities(
    service: StockMovementService, make_product: ProductFactory
) -> None:
    un = make_product(unit="UN")
    _in(service, un, "10")
    _out(service, un, "4")
    _adjust(service, un, "-1")
    assert service.current_stock(un.id) == 5


@pytest.mark.parametrize("unit", ["KG", "M", "L"])
def test_decimal_units_accept_three_decimals(
    service: StockMovementService, make_product: ProductFactory, unit: str
) -> None:
    product = make_product(unit=unit)
    _in(service, product, "1.234")
    assert service.current_stock(product.id) == D("1.234")


@pytest.mark.parametrize(
    "quantity",
    ["0.0001", "-0.0001", "1.0000000000000000000000000001", "1000000000"],
)
def test_more_than_three_decimals_or_too_large_is_rejected(
    service: StockMovementService, product: Product, quantity: str
) -> None:
    with pytest.raises(InvalidQuantityError):
        _in(service, product, quantity)
    with pytest.raises(InvalidQuantityError):
        _adjust(service, product, quantity)


@pytest.mark.parametrize("quantity", [1.5, True, "1.5", None, D("NaN"), D("Infinity"), D("-Infinity")])
def test_non_exact_or_non_finite_quantities_are_rejected(
    service: StockMovementService, product: Product, quantity: Any
) -> None:
    for kind, extra in (("IN", {"unit_price": D("1")}), ("ADJUSTMENT", {"reason": "CONTEO"})):
        with pytest.raises(InvalidQuantityError):
            service.register_movement(
                product_id=product.id, type=kind, quantity=quantity, **extra
            )


def test_an_integer_quantity_is_accepted(
    service: StockMovementService, product: Product
) -> None:
    service.register_movement(product_id=product.id, type="IN", quantity=3, unit_price=D("1"))
    assert service.current_stock(product.id) == 3


# --- RN22: precio unitario ---


@pytest.mark.parametrize("kind", ["IN", "OUT"])
def test_in_and_out_require_a_unit_price(
    service: StockMovementService, product: Product, kind: str
) -> None:
    _in(service, product, "5")
    with pytest.raises(UnitPriceRequiredError):
        service.register_movement(product_id=product.id, type=kind, quantity=D("1"))


@pytest.mark.parametrize("price", [D("-0.01"), D("1.005"), D("NaN"), D("10000000000"), 1.5])
def test_an_invalid_unit_price_is_rejected(
    service: StockMovementService, product: Product, price: Any
) -> None:
    with pytest.raises(InvalidPriceError):
        _in(service, product, "1", unit_price=price)


def test_a_zero_unit_price_is_valid_in_in_and_out(
    service: StockMovementService, product: Product
) -> None:
    _in(service, product, "2", unit_price=D("0"))
    assert _out(service, product, "1", unit_price=D("0")).unit_price == D("0.00")


@pytest.mark.parametrize("price", [D("1.00"), D("0")])
def test_an_adjustment_with_a_unit_price_is_rejected_even_if_zero(
    service: StockMovementService, product: Product, price: Decimal
) -> None:
    with pytest.raises(UnitPriceNotAllowedError):
        _adjust(service, product, "1", unit_price=price)


def test_the_unit_price_is_stored_with_two_decimals(
    service: StockMovementService, product: Product
) -> None:
    assert _in(service, product, "1", unit_price=D("7.5")).unit_price == D("7.50")
    assert _adjust(service, product, "1").unit_price is None


def test_the_unit_price_is_a_snapshot_and_product_prices_are_untouched(
    service: StockMovementService, session: Session, product: Product
) -> None:
    movement = _in(service, product, "1", unit_price=D("99.99"))
    out = _out(service, product, "1", unit_price=D("1.11"))
    session.refresh(product)
    assert (product.cost_price, product.sale_price) == (D("10.00"), D("20.00"))  # no se tocaron

    product.cost_price, product.sale_price = D("50.00"), D("80.00")
    session.commit()
    session.refresh(movement)
    session.refresh(out)
    assert (movement.unit_price, out.unit_price) == (D("99.99"), D("1.11"))  # la foto no cambia


# --- RN23: motivo, nota y referencia ---


def test_an_adjustment_without_a_reason_is_rejected(
    service: StockMovementService, product: Product
) -> None:
    for reason in (None, "", "   "):
        with pytest.raises(AdjustmentReasonRequiredError):
            _adjust(service, product, "1", reason=reason)


@pytest.mark.parametrize("reason", ["XX", "rotura", "Merma"])
def test_an_adjustment_with_a_reason_outside_the_list_is_rejected(
    service: StockMovementService, product: Product, reason: str
) -> None:
    with pytest.raises(InvalidAdjustmentReasonError):
        _adjust(service, product, "1", reason=reason)


@pytest.mark.parametrize("reason", ["ROTURA", "MERMA", "CONTEO", "ERROR_CARGA"])
def test_every_listed_reason_is_valid_without_a_note(
    service: StockMovementService, product: Product, reason: str
) -> None:
    assert _adjust(service, product, "1", reason=reason).reason == reason


@pytest.mark.parametrize("reason", ["ROTURA", "OTRO", ""])
def test_in_and_out_cannot_carry_a_reason(
    service: StockMovementService, product: Product, reason: str
) -> None:
    _in(service, product, "5")
    with pytest.raises(ReasonNotAllowedError):
        _in(service, product, "1", reason=reason)
    with pytest.raises(ReasonNotAllowedError):
        _out(service, product, "1", reason=reason)


@pytest.mark.parametrize("note", [None, "", "   ", "\t\n"])
def test_reason_otro_without_a_note_is_rejected(
    service: StockMovementService, session: Session, product: Product, note: str | None
) -> None:
    with pytest.raises(NoteRequiredError):
        _adjust(service, product, "1", reason="OTRO", note=note)
    assert _movement_count(session) == 0


def test_reason_otro_with_a_note_is_valid_and_trimmed(
    service: StockMovementService, product: Product
) -> None:
    movement = _adjust(service, product, "1", reason="OTRO", note="  se cayó de la estantería ")
    assert (movement.reason, movement.note) == ("OTRO", "se cayó de la estantería")


def test_note_and_reference_are_optional_trimmed_and_empty_becomes_null(
    service: StockMovementService, product: Product
) -> None:
    plain = _in(service, product, "1")
    assert (plain.note, plain.reference) == (None, None)
    blank = _in(service, product, "1", note="   ", reference="")
    assert (blank.note, blank.reference) == (None, None)
    full = _in(service, product, "1", note=" lote 7 ", reference=" R-0001-123 ")
    assert (full.note, full.reference) == ("lote 7", "R-0001-123")


def test_note_and_reference_have_a_maximum_length(
    service: StockMovementService, product: Product
) -> None:
    ok = _in(service, product, "1", note="n" * 500, reference="r" * 100)
    assert (len(ok.note), len(ok.reference)) == (500, 100)
    with pytest.raises(MovementFieldTooLongError):
        _in(service, product, "1", note="n" * 501)
    with pytest.raises(MovementFieldTooLongError):
        _in(service, product, "1", reference="r" * 101)


def test_an_unknown_movement_type_is_rejected(
    service: StockMovementService, product: Product
) -> None:
    for kind in ("XX", "in", "", None):
        with pytest.raises(InvalidMovementTypeError):
            service.register_movement(
                product_id=product.id, type=kind, quantity=D("1"), unit_price=D("1")
            )


# --- RN7 y producto inexistente ---


def test_an_inactive_product_does_not_accept_movements(
    service: StockMovementService, session: Session, product: Product
) -> None:
    _in(service, product, "5")
    product.is_active = False
    session.commit()

    with pytest.raises(InactiveProductError):
        _in(service, product, "1")
    with pytest.raises(InactiveProductError):
        _out(service, product, "1")
    with pytest.raises(InactiveProductError):
        _adjust(service, product, "1")
    assert _movement_count(session) == 1
    assert service.current_stock(product.id) == D("5")  # el stock se sigue pudiendo consultar


def test_a_reactivated_product_accepts_movements_again(
    service: StockMovementService, session: Session, product: Product
) -> None:
    product.is_active = False
    session.commit()
    product.is_active = True
    session.commit()
    _in(service, product, "1")


def test_an_unknown_product_raises_not_found(service: StockMovementService) -> None:
    with pytest.raises(ProductNotFoundError):
        service.register_movement(product_id=999, type="IN", quantity=D("1"), unit_price=D("1"))
    with pytest.raises(ProductNotFoundError):
        service.current_stock(999)


# --- RN25: una sola transacción ---


@pytest.fixture
def commits(engine: Engine) -> Iterator[list[str]]:
    seen: list[str] = []
    event.listen(engine, "commit", lambda _conn: seen.append("commit"))
    yield seen  # el engine (y su listener) se descarta al terminar el test


def test_register_movement_commits_exactly_once(
    service: StockMovementService, product: Product, commits: list[str]
) -> None:
    commits.clear()
    _in(service, product, "5")
    assert commits == ["commit"]


def test_a_rejected_movement_commits_nothing(
    service: StockMovementService, session: Session, product: Product, commits: list[str]
) -> None:
    _in(service, product, "1")
    commits.clear()
    for attempt in (
        lambda: _out(service, product, "2"),  # RN4
        lambda: _in(service, product, "1", unit_price=None),  # RN22
        lambda: _adjust(service, product, "1", reason=None),  # RN23
        lambda: _in(service, product, "0"),  # RN3
    ):
        with pytest.raises(DomainError):  # cada una levanta un error de dominio distinto
            attempt()
    assert commits == []
    assert _movement_count(session) == 1


# --- RN24: consulta agrupada, sin N+1 ---


def test_stock_by_product_returns_each_product_and_zero_for_the_untouched(
    service: StockMovementService, make_product: ProductFactory
) -> None:
    a, b, c = make_product(), make_product(), make_product()
    _in(service, a, "4")
    _out(service, a, "1.5")
    _in(service, b, "2")

    stock = service.current_stock_by_product([a.id, b.id, c.id])

    assert stock == {a.id: D("2.5"), b.id: D("2"), c.id: D("0")}
    assert service.current_stock_by_product([]) == {}


def test_stock_for_a_whole_listing_takes_a_single_query_whatever_its_size(
    service: StockMovementService, engine: Engine, make_product: ProductFactory
) -> None:
    statements: list[str] = []
    event.listen(
        engine, "before_cursor_execute", lambda _c, _cur, stmt, *_a: statements.append(stmt)
    )

    def queries_for(count: int) -> int:
        products = [make_product() for _ in range(count)]
        for item in products:
            _in(service, item, "1")
        statements.clear()
        result = service.current_stock_by_product([p.id for p in products])
        assert len(result) == count and all(value == 1 for value in result.values())
        return len(statements)

    assert queries_for(1) == 1
    assert queries_for(20) == 1


# --- RN5: inmutabilidad ---


def test_there_is_no_way_to_update_or_delete_a_movement_in_the_repository_or_service() -> None:
    forbidden = ("update", "delete", "remove", "edit", "set_", "cancel", "void")
    for cls in (StockMovementRepository, StockMovementService):
        public = [name for name in dir(cls) if not name.startswith("_")]
        offenders = [name for name in public if name.startswith(forbidden)]
        assert offenders == [], f"{cls.__name__} expone {offenders}"
    assert not hasattr(StockMovement, "updated_at")
