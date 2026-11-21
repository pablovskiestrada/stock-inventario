# CLAUDE.md: contexto del proyecto

Leer `SPEC.md` antes de cualquier tarea. Es la fuente de verdad del dominio, las reglas de negocio y el glosario.

## Stack
- Python 3.12, FastAPI, SQLAlchemy 2.x (estilo tipado), Alembic, Pydantic v2
- SQLite en desarrollo (compatible con PostgreSQL)
- Jinja2 + HTMX para la UI
- pytest para tests

## Estructura de carpetas
```
app/
  main.py            # creación de la app y routers
  config.py          # settings desde variables de entorno
  db.py              # engine, sesión, Base
  models/            # modelos SQLAlchemy (uno por entidad)
  schemas/           # esquemas Pydantic (entrada/salida)
  repositories/      # acceso a datos (único lugar con queries)
  services/          # lógica de negocio y reglas (RN*)
  routers/           # endpoints HTTP y vistas; sin lógica de negocio
  templates/         # Jinja2
  static/
migrations/          # Alembic
tests/
  unit/              # servicios con DB en memoria
  api/               # endpoints
SPEC.md
CLAUDE.md
```

## Arquitectura y reglas de capas
- routers -> services -> repositories -> models. Nunca saltear capas.
- Las reglas de negocio (RN1..RN10) viven SOLO en `services/`.
- Ningún SQL ni uso de sesión fuera de `repositories/`.
- Los routers validan con schemas Pydantic y traducen excepciones de dominio a HTTP.
- Excepciones de dominio propias (`DomainError`, `InsufficientStockError`, etc.), no `HTTPException` en services.

## Base de datos
- Todo cambio de esquema va con migración Alembic. Nunca `create_all` en código de aplicación.
- Restricciones en la base (PK, FK, NOT NULL, UNIQUE, CHECK), no solo en código.
- Todas las tablas tienen `created_at` y `updated_at`.
- Dinero: `Numeric(12, 2)` / `Decimal`. Nunca float.
- Nombres de tablas en inglés, plural y snake_case (`products`, `stock_movements`).

## Convenciones de código
- Nombres en inglés, siguiendo el glosario del SPEC. UI en español.
- Type hints en todo. Funciones cortas, una responsabilidad.
- Sin dependencias nuevas sin avisar y justificar.
- Secretos y configuración en variables de entorno (`.env` fuera del repo).

## Forma de trabajo
- Una rebanada vertical por vez, según el plan del SPEC. No adelantar funcionalidades.
- Antes de codear una tarea no trivial: mostrar el plan y esperar OK.
- Cada regla de negocio nueva lleva su test. Correr `pytest` antes de dar algo por terminado.
- Commits chicos, un cambio lógico por commit.
- Si algo del SPEC es ambiguo o hay que cambiarlo, preguntar y actualizar el SPEC en el mismo cambio.

## Comandos
- Instalar: `pip install -r requirements.txt`
- Migrar: `alembic upgrade head`
- Correr: `uvicorn app.main:app --reload`
- Tests: `pytest`
