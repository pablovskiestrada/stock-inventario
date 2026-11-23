from decimal import Decimal

import pytest

from app.templating import format_quantity


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        (Decimal("5.000"), "UN", "5"),
        (Decimal("0.000"), "UN", "0"),
        (Decimal("1.500"), "KG", "1.5"),
        (Decimal("2.000"), "M", "2"),
        (Decimal("0.001"), "L", "0.001"),
        (Decimal("10.250"), "KG", "10.25"),
        (Decimal("100.000"), "KG", "100"),  # no se recortan los ceros enteros
    ],
)
def test_format_quantity(value: Decimal, unit: str, expected: str) -> None:
    assert format_quantity(value, unit) == expected
