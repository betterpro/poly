from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from polymarket_mm_bot.config import Settings
from polymarket_mm_bot.database.orm import MarketRow, TradeRow


@dataclass
class _MarketLedger:
    market_id: str
    question: str | None = None
    buys: int = 0
    sells: int = 0
    bought_notional: float = 0.0
    sold_notional: float = 0.0
    yes_size: float = 0.0
    avg_yes_price: float = 0.0
    realized_pnl: float = 0.0

    def apply(self, side: str | None, price: float, size: float) -> None:
        if size <= 0:
            return
        notional = price * size
        if str(side).lower() == "buy":
            self.buys += 1
            self.bought_notional += notional
            total_cost = self.avg_yes_price * self.yes_size + notional
            self.yes_size += size
            self.avg_yes_price = total_cost / self.yes_size if self.yes_size > 0 else 0.0
            return
        if str(side).lower() != "sell":
            return
        self.sells += 1
        self.sold_notional += notional
        closed = min(size, self.yes_size)
        self.realized_pnl += closed * (price - self.avg_yes_price)
        self.yes_size = max(0.0, self.yes_size - closed)
        if self.yes_size <= 1e-9:
            self.yes_size = 0.0
            self.avg_yes_price = 0.0

    @property
    def fills(self) -> int:
        return self.buys + self.sells

    @property
    def traded_notional(self) -> float:
        return self.bought_notional + self.sold_notional

    @property
    def roi(self) -> float:
        if self.bought_notional <= 0:
            return 0.0
        return self.realized_pnl / self.bought_notional

    def recommendation(self) -> str:
        if self.fills < 4:
            return "wait_more_data"
        if self.realized_pnl > 0 and self.roi >= 0.015:
            return "candidate_scale_up"
        if self.realized_pnl < -1.0 or self.roi <= -0.015:
            return "reduce_or_block"
        return "keep_observing"

    def payload(self) -> dict:
        return {
            "market_id": self.market_id,
            "question": self.question,
            "fills": self.fills,
            "buys": self.buys,
            "sells": self.sells,
            "bought_notional": round(self.bought_notional, 4),
            "sold_notional": round(self.sold_notional, 4),
            "realized_pnl": round(self.realized_pnl, 4),
            "roi_pct": round(self.roi * 100, 2),
            "open_yes_size": round(self.yes_size, 6),
            "avg_yes_price": round(self.avg_yes_price, 6),
            "recommendation": self.recommendation(),
        }


def build_optimizer_report(session: Session, *, limit: int = 20) -> dict:
    markets = {
        row.condition_id: row.question
        for row in session.query(MarketRow.condition_id, MarketRow.question).all()
    }
    rows = (
        session.query(TradeRow)
        .filter(TradeRow.size > 0)
        .order_by(TradeRow.timestamp.asc(), TradeRow.id.asc())
        .all()
    )
    ledgers: dict[str, _MarketLedger] = {}
    for row in rows:
        ledger = ledgers.setdefault(
            row.market_id,
            _MarketLedger(market_id=row.market_id, question=markets.get(row.market_id)),
        )
        ledger.apply(row.side, float(row.price or 0.0), float(row.size or 0.0))

    ranked = sorted(ledgers.values(), key=lambda item: item.realized_pnl, reverse=True)
    payloads = [ledger.payload() for ledger in ranked]
    scale = [row for row in payloads if row["recommendation"] == "candidate_scale_up"]
    reduce = [row for row in payloads if row["recommendation"] == "reduce_or_block"]
    total_realized = sum(ledger.realized_pnl for ledger in ledgers.values())
    bought_notional = sum(ledger.bought_notional for ledger in ledgers.values())
    return {
        "summary": {
            "markets": len(ledgers),
            "fills": len(rows),
            "realized_pnl": round(total_realized, 4),
            "bought_notional": round(bought_notional, 4),
            "roi_pct": round((total_realized / bought_notional * 100) if bought_notional else 0.0, 2),
            "scale_candidates": len(scale),
            "reduce_candidates": len(reduce),
        },
        "scale_candidates": scale[:limit],
        "reduce_candidates": reduce[:limit],
        "markets": payloads[:limit],
    }


def build_optimizer_controls(session: Session, settings: Settings) -> dict:
    if not getattr(settings, "optimizer_auto_enabled", True):
        return {"blocked_market_ids": [], "scaled_market_ids": [], "report": build_optimizer_report(session)}
    report = build_optimizer_report(session, limit=100)
    return {
        "blocked_market_ids": [row["market_id"] for row in report["reduce_candidates"]],
        "scaled_market_ids": [row["market_id"] for row in report["scale_candidates"]],
        "report": report,
    }
