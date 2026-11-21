"""create categories

Revision ID: 65799495deb7
Revises: 
Create Date: 2026-11-21 10:27:58.933198

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '65799495deb7'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('categories',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint('length(trim(name)) > 0', name=op.f('ck_categories_name_not_blank')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_categories'))
    )
    # Autogenerate no detecta índices funcionales en SQLite: se declara a mano (RN11).
    op.create_index(
        'uq_categories_name_lower', 'categories', [sa.literal_column('lower(name)')], unique=True
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_categories_name_lower', table_name='categories')
    op.drop_table('categories')
