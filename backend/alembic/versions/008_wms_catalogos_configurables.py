"""Catálogos configurables WMS: tipos zona/ubicación, unidades medida, categorías y familias

Revision ID: 008
Revises: 007
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa

revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None

_ts = sa.DateTime(timezone=True)
_now = sa.text('NOW()')


def upgrade():
    op.create_table(
        'wms_tipos_zona',
        sa.Column('id',          sa.Integer(),    primary_key=True),
        sa.Column('nombre',      sa.String(60),   nullable=False, unique=True),
        sa.Column('descripcion', sa.String(255),  nullable=True),
        sa.Column('activo',      sa.Boolean(),    nullable=False, server_default='true'),
        sa.Column('created_at',  _ts, server_default=_now),
        sa.Column('updated_at',  _ts, server_default=_now),
    )
    op.create_index('ix_wms_tipos_zona_id', 'wms_tipos_zona', ['id'])

    op.create_table(
        'wms_tipos_ubicacion',
        sa.Column('id',          sa.Integer(),    primary_key=True),
        sa.Column('nombre',      sa.String(60),   nullable=False, unique=True),
        sa.Column('descripcion', sa.String(255),  nullable=True),
        sa.Column('activo',      sa.Boolean(),    nullable=False, server_default='true'),
        sa.Column('created_at',  _ts, server_default=_now),
        sa.Column('updated_at',  _ts, server_default=_now),
    )
    op.create_index('ix_wms_tipos_ubicacion_id', 'wms_tipos_ubicacion', ['id'])

    op.create_table(
        'wms_unidades_medida',
        sa.Column('id',          sa.Integer(),    primary_key=True),
        sa.Column('nombre',      sa.String(60),   nullable=False, unique=True),
        sa.Column('abreviatura', sa.String(15),   nullable=True),
        sa.Column('activo',      sa.Boolean(),    nullable=False, server_default='true'),
        sa.Column('created_at',  _ts, server_default=_now),
        sa.Column('updated_at',  _ts, server_default=_now),
    )
    op.create_index('ix_wms_unidades_medida_id', 'wms_unidades_medida', ['id'])

    op.create_table(
        'wms_categorias_producto',
        sa.Column('id',         sa.Integer(),    primary_key=True),
        sa.Column('nombre',     sa.String(100),  nullable=False, unique=True),
        sa.Column('activo',     sa.Boolean(),    nullable=False, server_default='true'),
        sa.Column('created_at', _ts, server_default=_now),
        sa.Column('updated_at', _ts, server_default=_now),
    )
    op.create_index('ix_wms_categorias_producto_id', 'wms_categorias_producto', ['id'])

    op.create_table(
        'wms_familias_producto',
        sa.Column('id',           sa.Integer(),   primary_key=True),
        sa.Column('nombre',       sa.String(100), nullable=False),
        sa.Column('categoria_id', sa.Integer(),   sa.ForeignKey('wms_categorias_producto.id'), nullable=False),
        sa.Column('activo',       sa.Boolean(),   nullable=False, server_default='true'),
        sa.Column('created_at',   _ts, server_default=_now),
        sa.Column('updated_at',   _ts, server_default=_now),
    )
    op.create_index('ix_wms_familias_producto_id', 'wms_familias_producto', ['id'])


def downgrade():
    op.drop_index('ix_wms_familias_producto_id', 'wms_familias_producto')
    op.drop_table('wms_familias_producto')
    op.drop_index('ix_wms_categorias_producto_id', 'wms_categorias_producto')
    op.drop_table('wms_categorias_producto')
    op.drop_index('ix_wms_unidades_medida_id', 'wms_unidades_medida')
    op.drop_table('wms_unidades_medida')
    op.drop_index('ix_wms_tipos_ubicacion_id', 'wms_tipos_ubicacion')
    op.drop_table('wms_tipos_ubicacion')
    op.drop_index('ix_wms_tipos_zona_id', 'wms_tipos_zona')
    op.drop_table('wms_tipos_zona')
