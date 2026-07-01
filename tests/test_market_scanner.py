from polymarket_mm_bot.market_scanner import MarketScanner


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
