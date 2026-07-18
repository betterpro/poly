"""add trade order id

Revision ID: 0003_trade_order_id
Revises: 0002_bot_config
Create Date: 2026-07-18
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_trade_order_id"
down_revision = "0002_bot_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trades", sa.Column("order_id", sa.String(length=128), nullable=True))
    op.create_index("ix_trades_order_id", "trades", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_trades_order_id", table_name="trades")
    op.drop_column("trades", "order_id")
