from datetime import UTC, datetime, timedelta

from polymarket_mm_bot.config import Settings
from polymarket_mm_bot.database.orm import Base, BotConfigRow, TradeRow
from polymarket_mm_bot.reporting.auto_optimizer import maybe_apply_optimizer_plan


def _factory(tmp_path, monkeypatch):
    db = tmp_path / "auto-optimizer.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db.as_posix()}")
    from polymarket_mm_bot.config.settings import Settings as S
    from polymarket_mm_bot.config.settings import get_settings
    from polymarket_mm_bot.database.session import get_engine, get_session_factory

    get_settings.cache_clear()
    Base.metadata.create_all(get_engine())
    return get_session_factory(S())


def test_optimizer_plan_scales_when_profitable_candidates_need_more_volume(tmp_path, monkeypatch):
    factory = _factory(tmp_path, monkeypatch)
    now = datetime(2026, 7, 26, 12, tzinfo=UTC)
    settings = Settings(
        optimizer_plan_interval_seconds=60,
        order_size=50,
        max_order_size=90,
        max_position_per_market=220,
        max_total_exposure=6000,
        max_open_orders=500,
        max_markets_traded=45,
        market_score_threshold=64,
        min_liquidity=2000,
        target_spread=0.022,
        optimizer_scale_multiplier=2.4,
    )
    with factory() as session:
        session.add(
            BotConfigRow(
                id=1,
                config_json={
                    "order_size": 50,
                    "max_order_size": 90,
                    "max_position_per_market": 220,
                    "max_total_exposure": 6000,
                    "max_open_orders": 500,
                    "max_markets_traded": 45,
                    "market_score_threshold": 64,
                    "min_liquidity": 2000,
                    "target_spread": 0.022,
                    "optimizer_scale_multiplier": 2.4,
                },
                status_json={},
            )
        )
        session.add_all(
            [
                TradeRow(order_id="b1", market_id="winner", side="buy", price=0.10, size=50, timestamp=now),
                TradeRow(order_id="s1", market_id="winner", side="sell", price=0.12, size=25, timestamp=now + timedelta(minutes=1)),
                TradeRow(order_id="s2", market_id="winner", side="sell", price=0.12, size=25, timestamp=now + timedelta(minutes=2)),
                TradeRow(order_id="b2", market_id="winner", side="buy", price=0.10, size=1, timestamp=now + timedelta(minutes=3)),
            ]
        )
        session.commit()

        result = maybe_apply_optimizer_plan(
            session,
            settings,
            metrics={"daily_pnl": 0.5, "total_pnl": 8.9, "selected_markets": 3, "open_orders": 4, "capital_deployed": 54},
            now=now + timedelta(hours=1),
        )
        row = session.get(BotConfigRow, 1)

    assert result["ran"] is True
    assert result["action"] == "scale_profitable_flow"
    assert row.config_json["order_size"] > 50
    assert row.config_json["max_total_exposure"] > 6000
    assert row.config_json["optimizer_plan"]["changed"]["order_size"]["before"] == 50


def test_optimizer_plan_tightens_when_daily_pnl_is_negative(tmp_path, monkeypatch):
    factory = _factory(tmp_path, monkeypatch)
    now = datetime(2026, 7, 26, 12, tzinfo=UTC)
    settings = Settings(
        optimizer_plan_interval_seconds=60,
        order_size=50,
        max_order_size=90,
        target_spread=0.022,
        market_score_threshold=64,
        per_market_stop_loss=1.5,
    )
    with factory() as session:
        session.add(
            BotConfigRow(
                id=1,
                config_json={
                    "order_size": 50,
                    "max_order_size": 90,
                    "target_spread": 0.022,
                    "market_score_threshold": 64,
                    "per_market_stop_loss": 1.5,
                },
                status_json={},
            )
        )
        session.commit()

        result = maybe_apply_optimizer_plan(
            session,
            settings,
            metrics={"daily_pnl": -1.0, "total_pnl": 7.0, "selected_markets": 3, "open_orders": 4, "capital_deployed": 54},
            now=now,
        )
        row = session.get(BotConfigRow, 1)

    assert result["ran"] is True
    assert result["action"] == "tighten_quiet_or_loss"
    assert row.config_json["order_size"] < 50
    assert row.config_json["target_spread"] > 0.022


def test_optimizer_plan_tightens_when_capital_is_deployed_without_recent_fills(tmp_path, monkeypatch):
    factory = _factory(tmp_path, monkeypatch)
    now = datetime(2026, 7, 26, 12, tzinfo=UTC)
    settings = Settings(
        optimizer_plan_interval_seconds=60,
        order_size=150,
        max_order_size=150,
        target_spread=0.022,
        market_score_threshold=55,
        optimizer_scale_multiplier=3.0,
    )
    with factory() as session:
        session.add(
            BotConfigRow(
                id=1,
                config_json={
                    "order_size": 150,
                    "max_order_size": 150,
                    "target_spread": 0.022,
                    "market_score_threshold": 55,
                    "optimizer_scale_multiplier": 3.0,
                },
                status_json={},
            )
        )
        session.commit()

        result = maybe_apply_optimizer_plan(
            session,
            settings,
            metrics={
                "daily_pnl": 0.0,
                "total_pnl": 8.4,
                "selected_markets": 3,
                "open_orders": 3,
                "capital_deployed": 400,
            },
            now=now,
        )
        row = session.get(BotConfigRow, 1)

    assert result["ran"] is True
    assert result["action"] == "tighten_quiet_or_loss"
    assert row.config_json["order_size"] == 127.5
    assert row.config_json["optimizer_scale_multiplier"] == 2.75


def test_optimizer_plan_observes_historical_winners_without_recent_closed_flow(tmp_path, monkeypatch):
    factory = _factory(tmp_path, monkeypatch)
    now = datetime(2026, 7, 26, 12, tzinfo=UTC)
    old = now - timedelta(days=2)
    settings = Settings(
        optimizer_plan_interval_seconds=60,
        order_size=50,
        max_order_size=90,
        max_total_exposure=6000,
    )
    with factory() as session:
        session.add(
            BotConfigRow(
                id=1,
                config_json={"order_size": 50, "max_order_size": 90, "max_total_exposure": 6000},
                status_json={},
            )
        )
        session.add_all(
            [
                TradeRow(order_id="b1", market_id="old-winner", side="buy", price=0.10, size=50, timestamp=old),
                TradeRow(order_id="s1", market_id="old-winner", side="sell", price=0.12, size=25, timestamp=old + timedelta(minutes=1)),
                TradeRow(order_id="s2", market_id="old-winner", side="sell", price=0.12, size=25, timestamp=old + timedelta(minutes=2)),
                TradeRow(order_id="b2", market_id="old-winner", side="buy", price=0.10, size=1, timestamp=old + timedelta(minutes=3)),
            ]
        )
        session.commit()

        result = maybe_apply_optimizer_plan(
            session,
            settings,
            metrics={"daily_pnl": 0.0, "total_pnl": 8.4, "selected_markets": 3, "open_orders": 3, "capital_deployed": 54},
            now=now,
        )
        row = session.get(BotConfigRow, 1)

    assert result["ran"] is True
    assert result["action"] == "observe"
    assert row.config_json["order_size"] == 50


def test_optimizer_plan_waits_for_interval(tmp_path, monkeypatch):
    factory = _factory(tmp_path, monkeypatch)
    now = datetime(2026, 7, 26, 12, tzinfo=UTC)
    settings = Settings(optimizer_plan_interval_seconds=3600)
    with factory() as session:
        session.add(
            BotConfigRow(
                id=1,
                config_json={"optimizer_plan": {"last_run_at": now.isoformat()}},
                status_json={},
            )
        )
        session.commit()

        result = maybe_apply_optimizer_plan(
            session,
            settings,
            metrics={"daily_pnl": 0, "total_pnl": 0, "selected_markets": 0, "open_orders": 0, "capital_deployed": 0},
            now=now + timedelta(minutes=10),
        )

    assert result["ran"] is False
    assert result["reason"] == "interval_wait"
