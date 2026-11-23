from enum import StrEnum


class MovementType(StrEnum):
    """Tipo de movimiento de stock (RN21)."""

    IN = "IN"
    OUT = "OUT"
    ADJUSTMENT = "ADJUSTMENT"


class AdjustmentReason(StrEnum):
    """Motivo de un ajuste (RN23). Lista fija; solo aplica a `ADJUSTMENT`."""

    ROTURA = "ROTURA"
    MERMA = "MERMA"
    CONTEO = "CONTEO"
    ERROR_CARGA = "ERROR_CARGA"
    OTRO = "OTRO"
