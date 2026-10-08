"""Alertas de faltantes de manifiesto y stock mínimo por bodega

Revision ID: 006
Revises: 005
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa

revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade():
    # Los ALTER TYPE deben ejecutarse fuera de una transacción activa en Postgres.
    # Si se aplica manualmente via psql, usar los comandos del bloque SQL al final.
    op.execute("ALTER TYPE estadoestiba ADD VALUE IF NOT EXISTS 'FALTANTE'")
    op.execute("ALTER TYPE tipoalerta ADD VALUE IF NOT EXISTS 'ESTIBA_FALTANTE'")
    op.execute("ALTER TYPE tipoalerta ADD VALUE IF NOT EXISTS 'STOCK_BAJO'")

    op.create_table(
        'estiba_stock_minimo',
        sa.Column('id',              sa.Integer(),     primary_key=True),
        sa.Column('ubicacion_id',    sa.Integer(),     sa.ForeignKey('ubicaciones.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tipo_estiba',     sa.String(20),    nullable=False),
        sa.Column('cantidad_minima', sa.Integer(),     nullable=False),
        sa.Column('activo',          sa.Boolean(),     nullable=False, server_default='true'),
        sa.Column('created_at',      sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at',      sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.UniqueConstraint('ubicacion_id', 'tipo_estiba', name='uq_stock_minimo_ubicacion_tipo'),
    )


def downgrade():
    op.drop_table('estiba_stock_minimo')
    # No se puede eliminar valores de un enum en Postgres sin recrearlo.
