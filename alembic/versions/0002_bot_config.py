"""bot config table

Revision ID: 0002_bot_config
Revises: 0001_initial_schema
Create Date: 2026-06-30
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_bot_config"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bot_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("config_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("bot_config")
