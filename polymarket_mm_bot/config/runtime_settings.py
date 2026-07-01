from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from polymarket_mm_bot.config.settings import Settings, get_settings
from polymarket_mm_bot.database.orm import BotConfigRow
from polymarket_mm_bot.database.session import get_session_factory


class EditableBotSettings(BaseModel):
    paper_trading: bool = True
    run_mode: Literal["paper", "live"] = "paper"
    max_daily_loss: float = Field(gt=0)
    max_position_per_market: float = Field(gt=0)
    max_total_exposure: float = Field(gt=0)
    max_order_size: float = Field(gt=0)
    max_open_orders: int = Field(gt=0)
    max_markets_traded: int = Field(gt=0)
    min_volume: float = Field(ge=0)
    min_liquidity: float = Field(ge=0)
    min_spread: float = Field(gt=0)
    market_score_threshold: float = Field(ge=0, le=100)
    target_spread: float = Field(gt=0)
    order_size: float = Field(gt=0)
    stale_order_seconds: int = Field(gt=0)
    allowed_categories: list[str] = Field(min_length=1)

    @classmethod
    def from_settings(cls, settings: Settings) -> EditableBotSettings:
        return cls(
            paper_trading=settings.paper_trading,
            run_mode=settings.run_mode,
            max_daily_loss=settings.max_daily_loss,
            max_position_per_market=settings.max_position_per_market,
            max_total_exposure=settings.max_total_exposure,
            max_order_size=settings.max_order_size,
            max_open_orders=settings.max_open_orders,
            max_markets_traded=settings.max_markets_traded,
            min_volume=settings.min_volume,
            min_liquidity=settings.min_liquidity,
            min_spread=settings.min_spread,
            market_score_threshold=settings.market_score_threshold,
            target_spread=settings.target_spread,
            order_size=settings.order_size,
            stale_order_seconds=settings.stale_order_seconds,
            allowed_categories=settings.allowed_categories,
        )

    @field_validator("allowed_categories", mode="before")
    @classmethod
    def normalize_allowed_categories(cls, value: list[str] | str | None) -> list[str]:
        from polymarket_mm_bot.utils import normalize_category_list

        normalized = normalize_category_list(value)
        if not normalized:
            raise ValueError("Select at least one market category.")
        return normalized

    @model_validator(mode="after")
    def enforce_live_safety(self) -> EditableBotSettings:
        if not self.paper_trading or self.run_mode == "live":
            base = get_settings()
            if not base.live_trading_confirmed:
                raise ValueError(
                    "Live mode requires LIVE_TRADING_CONFIRMED=true in server environment."
                )
            if not base.polymarket_private_key or not base.polymarket_funder_address:
                raise ValueError(
                    "Live mode requires wallet credentials in server environment."
                )
        return self

    def apply_to(self, settings: Settings) -> Settings:
        data = settings.model_dump()
        data.update(self.model_dump())
        return Settings.model_validate(data)


def _load_overrides(session: Session) -> dict:
    try:
        row = session.get(BotConfigRow, 1)
    except Exception:
        return {}
    if row is None:
        return {}
    return dict(row.config_json or {})


def get_editable_settings(session: Session | None = None) -> EditableBotSettings:
    base = get_settings()
    defaults = EditableBotSettings.from_settings(base)
    try:
        if session is None:
            session_factory = get_session_factory()
            with session_factory() as owned:
                overrides = _load_overrides(owned)
        else:
            overrides = _load_overrides(session)
        return EditableBotSettings.model_validate({**defaults.model_dump(), **overrides})
    except Exception:
        return defaults


def get_effective_settings(session: Session | None = None) -> Settings:
    editable = get_editable_settings(session)
    return editable.apply_to(get_settings())


def save_editable_settings(payload: EditableBotSettings, session: Session | None = None) -> EditableBotSettings:
    validated = EditableBotSettings.model_validate(payload.model_dump())
    if session is None:
        session_factory = get_session_factory()
        with session_factory() as owned:
            return _save(validated, owned)
    return _save(validated, session)


def _save(payload: EditableBotSettings, session: Session) -> EditableBotSettings:
    preserved_config_keys = ("daily_pnl_tracking", "trading_control")
    try:
        row = session.get(BotConfigRow, 1)
        preserved: dict = {}
        if row is not None and row.config_json:
            for key in preserved_config_keys:
                value = row.config_json.get(key)
                if value is not None:
                    preserved[key] = value
        if row is None:
            row = BotConfigRow(id=1, config_json={**payload.model_dump(), **preserved})
            session.add(row)
        else:
            row.config_json = {**payload.model_dump(), **preserved}
        session.commit()
    except Exception:
        session.rollback()
        raise
    clear_runtime_settings_cache()
    return payload


@lru_cache
def get_cached_effective_settings() -> Settings:
    return get_effective_settings()


def clear_runtime_settings_cache() -> None:
    get_cached_effective_settings.cache_clear()
