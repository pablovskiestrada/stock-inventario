from decimal import Decimal

import pytest

from app.models.unit import Unit
from app.services.errors import InvalidQuantityError, InvalidUnitError
from app.services.quantity import THOUSANDS_MESSAGE, parse_quantity_input, validate_quantity


def test_un_rejects_decimals() -> None:
    with pytest.raises(InvalidQuantityError, match="UN solo admite cantidades enteras"):
        validate_quantity("UN", Decimal("1.5"))


def test_un_accepts_integers() -> None:
    assert validate_quantity("UN", Decimal("2")) == Decimal("2.000")
    assert validate_quantity("UN", Decimal("2.0")) == Decimal("2")  # 2.0 sigue siendo entero
    assert validate_quantity("UN", 0) == Decimal("0")


@pytest.mark.parametrize("unit", ["KG", "M", "L", Unit.KG])
def test_decimal_units_accept_up_to_three_decimals(unit: str) -> None:
    assert validate_quantity(unit, Decimal("1.5")) == Decimal("1.500")
    assert validate_quantity(unit, Decimal("0.001")) == Decimal("0.001")


@pytest.mark.parametrize("unit", ["UN", "KG", "M", "L"])
def test_rejects_more_than_three_decimals(unit: str) -> None:
    with pytest.raises(InvalidQuantityError, match="hasta 3 decimales"):
        validate_quantity(unit, Decimal("0.0001"))


@pytest.mark.parametrize("value", [Decimal("-1"), Decimal("-0.001")])
def test_rejects_negative_values(value: Decimal) -> None:
    with pytest.raises(InvalidQuantityError, match="mayor o igual a 0"):
        validate_quantity("KG", value)


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_rejects_non_finite_values(value: Decimal) -> None:
    with pytest.raises(InvalidQuantityError):
        validate_quantity("KG", value)


@pytest.mark.parametrize("value", [1.5, True, "1.5"])
def test_rejects_float_bool_and_str(value: object) -> None:
    with pytest.raises(InvalidQuantityError):
        validate_quantity("KG", value)  # type: ignore[arg-type]


def test_rejects_values_above_the_cap() -> None:
    assert validate_quantity("KG", Decimal("999999999.999")) == Decimal("999999999.999")
    with pytest.raises(InvalidQuantityError, match="demasiado grande"):
        validate_quantity("KG", Decimal("1000000000"))


def test_rejects_unknown_unit() -> None:
    with pytest.raises(InvalidUnitError):
        validate_quantity("XX", Decimal("1"))


# --- RN20: entrada de texto ---


@pytest.mark.parametrize("raw", ["1,5", "1.5", " 1,5 ", "1.50"])
def test_single_separator_is_the_decimal(raw: str) -> None:
    assert parse_quantity_input(raw) == Decimal("1.5")


def test_single_separator_with_three_digits_is_still_decimal() -> None:
    assert parse_quantity_input("1.500") == Decimal("1.5")
    assert parse_quantity_input("1,500") == Decimal("1.5")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("5", "5"),
        ("0", "0"),
        ("0,001", "0.001"),
        (",5", "0.5"),
        (".5", "0.5"),
        ("5,", "5"),
        ("-1", "-1"),  # el signo se rechaza después, en validate_quantity
    ],
)
def test_parses_other_valid_shapes(raw: str, expected: str) -> None:
    assert parse_quantity_input(raw) == Decimal(expected)


def test_empty_is_zero() -> None:
    assert parse_quantity_input("") == Decimal("0")
    assert parse_quantity_input("   ") == Decimal("0")


@pytest.mark.parametrize("raw", ["1.500,5", "1,500.5", "1.2.3", "1,2,3", "1.000.000"])
def test_more_than_one_separator_is_rejected_with_a_clear_message(raw: str) -> None:
    with pytest.raises(InvalidQuantityError) as error:
        parse_quantity_input(raw)

    assert str(error.value) == THOUSANDS_MESSAGE


@pytest.mark.parametrize("raw", ["abc", "1e3", "NaN", "Infinity", "1_000", "١٢", "1 5", "--1", "."])
def test_rejects_non_numeric_text(raw: str) -> None:
    with pytest.raises(InvalidQuantityError, match="no es un número válido"):
        parse_quantity_input(raw)
