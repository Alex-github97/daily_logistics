"""Tabla de historial de cambios de estado para manifiestos

Revision ID: 004
Revises: 003
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa

revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'manifiesto_historial',
        sa.Column('id',              sa.Integer(),     primary_key=True),
        sa.Column('manifiesto_id',   sa.Integer(),     sa.ForeignKey('manifiestos.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('estado_anterior', sa.String(30),    nullable=True),
        sa.Column('estado_nuevo',    sa.String(30),    nullable=False),
        sa.Column('tipo_cambio',     sa.String(20),    nullable=False, server_default='AVANCE'),
        sa.Column('observacion',     sa.Text(),        nullable=True),
        sa.Column('usuario_id',      sa.Integer(),     sa.ForeignKey('usuarios.id', ondelete='SET NULL'), nullable=True),
        sa.Column('fecha',           sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )


def downgrade():
    op.drop_table('manifiesto_historial')
