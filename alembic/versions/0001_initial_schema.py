"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-06-30
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "markets",
        sa.Column("condition_id", sa.String(length=128), primary_key=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("slug", sa.String(length=256)),
        sa.Column("category", sa.String(length=128)),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("closed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("paused", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("volume", sa.Float(), nullable=False, server_default="0"),
        sa.Column("liquidity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("end_date", sa.DateTime(timezone=True)),
        sa.Column("yes_token_id", sa.String(length=256)),
        sa.Column("no_token_id", sa.String(length=256)),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "order_books",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("market_id", sa.String(length=128), nullable=False),
        sa.Column("token_id", sa.String(length=256)),
        sa.Column("bids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("asks", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_order_books_market_id", "order_books", ["market_id"])
    op.create_index("ix_order_books_token_id", "order_books", ["token_id"])
    op.create_table(
        "trades",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("market_id", sa.String(length=128), nullable=False),
        sa.Column("token_id", sa.String(length=256)),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("size", sa.Float(), nullable=False),
        sa.Column("side", sa.String(length=16)),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_trades_market_id", "trades", ["market_id"])
    op.create_index("ix_trades_token_id", "trades", ["token_id"])
    op.create_index("ix_trades_timestamp", "trades", ["timestamp"])
    op.create_table(
        "bot_orders",
        sa.Column("client_order_id", sa.String(length=128), primary_key=True),
        sa.Column("market_id", sa.String(length=128), nullable=False),
        sa.Column("token_id", sa.String(length=256)),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("size", sa.Float(), nullable=False),
        sa.Column("filled_size", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_bot_orders_market_id", "bot_orders", ["market_id"])
    op.create_index("ix_bot_orders_token_id", "bot_orders", ["token_id"])
    op.create_table(
        "positions",
        sa.Column("market_id", sa.String(length=128), primary_key=True),
        sa.Column("yes_size", sa.Float(), nullable=False, server_default="0"),
        sa.Column("no_size", sa.Float(), nullable=False, server_default="0"),
        sa.Column("realized_pnl", sa.Float(), nullable=False, server_default="0"),
        sa.Column("avg_yes_price", sa.Float(), nullable=False, server_default="0"),
        sa.Column("avg_no_price", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "pnl_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("daily_pnl", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total_pnl", sa.Float(), nullable=False, server_default="0"),
        sa.Column("unrealized_pnl", sa.Float(), nullable=False, server_default="0"),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_pnl_snapshots_timestamp", "pnl_snapshots", ["timestamp"])
    op.create_table(
        "risk_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("market_id", sa.String(length=128)),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_risk_events_market_id", "risk_events", ["market_id"])
    op.create_table(
        "strategy_signals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("market_id", sa.String(length=128), nullable=False),
        sa.Column("fair_price", sa.Float(), nullable=False),
        sa.Column("bid_price", sa.Float()),
        sa.Column("ask_price", sa.Float()),
        sa.Column("size", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
    )
    op.create_index("ix_strategy_signals_market_id", "strategy_signals", ["market_id"])
    op.create_table(
        "market_scores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("market_id", sa.String(length=128), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("rejected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reasons", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.create_index("ix_market_scores_market_id", "market_scores", ["market_id"])


def downgrade() -> None:
    for table in [
        "market_scores",
        "strategy_signals",
        "risk_events",
        "pnl_snapshots",
        "positions",
        "bot_orders",
        "trades",
        "order_books",
        "markets",
    ]:
        op.drop_table(table)
