"""Adapter between the bot and the Polymarket CLOB SDK (py_clob_client_v2).

All third-party SDK calls live behind the :class:`ClobGateway` protocol so the
execution engine can be unit-tested with a fake gateway and never imports the SDK
at module load time. The concrete :class:`PyClobV2Gateway` is intentionally kept
thin and is excluded from coverage because it can only be exercised against the
live exchange.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import structlog

from polymarket_mm_bot.config import Settings
from polymarket_mm_bot.models import Side

logger = structlog.get_logger()


class ClobUnavailable(RuntimeError):
    """Raised when the live CLOB SDK/credentials are not usable."""


@dataclass(frozen=True)
class PlacedOrder:
    order_id: str
    status: str = "live"


@dataclass(frozen=True)
class ExchangeTrade:
    order_id: str
    price: float
    size: float


class ClobGateway(Protocol):
    """Minimal surface the execution engine needs from the exchange."""

    def place_order(self, token_id: str, side: Side, price: float, size: float) -> PlacedOrder: ...

    def cancel(self, order_id: str) -> None: ...

    def cancel_market(self, token_id: str) -> None: ...

    def open_order_ids(self) -> set[str]: ...

    def trades(self) -> list[ExchangeTrade]: ...

    def collateral_balance(self) -> float: ...

    def collateral_allowance(self) -> float: ...


class PyClobV2Gateway:  # pragma: no cover - requires the live exchange + SDK
    """Concrete gateway backed by py_clob_client_v2.

    Field/method names follow the py-clob-client API. If the installed
    py_clob_client_v2 differs, adjust the thin mappings here only.
    """

    def __init__(self, settings: Settings):
        try:
            from py_clob_client_v2 import ClobClient
            from py_clob_client_v2.clob_types import ApiCreds
        except Exception as exc:  # ImportError or SDK-internal error
            raise ClobUnavailable(
                "py_clob_client_v2 is not installed. Install the live extra: pip install '.[live]'"
            ) from exc

        self._settings = settings
        self._client = ClobClient(
            settings.polymarket_host,
            key=settings.polymarket_private_key,
            chain_id=settings.polymarket_chain_id,
            signature_type=settings.signature_type,
            funder=settings.polymarket_funder_address,
        )
        if settings.polymarket_api_key and settings.polymarket_api_secret and settings.polymarket_api_passphrase:
            creds = ApiCreds(
                api_key=settings.polymarket_api_key,
                api_secret=settings.polymarket_api_secret,
                api_passphrase=settings.polymarket_api_passphrase,
            )
        else:
            creds = self._client.create_or_derive_api_key()
        self._client.set_api_creds(creds)

    def place_order(self, token_id: str, side: Side, price: float, size: float) -> PlacedOrder:
        from py_clob_client_v2.clob_types import OrderArgs, OrderType
        from py_clob_client_v2.order_builder.constants import BUY, SELL

        args = OrderArgs(
            token_id=token_id,
            price=price,
            size=size,
            side=BUY if side == Side.BUY else SELL,
        )
        signed = self._client.create_order(args)
        resp = self._client.post_order(signed, OrderType.GTC)
        order_id = resp.get("orderID") or resp.get("orderId") or resp.get("id") or ""
        if not order_id:
            raise ClobUnavailable(f"Order placement returned no id: {resp}")
        return PlacedOrder(order_id=str(order_id), status=str(resp.get("status", "live")))

    def cancel(self, order_id: str) -> None:
        self._client.cancel(order_id=order_id)

    def cancel_market(self, token_id: str) -> None:
        self._client.cancel_market_orders(asset_id=token_id)

    def open_order_ids(self) -> set[str]:
        rows = self._client.get_orders() or []
        ids: set[str] = set()
        for row in rows:
            oid = row.get("id") or row.get("orderID") or row.get("orderId")
            if oid:
                ids.add(str(oid))
        return ids

    def trades(self) -> list[ExchangeTrade]:
        rows = self._client.get_trades() or []
        out: list[ExchangeTrade] = []
        for row in rows:
            oid = row.get("taker_order_id") or row.get("order_id") or row.get("orderID")
            if not oid:
                continue
            out.append(
                ExchangeTrade(
                    order_id=str(oid),
                    price=float(row.get("price", 0) or 0),
                    size=float(row.get("size", 0) or 0),
                )
            )
        return out

    def _collateral_params(self):
        from py_clob_client_v2.clob_types import AssetType, BalanceAllowanceParams

        return BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)

    def collateral_balance(self) -> float:
        data = self._client.get_balance_allowance(self._collateral_params()) or {}
        return float(data.get("balance", 0) or 0)

    def collateral_allowance(self) -> float:
        data = self._client.get_balance_allowance(self._collateral_params()) or {}
        allowance = data.get("allowance")
        if allowance is None:
            allowances = data.get("allowances") or {}
            allowance = max((float(v) for v in allowances.values()), default=0)
        return float(allowance or 0)


def build_gateway(settings: Settings) -> ClobGateway:
    """Construct the live gateway; raises ClobUnavailable if the SDK is missing."""
    return PyClobV2Gateway(settings)
