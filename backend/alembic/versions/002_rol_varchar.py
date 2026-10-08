"""cambiar columna rol de enum a varchar

Revision ID: 002
Revises: 001
Create Date: 2026-06-22
"""
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE usuarios ALTER COLUMN rol TYPE VARCHAR(100) USING rol::text"
    )
    op.execute("DROP TYPE IF EXISTS rolusuario")


def downgrade() -> None:
    op.execute(
        "CREATE TYPE rolusuario AS ENUM "
        "('ADMINISTRADOR','SUPERVISOR_LOGISTICO','OPERADOR_BODEGA','AUDITOR','CONSULTA','CONDUCTOR')"
    )
    op.execute(
        "ALTER TABLE usuarios ALTER COLUMN rol TYPE rolusuario USING rol::rolusuario"
    )
