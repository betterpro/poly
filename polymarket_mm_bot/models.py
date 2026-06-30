from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


class Outcome(StrEnum):
    YES = "YES"
    NO = "NO"


class OrderStatus(StrEnum):
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"


class Market(BaseModel):
    condition_id: str
    question: str
    slug: str | None = None
    category: str | None = None
    active: bool = True
    closed: bool = False
    paused: bool = False
    volume: float = 0.0
    liquidity: float = 0.0
    end_date: datetime | None = None
    yes_token_id: str | None = None
    no_token_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BookLevel(BaseModel):
    price: float
    size: float


class OrderBook(BaseModel):
    market_id: str
    token_id: str | None = None
    bids: list[BookLevel] = Field(default_factory=list)
    asks: list[BookLevel] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def best_bid(self) -> float | None:
        return max((level.price for level in self.bids), default=None)

    @property
    def best_ask(self) -> float | None:
        return min((level.price for level in self.asks), default=None)

    @property
    def spread(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask - self.best_bid

    @property
    def bid_depth(self) -> float:
        return sum(level.size for level in self.bids[:5])

    @property
    def ask_depth(self) -> float:
        return sum(level.size for level in self.asks[:5])


class Trade(BaseModel):
    market_id: str
    token_id: str | None = None
    price: float
    size: float
    side: Side | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MarketScore(BaseModel):
    market_id: str
    score: float
    reasons: list[str] = Field(default_factory=list)
    rejected: bool = False


class StrategySignal(BaseModel):
    market_id: str
    fair_price: float
    bid_price: float | None
    ask_price: float | None
    size: float
    reason: str


class BotOrder(BaseModel):
    client_order_id: str
    market_id: str
    token_id: str | None = None
    side: Side
    outcome: Outcome = Outcome.YES
    price: float
    size: float
    filled_size: float = 0.0
    status: OrderStatus = OrderStatus.OPEN
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def remaining_size(self) -> float:
        return max(self.size - self.filled_size, 0.0)


class Position(BaseModel):
    market_id: str
    yes_size: float = 0.0
    no_size: float = 0.0
    realized_pnl: float = 0.0
    avg_yes_price: float = 0.0
    avg_no_price: float = 0.0

    @property
    def gross_exposure(self) -> float:
        return abs(self.yes_size * self.avg_yes_price) + abs(self.no_size * self.avg_no_price)

    @property
    def net_yes(self) -> float:
        return self.yes_size - self.no_size
