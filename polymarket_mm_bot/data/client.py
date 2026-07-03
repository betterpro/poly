from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
import websockets

from polymarket_mm_bot.config import Settings
from polymarket_mm_bot.models import BookLevel, Market, OrderBook, Side, Trade
from polymarket_mm_bot.utils import event_belongs_to_category

logger = structlog.get_logger()


class PolymarketDataClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.http = httpx.AsyncClient(timeout=15.0)

    async def close(self) -> None:
        await self.http.aclose()

    async def fetch_active_markets(self, limit: int = 200, categories: list[str] | None = None) -> list[Market]:
        if categories:
            return await self._fetch_markets_for_categories(categories, limit)
        params = {"active": "true", "closed": "false", "limit": limit}
        response = await self.http.get(f"{self.settings.polymarket_gamma_host}/markets", params=params)
        response.raise_for_status()
        payload = response.json()
        rows = payload if isinstance(payload, list) else payload.get("data", [])
        return [self._normalize_market(row) for row in rows if row]

    async def _fetch_markets_for_categories(self, categories: list[str], limit: int) -> list[Market]:
        seen: dict[str, Market] = {}
        per_category = max(limit // max(len(categories), 1), 25)
        for category in categories:
            params = {
                "active": "true",
                "closed": "false",
                "limit": per_category,
                "tag_slug": category,
            }
            response = await self.http.get(f"{self.settings.polymarket_gamma_host}/events", params=params)
            response.raise_for_status()
            payload = response.json()
            events = payload if isinstance(payload, list) else payload.get("data", [])
            for event in events or []:
                if not isinstance(event, dict) or not event_belongs_to_category(event, category):
                    continue
                for row in event.get("markets") or []:
                    market = self._normalize_market(row, category=category, event=event)
                    if market.condition_id and market.condition_id not in seen:
                        seen[market.condition_id] = market
        markets = list(seen.values())
        logger.info(
            "markets_fetched_for_categories",
            categories=categories,
            count=len(markets),
        )
        return markets[:limit]

    async def fetch_market_metadata(self, condition_id: str) -> dict[str, Any]:
        response = await self.http.get(f"{self.settings.polymarket_host}/clob-markets/{condition_id}")
        response.raise_for_status()
        return response.json()

    async def fetch_order_book(self, token_id: str, market_id: str | None = None) -> OrderBook:
        response = await self.http.get(f"{self.settings.polymarket_host}/book", params={"token_id": token_id})
        response.raise_for_status()
        return self._normalize_book(response.json(), market_id or token_id, token_id)

    async def fetch_recent_trades(self, market_id: str, limit: int = 100) -> list[Trade]:
        response = await self.http.get(
            f"{self.settings.polymarket_host}/trades",
            params={"market": market_id, "limit": limit},
        )
        if response.status_code in {401, 403, 404}:
            return []
        response.raise_for_status()
        payload = response.json()
        rows = payload if isinstance(payload, list) else payload.get("data", [])
        return [self._normalize_trade(row, market_id) for row in rows]

    async def subscribe_order_books(self, token_ids: list[str]) -> AsyncIterator[dict[str, Any]]:
        while True:
            try:
                async with websockets.connect(self.settings.polymarket_ws_url, ping_interval=10) as websocket:
                    await websocket.send(json.dumps({"assets_ids": token_ids, "type": "market"}))
                    async for message in websocket:
                        yield {"raw": message}
            except Exception as exc:  # pragma: no cover - network recovery path
                logger.warning("websocket_disconnect", error=str(exc))
                await asyncio.sleep(3)

    def _normalize_market(
        self,
        row: dict[str, Any],
        *,
        category: str | None = None,
        event: dict[str, Any] | None = None,
    ) -> Market:
        token_ids = row.get("clobTokenIds") or row.get("clob_token_ids") or []
        if isinstance(token_ids, str):
            token_ids = [part.strip().strip('"') for part in token_ids.strip("[]").split(",") if part.strip()]
        end_date_raw = row.get("endDate") or row.get("end_date")
        end_date = None
        if end_date_raw:
            try:
                end_date = datetime.fromisoformat(str(end_date_raw).replace("Z", "+00:00"))
            except ValueError:
                end_date = None
        metadata = dict(row)
        if event:
            metadata["event"] = event
            metadata["tags"] = event.get("tags") or metadata.get("tags")
        resolved_category = category or row.get("category")
        return Market(
            condition_id=str(row.get("conditionId") or row.get("condition_id") or row.get("id")),
            question=str(row.get("question") or row.get("title") or ""),
            slug=row.get("slug"),
            category=resolved_category,
            active=bool(row.get("active", True)),
            closed=bool(row.get("closed", False)),
            paused=bool(row.get("paused", False)),
            volume=float(row.get("volume") or row.get("volumeNum") or 0),
            liquidity=float(row.get("liquidity") or row.get("liquidityNum") or 0),
            end_date=end_date,
            yes_token_id=str(token_ids[0]) if len(token_ids) > 0 else None,
            no_token_id=str(token_ids[1]) if len(token_ids) > 1 else None,
            metadata=metadata,
        )

    def _normalize_book(self, row: dict[str, Any], market_id: str, token_id: str) -> OrderBook:
        def levels(values: list[dict[str, Any]]) -> list[BookLevel]:
            parsed = []
            for level in values or []:
                parsed.append(BookLevel(price=float(level["price"]), size=float(level["size"])))
            return parsed

        return OrderBook(
            market_id=market_id,
            token_id=token_id,
            bids=levels(row.get("bids", [])),
            asks=levels(row.get("asks", [])),
        )

    def _normalize_trade(self, row: dict[str, Any], market_id: str) -> Trade:
        side = row.get("side")
        timestamp = self._parse_trade_timestamp(row)
        trade = Trade(
            market_id=str(row.get("market") or row.get("market_id") or market_id),
            token_id=row.get("asset_id") or row.get("token_id"),
            price=float(row.get("price", 0)),
            size=float(row.get("size", 0)),
            side=Side(side.lower()) if side else None,
        )
        if timestamp is not None:
            trade.timestamp = timestamp
        return trade

    @staticmethod
    def _parse_trade_timestamp(row: dict[str, Any]) -> datetime | None:
        raw = row.get("match_time") or row.get("timestamp") or row.get("last_update")
        if raw is None:
            return None
        try:
            return datetime.fromtimestamp(float(raw), tz=UTC)
        except (TypeError, ValueError, OSError):
            pass
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return None
