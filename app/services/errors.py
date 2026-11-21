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
