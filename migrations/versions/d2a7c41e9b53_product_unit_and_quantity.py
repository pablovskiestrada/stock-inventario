"""product unit and quantity

Agrega `products.unit` (RN17) y convierte `products.min_stock` a milésimas enteras (RN19).

Revision ID: d2a7c41e9b53
Revises: 8e0b61370e55
Create Date: 2026-11-23 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2a7c41e9b53'
down_revision: Union[str, Sequence[str], None] = '8e0b61370e55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

QUANTITY_FACTOR = 1000  # milésimas por unidad
SKU_LOWER_INDEX = 'uq_products_sku_lower'


def _create_sku_lower_index() -> None:
    # Autogenerate no detecta índices funcionales en SQLite y el batch no los refleja:
    # se suelta antes y se recrea después de cada batch (RN1).
    op.create_index(
        SKU_LOWER_INDEX, 'products', [sa.literal_column('lower(sku)')], unique=True
    )


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index(SKU_LOWER_INDEX, table_name='products')
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('unit', sa.String(length=5), server_default=sa.text("'UN'"), nullable=False)
        )
        batch_op.create_check_constraint(
            op.f('ck_products_unit_valid'), "unit IN ('UN', 'KG', 'M', 'L')"
        )
        batch_op.alter_column(
            'min_stock',
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            existing_nullable=False,
            existing_server_default=sa.text('0'),
        )
    # Los valores existentes pasan de unidades enteras a milésimas (5 -> 5000).
    op.execute(sa.text(f'UPDATE products SET min_stock = min_stock * {QUANTITY_FACTOR}'))
    _create_sku_lower_index()


def downgrade() -> None:
    """Downgrade schema.

    Se pierde la unidad de medida (la columna `unit` se elimina). Si algún producto tiene un
    `min_stock` con decimales no se puede volver a entero sin perder datos: el downgrade
    aborta antes de tocar nada y lista los SKU afectados.
    """
    if not context.is_offline_mode():
        fractional = op.get_bind().execute(
            sa.text(f'SELECT sku FROM products WHERE min_stock % {QUANTITY_FACTOR} != 0 ORDER BY sku')
        ).scalars().all()
        if fractional:
            raise RuntimeError(
                'No se puede volver a min_stock entero sin perder datos: '
                f'estos productos tienen stock mínimo con decimales: {", ".join(fractional)}. '
                'Corregilos (o ajustalos a un entero) y reintentá.'
            )
    op.drop_index(SKU_LOWER_INDEX, table_name='products')
    op.execute(sa.text(f'UPDATE products SET min_stock = min_stock / {QUANTITY_FACTOR}'))
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_constraint(op.f('ck_products_unit_valid'), type_='check')
        batch_op.drop_column('unit')
        batch_op.alter_column(
            'min_stock',
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            existing_nullable=False,
            existing_server_default=sa.text('0'),
        )
    _create_sku_lower_index()
