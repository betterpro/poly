from polymarket_mm_bot.market_scanner import MarketScanner
from polymarket_mm_bot.models import BookLevel, OrderBook, Side, Trade

from datetime import UTC, datetime, timedelta


def test_market_scoring_accepts_liquid_market(settings, market, book):
    score = MarketScanner(settings).score_market(market, book, [])
    assert score.score >= settings.market_score_threshold
    assert score.rejected is False


def test_market_scoring_rejects_tiny_market(settings, market, book):
    market.volume = 1
    score = MarketScanner(settings).score_market(market, book, [])
    assert score.rejected is True
    assert "volume_below_min" in score.reasons


def test_market_scoring_rejects_disallowed_category(settings, market, book):
    settings.allowed_categories = ["sports"]
    market.category = "crypto"
    score = MarketScanner(settings).score_market(market, book, [])
    assert score.rejected is True
    assert "category_not_allowed" in score.reasons


def test_market_scoring_rejects_high_volatility(settings, market, book):
    trades = [
        Trade(
            market_id="m1",
            price=price,
            size=10,
            side=Side.BUY,
            timestamp=datetime.now(UTC) - timedelta(seconds=i),
        )
        for i, price in enumerate([0.1, 0.9, 0.12, 0.88, 0.11])
    ]
    score = MarketScanner(settings).score_market(market, book, trades)
    assert score.rejected is True
    assert "high_volatility" in score.reasons


def test_market_scoring_ignores_stale_high_volatility(settings, market, book):
    trades = [
        Trade(
            market_id="m1",
            price=price,
            size=10,
            side=Side.BUY,
            timestamp=datetime.now(UTC) - timedelta(seconds=settings.toxicity_window_seconds + i + 1),
        )
        for i, price in enumerate([0.1, 0.9, 0.12, 0.88, 0.11])
    ]
    score = MarketScanner(settings).score_market(market, book, trades)
    assert "high_volatility" not in score.reasons


def test_market_scoring_rejects_too_small_spread(settings, market):
    flat_book = OrderBook(
        market_id="m1",
        token_id="yes-token",
        bids=[BookLevel(price=0.5, size=500)],
        asks=[BookLevel(price=0.5, size=500)],
    )
    score = MarketScanner(settings).score_market(market, flat_book, [])
    assert score.rejected is True
    assert "spread_too_small" in score.reasons


def test_market_scoring_rejects_sub_minimum_positive_spread(settings, market):
    book = OrderBook(
        market_id="m1",
        token_id="yes-token",
        bids=[BookLevel(price=0.002, size=2000)],
        asks=[BookLevel(price=0.003, size=2000)],
    )
    score = MarketScanner(settings).score_market(market, book, [])
    assert score.rejected is True
    assert "spread_too_small" in score.reasons
