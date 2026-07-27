import pytest
from pydantic import ValidationError

from polymarket_mm_bot.config import Settings


def test_paper_trading_default_is_safe():
    settings = Settings()
    assert settings.paper_trading is True
    assert settings.live_trading_confirmed is False
    assert settings.min_quote_price == 0.05
    assert settings.per_market_stop_loss == 2.0
    assert settings.optimizer_auto_enabled is True
    assert settings.optimizer_scale_multiplier == 1.5
    assert settings.optimizer_plan_enabled is True
    assert settings.optimizer_plan_interval_seconds == 3600
    assert settings.optimizer_target_daily_pnl == 100.0


def test_live_trading_requires_confirmation_and_key():
    with pytest.raises(ValidationError):
        Settings(paper_trading=False, run_mode="live", live_trading_confirmed=False)


def test_sqlite_database_url_is_not_given_postgres_timeout():
    settings = Settings(database_url="sqlite:///runtime.db")
    assert settings.database_url == "sqlite:///runtime.db"


def test_postgres_scheme_is_normalized_for_psycopg():
    settings = Settings(database_url="postgres://user:pass@postgres.railway.internal:5432/railway")
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert "connect_timeout=5" in settings.database_url
