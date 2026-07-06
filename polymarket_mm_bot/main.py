from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog

from polymarket_mm_bot.config.runtime_settings import clear_runtime_settings_cache, get_effective_settings
from polymarket_mm_bot.dashboard.pnl_baseline import resolve_daily_pnl
from polymarket_mm_bot.dashboard.trading_control import is_trading_enabled
from polymarket_mm_bot.dashboard.state import state
from polymarket_mm_bot.dashboard.status_store import save_status_snapshot
from polymarket_mm_bot.database.migrate import run_migrations
from polymarket_mm_bot.database.runtime_state import save_risk_event
from polymarket_mm_bot.data import PolymarketDataClient
from polymarket_mm_bot.logging import configure_logging
from polymarket_mm_bot.models import BotOrder, Market, OrderBook, OrderStatus, Position, Side
from polymarket_mm_bot.market_scanner import MarketScanner
from polymarket_mm_bot.strategy import REASON_TOXIC_PULL, MarketMakingStrategy
from polymarket_mm_bot.trading_runtime import get_trading_runtime
from polymarket_mm_bot.utils import clamp, estimate_taker_fee, maker_fee

logger = structlog.get_logger()

_OPEN_ORDER_STATUSES = {OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED}


@dataclass(frozen=True)
class _QuoteSpec:
    side: Side
    price: float
    size: float
    token_id: str | None


def _yes_price_from_market(market: Market) -> float | None:
    raw = market.metadata.get("outcomePrices")
    if not raw:
        return None
    try:
        prices = json.loads(raw) if isinstance(raw, str) else raw
        return float(prices[0])
    except (TypeError, ValueError, IndexError):
        return None


def _mark_price(market: Market, book: OrderBook | None) -> float | None:
    if book and book.best_bid is not None and book.best_ask is not None:
        return (book.best_bid + book.best_ask) / 2
    return _yes_price_from_market(market)


def _order_payload(order: BotOrder) -> dict:
    payload = order.model_dump(mode="json")
    payload["remaining_size"] = round(order.remaining_size, 6)
    payload["filled_notional"] = round(order.filled_size * order.price, 6)
    payload["remaining_notional"] = round(order.remaining_size * order.price, 6)
    payload["notional"] = round(order.size * order.price, 6)
    return payload


def _position_payload(inventory, position: Position, mark_price: float | None) -> dict:
    payload = position.model_dump(mode="json")
    unrealized = inventory.unrealized_pnl(position.market_id, mark_price) if mark_price is not None else 0.0
    payload["net_yes"] = round(position.net_yes, 6)
    payload["gross_exposure"] = round(position.gross_exposure, 6)
    payload["mark_price"] = round(mark_price, 6) if mark_price is not None else None
    payload["mark_missing"] = mark_price is None and (position.yes_size > 0 or position.no_size > 0)
    payload["unrealized_pnl"] = round(unrealized, 4)
    payload["total_pnl"] = round(position.realized_pnl + unrealized, 4)
    return payload


def _market_card_payload(market: Market, orders: list, order_size: float) -> dict:
    buy_order = next(
        (
            o
            for o in orders
            if o.market_id == market.condition_id and o.side == Side.BUY and o.status == OrderStatus.OPEN
        ),
        None,
    )
    sell_order = next(
        (
            o
            for o in orders
            if o.market_id == market.condition_id and o.side == Side.SELL and o.status == OrderStatus.OPEN
        ),
        None,
    )
    yes_price = _yes_price_from_market(market)
    buy_price = buy_order.price if buy_order else yes_price
    sell_price = sell_order.price if sell_order else yes_price
    payload = market.model_dump(mode="json")
    payload.update(
        {
            "bot_buy_price": buy_order.price if buy_order else None,
            "bot_sell_price": sell_order.price if sell_order else None,
            "buy_fee_maker": maker_fee(),
            "sell_fee_maker": maker_fee(),
            "buy_fee_taker": estimate_taker_fee(order_size, buy_price, market.category),
            "sell_fee_taker": estimate_taker_fee(order_size, sell_price, market.category),
            "fee_order_size": order_size,
        }
    )
    return payload


def _sell_quote_size(settings, position: Position, signal_size: float) -> float:
    if position.yes_size <= 0:
        return 0.0
    limit = max(settings.max_position_per_market, 1.0)
    if position.yes_size >= limit * 0.8:
        return min(position.yes_size, settings.max_order_size)
    return min(signal_size, position.yes_size)


def _metadata_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _metadata_quoteable(settings, market: Market) -> bool:
    bid = _metadata_float(market.metadata.get("bestBid"))
    ask = _metadata_float(market.metadata.get("bestAsk"))
    if bid is None or ask is None:
        return False
    return ask - bid >= settings.min_spread and ask > settings.min_tick and bid < 1 - settings.min_tick


def _quote_matches(order: BotOrder, market_id: str, quote: _QuoteSpec) -> bool:
    return (
        order.market_id == market_id
        and order.side == quote.side
        and order.token_id == quote.token_id
        and order.status in _OPEN_ORDER_STATUSES
        and abs(order.price - quote.price) <= 1e-9
        and abs(order.remaining_size - quote.size) <= 1e-9
    )


async def _sync_market_quotes(execution, market_id: str, quotes: list[_QuoteSpec]) -> None:
    """Keep unchanged quotes resting and replace only stale or disabled sides."""
    desired = [quote for quote in quotes if quote.size > 0]
    kept_ids: set[str] = set()
    for quote in desired:
        match = next(
            (
                order
                for order in execution.orders.values()
                if order.client_order_id not in kept_ids and _quote_matches(order, market_id, quote)
            ),
            None,
        )
        if match is not None:
            kept_ids.add(match.client_order_id)

    for order in list(execution.orders.values()):
        if (
            order.market_id == market_id
            and order.status in _OPEN_ORDER_STATUSES
            and order.client_order_id not in kept_ids
        ):
            await execution.cancel_order(order.client_order_id)

    kept_sides = {order.side for order in execution.orders.values() if order.client_order_id in kept_ids}
    for quote in desired:
        if quote.side in kept_sides:
            continue
        order = await execution.create_order(market_id, quote.side, quote.price, quote.size, quote.token_id)
        if order.status in _OPEN_ORDER_STATUSES:
            kept_sides.add(order.side)


async def _unwind_orphaned_positions(
    settings,
    inventory,
    execution,
    markets: list[Market],
    selected: list[Market],
    books: dict[str, OrderBook],
    trades: dict[str, list],
) -> None:
    """Quote exits for inventory held in markets the scanner no longer selects.

    Without this, a position acquired in a market that later drops out of the
    selection set would never be quoted on the sell side and stay stuck forever.
    """
    selected_ids = {market.condition_id for market in selected}
    market_lookup = {market.condition_id: market for market in markets}
    for position in list(inventory.positions.values()):
        if position.yes_size <= 0 or position.market_id in selected_ids:
            continue
        market = market_lookup.get(position.market_id)
        book = books.get(position.market_id)
        if market is None or not market.yes_token_id or book is None:
            continue
        if book.best_bid is None or book.best_ask is None:
            continue
        has_open_sell = any(
            order.market_id == position.market_id
            and order.side == Side.SELL
            and order.status in {OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED}
            for order in execution.orders.values()
        )
        if has_open_sell:
            continue
        # Quote one tick inside the ask when possible, otherwise cross to the
        # bid so the position actually exits. Sub-penny books (longshots) are
        # allowed here: Polymarket supports 0.001 ticks at the extremes, and
        # clamping to 0.01 would leave the exit resting above the entire book.
        ask = round(clamp(max(book.best_ask - settings.min_tick, book.best_bid), 0.001, 0.999), 3)
        size = min(position.yes_size, settings.max_order_size)
        await execution.create_order(position.market_id, Side.SELL, ask, size, market.yes_token_id)
        logger.info("unwind_quote_placed", market_id=position.market_id, price=ask, size=size)
        if settings.paper_trading:
            await execution.simulate_fills(book, trades.get(position.market_id, []))


def _record_risk_event(runtime, market_id: str | None, code: str, message: str | None = None) -> None:
    event = {"market_id": market_id, "code": code}
    state.risk_events.append(event)
    if runtime.session_factory is None:
        return
    try:
        with runtime.session_factory() as session:
            save_risk_event(session, code, market_id, message or f"Risk blocked trading: {code}")
    except Exception as exc:
        logger.warning("risk_event_persist_failed", code=code, error=str(exc))


async def _load_books_and_trades(
    data: PolymarketDataClient,
    settings,
    markets: list[Market],
    *,
    limit: int = 80,
    include_market_ids: set[str] | None = None,
) -> tuple[dict[str, OrderBook], dict[str, list], int]:
    include_market_ids = include_market_ids or set()
    sorted_markets = sorted(markets, key=lambda market: (market.liquidity, market.volume), reverse=True)
    quoteable_markets = [market for market in sorted_markets if _metadata_quoteable(settings, market)]
    candidate_pool = [*quoteable_markets, *sorted_markets]
    candidates_by_id: dict[str, Market] = {}
    for market in candidate_pool:
        if len(candidates_by_id) >= limit:
            break
        candidates_by_id[market.condition_id] = market
    for market in sorted_markets:
        if market.condition_id in include_market_ids:
            candidates_by_id[market.condition_id] = market
    candidates = list(candidates_by_id.values())
    books: dict[str, OrderBook] = {}
    trades: dict[str, list] = {}
    error_count = 0

    async def load_market_data(market: Market) -> None:
        nonlocal error_count
        token_id = market.yes_token_id
        if not token_id:
            return
        try:
            books[market.condition_id] = await data.fetch_order_book(token_id, market.condition_id)
        except Exception as exc:
            logger.debug("book_unavailable", market_id=market.condition_id, error=str(exc))
            error_count += 1
            return
        try:
            trades[market.condition_id] = await data.fetch_recent_trades(market.condition_id)
        except Exception as exc:
            logger.debug("trades_unavailable", market_id=market.condition_id, error=str(exc))
            trades[market.condition_id] = []

    await asyncio.gather(*(load_market_data(market) for market in candidates))
    return books, trades, error_count


async def run_once() -> None:
    clear_runtime_settings_cache()
    settings = get_effective_settings()
    configure_logging(settings.log_level)
    try:
        runtime = get_trading_runtime(settings)
    except RuntimeError as exc:
        # Live mode is selected but the live execution engine is not wired yet.
        # Stay up and trade nothing rather than fabricate paper fills as "live".
        state.bot_status = "live_unavailable"
        state.trading_enabled = False
        logger.error("live_execution_unavailable", error=str(exc))
        save_status_snapshot(
            {
                "bot_status": state.bot_status,
                "trading_enabled": False,
                "mode_warning": settings.mode_warning,
                "allowed_categories": settings.allowed_categories,
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        return
    inventory = runtime.inventory
    risk = runtime.risk
    execution = runtime.execution
    strategy = MarketMakingStrategy(settings, inventory)
    scanner = MarketScanner(settings)
    data = PolymarketDataClient(settings)
    state.bot_status = "starting"
    try:
        try:
            markets = await data.fetch_active_markets(categories=settings.allowed_categories)
        except Exception as exc:
            decision = risk.record_api_error()
            await execution.cancel_all_open_orders()
            state.bot_status = "api_error"
            state.trading_enabled = False
            code = decision.code if not decision.allowed else "api_error"
            _record_risk_event(runtime, None, code, str(exc))
            save_status_snapshot(
                {
                    "bot_status": state.bot_status,
                    "trading_enabled": state.trading_enabled,
                    "mode_warning": settings.mode_warning,
                    "allowed_categories": settings.allowed_categories,
                    "updated_at": datetime.now(UTC).isoformat(),
                    "active_markets": [m.model_dump(mode="json") for m in state.active_markets],
                    "selected_markets": [m.model_dump(mode="json") for m in state.selected_markets],
                    "orders": [o.model_dump(mode="json") for o in state.orders],
                    "positions": [p.model_dump(mode="json") for p in state.positions],
                    "daily_pnl": state.daily_pnl,
                    "total_pnl": state.total_pnl,
                    "realized_pnl": state.realized_pnl,
                    "unrealized_pnl": state.unrealized_pnl,
                    "daily_pnl_reset_at": state.daily_pnl_reset_at,
                    "risk_events": state.risk_events[-50:],
                    "strategy_status": state.strategy_status,
                }
            )
            logger.warning("market_fetch_failed", error=str(exc))
            return
        state.active_markets = markets
        position_market_ids = {
            position.market_id
            for position in inventory.positions.values()
            if position.yes_size > 0 or position.no_size > 0
        }
        books, trades, market_data_errors = await _load_books_and_trades(
            data,
            settings,
            markets,
            include_market_ids=position_market_ids,
        )
        api_blocked = False
        api_error_signals = 1 if market_data_errors and not books else 0
        for _ in range(api_error_signals):
            decision = risk.record_api_error()
            if not decision.allowed:
                await execution.cancel_all_open_orders()
                if risk.api_errors == settings.max_api_errors:
                    _record_risk_event(runtime, None, decision.code)
                api_blocked = True
                break
        if market_data_errors == 0 or books:
            risk.reset_api_errors()

        selected = scanner.select_markets(markets, books, trades)
        state.selected_markets = selected
        trading_enabled = is_trading_enabled() and not api_blocked
        trade_mode = "paper_trading" if settings.paper_trading else "live_trading"
        state.bot_status = trade_mode if trading_enabled else "trading_paused"
        state.trading_enabled = trading_enabled
        mark_prices = {}
        for market in markets:
            if market.condition_id in position_market_ids and (
                mark := _mark_price(market, books.get(market.condition_id))
            ) is not None:
                mark_prices[market.condition_id] = mark
        realized_pnl, unrealized_pnl, total_pnl = inventory.portfolio_pnl(mark_prices)
        _, daily_pnl, pnl_tracking = resolve_daily_pnl(total_pnl)
        pnl_decision = risk.update_daily_pnl(daily_pnl)
        if not pnl_decision.allowed:
            await execution.cancel_all_open_orders()
            _record_risk_event(runtime, None, pnl_decision.code, pnl_decision.message)
            trading_enabled = False
            state.trading_enabled = False
            state.bot_status = "risk_paused"

        if trading_enabled:
            strategy_status: dict[str, str] = {market.condition_id: "running" for market in selected}
            for market in selected:
                book = books.get(market.condition_id)
                if not book:
                    continue
                decision = risk.check_market(market, book)
                if not decision.allowed:
                    await execution.cancel_all_for_market(market.condition_id)
                    _record_risk_event(runtime, market.condition_id, decision.code, decision.message)
                    continue
                # Match resting quotes from the previous cycle against fresh
                # market prints BEFORE canceling/replacing them. Otherwise
                # passive orders are torn down every cycle without ever having
                # a chance to fill on the trades that happened in between.
                if settings.paper_trading:
                    await execution.simulate_fills(book, trades.get(market.condition_id, []))
                signal = strategy.build_signal(market.condition_id, book, trades.get(market.condition_id, []))
                if signal and signal.reason == REASON_TOXIC_PULL:
                    # Informed flow detected: get out of the way immediately
                    # instead of waiting for stale-order cleanup.
                    await execution.cancel_all_for_market(market.condition_id)
                    strategy_status[market.condition_id] = "toxic_flow_paused"
                    logger.info("toxic_flow_quotes_pulled", market_id=market.condition_id)
                elif signal and signal.bid_price and signal.ask_price:
                    quotes: list[_QuoteSpec] = []
                    if inventory.can_quote_side(market.condition_id, Side.BUY):
                        quotes.append(_QuoteSpec(Side.BUY, signal.bid_price, signal.size, market.yes_token_id))
                    position = inventory.get_position(market.condition_id)
                    sell_size = _sell_quote_size(settings, position, signal.size)
                    if sell_size > 0:
                        quotes.append(_QuoteSpec(Side.SELL, signal.ask_price, sell_size, market.yes_token_id))
                    await _sync_market_quotes(execution, market.condition_id, quotes)
                    logger.info("strategy_signal", **signal.model_dump())
                # Fills are only ever simulated in paper mode.
                if settings.paper_trading:
                    await execution.simulate_fills(book, trades.get(market.condition_id, []))
            await _unwind_orphaned_positions(settings, inventory, execution, markets, selected, books, trades)
            await execution.cancel_stale_orders()
            # In live mode, learn fills by reconciling against the exchange.
            if not settings.paper_trading:
                await execution.sync_fills()
            state.strategy_status = strategy_status
        else:
            await execution.cancel_all_open_orders()
            state.strategy_status = {market.condition_id: "paused" for market in selected}
            logger.info("trading_paused")

        state.orders = [
            order
            for order in execution.orders.values()
            if order.status in {OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED}
        ]
        open_positions = [
            position
            for position in inventory.positions.values()
            if position.yes_size > 0 or position.no_size > 0 or position.realized_pnl != 0
        ]
        realized_pnl, unrealized_pnl, total_pnl = inventory.portfolio_pnl(mark_prices)
        state.positions = open_positions
        state.realized_pnl = realized_pnl
        state.unrealized_pnl = unrealized_pnl
        state.total_pnl = total_pnl
        _, daily_pnl, pnl_tracking = resolve_daily_pnl(total_pnl)
        state.daily_pnl = daily_pnl
        state.daily_pnl_reset_at = pnl_tracking.get("reset_at")
        risk.update_daily_pnl(state.daily_pnl)
        state.mode_warning = settings.mode_warning
        state.recent_fills = list(getattr(execution, "recent_fills", []))[-50:]
        save_status_snapshot(
            {
                "bot_status": state.bot_status,
                "trading_enabled": state.trading_enabled,
                "mode_warning": state.mode_warning,
                "allowed_categories": settings.allowed_categories,
                "updated_at": datetime.now(UTC).isoformat(),
                "active_markets": [m.model_dump(mode="json") for m in state.active_markets],
                "selected_markets": [
                    _market_card_payload(m, state.orders, settings.order_size) for m in state.selected_markets
                ],
                "orders": [_order_payload(o) for o in state.orders],
                "positions": [
                    _position_payload(
                        inventory,
                        position,
                        mark_prices.get(position.market_id),
                    )
                    for position in open_positions
                ],
                "daily_pnl": state.daily_pnl,
                "total_pnl": state.total_pnl,
                "realized_pnl": state.realized_pnl,
                "unrealized_pnl": state.unrealized_pnl,
                "daily_pnl_reset_at": state.daily_pnl_reset_at,
                "risk_events": state.risk_events[-50:],
                "recent_fills": state.recent_fills,
                "strategy_status": state.strategy_status,
            }
        )
    finally:
        await data.close()


def _skip_startup_migrations() -> bool:
    import os

    return os.environ.get("SKIP_STARTUP_MIGRATIONS", "").lower() in {"1", "true", "yes"}


async def main() -> None:
    if not _skip_startup_migrations():
        try:
            run_migrations()
        except Exception as exc:
            logger.warning("bot_migration_failed", error=str(exc))
    while True:
        try:
            await run_once()
        except Exception as exc:
            logger.error("run_once_failed", error=str(exc))
        await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())
