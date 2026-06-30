from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

import httpx
import structlog
import websockets

from polymarket_mm_bot.config import Settings
from polymarket_mm_bot.models import BookLevel, Market, OrderBook, Side, Trade

logger = structlog.get_logger()


class PolymarketDataClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.http = httpx.AsyncClient(timeout=15.0)

    async def close(self) -> None:
        await self.http.aclose()

    async def fetch_active_markets(self, limit: int = 200) -> list[Market]:
        params = {"active": "true", "closed": "false", "limit": limit}
        response = await self.http.get(f"{self.settings.polymarket_gamma_host}/markets", params=params)
        response.raise_for_status()
        payload = response.json()
        rows = payload if isinstance(payload, list) else payload.get("data", [])
        return [self._normalize_market(row) for row in rows if row]

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
        if response.status_code == 404:
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

    def _normalize_market(self, row: dict[str, Any]) -> Market:
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
        return Market(
            condition_id=str(row.get("conditionId") or row.get("condition_id") or row.get("id")),
            question=str(row.get("question") or row.get("title") or ""),
            slug=row.get("slug"),
            category=row.get("category"),
            active=bool(row.get("active", True)),
            closed=bool(row.get("closed", False)),
            paused=bool(row.get("paused", False)),
            volume=float(row.get("volume") or row.get("volumeNum") or 0),
            liquidity=float(row.get("liquidity") or row.get("liquidityNum") or 0),
            end_date=end_date,
            yes_token_id=str(token_ids[0]) if len(token_ids) > 0 else None,
            no_token_id=str(token_ids[1]) if len(token_ids) > 1 else None,
            metadata=row,
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
        return Trade(
            market_id=str(row.get("market") or row.get("market_id") or market_id),
            token_id=row.get("asset_id") or row.get("token_id"),
            price=float(row.get("price", 0)),
            size=float(row.get("size", 0)),
            side=Side(side.lower()) if side else None,
        )
