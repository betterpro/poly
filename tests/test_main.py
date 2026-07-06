from polymarket_mm_bot.main import _QuoteSpec, _metadata_quoteable, _quote_matches, _sell_quote_size, _sync_market_quotes
from polymarket_mm_bot.models import BotOrder, Market, OrderStatus, Position, Side


def test_sell_quote_size_uses_max_clip_when_inventory_is_high(settings):
    position = Position(market_id="m1", yes_size=settings.max_position_per_market * 0.9)
    assert _sell_quote_size(settings, position, signal_size=5) == settings.max_order_size


def test_sell_quote_size_uses_signal_size_for_normal_inventory(settings):
    position = Position(market_id="m1", yes_size=12)
    assert _sell_quote_size(settings, position, signal_size=5) == 5


def test_quote_matches_requires_exact_resting_quote():
    order = BotOrder(
        client_order_id="o1",
        market_id="m1",
        token_id="yes-token",
        side=Side.BUY,
        price=0.49,
        size=5,
    )

    assert _quote_matches(order, "m1", _QuoteSpec(Side.BUY, 0.49, 5, "yes-token"))
    assert not _quote_matches(order, "m1", _QuoteSpec(Side.BUY, 0.48, 5, "yes-token"))


def test_metadata_quoteable_requires_configured_spread(settings):
    market = Market(
        condition_id="m1",
        question="Will this be quoteable?",
        metadata={"bestBid": 0.19, "bestAsk": 0.2},
    )
    tight_market = Market(
        condition_id="m2",
        question="Will this be too tight?",
        metadata={"bestBid": 0.002, "bestAsk": 0.003},
    )

    assert _metadata_quoteable(settings, market)
    assert not _metadata_quoteable(settings, tight_market)


class FakeExecution:
    def __init__(self, orders: list[BotOrder] | None = None):
        self.orders = {order.client_order_id: order for order in orders or []}
        self.created: list[BotOrder] = []
        self.canceled: list[str] = []

    async def create_order(self, market_id: str, side: Side, price: float, size: float, token_id: str | None = None):
        order = BotOrder(
            client_order_id=f"new-{len(self.created) + 1}",
            market_id=market_id,
            token_id=token_id,
            side=side,
            price=price,
            size=size,
        )
        self.orders[order.client_order_id] = order
        self.created.append(order)
        return order

    async def cancel_order(self, client_order_id: str) -> None:
        self.canceled.append(client_order_id)
        self.orders[client_order_id].status = OrderStatus.CANCELED


async def test_sync_market_quotes_reuses_unchanged_quote():
    existing = BotOrder(
        client_order_id="o1",
        market_id="m1",
        token_id="yes-token",
        side=Side.BUY,
        price=0.49,
        size=5,
    )
    execution = FakeExecution([existing])

    await _sync_market_quotes(execution, "m1", [_QuoteSpec(Side.BUY, 0.49, 5, "yes-token")])

    assert execution.created == []
    assert execution.canceled == []
    assert existing.status == OrderStatus.OPEN


async def test_sync_market_quotes_replaces_stale_quote():
    existing = BotOrder(
        client_order_id="o1",
        market_id="m1",
        token_id="yes-token",
        side=Side.BUY,
        price=0.48,
        size=5,
    )
    execution = FakeExecution([existing])

    await _sync_market_quotes(execution, "m1", [_QuoteSpec(Side.BUY, 0.49, 5, "yes-token")])

    assert execution.canceled == ["o1"]
    assert len(execution.created) == 1
    assert execution.created[0].price == 0.49


async def test_sync_market_quotes_cancels_disabled_side():
    buy = BotOrder(
        client_order_id="buy",
        market_id="m1",
        token_id="yes-token",
        side=Side.BUY,
        price=0.49,
        size=5,
    )
    sell = BotOrder(
        client_order_id="sell",
        market_id="m1",
        token_id="yes-token",
        side=Side.SELL,
        price=0.51,
        size=5,
    )
    execution = FakeExecution([buy, sell])

    await _sync_market_quotes(execution, "m1", [_QuoteSpec(Side.SELL, 0.51, 5, "yes-token")])

    assert execution.canceled == ["buy"]
    assert execution.created == []
    assert sell.status == OrderStatus.OPEN
