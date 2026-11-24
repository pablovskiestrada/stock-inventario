from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

import app.templating as templating
from app.templating import format_local_datetime, format_quantity, format_signed_quantity, to_local

# Zonas fijas (sin tzdata): los tests de fechas no dependen de la zona de la máquina.
ART = timezone(timedelta(hours=-3))
CET = timezone(timedelta(hours=1))


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


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        (Decimal("1.500"), "KG", "+1.5"),
        (Decimal("-3.000"), "KG", "-3"),
        (Decimal("4.000"), "UN", "+4"),
        (Decimal("-4.000"), "UN", "-4"),
        (Decimal("0.001"), "L", "+0.001"),
        (Decimal("-0.125"), "M", "-0.125"),
    ],
)
def test_format_signed_quantity_marks_positive_values_and_keeps_the_minus(
    value: Decimal, unit: str, expected: str
) -> None:
    assert format_signed_quantity(value, unit) == expected


# --- fechas (RN32): SQLite devuelve datetimes sin zona, y son UTC ---


def test_to_local_treats_a_naive_datetime_as_utc() -> None:
    naive = datetime(2026, 11, 23, 17, 5)

    local = to_local(naive, ART)

    assert (local.year, local.month, local.day, local.hour, local.minute) == (2026, 11, 23, 14, 5)
    assert local.utcoffset() == timedelta(hours=-3)
    assert local == to_local(naive.replace(tzinfo=UTC), ART)  # igual que declararlo UTC


def test_to_local_converts_an_aware_datetime_from_another_zone() -> None:
    aware = datetime(2026, 11, 23, 15, 5, tzinfo=CET)  # 14:05 UTC

    assert to_local(aware, ART).hour == 11


def test_to_local_can_cross_the_date_line() -> None:
    local = to_local(datetime(2026, 11, 24, 2, 30), ART)

    assert (local.day, local.hour, local.minute) == (23, 23, 30)


def test_to_local_without_a_zone_keeps_the_same_instant_in_the_system_zone() -> None:
    naive = datetime(2026, 11, 23, 17, 5)

    local = to_local(naive)

    assert local.tzinfo is not None
    assert local == naive.replace(tzinfo=UTC)  # mismo instante, cualquiera sea la zona de la máquina


def test_format_local_datetime_uses_the_display_zone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(templating, "DISPLAY_TZ", ART)

    assert format_local_datetime(datetime(2026, 11, 23, 17, 5, 59)) == "23/11/2026 14:05"
    assert format_local_datetime(datetime(2026, 11, 24, 2, 30)) == "23/11/2026 23:30"
    assert format_local_datetime(datetime(2026, 1, 5, 9, 0, tzinfo=UTC)) == "05/01/2026 06:00"
