from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from polymarket_mm_bot.config import get_settings
from polymarket_mm_bot.dashboard.state import state


def create_app() -> FastAPI:
    settings = get_settings()
    state.mode_warning = settings.mode_warning
    app = FastAPI(title=settings.app_name)

    @app.get("/", response_class=HTMLResponse)
    async def root() -> str:
        return """
        <html>
          <head><title>Polymarket MM Bot</title></head>
          <body>
            <h1>Polymarket MM Bot</h1>
            <strong id="mode"></strong>
            <pre id="data"></pre>
            <script>
              async function refresh() {
                const [health, markets, positions, orders, pnl, risk] = await Promise.all([
                  fetch('/health').then(r => r.json()),
                  fetch('/selected-markets').then(r => r.json()),
                  fetch('/positions').then(r => r.json()),
                  fetch('/orders').then(r => r.json()),
                  fetch('/pnl').then(r => r.json()),
                  fetch('/risk-events').then(r => r.json())
                ]);
                document.getElementById('mode').innerText = health.mode_warning;
                document.getElementById('data').innerText = JSON.stringify({health, markets, positions, orders, pnl, risk}, null, 2);
              }
              refresh(); setInterval(refresh, 3000);
            </script>
          </body>
        </html>
        """

    @app.get("/health")
    async def health() -> dict:
        return {"ok": True, "status": state.bot_status, "mode_warning": state.mode_warning}

    @app.get("/markets")
    async def markets():
        return state.active_markets

    @app.get("/selected-markets")
    async def selected_markets():
        return state.selected_markets

    @app.get("/positions")
    async def positions():
        return state.positions

    @app.get("/orders")
    async def orders():
        return state.orders

    @app.get("/pnl")
    async def pnl() -> dict:
        return {"daily_pnl": state.daily_pnl, "total_pnl": state.total_pnl}

    @app.get("/risk-events")
    async def risk_events():
        return state.risk_events

    @app.get("/strategy-status")
    async def strategy_status():
        return state.strategy_status

    return app


app = create_app()
