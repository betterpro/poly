from polymarket_mm_bot.utils import (
    category_aliases,
    event_belongs_to_category,
    event_tag_slugs,
    market_category_slugs,
    market_dict_matches_categories,
    market_matches_categories,
)


def test_market_category_slugs_from_category_field():
    slugs = market_category_slugs("sports", {})
    assert slugs == {"sports"}


def test_market_category_slugs_from_event_tags():
    metadata = {
        "event": {
            "tags": [
                {"slug": "soccer", "label": "Soccer"},
                {"slug": "sports", "label": "Sports"},
            ]
        }
    }
    slugs = market_category_slugs("sports", metadata)
    assert slugs == {"sports", "soccer"}


def test_event_belongs_to_category_sports():
    event = {"tags": [{"slug": "soccer"}, {"slug": "fifa-world-cup"}]}
    assert event_belongs_to_category(event, "sports") is True


def test_event_belongs_to_category_rejects_gta():
    event = {"tags": [{"slug": "pop-culture"}, {"slug": "gta-vi"}, {"slug": "politics"}]}
    assert event_belongs_to_category(event, "sports") is False


def test_market_matches_categories():
    metadata = {"event": {"tags": [{"slug": "nba"}, {"slug": "sports"}]}}
    assert market_matches_categories("sports", metadata, {"sports"}) is True
    assert market_matches_categories("sports", metadata, {"crypto"}) is False


def test_market_dict_matches_categories_ignores_misleading_label():
    market = {
        "category": "sports",
        "metadata": {"event": {"tags": [{"slug": "pop-culture"}, {"slug": "gta-vi"}]}},
    }
    assert market_dict_matches_categories(market, {"sports"}) is False
