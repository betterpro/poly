from polymarket_mm_bot.utils import estimate_taker_fee, fee_rate_for_category, maker_fee


def test_maker_fee_is_zero():
    assert maker_fee() == 0.0


def test_taker_fee_at_midpoint_culture():
    # 10 shares × 0.05 × 0.50 × 0.50 = 0.125
    fee = estimate_taker_fee(10, 0.5, "culture")
    assert abs(fee - 0.125) < 1e-9


def test_geopolitics_has_no_fee():
    assert fee_rate_for_category("geopolitics") == 0.0
    assert estimate_taker_fee(10, 0.5, "geopolitics") == 0.0
