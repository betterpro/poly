import pytest
from pydantic import ValidationError

from polymarket_mm_bot.config import Settings


def test_paper_trading_default_is_safe():
    settings = Settings()
    assert settings.paper_trading is True
    assert settings.live_trading_confirmed is False


def test_live_trading_requires_confirmation_and_key():
    with pytest.raises(ValidationError):
        Settings(paper_trading=False, run_mode="live", live_trading_confirmed=False)


def test_sqlite_database_url_is_not_given_postgres_timeout():
    settings = Settings(database_url="sqlite:///runtime.db")
    assert settings.database_url == "sqlite:///runtime.db"
