from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime

import structlog

from polymarket_mm_bot.config.runtime_settings import clear_runtime_settings_cache, get_effective_settings
from polymarket_mm_bot.dashboard.pnl_baseline import resolve_daily_pnl
from polymarket_mm_bot.dashboard.trading_control import is_trading_enabled
from polymarket_mm_bot.dashboard.state import state
from polymarket_mm_bot.dashboard.status_store import save_status_snapshot
from polymarket_mm_bot.database.migrate import run_migrations
from polymarket_mm_bot.database.runtime_state import save_pnl_snapshot, save_risk_event
from polymarket_mm_bot.data import PolymarketDataClient
from polymarket_mm_bot.execution import PaperExecutionEngine
from polymarket_mm_bot.inventory import InventoryManager
from polymarket_mm_bot.logging import configure_logging
from polymarket_mm_bot.models import BotOrder, Market, OrderBook, OrderStatus, Position, Side
from polymarket_mm_bot.market_scanner import MarketScanner
from polymarket_mm_bot.risk import RiskEngine
from polymarket_mm_bot.reporting.auto_optimizer import maybe_apply_optimizer_plan
from polymarket_mm_bot.reporting.optimizer import build_optimizer_controls
from polymarket_mm_bot.strategy import REASON_TOXIC_PULL, MarketMakingStrategy
from polymarket_mm_bot.trading_runtime import get_trading_runtime
from polymarket_mm_bot.utils import clamp, estimate_taker_fee, maker_fee

logger = structlog.get_logger()

_OPEN_ORDER_STATUSES = {OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED}
_PAPER_DAILY_TARGET = 100.0
_last_pnl_snapshot_at: datetime | None = None


def _maybe_write_pnl_snapshot(runtime, settings) -> None:
    """Append a throttled row to the pnl_snapshots performance time-series."""
    global _last_pnl_snapshot_at
    interval = getattr(settings, "pnl_snapshot_seconds", 300)
    if interval <= 0 or runtime.session_factory is None:
        return
    now = datetime.now(UTC)
    if _last_pnl_snapshot_at is not None and (now - _last_pnl_snapshot_at).total_seconds() < interval:
        return
    try:
        with runtime.session_factory() as session:
            save_pnl_snapshot(
                session,
                daily_pnl=state.daily_pnl,
                total_pnl=state.total_pnl,
                unrealized_pnl=state.unrealized_pnl,
                metadata={"bot_status": state.bot_status, "realized_pnl": state.realized_pnl},
            )
        _last_pnl_snapshot_at = now
    except Exception as exc:
        logger.warning("pnl_snapshot_failed", error=str(exc))


@dataclass(frozen=True)
class _QuoteSpec:
    side: Side
    price: float
    size: float
    token_id: str | None


@dataclass(frozen=True)
class _OptimizerControls:
    blocked_market_ids: set[str]
    scaled_market_ids: set[str]
    report: dict | None = None


@dataclass(frozen=True)
class _StrategyProfileSpec:
    name: str
    description: str
    overrides: dict


@dataclass
class _ShadowProfileState:
    settings: object
    inventory: InventoryManager
    risk: RiskEngine
    execution: PaperExecutionEngine
    baseline_date: date | None = None
    baseline_total_pnl: float = 0.0


_SHADOW_PROFILES: dict[str, _ShadowProfileState] = {}


def _strategy_profile_specs() -> list[_StrategyProfileSpec]:
    return [
        _StrategyProfileSpec(
            name="growth_100",
            description="Higher turnover paper profile aimed at the $100/day target with stronger liquidity filters.",
            overrides={
                "order_size": 35.0,
                "max_order_size": 50.0,
                "max_position_per_market": 120.0,
                "max_total_exposure": 3000.0,
                "max_daily_loss": 100.0,
                "max_markets_traded": 30,
                "max_open_orders": 300,
                "min_liquidity": 3000.0,
                "market_score_threshold": 75.0,
                "target_spread": 0.025,
            },
        ),
        _StrategyProfileSpec(
            name="selective_spread",
            description="Fewer, higher-quality markets with wider quotes for cleaner spread capture.",
            overrides={
                "order_size": 25.0,
                "max_order_size": 40.0,
                "max_position_per_market": 90.0,
                "max_total_exposure": 1800.0,
                "max_daily_loss": 60.0,
                "max_markets_traded": 12,
                "max_open_orders": 80,
                "min_liquidity": 5000.0,
                "market_score_threshold": 80.0,
                "target_spread": 0.04,
            },
        ),
        _StrategyProfileSpec(
            name="fast_recycle",
            description="Smaller clips across more liquid markets to test repeatable fill frequency.",
            overrides={
                "order_size": 18.0,
                "max_order_size": 30.0,
                "max_position_per_market": 80.0,
                "max_total_exposure": 2200.0,
                "max_daily_loss": 70.0,
                "max_markets_traded": 35,
                "max_open_orders": 250,
                "min_liquidity": 2500.0,
                "market_score_threshold": 72.0,
                "target_spread": 0.02,
            },
        ),
    ]


def _profile_settings(base_settings, overrides: dict):
    data = base_settings.model_dump()
    data.update(overrides)
    return type(base_settings).model_validate(data)


def _shadow_state(base_settings, spec: _StrategyProfileSpec) -> _ShadowProfileState:
    profile_settings = _profile_settings(base_settings, spec.overrides)
    existing = _SHADOW_PROFILES.get(spec.name)
    if existing is not None:
        existing.settings = profile_settings
        existing.inventory.settings = profile_settings
        existing.risk.settings = profile_settings
        existing.execution.settings = profile_settings
        return existing
    inventory = InventoryManager(profile_settings)
    risk = RiskEngine(profile_settings, inventory)
    execution = PaperExecutionEngine(profile_settings, inventory, risk)
    profile = _ShadowProfileState(profile_settings, inventory, risk, execution)
    _SHADOW_PROFILES[spec.name] = profile
    return profile


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


def _slim_market_payload(market: Market) -> dict:
    """A compact market dict for the dashboard snapshot.

    Deliberately excludes the raw Gamma metadata/event blob (kept in memory for
    scanning) so the persisted status snapshot stays small — the snapshot is read
    by the dashboard poller constantly, and shipping full metadata was driving
    hundreds of GB of DB egress.
    """
    raw_prices = market.metadata.get("outcomePrices") if isinstance(market.metadata, dict) else None
    return {
        "condition_id": market.condition_id,
        "question": market.question,
        "slug": market.slug,
        "category": market.category,
        "active": market.active,
        "closed": market.closed,
        "paused": market.paused,
        "volume": market.volume,
        "liquidity": market.liquidity,
        "end_date": market.end_date.isoformat() if market.end_date else None,
        "yes_token_id": market.yes_token_id,
        "metadata": {"outcomePrices": raw_prices} if raw_prices is not None else {},
    }


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
    payload = _slim_market_payload(market)
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


def _buy_quote_size(settings, position: Position, signal_size: float) -> float:
    limit = max(settings.max_position_per_market, 1.0)
    fraction = clamp(getattr(settings, "inventory_target_fraction", 0.35), 0.05, 1.0)
    target_inventory = limit * fraction
    remaining = target_inventory - position.yes_size
    if remaining <= 0:
        return 0.0
    # Taper: buy full size when flat, shrinking toward zero as inventory fills up,
    # so the bot can't load a big one-sided position into a single market.
    fill_fraction = clamp(remaining / target_inventory, 0.0, 1.0)
    tapered = max(signal_size * fill_fraction, 1.0)
    return min(tapered, signal_size, settings.max_order_size, remaining)


def _scaled_signal_size(settings, market_id: str, signal_size: float, controls: _OptimizerControls) -> float:
    if market_id not in controls.scaled_market_ids:
        return signal_size
    multiplier = clamp(getattr(settings, "optimizer_scale_multiplier", 1.5), 1.0, 3.0)
    return min(signal_size * multiplier, settings.max_order_size)


def _position_marked_pnl(inventory, position: Position, mark_price: float | None) -> float:
    unrealized = inventory.unrealized_pnl(position.market_id, mark_price) if mark_price is not None else 0.0
    return position.realized_pnl + unrealized


async def _cancel_buy_orders_for_market(execution, market_id: str) -> None:
    for order in list(execution.orders.values()):
        if (
            order.market_id == market_id
            and order.side == Side.BUY
            and order.status in _OPEN_ORDER_STATUSES
        ):
            await execution.cancel_order(order.client_order_id)


def _load_optimizer_controls(runtime, settings) -> _OptimizerControls:
    if runtime.session_factory is None:
        return _OptimizerControls(set(), set(), None)
    try:
        with runtime.session_factory() as session:
            payload = build_optimizer_controls(session, settings)
    except Exception as exc:
        logger.warning("optimizer_controls_failed", error=str(exc))
        return _OptimizerControls(set(), set(), None)
    return _OptimizerControls(
        blocked_market_ids=set(payload.get("blocked_market_ids") or []),
        scaled_market_ids=set(payload.get("scaled_market_ids") or []),
        report=payload.get("report"),
    )


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


def _with_optimizer_scale_candidates(
    settings,
    selected: list[Market],
    markets: list[Market],
    books: dict[str, OrderBook],
    trades: dict[str, list],
    scanner: MarketScanner,
    controls: _OptimizerControls,
) -> list[Market]:
    """Keep proven-positive optimizer candidates in the quoted set when valid."""
    selected_by_id = {market.condition_id: market for market in selected}
    if not controls.scaled_market_ids:
        return list(selected_by_id.values())

    market_lookup = {market.condition_id: market for market in markets}
    for market_id in sorted(controls.scaled_market_ids):
        if market_id in selected_by_id or market_id in controls.blocked_market_ids:
            continue
        market = market_lookup.get(market_id)
        book = books.get(market_id)
        if market is None or book is None:
            continue
        score = scanner.score_market(market, book, trades.get(market_id, []))
        if not score.rejected:
            selected_by_id[market_id] = market

    return list(selected_by_id.values())[: settings.max_markets_traded]


def _quote_matches(order: BotOrder, market_id: str, quote: _QuoteSpec) -> bool:
    return (
        order.market_id == market_id
        and order.side == quote.side
        and order.token_id == quote.token_id
        and order.status in _OPEN_ORDER_STATUSES
        and abs(order.price - quote.price) <= 1e-9
        and abs(order.remaining_size - quote.size) <= 1e-9
    )


async def _cancel_unmanaged_stale_orders(execution, settings, managed_market_ids: set[str]) -> None:
    now = datetime.now(UTC)
    for order in list(execution.orders.values()):
        if order.status not in _OPEN_ORDER_STATUSES or order.market_id in managed_market_ids:
            continue
        if (now - order.created_at).total_seconds() > settings.stale_order_seconds:
            await execution.cancel_order(order.client_order_id)


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
        for order in list(execution.orders.values()):
            if (
                order.market_id == position.market_id
                and order.side == Side.BUY
                and order.status in _OPEN_ORDER_STATUSES
            ):
                await execution.cancel_order(order.client_order_id)
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


def _mark_prices_for_inventory(
    markets: list[Market],
    books: dict[str, OrderBook],
    inventory: InventoryManager,
) -> dict[str, float]:
    market_lookup = {market.condition_id: market for market in markets}
    mark_prices: dict[str, float] = {}
    for position in inventory.positions.values():
        if position.yes_size <= 0 and position.no_size <= 0:
            continue
        market = market_lookup.get(position.market_id)
        if market is None:
            continue
        mark = _mark_price(market, books.get(position.market_id))
        if mark is not None:
            mark_prices[position.market_id] = mark
    return mark_prices


def _open_buy_credit(orders: list[BotOrder]) -> float:
    return round(
        sum(order.remaining_size * order.price for order in orders if order.side == Side.BUY),
        4,
    )


def _capital_deployed(orders: list[BotOrder], positions: list[Position]) -> float:
    return round(_open_buy_credit(orders) + sum(position.gross_exposure for position in positions), 4)


def _active_strategy_profile_payload(settings, orders: list[BotOrder]) -> dict:
    open_orders = [order for order in orders if order.status in _OPEN_ORDER_STATUSES]
    return {
        "name": "active",
        "description": "Production paper profile currently placing orders.",
        "active": True,
        "target_daily_pnl": _PAPER_DAILY_TARGET,
        "daily_pnl": round(state.daily_pnl, 4),
        "target_progress_pct": round((state.daily_pnl / _PAPER_DAILY_TARGET) * 100, 2),
        "total_pnl": round(state.total_pnl, 4),
        "realized_pnl": round(state.realized_pnl, 4),
        "unrealized_pnl": round(state.unrealized_pnl, 4),
        "open_orders": len(open_orders),
        "open_buy_credit": _open_buy_credit(open_orders),
        "positions": len(state.positions),
        "recent_fills": len(state.recent_fills),
        "settings": {
            "order_size": settings.order_size,
            "max_position_per_market": settings.max_position_per_market,
            "max_total_exposure": settings.max_total_exposure,
            "max_daily_loss": settings.max_daily_loss,
            "per_market_stop_loss": settings.per_market_stop_loss,
            "optimizer_auto_enabled": settings.optimizer_auto_enabled,
            "optimizer_scale_multiplier": settings.optimizer_scale_multiplier,
            "max_markets_traded": settings.max_markets_traded,
            "min_liquidity": settings.min_liquidity,
            "market_score_threshold": settings.market_score_threshold,
            "target_spread": settings.target_spread,
        },
    }


def _shadow_strategy_profile_payload(
    spec: _StrategyProfileSpec,
    profile: _ShadowProfileState,
    selected: list[Market],
    markets: list[Market],
    books: dict[str, OrderBook],
) -> dict:
    mark_prices = _mark_prices_for_inventory(markets, books, profile.inventory)
    realized, unrealized, total = profile.inventory.portfolio_pnl(mark_prices)
    today = datetime.now(UTC).date()
    if profile.baseline_date != today:
        profile.baseline_date = today
        profile.baseline_total_pnl = total
    daily = total - profile.baseline_total_pnl
    open_orders = [
        order
        for order in profile.execution.orders.values()
        if order.status in _OPEN_ORDER_STATUSES
    ]
    positions = [
        position
        for position in profile.inventory.positions.values()
        if position.yes_size > 0 or position.no_size > 0 or position.realized_pnl != 0
    ]
    return {
        "name": spec.name,
        "description": spec.description,
        "active": False,
        "target_daily_pnl": _PAPER_DAILY_TARGET,
        "daily_pnl": round(daily, 4),
        "target_progress_pct": round((daily / _PAPER_DAILY_TARGET) * 100, 2),
        "total_pnl": round(total, 4),
        "realized_pnl": round(realized, 4),
        "unrealized_pnl": round(unrealized, 4),
        "open_orders": len(open_orders),
        "open_buy_credit": _open_buy_credit(open_orders),
        "positions": len(positions),
        "recent_fills": len(profile.execution.recent_fills),
        "selected_markets": len(selected),
        "settings": {
            "order_size": profile.settings.order_size,
            "max_position_per_market": profile.settings.max_position_per_market,
            "max_total_exposure": profile.settings.max_total_exposure,
            "max_daily_loss": profile.settings.max_daily_loss,
            "per_market_stop_loss": profile.settings.per_market_stop_loss,
            "max_markets_traded": profile.settings.max_markets_traded,
            "min_liquidity": profile.settings.min_liquidity,
            "market_score_threshold": profile.settings.market_score_threshold,
            "target_spread": profile.settings.target_spread,
        },
    }


async def _run_shadow_strategy_profiles(
    base_settings,
    markets: list[Market],
    books: dict[str, OrderBook],
    trades: dict[str, list],
) -> list[dict]:
    if not base_settings.paper_trading:
        return []
    profiles: list[dict] = []
    for spec in _strategy_profile_specs():
        profile = _shadow_state(base_settings, spec)
        scanner = MarketScanner(profile.settings)
        strategy = MarketMakingStrategy(profile.settings, profile.inventory)
        selected = scanner.select_markets(markets, books, trades)
        for market in selected:
            book = books.get(market.condition_id)
            if not book:
                continue
            decision = profile.risk.check_market(market, book)
            if not decision.allowed:
                await profile.execution.cancel_all_for_market(market.condition_id)
                continue
            await profile.execution.simulate_fills(book, trades.get(market.condition_id, []))
            signal = strategy.build_signal(market.condition_id, book, trades.get(market.condition_id, []))
            if signal and signal.reason == REASON_TOXIC_PULL:
                await profile.execution.cancel_all_for_market(market.condition_id)
                continue
            if signal and signal.bid_price and signal.ask_price:
                position = profile.inventory.get_position(market.condition_id)
                quotes: list[_QuoteSpec] = []
                buy_size = _buy_quote_size(profile.settings, position, signal.size)
                if buy_size > 0 and profile.inventory.can_quote_side(market.condition_id, Side.BUY):
                    quotes.append(_QuoteSpec(Side.BUY, signal.bid_price, buy_size, market.yes_token_id))
                sell_size = _sell_quote_size(profile.settings, position, signal.size)
                if sell_size > 0:
                    quotes.append(_QuoteSpec(Side.SELL, signal.ask_price, sell_size, market.yes_token_id))
                await _sync_market_quotes(profile.execution, market.condition_id, quotes)
            await profile.execution.simulate_fills(book, trades.get(market.condition_id, []))
        managed_market_ids = {market.condition_id for market in selected}
        managed_market_ids.update(
            position.market_id
            for position in profile.inventory.positions.values()
            if position.yes_size > 0 or position.no_size > 0
        )
        await _cancel_unmanaged_stale_orders(profile.execution, profile.settings, managed_market_ids)
        profiles.append(_shadow_strategy_profile_payload(spec, profile, selected, markets, books))
    return profiles


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
    optimizer_controls = _load_optimizer_controls(runtime, settings)
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
                    "active_markets_count": len(state.active_markets),
                    "selected_markets": [_slim_market_payload(m) for m in state.selected_markets],
                    "orders": [o.model_dump(mode="json") for o in state.orders],
                    "positions": [p.model_dump(mode="json") for p in state.positions],
                    "daily_pnl": state.daily_pnl,
                    "total_pnl": state.total_pnl,
                    "realized_pnl": state.realized_pnl,
                    "unrealized_pnl": state.unrealized_pnl,
                    "daily_pnl_reset_at": state.daily_pnl_reset_at,
                    "risk_events": state.risk_events[-50:],
                    "strategy_status": state.strategy_status,
                    "strategy_profiles": state.strategy_profiles,
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
            include_market_ids=position_market_ids
            | optimizer_controls.scaled_market_ids
            | optimizer_controls.blocked_market_ids,
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
        if optimizer_controls.blocked_market_ids:
            selected = [
                market for market in selected if market.condition_id not in optimizer_controls.blocked_market_ids
            ]
            for market_id in optimizer_controls.blocked_market_ids:
                await _cancel_buy_orders_for_market(execution, market_id)
        selected = _with_optimizer_scale_candidates(
            settings,
            selected,
            markets,
            books,
            trades,
            scanner,
            optimizer_controls,
        )
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
                    position = inventory.get_position(market.condition_id)
                    marked_pnl = _position_marked_pnl(inventory, position, mark_prices.get(market.condition_id))
                    market_stop_loss = abs(getattr(settings, "per_market_stop_loss", 2.0))
                    if marked_pnl <= -market_stop_loss:
                        await _cancel_buy_orders_for_market(execution, market.condition_id)
                        strategy_status[market.condition_id] = "market_stop_loss_exit_only"
                    else:
                        signal_size = _scaled_signal_size(
                            settings,
                            market.condition_id,
                            signal.size,
                            optimizer_controls,
                        )
                        buy_size = _buy_quote_size(settings, position, signal_size)
                        if buy_size > 0 and inventory.can_quote_side(market.condition_id, Side.BUY):
                            quotes.append(_QuoteSpec(Side.BUY, signal.bid_price, buy_size, market.yes_token_id))
                    sell_size = _sell_quote_size(settings, position, signal.size)
                    if sell_size > 0:
                        quotes.append(_QuoteSpec(Side.SELL, signal.ask_price, sell_size, market.yes_token_id))
                    await _sync_market_quotes(execution, market.condition_id, quotes)
                    logger.info("strategy_signal", **signal.model_dump())
                # Fills are only ever simulated in paper mode.
                if settings.paper_trading:
                    await execution.simulate_fills(book, trades.get(market.condition_id, []))
            await _unwind_orphaned_positions(settings, inventory, execution, markets, selected, books, trades)
            managed_market_ids = {market.condition_id for market in selected}
            managed_market_ids.update(
                position.market_id
                for position in inventory.positions.values()
                if position.yes_size > 0 or position.no_size > 0
            )
            await _cancel_unmanaged_stale_orders(execution, settings, managed_market_ids)
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
        _maybe_write_pnl_snapshot(runtime, settings)
        optimizer_plan = {}
        if runtime.session_factory is not None:
            try:
                with runtime.session_factory() as session:
                    optimizer_plan = maybe_apply_optimizer_plan(
                        session,
                        settings,
                        metrics={
                            "daily_pnl": state.daily_pnl,
                            "total_pnl": state.total_pnl,
                            "selected_markets": len(state.selected_markets),
                            "open_orders": len(state.orders),
                            "capital_deployed": _capital_deployed(state.orders, state.positions),
                        },
                    )
                if optimizer_plan.get("ran"):
                    clear_runtime_settings_cache()
                    logger.info(
                        "optimizer_plan_applied",
                        action=optimizer_plan.get("action"),
                        changed=optimizer_plan.get("changed"),
                    )
            except Exception as exc:
                optimizer_plan = {"ran": False, "reason": "error", "error": str(exc)}
                logger.warning("optimizer_plan_failed", error=str(exc))
        shadow_profiles = await _run_shadow_strategy_profiles(settings, markets, books, trades)
        state.strategy_profiles = [
            _active_strategy_profile_payload(settings, state.orders),
            *shadow_profiles,
        ]
        save_status_snapshot(
            {
                "bot_status": state.bot_status,
                "trading_enabled": state.trading_enabled,
                "mode_warning": state.mode_warning,
                "allowed_categories": settings.allowed_categories,
                "updated_at": datetime.now(UTC).isoformat(),
                # The full active-markets list (up to 200 rows) is not shown in the
                # dashboard, so persist only its count. Selected markets (the ones
                # actually quoted) are small and stay. This keeps the snapshot — read
                # by the poller every cycle — tiny, avoiding large DB egress.
                "active_markets_count": len(state.active_markets),
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
                "strategy_profiles": state.strategy_profiles,
                "optimizer_controls": {
                    "blocked_market_ids": sorted(optimizer_controls.blocked_market_ids),
                    "scaled_market_ids": sorted(optimizer_controls.scaled_market_ids),
                    "summary": (optimizer_controls.report or {}).get("summary", {}),
                },
                "optimizer_plan": optimizer_plan,
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
