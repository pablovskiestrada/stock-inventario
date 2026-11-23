"""create stock movements

Crea `stock_movements`, el libro mayor inmutable del stock (RN5, RN21 a RN23).
Escrita a mano: los tipos y motivos van como literales congelados, sin importar
enums de la aplicación. No usa batch ni toca `categories` ni `products`.

Revision ID: a3f9c2d17b64
Revises: d2a7c41e9b53
Create Date: 2026-11-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f9c2d17b64'
down_revision: Union[str, Sequence[str], None] = 'd2a7c41e9b53'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('stock_movements',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('type', sa.String(length=10), nullable=False),
    sa.Column('quantity', sa.BigInteger(), nullable=False),
    sa.Column('unit_price', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('reason', sa.String(length=20), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('reference', sa.String(length=100), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint("type IN ('IN', 'OUT', 'ADJUSTMENT')", name=op.f('ck_stock_movements_type_valid')),
    sa.CheckConstraint("(type = 'ADJUSTMENT' AND quantity <> 0) OR (type <> 'ADJUSTMENT' AND quantity > 0)", name=op.f('ck_stock_movements_quantity_sign_by_type')),
    sa.CheckConstraint('unit_price IS NULL OR unit_price >= 0', name=op.f('ck_stock_movements_unit_price_non_negative')),
    sa.CheckConstraint("(type = 'ADJUSTMENT' AND unit_price IS NULL) OR (type <> 'ADJUSTMENT' AND unit_price IS NOT NULL)", name=op.f('ck_stock_movements_unit_price_by_type')),
    sa.CheckConstraint("(type = 'ADJUSTMENT' AND reason IS NOT NULL AND reason IN ('ROTURA', 'MERMA', 'CONTEO', 'ERROR_CARGA', 'OTRO')) OR (type <> 'ADJUSTMENT' AND reason IS NULL)", name=op.f('ck_stock_movements_reason_by_type')),
    sa.CheckConstraint("reason IS NULL OR reason <> 'OTRO' OR (note IS NOT NULL AND length(trim(note)) > 0)", name=op.f('ck_stock_movements_note_required_for_other')),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_stock_movements_product_id_products')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_stock_movements'))
    )
    op.create_index(op.f('ix_stock_movements_product_id'), 'stock_movements', ['product_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema.

    Borrar la tabla destruye el libro mayor: si tiene movimientos el downgrade aborta
    antes de tocar nada y dice cuántos son.
    """
    if not context.is_offline_mode():
        count = op.get_bind().execute(sa.text('SELECT COUNT(*) FROM stock_movements')).scalar_one()
        if count:
            raise RuntimeError(
                f'No se puede borrar stock_movements: tiene {count} movimiento(s) y se perderían '
                'datos. Los movimientos son inmutables (RN5); exportalos o conservá la tabla.'
            )
    op.drop_index(op.f('ix_stock_movements_product_id'), table_name='stock_movements')
    op.drop_table('stock_movements')
