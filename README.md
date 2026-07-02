# polymarket-mm-bot

Production-oriented MVP for a low-risk Polymarket spread-capture and market-making bot.

The bot is paper-trading by default. Live order placement is implemented (`LiveExecutionEngine` via the `py_clob_client_v2` gateway) but heavily gated: it will not place real orders unless `PAPER_TRADING=false`, `RUN_MODE=live`, `LIVE_TRADING_CONFIRMED=true`, wallet credentials are present, an authenticator (TOTP) confirmation is used to switch modes, and a startup preflight (exchange reachable, USDC balance + allowance sufficient) passes.

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

## Going Live

Live trading requires the optional CLOB SDK and several deliberate steps. Do this
only after extended paper trading and with a dedicated, limited-funds wallet.

1. Install the live extra: `pip install '.[live]'` (pulls `py-clob-client-v2`).
2. Fund the trading wallet with USDC and approve the Polymarket exchange USDC
   allowance for at least `MAX_TOTAL_EXPOSURE` (standard Polymarket onboarding).
3. Derive L2 API credentials: `python -m polymarket_mm_bot.scripts.derive_api_creds`
   and put them in `.env` (`POLYMARKET_API_KEY/SECRET/PASSPHRASE`).
4. Set `LIVE_TRADING_CONFIRMED=true`, `POLYMARKET_PRIVATE_KEY`, and
   `POLYMARKET_FUNDER_ADDRESS` in the server environment (never in the image).
5. Enroll an authenticator: `python -m scripts.setup_live_totp` and set
   `LIVE_TOTP_SECRET`.
6. In the dashboard, use **Trading mode → Switch to LIVE** and enter the 6-digit
   authenticator code. The runtime then runs a preflight; if the exchange is
   unreachable or collateral/allowance is insufficient it reports
   `live_unavailable` and places no orders.

In live mode fills are not simulated — they are reconciled from the exchange's
own trades and open orders each loop (`LiveExecutionEngine.sync_fills`).

### Still recommended before real size

- Run extended paper trading with production-like latency and market data.
- Start live with tiny `ORDER_SIZE`/exposure caps and watch reconciliation.
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
