from polymarket_mm_bot.dashboard.app import _filter_markets


def test_filter_markets_keeps_only_allowed_category():
    markets = [
        {
            "category": "sports",
            "question": "Will Spain win the 2026 FIFA World Cup?",
            "metadata": {"event": {"tags": [{"slug": "soccer"}, {"slug": "sports"}]}},
        },
        {
            "category": "sports",
            "question": "New Rihanna Album before GTA VI?",
            "metadata": {"event": {"tags": [{"slug": "pop-culture"}, {"slug": "gta-vi"}]}},
        },
    ]
    filtered = _filter_markets(markets, ["sports"])
    assert len(filtered) == 1
    assert "Spain" in filtered[0]["question"]
