from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from polymarket_mm_bot.database.orm import BotOrderRow, PnlSnapshotRow, PositionRow, RiskEventRow, TradeRow
from polymarket_mm_bot.models import BotOrder, OrderStatus, Position


def _as_utc_date(value: datetime | None) -> date | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).date()


def save_pnl_snapshot(
    session: Session,
    *,
    daily_pnl: float,
    total_pnl: float,
    unrealized_pnl: float,
    metadata: dict | None = None,
) -> None:
    """Append a point to the pnl_snapshots performance time-series."""
    session.add(
        PnlSnapshotRow(
            timestamp=datetime.now(UTC),
            daily_pnl=daily_pnl,
            total_pnl=total_pnl,
            unrealized_pnl=unrealized_pnl,
            metadata_json=metadata or {},
        )
    )
    session.commit()


def _parse_fill_timestamp(value: str | datetime | None) -> datetime:
    if isinstance(value, datetime):
        timestamp = value
    elif isinstance(value, str) and value:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        timestamp = datetime.now(UTC)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC)


def save_fill_trade(session: Session, fill: dict) -> bool:
    """Persist a bot fill into trades, returning False when it already exists."""
    order_id = fill.get("order_id")
    timestamp = _parse_fill_timestamp(fill.get("at") or fill.get("timestamp"))
    market_id = fill.get("market_id")
    if not market_id:
        return False
    price = float(fill.get("price") or 0.0)
    size = float(fill.get("size") or 0.0)
    if size <= 0:
        return False
    if order_id:
        existing = (
            session.query(TradeRow)
            .filter(
                TradeRow.order_id == order_id,
                TradeRow.timestamp == timestamp,
                TradeRow.price == price,
                TradeRow.size == size,
            )
            .first()
        )
        if existing is not None:
            return False
    session.add(
        TradeRow(
            order_id=order_id,
            market_id=str(market_id),
            token_id=fill.get("token_id"),
            price=price,
            size=size,
            side=fill.get("side"),
            timestamp=timestamp,
        )
    )
    session.commit()
    return True


def load_daily_pnl_history(session: Session, *, limit: int = 30) -> list[dict]:
    """Return daily PnL history from the snapshot time-series.

    Each day uses the last total_pnl snapshot for that UTC date. Daily profit is
    the change versus the previous tracked day; the first day has no previous
    baseline and reports 0 daily_pnl.
    """
    rows = (
        session.query(PnlSnapshotRow)
        .order_by(PnlSnapshotRow.timestamp.asc(), PnlSnapshotRow.id.asc())
        .all()
    )
    last_by_day: dict[date, PnlSnapshotRow] = {}
    for row in rows:
        day = _as_utc_date(row.timestamp)
        if day is not None:
            last_by_day[day] = row

    history: list[dict] = []
    previous_total: float | None = None
    for day in sorted(last_by_day):
        row = last_by_day[day]
        total = float(row.total_pnl or 0.0)
        daily = 0.0 if previous_total is None else total - previous_total
        history.append(
            {
                "date": day.isoformat(),
                "daily_pnl": round(daily, 4),
                "total_pnl": round(total, 4),
                "unrealized_pnl": round(float(row.unrealized_pnl or 0.0), 4),
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            }
        )
        previous_total = total
    return history[-limit:]


def load_orders(session: Session) -> dict[str, BotOrder]:
    rows = session.query(BotOrderRow).all()
    return {
        row.client_order_id: BotOrder(
            client_order_id=row.client_order_id,
            market_id=row.market_id,
            token_id=row.token_id,
            side=row.side,
            outcome=row.outcome,
            price=row.price,
            size=row.size,
            filled_size=row.filled_size,
            status=row.status,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    }


def load_positions(session: Session) -> dict[str, Position]:
    rows = session.query(PositionRow).all()
    return {
        row.market_id: Position(
            market_id=row.market_id,
            yes_size=row.yes_size,
            no_size=row.no_size,
            realized_pnl=row.realized_pnl,
            avg_yes_price=row.avg_yes_price,
            avg_no_price=row.avg_no_price,
        )
        for row in rows
    }


def save_order(session: Session, order: BotOrder) -> None:
    row = session.get(BotOrderRow, order.client_order_id)
    if row is None:
        row = BotOrderRow(client_order_id=order.client_order_id)
        session.add(row)
    row.market_id = order.market_id
    row.token_id = order.token_id
    row.side = order.side.value
    row.outcome = order.outcome.value
    row.price = order.price
    row.size = order.size
    row.filled_size = order.filled_size
    row.status = order.status.value
    session.commit()


def save_orders(session: Session, orders: Iterable[BotOrder]) -> None:
    for order in orders:
        row = session.get(BotOrderRow, order.client_order_id)
        if row is None:
            row = BotOrderRow(client_order_id=order.client_order_id)
            session.add(row)
        row.market_id = order.market_id
        row.token_id = order.token_id
        row.side = order.side.value
        row.outcome = order.outcome.value
        row.price = order.price
        row.size = order.size
        row.filled_size = order.filled_size
        row.status = order.status.value
    session.commit()


def save_position(session: Session, position: Position) -> None:
    row = session.get(PositionRow, position.market_id)
    if row is None:
        row = PositionRow(market_id=position.market_id)
        session.add(row)
    row.yes_size = position.yes_size
    row.no_size = position.no_size
    row.realized_pnl = position.realized_pnl
    row.avg_yes_price = position.avg_yes_price
    row.avg_no_price = position.avg_no_price
    session.commit()


def save_positions(session: Session, positions: Iterable[Position]) -> None:
    for position in positions:
        row = session.get(PositionRow, position.market_id)
        if row is None:
            row = PositionRow(market_id=position.market_id)
            session.add(row)
        row.yes_size = position.yes_size
        row.no_size = position.no_size
        row.realized_pnl = position.realized_pnl
        row.avg_yes_price = position.avg_yes_price
        row.avg_no_price = position.avg_no_price
    session.commit()


def save_risk_event(session: Session, code: str, market_id: str | None, message: str) -> None:
    session.add(
        RiskEventRow(
            market_id=market_id,
            code=code,
            message=message,
            metadata_json={},
        )
    )
    session.commit()


def open_or_live_orders(orders: dict[str, BotOrder]) -> list[BotOrder]:
    return [
        order
        for order in orders.values()
        if order.status
        in {
            OrderStatus.OPEN,
            OrderStatus.PARTIALLY_FILLED,
        }
    ]
