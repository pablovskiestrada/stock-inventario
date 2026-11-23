from decimal import Decimal

import pytest

from app.services.errors import InvalidPriceError
from app.services.money import validate_price


@pytest.mark.parametrize(
    "value,expected",
    [
        (Decimal("0"), "0.00"),
        (Decimal("19.9"), "19.90"),
        (Decimal("9999999999.99"), "9999999999.99"),
        (7, "7.00"),  # un entero es un importe exacto
    ],
)
def test_valid_prices_come_back_with_two_decimals(value: Decimal | int, expected: str) -> None:
    assert str(validate_price(value, "El precio")) == expected


@pytest.mark.parametrize(
    "value",
    [
        Decimal("-0.01"),
        Decimal("1.005"),
        Decimal("10000000000"),
        Decimal("NaN"),
        Decimal("Infinity"),
        1.5,  # nunca float
        True,
        "10.00",
        None,
    ],
)
def test_invalid_prices_are_rejected_with_the_given_label(value: object) -> None:
    with pytest.raises(InvalidPriceError, match="^El precio unitario debe ser un importe"):
        validate_price(value, "El precio unitario")  # type: ignore[arg-type]
