from datetime import UTC, datetime

import pytest

from polymarket_mm_bot.main import (
    _PAPER_DAILY_TARGET,
    _SHADOW_PROFILES,
    _profile_settings,
    _run_shadow_strategy_profiles,
    _strategy_profile_specs,
)
from polymarket_mm_bot.models import Side, Trade


def test_growth_profile_targets_more_daily_pnl_than_base(settings):
    growth = next(spec for spec in _strategy_profile_specs() if spec.name == "growth_100")
    profile_settings = _profile_settings(settings, growth.overrides)

    assert _PAPER_DAILY_TARGET == 100.0
    assert profile_settings.order_size > settings.order_size
    assert profile_settings.max_total_exposure > settings.max_total_exposure
    assert profile_settings.min_liquidity >= settings.min_liquidity


@pytest.mark.asyncio
async def test_shadow_strategy_profiles_keep_isolated_paper_ledgers(settings, market, book):
    _SHADOW_PROFILES.clear()
    trade = Trade(
        market_id=market.condition_id,
        token_id=market.yes_token_id,
        price=0.49,
        size=10,
        side=Side.SELL,
        timestamp=datetime.now(UTC),
    )

    first = await _run_shadow_strategy_profiles(
        settings,
        [market],
        {market.condition_id: book},
        {market.condition_id: [trade]},
    )
    second = await _run_shadow_strategy_profiles(
        settings,
        [market],
        {market.condition_id: book},
        {market.condition_id: [trade]},
    )

    assert {profile["name"] for profile in first} == {"growth_100", "selective_spread", "fast_recycle"}
    assert all(profile["target_daily_pnl"] == 100.0 for profile in first)
    assert all(profile["active"] is False for profile in first)
    assert _SHADOW_PROFILES
    assert second[0]["open_orders"] >= 0
