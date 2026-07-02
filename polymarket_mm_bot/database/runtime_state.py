from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.orm import Session

from polymarket_mm_bot.database.orm import BotOrderRow, PositionRow, RiskEventRow
from polymarket_mm_bot.models import BotOrder, OrderStatus, Position


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
