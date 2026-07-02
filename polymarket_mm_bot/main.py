from __future__ import annotations

import asyncio
import json
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
from polymarket_mm_bot.strategy import MarketMakingStrategy
from polymarket_mm_bot.trading_runtime import get_trading_runtime
from polymarket_mm_bot.utils import estimate_taker_fee, maker_fee

logger = structlog.get_logger()


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
    markets: list[Market],
    *,
    limit: int = 40,
    include_market_ids: set[str] | None = None,
) -> tuple[dict[str, OrderBook], dict[str, list], int]:
    include_market_ids = include_market_ids or set()
    sorted_markets = sorted(markets, key=lambda market: (market.liquidity, market.volume), reverse=True)
    candidates_by_id = {market.condition_id: market for market in sorted_markets[:limit]}
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
            error_count += 1
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
            markets,
            include_market_ids=position_market_ids,
        )
        api_blocked = False
        for _ in range(market_data_errors):
            decision = risk.record_api_error()
            if not decision.allowed:
                await execution.cancel_all_open_orders()
                _record_risk_event(runtime, None, decision.code)
                api_blocked = True
                break

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
            for market in selected:
                book = books.get(market.condition_id)
                if not book:
                    continue
                decision = risk.check_market(market, book)
                if not decision.allowed:
                    await execution.cancel_all_for_market(market.condition_id)
                    _record_risk_event(runtime, market.condition_id, decision.code, decision.message)
                    continue
                signal = strategy.build_signal(market.condition_id, book, trades.get(market.condition_id, []))
                if signal and signal.bid_price and signal.ask_price:
                    await execution.cancel_all_for_market(market.condition_id)
                    if inventory.can_quote_side(market.condition_id, Side.BUY):
                        await execution.create_order(
                            market.condition_id,
                            Side.BUY,
                            signal.bid_price,
                            signal.size,
                            market.yes_token_id,
                        )
                    position = inventory.get_position(market.condition_id)
                    sell_size = min(signal.size, position.yes_size)
                    if sell_size > 0:
                        await execution.create_order(
                            market.condition_id,
                            Side.SELL,
                            signal.ask_price,
                            sell_size,
                            market.yes_token_id,
                        )
                    logger.info("strategy_signal", **signal.model_dump())
                # Fills are only ever simulated in paper mode.
                if settings.paper_trading:
                    await execution.simulate_fills(book)
            await execution.cancel_stale_orders()
            state.strategy_status = {market.condition_id: "running" for market in selected}
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
                "strategy_status": state.strategy_status,
            }
        )
    finally:
        await data.close()


async def main() -> None:
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
