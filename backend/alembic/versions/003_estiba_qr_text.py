"""ampliar codigo_qr de VARCHAR(500) a TEXT

Revision ID: 003
Revises: 002
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa


revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        'estibas', 'codigo_qr',
        type_=sa.Text(),
        existing_nullable=True,
    )
    # Eliminar el índice único anterior (era sobre VARCHAR(500))
    op.drop_index('ix_estibas_codigo_qr', table_name='estibas', if_exists=True)
    op.create_unique_constraint('uq_estibas_codigo_qr', 'estibas', ['codigo_qr'])


def downgrade():
    op.drop_constraint('uq_estibas_codigo_qr', 'estibas', type_='unique')
    op.alter_column(
        'estibas', 'codigo_qr',
        type_=sa.String(500),
        existing_nullable=True,
    )
    op.create_index('ix_estibas_codigo_qr', 'estibas', ['codigo_qr'], unique=True)
