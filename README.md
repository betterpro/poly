# polymarket-mm-bot

Production-oriented MVP for a low-risk Polymarket spread-capture and market-making bot.

The bot is paper-trading by default. It will not place real orders unless `PAPER_TRADING=false`, `RUN_MODE=live`, `LIVE_TRADING_CONFIRMED=true`, and live credentials are provided. The live execution adapter is intentionally guarded and must be reviewed before use.

## Setup

```powershell
copy .env.example .env
make setup
docker compose up -d postgres redis
make migrate
```

## Run Paper Trading

```powershell
make run-paper
```

In another terminal:

```powershell
make dashboard
```

Open `http://localhost:8000`.

## Run Tests

```powershell
make test
```

## Dashboard Endpoints

- `/health`
- `/markets`
- `/selected-markets`
- `/positions`
- `/orders`
- `/pnl`
- `/risk-events`
- `/strategy-status`

## What Remains Before Live Trading

- Replace the guarded `LiveExecutionEngine` stub with a reviewed `py_clob_client_v2` implementation.
- Run extended paper trading with production-like latency and market data.
- Add exchange-specific order reconciliation against authenticated open orders.
- Add persistent writes in the main loop for every order, fill, position, score, and risk event.
- Add alerting for drawdown, stale data, WebSocket disconnects, API errors, and exposure.
- Complete a legal, tax, jurisdiction, and Polymarket terms review.

## Security Checklist

- Keep `.env` out of git.
- Never log private keys, API secrets, or passphrases.
- Use a dedicated wallet with limited funds.
- Use paper trading for all development and testing.
- Rotate API credentials after any exposure.
- Keep live credentials out of Docker images and source code.

## Risk Checklist

- Confirm max daily loss, per-market exposure, total exposure, order size, and open-order caps.
- Confirm near-resolution markets are disabled unless intentionally enabled.
- Confirm stale WebSocket/API data stops quoting.
- Confirm consecutive order failures pause a market.
- Confirm every risk violation cancels open orders for the affected market.
- Confirm live mode requires manual config changes and credential presence.

## Notes

The data client uses public Polymarket Gamma and CLOB read endpoints for discovery and order books. Official docs currently describe authenticated trading through the newer `py_clob_client_v2` SDK with L1 private-key signing and L2 API credentials.
