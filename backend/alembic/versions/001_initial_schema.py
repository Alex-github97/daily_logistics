"""initial schema

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Las tablas se crean automaticamente via SQLAlchemy en el lifespan del app.
    # Esta migración establece el punto de partida.
    pass


def downgrade() -> None:
    pass
