from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from polymarket_mm_bot.config import Settings
from polymarket_mm_bot.database.orm import BotConfigRow
from polymarket_mm_bot.reporting.optimizer import build_optimizer_report
from polymarket_mm_bot.utils import clamp


_SETTINGS_KEYS = {
    "max_daily_loss",
    "per_market_stop_loss",
    "optimizer_auto_enabled",
    "optimizer_scale_multiplier",
    "max_position_per_market",
    "max_total_exposure",
    "max_order_size",
    "max_open_orders",
    "max_markets_traded",
    "min_liquidity",
    "market_score_threshold",
    "target_spread",
    "order_size",
}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _current_config(row: BotConfigRow | None, settings: Settings) -> dict:
    config = dict(row.config_json) if row is not None and row.config_json else {}
    for key in _SETTINGS_KEYS:
        config.setdefault(key, getattr(settings, key))
    return config


def _bounded(value: float, *, floor: float, ceiling: float, ndigits: int = 4) -> float:
    return round(clamp(value, floor, ceiling), ndigits)


def _next_scaled_config(config: dict, settings: Settings, metrics: dict, report: dict) -> tuple[str, dict]:
    daily_pnl = float(metrics.get("daily_pnl") or 0.0)
    selected_markets = int(metrics.get("selected_markets") or 0)
    scale_count = int((report.get("summary") or {}).get("scale_candidates") or 0)
    reduce_count = int((report.get("summary") or {}).get("reduce_candidates") or 0)
    roi_pct = float((report.get("summary") or {}).get("roi_pct") or 0.0)
    target_daily = float(getattr(settings, "optimizer_target_daily_pnl", 100.0))
    order_ceiling = float(getattr(settings, "optimizer_max_order_size_ceiling", 150.0))
    exposure_ceiling = float(getattr(settings, "optimizer_max_exposure_ceiling", 10_000.0))

    updated = dict(config)
    updated["optimizer_auto_enabled"] = True

    if daily_pnl < 0 or roi_pct <= -5.0:
        updated["order_size"] = _bounded(float(config["order_size"]) * 0.85, floor=10.0, ceiling=order_ceiling)
        updated["max_order_size"] = _bounded(float(config["max_order_size"]) * 0.9, floor=20.0, ceiling=order_ceiling)
        updated["target_spread"] = _bounded(float(config["target_spread"]) + 0.003, floor=0.018, ceiling=0.05)
        updated["market_score_threshold"] = _bounded(float(config["market_score_threshold"]) + 3, floor=55, ceiling=85, ndigits=2)
        updated["per_market_stop_loss"] = _bounded(float(config["per_market_stop_loss"]) * 0.9, floor=0.75, ceiling=3.0)
        return "tighten_risk", updated

    if daily_pnl < target_daily and scale_count > 0:
        updated["order_size"] = _bounded(float(config["order_size"]) * 1.15, floor=10.0, ceiling=order_ceiling)
        updated["max_order_size"] = _bounded(max(float(config["max_order_size"]) * 1.15, updated["order_size"] * 1.6), floor=20.0, ceiling=order_ceiling)
        updated["max_position_per_market"] = _bounded(float(config["max_position_per_market"]) * 1.12, floor=50.0, ceiling=order_ceiling * 3)
        updated["max_total_exposure"] = _bounded(float(config["max_total_exposure"]) * 1.18, floor=500.0, ceiling=exposure_ceiling)
        updated["optimizer_scale_multiplier"] = _bounded(float(config["optimizer_scale_multiplier"]) + 0.15, floor=1.0, ceiling=3.0)
        updated["max_open_orders"] = int(clamp(int(config["max_open_orders"]) + 40, 20, 700))
        updated["max_markets_traded"] = int(clamp(int(config["max_markets_traded"]) + 5, 5, 70))
        if selected_markets < 8:
            updated["market_score_threshold"] = _bounded(float(config["market_score_threshold"]) - 2, floor=55, ceiling=85, ndigits=2)
            updated["min_liquidity"] = _bounded(float(config["min_liquidity"]) * 0.9, floor=1000.0, ceiling=10_000.0)
        if reduce_count == 0:
            updated["target_spread"] = _bounded(float(config["target_spread"]) - 0.001, floor=0.018, ceiling=0.05)
        return "scale_profitable_flow", updated

    return "observe", updated


def maybe_apply_optimizer_plan(
    session: Session,
    settings: Settings,
    *,
    metrics: dict,
    now: datetime | None = None,
) -> dict:
    if not getattr(settings, "optimizer_plan_enabled", True):
        return {"ran": False, "reason": "disabled"}
    if not settings.paper_trading:
        return {"ran": False, "reason": "paper_only"}

    now = now or _utcnow()
    row = session.get(BotConfigRow, 1)
    if row is None:
        row = BotConfigRow(id=1, config_json={}, status_json={})
        session.add(row)
        session.flush()

    config = _current_config(row, settings)
    state = dict(config.get("optimizer_plan") or {})
    last_run = _parse_dt(state.get("last_run_at"))
    interval = int(getattr(settings, "optimizer_plan_interval_seconds", 3600))
    if last_run is not None and (now - last_run).total_seconds() < interval:
        next_run = last_run.timestamp() + interval
        return {
            "ran": False,
            "reason": "interval_wait",
            "last_run_at": last_run.isoformat(),
            "next_run_at": datetime.fromtimestamp(next_run, tz=UTC).isoformat(),
        }

    report = build_optimizer_report(session, limit=100)
    action, updated = _next_scaled_config(config, settings, metrics, report)
    changed = {
        key: {"before": config.get(key), "after": updated.get(key)}
        for key in _SETTINGS_KEYS
        if updated.get(key) != config.get(key)
    }
    summary = report.get("summary") or {}
    plan_state = {
        "last_run_at": now.isoformat(),
        "action": action,
        "changed": changed,
        "metrics": {
            "daily_pnl": round(float(metrics.get("daily_pnl") or 0.0), 4),
            "total_pnl": round(float(metrics.get("total_pnl") or 0.0), 4),
            "selected_markets": int(metrics.get("selected_markets") or 0),
            "open_orders": int(metrics.get("open_orders") or 0),
            "capital_deployed": round(float(metrics.get("capital_deployed") or 0.0), 4),
        },
        "optimizer_summary": {
            "fills": summary.get("fills"),
            "realized_pnl": summary.get("realized_pnl"),
            "roi_pct": summary.get("roi_pct"),
            "scale_candidates": summary.get("scale_candidates"),
            "reduce_candidates": summary.get("reduce_candidates"),
        },
    }
    for key in _SETTINGS_KEYS:
        if key in updated:
            config[key] = updated[key]
    config["optimizer_plan"] = plan_state
    row.config_json = config
    session.commit()
    return {"ran": True, **plan_state}
