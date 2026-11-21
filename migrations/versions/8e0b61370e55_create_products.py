"""create products

Revision ID: 8e0b61370e55
Revises: 65799495deb7
Create Date: 2026-11-21 15:48:32.904498

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8e0b61370e55'
down_revision: Union[str, Sequence[str], None] = '65799495deb7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('products',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('sku', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.Column('cost_price', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('sale_price', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('min_stock', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint('cost_price >= 0', name=op.f('ck_products_cost_price_non_negative')),
    sa.CheckConstraint('length(trim(name)) > 0', name=op.f('ck_products_name_not_blank')),
    sa.CheckConstraint('length(trim(sku)) > 0', name=op.f('ck_products_sku_not_blank')),
    sa.CheckConstraint('min_stock >= 0', name=op.f('ck_products_min_stock_non_negative')),
    sa.CheckConstraint('sale_price >= 0', name=op.f('ck_products_sale_price_non_negative')),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], name=op.f('fk_products_category_id_categories')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_products'))
    )
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_products_category_id'), ['category_id'], unique=False)

    # Autogenerate no detecta índices funcionales en SQLite: se declara a mano (RN1).
    op.create_index(
        'uq_products_sku_lower', 'products', [sa.literal_column('lower(sku)')], unique=True
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_products_sku_lower', table_name='products')
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_products_category_id'))

    op.drop_table('products')
