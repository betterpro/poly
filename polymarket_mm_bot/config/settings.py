from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from polymarket_mm_bot.config.db_url import normalize_database_url
from polymarket_mm_bot.utils import DEFAULT_ALLOWED_CATEGORIES, normalize_category_list


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "polymarket-mm-bot"
    environment: str = "local"
    log_level: str = "INFO"

    dashboard_username: str = "admin"
    dashboard_password: str | None = None

    paper_trading: bool = True
    live_trading_confirmed: bool = False
    starting_capital: float = 10_000.0

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/polymarket_mm"
    redis_url: str = "redis://localhost:6379/0"

    polymarket_host: str = "https://clob.polymarket.com"
    polymarket_gamma_host: str = "https://gamma-api.polymarket.com"
    # Public trade prints (no auth). The CLOB /trades endpoint requires L2 auth.
    polymarket_data_host: str = "https://data-api.polymarket.com"
    polymarket_ws_url: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    polymarket_api_key: str | None = None
    polymarket_api_secret: str | None = None
    polymarket_api_passphrase: str | None = None
    polymarket_private_key: str | None = None
    polymarket_funder_address: str | None = None
    # Base32 TOTP secret used to confirm the paper -> live switch from the dashboard.
    live_totp_secret: str | None = None
    polymarket_chain_id: int = 137
    signature_type: int = 0

    max_daily_loss: float = 300.0
    max_position_per_market: float = 200.0
    max_total_exposure: float = 1_000.0
    max_order_size: float = 25.0
    max_open_orders: int = 20
    max_markets_traded: int = 10
    max_api_errors: int = 5
    max_order_failures_per_market: int = 3

    min_volume: float = 10_000.0
    min_liquidity: float = 2_000.0
    min_spread: float = 0.01
    market_score_threshold: float = 70.0
    min_time_to_resolution_hours: float = 12.0
    allow_near_resolution: bool = False

    target_spread: float = 0.02
    min_tick: float = 0.01
    order_size: float = 10.0
    stale_order_seconds: int = 30
    stale_data_seconds: int = 15
    # In a wide book, step this many ticks inside the touch to win queue priority
    # (more fills) while still keeping at least target_spread of edge. 0 disables
    # (quote exactly at the touch). Never crosses the spread.
    quote_improve_ticks: int = 1
    # Inventory control. The bot stops buying a market once it holds this fraction
    # of max_position_per_market, and tapers buy size as it fills up so it can't
    # pile a large one-sided (directional) position into a single market.
    inventory_target_fraction: float = 0.35
    # How often (seconds) to append a row to pnl_snapshots for the performance
    # time-series. 0 disables. Kept infrequent to avoid unnecessary DB writes.
    pnl_snapshot_seconds: int = 300

    # Adverse-selection (toxic flow) protection. When recent taker flow is
    # heavily one-sided or price is trending fast, informed traders are likely
    # active: widen quotes first, then pull them entirely.
    toxicity_window_seconds: int = 90
    toxicity_min_trades: int = 3
    toxicity_widen_threshold: float = 0.60
    toxicity_pull_threshold: float = 0.85
    toxicity_momentum_pull_ticks: float = 3.0
    toxicity_spread_multiplier: float = 2.0
    toxicity_size_multiplier: float = 0.5

    allowed_categories: list[str] = Field(default_factory=lambda: list(DEFAULT_ALLOWED_CATEGORIES))

    run_mode: Literal["paper", "live"] = "paper"

    @field_validator("allowed_categories", mode="before")
    @classmethod
    def normalize_allowed_categories(cls, value: list[str] | str | None) -> list[str]:
        return normalize_category_list(value)

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        return normalize_database_url(str(value))

    @model_validator(mode="after")
    def enforce_live_safety(self) -> "Settings":
        if not self.paper_trading or self.run_mode == "live":
            if not self.live_trading_confirmed:
                raise ValueError("Live trading requires LIVE_TRADING_CONFIRMED=true.")
            if not self.polymarket_private_key:
                raise ValueError("Live trading requires POLYMARKET_PRIVATE_KEY.")
            if not self.polymarket_funder_address:
                raise ValueError("Live trading requires POLYMARKET_FUNDER_ADDRESS.")
        return self

    @property
    def mode_warning(self) -> str:
        return "PAPER TRADING - no real orders" if self.paper_trading else "LIVE TRADING ENABLED"


@lru_cache
def get_settings() -> Settings:
    return Settings()
