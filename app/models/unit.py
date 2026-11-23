from enum import StrEnum


class Unit(StrEnum):
    """Unidad de medida del producto (RN17)."""

    UN = "UN"
    KG = "KG"
    M = "M"
    L = "L"

    @property
    def allows_decimals(self) -> bool:
        """RN18: UN solo admite enteros; el resto, hasta 3 decimales."""
        return self is not Unit.UN
