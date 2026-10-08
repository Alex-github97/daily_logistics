"""Tabla de historial de cambios de estado para entidades WMS

Revision ID: 005
Revises: 004
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa

revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'wms_historial_estado',
        sa.Column('id',              sa.Integer(),     primary_key=True),
        sa.Column('entidad_tipo',    sa.String(30),    nullable=False, index=True),
        sa.Column('entidad_id',      sa.Integer(),     nullable=False, index=True),
        sa.Column('estado_anterior', sa.String(30),    nullable=True),
        sa.Column('estado_nuevo',    sa.String(30),    nullable=False),
        sa.Column('tipo_cambio',     sa.String(20),    nullable=False, server_default='AVANCE'),
        sa.Column('observacion',     sa.Text(),        nullable=True),
        sa.Column('usuario_id',      sa.Integer(),     sa.ForeignKey('usuarios.id', ondelete='SET NULL'), nullable=True),
        sa.Column('fecha',           sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )


def downgrade():
    op.drop_table('wms_historial_estado')
