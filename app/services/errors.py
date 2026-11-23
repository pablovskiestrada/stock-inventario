class DomainError(Exception):
    """Base de las excepciones de dominio. Los routers las traducen a HTTP."""


class CategoryNotFoundError(DomainError):
    def __init__(self, category_id: int) -> None:
        super().__init__(f"La categoría {category_id} no existe.")
        self.category_id = category_id


class CategoryNameRequiredError(DomainError):
    def __init__(self) -> None:
        super().__init__("El nombre de la categoría es obligatorio.")


class DuplicateCategoryNameError(DomainError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Ya existe una categoría llamada «{name}».")
        self.name = name


class CategoryInUseError(DomainError):
    def __init__(self, category_id: int) -> None:
        super().__init__("No se puede eliminar una categoría que tiene productos.")
        self.category_id = category_id


class ProductNotFoundError(DomainError):
    def __init__(self, product_id: int) -> None:
        super().__init__(f"El producto {product_id} no existe.")
        self.product_id = product_id


class ProductSkuRequiredError(DomainError):
    def __init__(self) -> None:
        super().__init__("El SKU es obligatorio.")


class ProductNameRequiredError(DomainError):
    def __init__(self) -> None:
        super().__init__("El nombre del producto es obligatorio.")


class ProductFieldTooLongError(DomainError):
    def __init__(self, label: str, max_length: int) -> None:
        super().__init__(f"{label} no puede superar los {max_length} caracteres.")
        self.max_length = max_length


class DuplicateSkuError(DomainError):
    def __init__(self, sku: str) -> None:
        super().__init__(f"Ya existe un producto con el SKU «{sku}».")
        self.sku = sku


class InvalidProductCategoryError(DomainError):
    def __init__(self, category_id: int) -> None:
        super().__init__(f"La categoría {category_id} no existe.")
        self.category_id = category_id


class InvalidPriceError(DomainError):
    def __init__(self, label: str) -> None:
        super().__init__(f"{label} debe ser un importe mayor o igual a 0, con hasta 2 decimales.")


class InvalidMinStockError(DomainError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"El stock mínimo no es válido. {reason}")
        self.reason = reason


class InvalidUnitError(DomainError):
    def __init__(self, unit: object) -> None:
        super().__init__(f"La unidad «{unit}» no es válida. Usá UN, KG, M o L.")
        self.unit = unit


class InvalidQuantityError(DomainError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
