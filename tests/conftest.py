from datetime import UTC, datetime, timedelta

import pytest

from polymarket_mm_bot.config import Settings
from polymarket_mm_bot.models import BookLevel, Market, OrderBook


@pytest.fixture
def settings() -> Settings:
    return Settings(
        min_volume=100,
        min_liquidity=100,
        market_score_threshold=50,
        max_position_per_market=50,
        max_total_exposure=100,
        max_order_size=20,
        order_size=10,
    )


@pytest.fixture
def market() -> Market:
    return Market(
        condition_id="m1",
        question="Will this test pass?",
        volume=1_000,
        liquidity=1_000,
        category="crypto",
        end_date=datetime.now(UTC) + timedelta(days=5),
        yes_token_id="yes-token",
    )


@pytest.fixture
def book() -> OrderBook:
    return OrderBook(
        market_id="m1",
        token_id="yes-token",
        bids=[BookLevel(price=0.49, size=500), BookLevel(price=0.48, size=500)],
        asks=[BookLevel(price=0.52, size=500), BookLevel(price=0.53, size=500)],
    )
