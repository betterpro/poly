from datetime import UTC, datetime

from pydantic import BaseModel, Field

from polymarket_mm_bot.models import BotOrder, Market, MarketScore, Position


class DashboardState(BaseModel):
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    bot_status: str = "idle"
    trading_enabled: bool = True
    mode_warning: str = "PAPER TRADING - no real orders"
    active_markets: list[Market] = Field(default_factory=list)
    selected_markets: list[Market] = Field(default_factory=list)
    market_scores: list[MarketScore] = Field(default_factory=list)
    orders: list[BotOrder] = Field(default_factory=list)
    positions: list[Position] = Field(default_factory=list)
    daily_pnl: float = 0.0
    total_pnl: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    daily_pnl_reset_at: str | None = None
    risk_events: list[dict] = Field(default_factory=list)
    strategy_status: dict[str, str] = Field(default_factory=dict)


state = DashboardState()
