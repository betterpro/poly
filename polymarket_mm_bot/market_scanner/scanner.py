from datetime import UTC, datetime

import numpy as np
import structlog

from polymarket_mm_bot.config import Settings
from polymarket_mm_bot.models import Market, MarketScore, OrderBook, Trade
from polymarket_mm_bot.utils import clamp, market_dict_matches_categories

logger = structlog.get_logger()


class MarketScanner:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._allowed_categories = {category.lower() for category in settings.allowed_categories}

    def _category_allowed(self, market: Market) -> bool:
        return market_dict_matches_categories(market.model_dump(mode="json"), self._allowed_categories)

    def score_market(
        self,
        market: Market,
        order_book: OrderBook | None = None,
        recent_trades: list[Trade] | None = None,
    ) -> MarketScore:
        reasons: list[str] = []
        if not market.active or market.closed or market.paused:
            return MarketScore(market_id=market.condition_id, score=0, rejected=True, reasons=["inactive"])
        if not self._category_allowed(market):
            return MarketScore(
                market_id=market.condition_id,
                score=0,
                rejected=True,
                reasons=["category_not_allowed"],
            )
        if order_book is None:
            return MarketScore(
                market_id=market.condition_id,
                score=0,
                rejected=True,
                reasons=["missing_order_book"],
            )

        volume_score = clamp(market.volume / max(self.settings.min_volume, 1) * 20, 0, 20)
        liquidity_score = clamp(market.liquidity / max(self.settings.min_liquidity, 1) * 20, 0, 20)
        if market.volume < self.settings.min_volume:
            reasons.append("volume_below_min")
        if market.liquidity < self.settings.min_liquidity:
            reasons.append("liquidity_below_min")

        spread_score = 0.0
        depth_score = 0.0
        stale_score = 10.0
        if order_book:
            spread = order_book.spread
            if spread is None or spread <= 0:
                reasons.append("spread_too_small")
            elif spread > 0.15:
                reasons.append("spread_manipulation_risk")
                spread_score = 4
            else:
                spread_score = clamp((0.08 - abs(spread - 0.03)) / 0.08 * 15, 0, 15)
            depth = order_book.bid_depth + order_book.ask_depth
            depth_score = clamp(depth / max(self.settings.min_liquidity, 1) * 15, 0, 15)
            age = (datetime.now(UTC) - order_book.updated_at).total_seconds()
            stale_score = 0 if age > self.settings.stale_data_seconds else 10
            if stale_score == 0:
                reasons.append("stale_order_book")

        trades = recent_trades or []
        trade_count_score = clamp(len(trades) / 50 * 10, 0, 10)
        volatility_score = 10.0
        if len(trades) >= 5:
            prices = np.array([trade.price for trade in trades])
            volatility = float(np.std(prices))
            volatility_score = clamp((0.08 - volatility) / 0.08 * 10, 0, 10)
            if volatility > 0.12:
                reasons.append("high_volatility")

        time_score = 10.0
        if market.end_date:
            hours = (market.end_date - datetime.now(UTC)).total_seconds() / 3600
            if hours < self.settings.min_time_to_resolution_hours and not self.settings.allow_near_resolution:
                reasons.append("near_resolution")
                time_score = 0
            else:
                time_score = clamp(hours / 72 * 10, 3, 10)

        category_score = 5.0 if self._category_allowed(market) else 2.0
        manipulation_penalty = 10.0 if "spread_manipulation_risk" in reasons else 0.0

        score = (
            volume_score
            + liquidity_score
            + spread_score
            + depth_score
            + stale_score
            + trade_count_score
            + volatility_score
            + time_score
            + category_score
            - manipulation_penalty
        )
        rejected = score < self.settings.market_score_threshold or any(
            reason in reasons
            for reason in [
                "volume_below_min",
                "liquidity_below_min",
                "near_resolution",
                "stale_order_book",
                "missing_order_book",
            ]
        )
        event = "market_rejected" if rejected else "market_selected"
        logger.info(event, market_id=market.condition_id, score=round(score, 2), reasons=reasons)
        return MarketScore(market_id=market.condition_id, score=round(score, 2), rejected=rejected, reasons=reasons)

    def select_markets(
        self,
        markets: list[Market],
        books: dict[str, OrderBook],
        trades: dict[str, list[Trade]],
    ) -> list[Market]:
        scored = [
            (market, self.score_market(market, books.get(market.condition_id), trades.get(market.condition_id, [])))
            for market in markets
        ]
        accepted = [market for market, score in scored if not score.rejected]
        accepted.sort(
            key=lambda market: next(item[1].score for item in scored if item[0].condition_id == market.condition_id),
            reverse=True,
        )
        return accepted[: self.settings.max_markets_traded]
