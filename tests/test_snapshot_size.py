"""Guards against the DB-egress blowout: the persisted status snapshot must stay
small (no raw Gamma metadata / nested event blobs)."""

from __future__ import annotations

import json

from polymarket_mm_bot.main import _slim_market_payload
from polymarket_mm_bot.models import Market


def test_slim_market_drops_heavy_metadata_but_keeps_prices():
    market = Market(
        condition_id="c1",
        question="Will it happen?",
        category="crypto",
        metadata={
            "event": {"markets": [{"x": "y"} for _ in range(50)], "description": "z" * 2000},
            "outcomePrices": '["0.5","0.5"]',
            "description": "x" * 2000,
        },
    )
    slim = _slim_market_payload(market)
    # Prices are preserved (dashboard needs them) but the heavy blob is gone.
    assert slim["metadata"] == {"outcomePrices": '["0.5","0.5"]'}
    assert "event" not in slim["metadata"]
    assert slim["condition_id"] == "c1"
    assert slim["category"] == "crypto"
    # A slim market must serialize tiny regardless of how bloated the source row is.
    assert len(json.dumps(slim)) < 500


def test_slim_market_handles_missing_prices():
    market = Market(condition_id="c2", question="Q", metadata={})
    slim = _slim_market_payload(market)
    assert slim["metadata"] == {}
    assert slim["condition_id"] == "c2"
