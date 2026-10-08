"""Catálogos de países y ciudades para WMS

Revision ID: 007
Revises: 006
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa

revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'wms_paises',
        sa.Column('id',         sa.Integer(),    primary_key=True),
        sa.Column('nombre',     sa.String(100),  nullable=False, unique=True),
        sa.Column('codigo_iso', sa.String(5),    nullable=True),
        sa.Column('activo',     sa.Boolean(),    nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('ix_wms_paises_id', 'wms_paises', ['id'])

    op.create_table(
        'wms_ciudades',
        sa.Column('id',         sa.Integer(),    primary_key=True),
        sa.Column('nombre',     sa.String(100),  nullable=False),
        sa.Column('pais_id',    sa.Integer(),    sa.ForeignKey('wms_paises.id'), nullable=False),
        sa.Column('activo',     sa.Boolean(),    nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('ix_wms_ciudades_id', 'wms_ciudades', ['id'])


def downgrade():
    op.drop_index('ix_wms_ciudades_id', 'wms_ciudades')
    op.drop_table('wms_ciudades')
    op.drop_index('ix_wms_paises_id', 'wms_paises')
    op.drop_table('wms_paises')
