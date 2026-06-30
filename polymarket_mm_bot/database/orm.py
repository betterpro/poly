from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MarketRow(Base, TimestampMixin):
    __tablename__ = "markets"

    condition_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    question: Mapped[str] = mapped_column(Text)
    slug: Mapped[str | None] = mapped_column(String(256))
    category: Mapped[str | None] = mapped_column(String(128))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    closed: Mapped[bool] = mapped_column(Boolean, default=False)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    volume: Mapped[float] = mapped_column(Float, default=0)
    liquidity: Mapped[float] = mapped_column(Float, default=0)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    yes_token_id: Mapped[str | None] = mapped_column(String(256))
    no_token_id: Mapped[str | None] = mapped_column(String(256))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class OrderBookRow(Base, TimestampMixin):
    __tablename__ = "order_books"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market_id: Mapped[str] = mapped_column(String(128), index=True)
    token_id: Mapped[str | None] = mapped_column(String(256), index=True)
    bids: Mapped[list] = mapped_column(JSON, default=list)
    asks: Mapped[list] = mapped_column(JSON, default=list)


class TradeRow(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market_id: Mapped[str] = mapped_column(String(128), index=True)
    token_id: Mapped[str | None] = mapped_column(String(256), index=True)
    price: Mapped[float] = mapped_column(Float)
    size: Mapped[float] = mapped_column(Float)
    side: Mapped[str | None] = mapped_column(String(16))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class BotOrderRow(Base, TimestampMixin):
    __tablename__ = "bot_orders"

    client_order_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    market_id: Mapped[str] = mapped_column(String(128), index=True)
    token_id: Mapped[str | None] = mapped_column(String(256), index=True)
    side: Mapped[str] = mapped_column(String(16))
    outcome: Mapped[str] = mapped_column(String(16), default="YES")
    price: Mapped[float] = mapped_column(Float)
    size: Mapped[float] = mapped_column(Float)
    filled_size: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(32))


class PositionRow(Base, TimestampMixin):
    __tablename__ = "positions"

    market_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    yes_size: Mapped[float] = mapped_column(Float, default=0)
    no_size: Mapped[float] = mapped_column(Float, default=0)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0)
    avg_yes_price: Mapped[float] = mapped_column(Float, default=0)
    avg_no_price: Mapped[float] = mapped_column(Float, default=0)


class PnlSnapshotRow(Base):
    __tablename__ = "pnl_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    daily_pnl: Mapped[float] = mapped_column(Float, default=0)
    total_pnl: Mapped[float] = mapped_column(Float, default=0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class RiskEventRow(Base):
    __tablename__ = "risk_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    market_id: Mapped[str | None] = mapped_column(String(128), index=True)
    severity: Mapped[str] = mapped_column(String(32), default="warning")
    code: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class StrategySignalRow(Base):
    __tablename__ = "strategy_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    market_id: Mapped[str] = mapped_column(String(128), index=True)
    fair_price: Mapped[float] = mapped_column(Float)
    bid_price: Mapped[float | None] = mapped_column(Float)
    ask_price: Mapped[float | None] = mapped_column(Float)
    size: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)


class MarketScoreRow(Base):
    __tablename__ = "market_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    market_id: Mapped[str] = mapped_column(String(128), index=True)
    score: Mapped[float] = mapped_column(Float)
    rejected: Mapped[bool] = mapped_column(Boolean, default=False)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
