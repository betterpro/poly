.PHONY: setup migrate test run-paper run-live backtest dashboard

setup:
	python -m pip install -e ".[dev]"
	if not exist .env copy .env.example .env

migrate:
	alembic upgrade head

test:
	pytest -q

dashboard:
	uvicorn polymarket_mm_bot.dashboard.app:app --host 0.0.0.0 --port 8000

run-paper:
	set PAPER_TRADING=true&& set LIVE_TRADING_CONFIRMED=false&& python -m polymarket_mm_bot.main

run-live:
	set PAPER_TRADING=false&& set RUN_MODE=live&& python -m polymarket_mm_bot.main

backtest:
	python -m polymarket_mm_bot.scripts.backtest_sample
