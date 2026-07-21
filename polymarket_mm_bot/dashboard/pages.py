DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>MM Bot</title>
  <style>
    :root { color-scheme: dark; font-family: ui-sans-serif, system-ui, sans-serif; }
    body { margin: 0; background: #0b1220; color: #e5e7eb; }
    header { padding: 1rem 1.5rem; border-bottom: 1px solid #1f2937; display: flex; gap: 1rem; align-items: center; flex-wrap: wrap; }
    h1 { margin: 0; font-size: 1.25rem; }
    .badge { background: #14532d; color: #bbf7d0; padding: 0.25rem 0.6rem; border-radius: 999px; font-size: 0.85rem; }
    nav { display: flex; gap: 0.5rem; margin-left: auto; }
    nav button { background: #111827; color: #e5e7eb; border: 1px solid #374151; border-radius: 8px; padding: 0.45rem 0.8rem; cursor: pointer; }
    nav button.active { background: #2563eb; border-color: #2563eb; }
    main { padding: 1.5rem; max-width: 1100px; margin: 0 auto; }
    .panel { display: none; }
    .panel.active { display: block; }
    pre { background: #111827; border: 1px solid #1f2937; border-radius: 12px; padding: 1rem; overflow: auto; font-size: 0.8rem; }
    .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 0.75rem; margin-bottom: 1.25rem; }
    .stat { background: #111827; border: 1px solid #1f2937; border-radius: 12px; padding: 0.9rem 1rem; }
    .stat-label { color: #94a3b8; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 0.35rem; }
    .stat-sub { color: #64748b; font-size: 0.72rem; margin-top: 0.25rem; font-weight: 400; text-transform: none; letter-spacing: normal; }
    .stat-value { font-size: 1.35rem; font-weight: 600; overflow-wrap: anywhere; }
    .stat-value.positive { color: #4ade80; }
    .stat-value.negative { color: #f87171; }
    .positive { color: #4ade80; }
    .negative { color: #f87171; }
    .stat-value.neutral { color: #e5e7eb; }
    .pnl-summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 0.75rem; margin-bottom: 1.25rem; }
    .pnl-card { background: #111827; border: 1px solid #1f2937; border-radius: 12px; padding: 1rem 1.1rem; }
    .pnl-card.highlight { border-color: #334155; background: linear-gradient(180deg, #0f172a 0%, #111827 100%); }
    .pnl-card.profit { border-color: #166534; }
    .pnl-card.loss { border-color: #991b1b; }
    .pnl-card.credit { border-color: #1e40af; }
    .pnl-card-label { color: #94a3b8; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 0.4rem; }
    .pnl-card-value { font-size: 1.65rem; font-weight: 700; overflow-wrap: anywhere; }
    .pnl-card-sub { color: #64748b; font-size: 0.76rem; margin-top: 0.35rem; line-height: 1.35; }
    .chart-wrap { background: #111827; border: 1px solid #1f2937; border-radius: 12px; padding: 0.9rem; overflow-x: auto; }
    .chart-svg { width: 100%; min-width: 560px; height: 240px; display: block; }
    .chart-axis { stroke: #334155; stroke-width: 1; }
    .chart-line { fill: none; stroke: #38bdf8; stroke-width: 2.5; }
    .chart-dot { fill: #38bdf8; }
    .chart-bar.positive { fill: #22c55e; }
    .chart-bar.negative { fill: #ef4444; }
    .chart-label { fill: #94a3b8; font-size: 11px; }
    .chart-value { fill: #e5e7eb; font-size: 11px; font-weight: 600; }
    .section { margin-bottom: 1.5rem; }
    .section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.65rem; }
    .section-head h2 { margin: 0; font-size: 1rem; font-weight: 600; color: #f1f5f9; }
    .section-head span { color: #64748b; font-size: 0.85rem; }
    .section-desc { color: #64748b; font-size: 0.82rem; margin: -0.35rem 0 0.7rem; line-height: 1.4; }
    .stat-label .info { cursor: help; color: #475569; margin-left: 0.2rem; }
    .side-buy { color: #4ade80; font-weight: 600; }
    .side-sell { color: #f87171; font-weight: 600; }
    .legend { display: flex; flex-wrap: wrap; gap: 0.5rem 1.25rem; color: #64748b; font-size: 0.78rem; margin: 0.5rem 0 0; }
    .legend b { color: #94a3b8; font-weight: 600; }
    th[title] { cursor: help; border-bottom: 1px dotted #475569; }
    .card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 0.75rem; }
    .market-card { background: #111827; border: 1px solid #1f2937; border-radius: 12px; padding: 1rem; display: flex; flex-direction: column; gap: 0.65rem; }
    .market-card h3 { margin: 0; font-size: 0.95rem; line-height: 1.35; color: #f8fafc; }
    .market-meta { display: flex; flex-wrap: wrap; gap: 0.45rem; }
    .chip { background: #1e293b; color: #cbd5e1; border-radius: 999px; padding: 0.2rem 0.55rem; font-size: 0.75rem; }
    .chip.yes { background: #14532d; color: #bbf7d0; }
    .chip.no { background: #450a0a; color: #fecaca; }
    .chip.warn { background: #422006; color: #fde68a; }
    .market-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; font-size: 0.85rem; }
    .market-stats dt { color: #64748b; margin: 0; }
    .market-stats dd { margin: 0; font-weight: 500; color: #e2e8f0; }
    .market-stats dd .fee-sub { font-size: 0.75rem; color: #64748b; font-weight: 400; }
    table.data { width: 100%; border-collapse: collapse; font-size: 0.85rem; background: #111827; border: 1px solid #1f2937; border-radius: 12px; overflow: hidden; }
    table.data th, table.data td { padding: 0.65rem 0.75rem; text-align: left; border-bottom: 1px solid #1f2937; }
    table.data th { color: #94a3b8; font-weight: 500; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.03em; background: #0f172a; }
    table.data tr:last-child td { border-bottom: none; }
    table.data td.num { text-align: right; font-variant-numeric: tabular-nums; }
    .empty { color: #64748b; font-size: 0.9rem; padding: 1rem; background: #111827; border: 1px dashed #334155; border-radius: 12px; text-align: center; }
    .risk-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 0.45rem; }
    .risk-item { background: #111827; border: 1px solid #1f2937; border-left: 3px solid #f59e0b; border-radius: 8px; padding: 0.6rem 0.75rem; font-size: 0.85rem; }
    .risk-item time { color: #64748b; font-size: 0.75rem; display: block; margin-top: 0.2rem; }
    .profile-name { font-weight: 700; color: #f8fafc; }
    .profile-desc { color: #64748b; font-size: 0.74rem; line-height: 1.35; margin-top: 0.2rem; max-width: 18rem; }
    .profile-active { color: #93c5fd; font-size: 0.72rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.03em; }
    .profile-settings { color: #94a3b8; font-size: 0.76rem; line-height: 1.35; }
    .progress-track { min-width: 7rem; height: 0.45rem; background: #1e293b; border-radius: 999px; overflow: hidden; margin-top: 0.35rem; }
    .progress-bar { height: 100%; background: #2563eb; border-radius: inherit; }
    .progress-bar.negative { background: #dc2626; }
    .status-pill { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 999px; font-size: 0.72rem; text-transform: uppercase; font-weight: 600; }
    .status-pill.open { background: #1e3a8a; color: #bfdbfe; }
    .status-pill.filled { background: #14532d; color: #bbf7d0; }
    .status-pill.canceled, .status-pill.rejected { background: #450a0a; color: #fecaca; }
    .status-pill.partially_filled { background: #422006; color: #fde68a; }
    form { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; }
    label { display: flex; flex-direction: column; gap: 0.35rem; font-size: 0.9rem; color: #cbd5e1; }
    .field { display: flex; flex-direction: column; gap: 0.35rem; }
    .field-label { font-size: 0.9rem; color: #cbd5e1; }
    .field-hint { color: #64748b; font-size: 0.78rem; line-height: 1.35; margin: -0.1rem 0 0.15rem; }
    .checkbox-row { flex-direction: row; align-items: center; gap: 0.5rem; width: fit-content; cursor: pointer; }
    .field-categories { grid-column: 1 / -1; }
    .category-grid { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.25rem; }
    .category-option { flex-direction: row; align-items: center; gap: 0.4rem; background: #111827; border: 1px solid #374151; border-radius: 8px; padding: 0.45rem 0.65rem; cursor: pointer; text-transform: capitalize; }
    .category-option input { width: auto; margin: 0; }
    input, select { background: #111827; color: #f8fafc; border: 1px solid #374151; border-radius: 8px; padding: 0.55rem 0.65rem; }
    .actions { grid-column: 1 / -1; display: flex; gap: 0.75rem; align-items: center; margin-top: 0.5rem; }
    button.primary { background: #2563eb; color: white; border: none; border-radius: 8px; padding: 0.65rem 1rem; cursor: pointer; }
    button.secondary { background: #111827; color: #e5e7eb; border: 1px solid #374151; border-radius: 8px; padding: 0.55rem 0.9rem; cursor: pointer; font-size: 0.85rem; }
    button.secondary:hover { border-color: #64748b; }
    button.danger { background: #450a0a; color: #fecaca; border: 1px solid #991b1b; border-radius: 8px; padding: 0.55rem 0.9rem; cursor: pointer; font-size: 0.85rem; }
    button.success { background: #14532d; color: #bbf7d0; border: 1px solid #166534; border-radius: 8px; padding: 0.55rem 0.9rem; cursor: pointer; font-size: 0.85rem; }
    .control-actions { display: flex; align-items: center; gap: 0.75rem; margin: -0.5rem 0 1rem; flex-wrap: wrap; }
    .control-note { color: #64748b; font-size: 0.82rem; }
    .pnl-actions { display: flex; align-items: center; gap: 0.75rem; margin: 0 0 1rem; flex-wrap: wrap; }
    .pnl-reset-note { color: #64748b; font-size: 0.82rem; }
    .hint { color: #94a3b8; font-size: 0.9rem; margin-bottom: 1rem; }
    .message { min-height: 1.25rem; color: #86efac; }
    .message.error { color: #fca5a5; }
    .mode-controls { display: flex; gap: 0.6rem; align-items: center; flex-wrap: wrap; margin: 0.5rem 0; }
    .mode-controls input { width: 8rem; background: #0f172a; color: #e5e7eb; border: 1px solid #374151; border-radius: 8px; padding: 0.45rem 0.6rem; font-size: 1rem; letter-spacing: 0.2em; }
    #mode-section { background: #111827; border: 1px solid #1f2937; border-radius: 12px; padding: 1rem 1.25rem; }
    .mode-badge-live { background: #7f1d1d; color: #fecaca; }
    .mode-badge-paper { background: #14532d; color: #bbf7d0; }
    .warn { background: #451a1a; border: 1px solid #991b1b; color: #fecaca; padding: 0.75rem 1rem; border-radius: 8px; margin-bottom: 1rem; }
    .error { color: #fca5a5; }
  </style>
</head>
<body>
  <header>
    <h1>MM Bot</h1>
    <span class="badge" id="mode">Loading...</span>
    <nav>
      <button id="tab-overview" class="active" type="button">Overview</button>
      <button id="tab-settings" type="button">Settings</button>
    </nav>
  </header>
  <main>
    <section id="overview" class="panel active">
      <p class="hint">Live bot metrics are synced from the worker every loop.</p>
      <div id="overview-content">
        <div class="pnl-summary" id="pnl-summary"></div>
        <div class="stats" id="stats-row"></div>
        <div class="control-actions">
          <button class="danger" id="stop-trading" type="button">Stop trading</button>
          <button class="success" id="resume-trading" type="button" style="display:none">Resume trading</button>
          <span class="control-note" id="trading-control-note"></span>
        </div>
        <div class="pnl-actions">
          <button class="secondary" id="reset-daily-pnl" type="button">Reset today's change</button>
          <span class="pnl-reset-note" id="pnl-reset-note"></span>
        </div>
        <div class="section">
          <div class="section-head"><h2>Daily profit</h2><span id="daily-pnl-count"></span></div>
          <p class="section-desc">One point per UTC day from the saved PnL snapshots. Bars show daily profit or loss; the blue line shows total PnL.</p>
          <div class="chart-wrap" id="daily-pnl-chart"></div>
        </div>
        <div class="section">
          <div class="section-head"><h2>Strategy profiles</h2><span id="profiles-count"></span></div>
          <p class="section-desc">Paper-only comparison flows. The active profile places the current paper orders; shadow profiles keep separate simulated ledgers so you can compare performance before promoting one.</p>
          <div id="profiles-wrap"></div>
        </div>
        <div class="section">
          <div class="section-head"><h2>Performance optimizer</h2><span id="optimizer-count"></span></div>
          <p class="section-desc">Uses persisted fills to rank markets by realized PnL. Scale candidates need repeatable positive fills; reduce candidates should not receive more buy exposure.</p>
          <div id="optimizer-wrap"></div>
        </div>
        <div class="section">
          <div class="section-head"><h2>Recent trades</h2><span id="trades-count"></span></div>
          <p class="section-desc">Each row is a fill — a moment the bot actually bought or sold shares. <b class="side-buy">BUY</b> puts credit out (cash spent); <b class="side-sell">SELL</b> brings proceeds back. Price is per share in cents (0–100¢). The cash-flow column shows money in or out on that trade.</p>
          <div id="trades-wrap"></div>
        </div>
        <div class="section">
          <div class="section-head"><h2>Open orders</h2><span id="orders-count"></span></div>
          <p class="section-desc">Quotes the bot currently has resting on the book, waiting to be filled. "Filled" shows how much has traded so far; "Remaining" is still working. These are intentions, not trades yet — a trade appears above once one fills.</p>
          <div id="orders-wrap"></div>
        </div>
        <div class="section">
          <div class="section-head"><h2>Positions</h2><span id="positions-count"></span></div>
          <p class="section-desc">What the bot is holding right now, per market, after all fills. <b>Net yes</b> = YES shares minus NO shares. <b>Mark</b> is the current fair price used to value the position. <b>Realized</b> is locked-in profit from closed shares; <b>Unrealized</b> is paper profit on what's still held.</p>
          <div id="positions-wrap"></div>
        </div>
        <div class="section">
          <div class="section-head"><h2>Selected markets</h2><span id="markets-count"></span></div>
          <p class="section-desc">Markets that passed the scanner and where the bot is quoting. "Bot buy/sell" are the prices it is currently offering.</p>
          <div class="card-grid" id="markets-grid"></div>
        </div>
        <div class="section">
          <div class="section-head"><h2>Risk events</h2><span id="risk-count"></span></div>
          <p class="section-desc">Times a safety rule blocked or paused trading (e.g. exposure caps, stale data, daily-loss limit). Frequent events here explain why the bot may not be quoting.</p>
          <ul class="risk-list" id="risk-list"></ul>
        </div>
      </div>
    </section>
    <section id="settings" class="panel">
      <p class="hint">Strategy and risk limits. Secrets stay in server environment variables.</p>
      <div id="db-warning" class="warn" style="display:none;"></div>
      <div class="section" id="mode-section">
        <div class="section-head"><h2>Trading mode</h2><span id="mode-badge"></span></div>
        <p class="hint" id="mode-hint"></p>
        <div id="mode-prereqs" class="hint"></div>
        <div class="mode-controls">
          <input id="totp-code" inputmode="numeric" autocomplete="one-time-code"
                 maxlength="6" placeholder="6-digit code" />
          <button class="primary" id="go-live" type="button">Switch to LIVE</button>
          <button class="secondary" id="go-paper" type="button">Return to paper</button>
        </div>
        <span class="message" id="mode-message"></span>
      </div>
      <form id="settings-form"></form>
      <div class="actions">
        <button class="primary" id="save-settings" type="button">Save settings</button>
        <span class="message" id="settings-message"></span>
      </div>
      <div class="section" id="database-section">
        <div class="section-head"><h2>Database</h2><span>paper reset</span></div>
        <p class="hint">Clean orders, positions, PnL history, risk events, market cache, and the current dashboard snapshot. Settings are kept and trading is paused.</p>
        <div class="actions">
          <button class="danger" id="clean-database" type="button">Clean database</button>
          <span class="message" id="database-message"></span>
        </div>
      </div>
    </section>
  </main>
  <script>
    const fields = [
      ["max_daily_loss", "number", "Max daily loss"],
      ["per_market_stop_loss", "number", "Per-market stop loss"],
      ["optimizer_auto_enabled", "checkbox", "Auto optimizer"],
      ["optimizer_scale_multiplier", "number", "Optimizer scale multiplier"],
      ["max_position_per_market", "number", "Max position / market"],
      ["max_total_exposure", "number", "Max total exposure"],
      ["max_order_size", "number", "Max order size"],
      ["max_open_orders", "number", "Max open orders"],
      ["max_markets_traded", "number", "Max markets traded"],
      ["allowed_categories", "categories", "Market categories"],
      ["min_volume", "number", "Min volume"],
      ["min_liquidity", "number", "Min liquidity"],
      ["min_spread", "number", "Min spread"],
      ["market_score_threshold", "number", "Market score threshold"],
      ["target_spread", "number", "Target spread"],
      ["order_size", "number", "Order size"],
      ["stale_order_seconds", "number", "Stale order seconds"],
    ];

    const fieldHints = {
      paper_trading: "Simulate quotes and fills only. No real Polymarket orders are sent.",
      run_mode: "Paper uses the simulator; live sends real orders (requires LIVE_TRADING_CONFIRMED and wallet env vars).",
      max_daily_loss: "Stop trading when today's PnL falls below this loss, in USD. Resets each calendar day.",
      per_market_stop_loss: "Stop adding new buy exposure to a market once its marked PnL is below this loss. Sells remain allowed so inventory can exit.",
      optimizer_auto_enabled: "Automatically block reduce candidates and scale proven positive candidates from persisted fill analytics.",
      optimizer_scale_multiplier: "Multiplier applied to signal size only for optimizer scale candidates. Still capped by max order size.",
      max_position_per_market: "Maximum shares held on one side (yes or no) in a single market.",
      max_total_exposure: "Cap on total capital at risk across all open positions, in USD.",
      max_order_size: "Largest single order the bot may place, in shares.",
      max_open_orders: "Maximum number of resting orders allowed at once.",
      max_markets_traded: "How many markets the scanner may select per cycle.",
      allowed_categories: "Only trade markets in the selected categories.",
      min_volume: "Markets below this lifetime volume are filtered out.",
      min_liquidity: "Minimum order-book depth required for a market to qualify.",
      min_spread: "Minimum bid-ask spread required; also floors how tight quotes can be.",
      market_score_threshold: "Minimum scanner score (0–100) required to trade a market.",
      target_spread: "Width between bid and ask around fair value (e.g. 0.02 = 2¢).",
      order_size: "Default share count per quote the strategy places.",
      stale_order_seconds: "Cancel resting orders that remain open longer than this many seconds.",
    };

    let categoryOptions = [];

    function apiFetch(url, options = {}) {
      const path = url.startsWith("/") ? url : `/${url}`;
      // Avoid fetch() failing when the page was opened via user:pass@host URLs.
      const target = `${window.location.origin}${path}`;
      return fetch(target, { credentials: "same-origin", ...options });
    }

    async function readListJson(res) {
      const body = await readJsonResponse(res);
      return res.ok && Array.isArray(body) ? body : [];
    }

    async function readObjectJson(res, fallback = {}) {
      const body = await readJsonResponse(res);
      return res.ok && body && typeof body === "object" && !Array.isArray(body) ? body : fallback;
    }

    function showPanel(name) {
      document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
      document.querySelectorAll("nav button").forEach(b => b.classList.remove("active"));
      document.getElementById(name).classList.add("active");
      document.getElementById("tab-" + name).classList.add("active");
    }

    document.getElementById("tab-overview").onclick = () => showPanel("overview");
    document.getElementById("tab-settings").onclick = () => { showPanel("settings"); loadSettings(); loadMode(); };

    function renderMode(state) {
      const badge = document.getElementById("mode-badge");
      const hint = document.getElementById("mode-hint");
      const prereqs = document.getElementById("mode-prereqs");
      const goLive = document.getElementById("go-live");
      const goPaper = document.getElementById("go-paper");
      const isLive = state.mode === "live";
      badge.textContent = isLive ? "LIVE" : "PAPER";
      badge.className = "badge " + (isLive ? "mode-badge-live" : "mode-badge-paper");
      hint.textContent = isLive
        ? "Live mode is active. Switching to paper is immediate and needs no code."
        : "Paper mode. Switching to live requires a code from your authenticator app.";
      const p = state.prerequisites || {};
      const rows = [
        ["Authenticator configured", p.totp_configured],
        ["LIVE_TRADING_CONFIRMED", p.live_trading_confirmed],
        ["Wallet credentials", p.wallet_configured],
        ["Live execution implemented", p.execution_implemented],
      ];
      prereqs.innerHTML = rows
        .map(([label, ok]) => (ok ? "✅ " : "❌ ") + escapeHtml(label))
        .join(" &nbsp; ");
      goLive.disabled = isLive || !state.can_go_live;
      goPaper.disabled = !isLive;
    }

    async function loadMode() {
      const msg = document.getElementById("mode-message");
      msg.className = "message";
      msg.textContent = "";
      try {
        const res = await apiFetch("/trading/mode");
        const body = await readJsonResponse(res);
        if (!res.ok) {
          msg.className = "message error";
          msg.textContent = typeof body.detail === "string" ? body.detail : "Could not load trading mode.";
          return;
        }
        renderMode(body);
      } catch (err) {
        msg.className = "message error";
        msg.textContent = String(err && err.message || err);
      }
    }

    async function goLive() {
      const msg = document.getElementById("mode-message");
      const code = (document.getElementById("totp-code").value || "").trim();
      if (!/^[0-9]{6}$/.test(code)) {
        msg.className = "message error";
        msg.textContent = "Enter the 6-digit code from your authenticator app.";
        return;
      }
      if (!confirm("Switch to LIVE trading? This enables real-money order placement once execution is implemented.")) {
        return;
      }
      msg.className = "message";
      msg.textContent = "Verifying...";
      const res = await apiFetch("/trading/mode/live", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      const body = await readJsonResponse(res);
      document.getElementById("totp-code").value = "";
      if (!res.ok) {
        msg.className = "message error";
        msg.textContent = typeof body.detail === "string" ? body.detail : ("Switch failed (" + res.status + ").");
        return;
      }
      msg.className = "message";
      msg.textContent = body.warning || "Switched to LIVE.";
      renderMode(body);
    }

    async function goPaper() {
      const msg = document.getElementById("mode-message");
      msg.className = "message";
      msg.textContent = "Switching...";
      const res = await apiFetch("/trading/mode/paper", { method: "POST" });
      const body = await readJsonResponse(res);
      if (!res.ok) {
        msg.className = "message error";
        msg.textContent = typeof body.detail === "string" ? body.detail : ("Switch failed (" + res.status + ").");
        return;
      }
      msg.textContent = "Switched to paper.";
      renderMode(body);
    }

    document.getElementById("go-live").onclick = goLive;
    document.getElementById("go-paper").onclick = goPaper;

    function buildSettingsForm(data) {
      const form = document.getElementById("settings-form");
      form.innerHTML = "";
      for (const field of fields) {
        const [key, type, label, options] = field;
        if (type === "categories") {
          const wrap = document.createElement("div");
          wrap.className = "field-categories";
          const title = document.createElement("div");
          title.className = "field-label";
          title.textContent = label;
          wrap.appendChild(title);
          const hint = document.createElement("div");
          hint.className = "field-hint";
          hint.textContent = fieldHints[key] || "";
          wrap.appendChild(hint);
          const box = document.createElement("div");
          box.className = "category-grid";
          const selected = new Set((data[key] || []).map((c) => String(c).toLowerCase()));
          for (const cat of categoryOptions) {
            const option = document.createElement("label");
            option.className = "category-option";
            const input = document.createElement("input");
            input.type = "checkbox";
            input.name = key;
            input.value = cat;
            input.checked = selected.has(String(cat).toLowerCase());
            option.appendChild(input);
            option.appendChild(document.createTextNode(cat));
            box.appendChild(option);
          }
          wrap.appendChild(box);
          form.appendChild(wrap);
          continue;
        }
        const wrap = document.createElement("div");
        wrap.className = "field";
        const title = document.createElement("div");
        title.className = "field-label";
        title.textContent = label;
        wrap.appendChild(title);
        const hintText = fieldHints[key];
        if (hintText) {
          const hint = document.createElement("div");
          hint.className = "field-hint";
          hint.textContent = hintText;
          wrap.appendChild(hint);
        }
        let input;
        if (type === "checkbox") {
          input = document.createElement("input");
          input.type = "checkbox";
          input.checked = !!data[key];
        } else if (type === "select") {
          input = document.createElement("select");
          for (const opt of options) {
            const o = document.createElement("option");
            o.value = opt; o.textContent = opt;
            if (data[key] === opt) o.selected = true;
            input.appendChild(o);
          }
        } else {
          input = document.createElement("input");
          input.type = "number";
          input.step = key.includes("spread") ? "0.001" : "1";
          input.value = data[key];
        }
        input.name = key;
        if (type === "checkbox") {
          const row = document.createElement("label");
          row.className = "checkbox-row";
          row.appendChild(input);
          row.appendChild(document.createTextNode("Enabled"));
          wrap.appendChild(row);
        } else {
          wrap.appendChild(input);
        }
        form.appendChild(wrap);
      }
    }

    async function readJsonResponse(res) {
      const text = await res.text();
      if (!text) return {};
      const trimmed = text.trimStart();
      if (trimmed.startsWith("<!DOCTYPE") || trimmed.startsWith("<html")) {
        return {
          detail: "Gateway timeout (" + res.status + "). Database likely unreachable. "
            + "Set DATABASE_URL to ${{Postgres.DATABASE_PRIVATE_URL}} in Railway."
        };
      }
      try {
        return JSON.parse(text);
      } catch (_) {
        return { detail: "Unexpected server response (" + res.status + ")." };
      }
    }

    async function loadSettingsStatus() {
      const res = await apiFetch("/settings/status");
      const status = await readJsonResponse(res);
      const warn = document.getElementById("db-warning");
      const saveBtn = document.getElementById("save-settings");
      if (!status.database_ok) {
        warn.style.display = "block";
        warn.textContent = status.message || "Database not connected. Save is disabled until DATABASE_URL is fixed.";
        saveBtn.disabled = true;
        return false;
      }
      warn.style.display = "none";
      saveBtn.disabled = false;
      return true;
    }

    async function loadSettings() {
      const msg = document.getElementById("settings-message");
      msg.className = "message";
      msg.textContent = "";
      await loadSettingsStatus();
      const [settingsRes, categoriesRes] = await Promise.all([
        apiFetch("/settings"),
        apiFetch("/settings/categories"),
      ]);
      const data = await readJsonResponse(settingsRes);
      const categoriesBody = await readJsonResponse(categoriesRes);
      if (categoriesRes.ok && Array.isArray(categoriesBody.categories)) {
        categoryOptions = categoriesBody.categories;
      }
      if (!settingsRes.ok) {
        msg.className = "message error";
        const detail = data.detail;
        msg.textContent = typeof detail === "string" ? detail : ("Could not load settings (" + settingsRes.status + ").");
        return;
      }
      buildSettingsForm(data);
    }

    async function saveSettings() {
      if (!(await loadSettingsStatus())) {
        return;
      }
      const form = document.getElementById("settings-form");
      const payload = {};
      for (const [key, type] of fields.map(f => [f[0], f[1]])) {
        if (type === "categories") {
          payload[key] = Array.from(form.querySelectorAll(`input[name="${key}"]:checked`)).map((el) => el.value);
          continue;
        }
        const el = form.elements[key];
        payload[key] = type === "checkbox" ? el.checked : (type === "select" ? el.value : Number(el.value));
      }
      if (!payload.allowed_categories || !payload.allowed_categories.length) {
        const msg = document.getElementById("settings-message");
        msg.className = "message error";
        msg.textContent = "Select at least one market category.";
        return;
      }
      const msg = document.getElementById("settings-message");
      msg.className = "message";
      msg.textContent = "Saving...";
      const res = await apiFetch("/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await readJsonResponse(res);
      if (!res.ok) {
        msg.className = "message error";
        const detail = body.detail;
        msg.textContent = typeof detail === "string" ? detail : ("Save failed (" + res.status + ").");
        return;
      }
      msg.textContent = "Saved. Bot picks up changes on next loop.";
      buildSettingsForm(body);
    }

    document.getElementById("save-settings").onclick = saveSettings;

    async function cleanDatabase() {
      const msg = document.getElementById("database-message");
      const button = document.getElementById("clean-database");
      if (!confirm("Clean all paper trading database state? This removes orders, positions, PnL history, fills, risk events, market cache, and pauses trading.")) {
        return;
      }
      msg.className = "message";
      msg.textContent = "Cleaning...";
      button.disabled = true;
      try {
        const res = await apiFetch("/settings/clean-database", { method: "POST" });
        const body = await readJsonResponse(res);
        if (!res.ok) {
          throw new Error(typeof body.detail === "string" ? body.detail : "Clean failed");
        }
        const deleted = body.deleted || {};
        const count = Object.values(deleted).reduce((sum, value) => sum + (Number(value) || 0), 0);
        msg.textContent = `Cleaned ${count} rows. Trading paused.`;
        await refreshOverview();
        await loadSettingsStatus();
      } catch (err) {
        msg.className = "message error";
        msg.textContent = String(err && err.message || err);
      } finally {
        button.disabled = false;
      }
    }

    document.getElementById("clean-database").onclick = cleanDatabase;

    function escapeHtml(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }

    function fmtMoney(n) {
      const v = Number(n) || 0;
      const sign = v < 0 ? "-" : "";
      return sign + "$" + Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: 2 });
    }

    function fmtNum(n, digits = 2) {
      return (Number(n) || 0).toLocaleString(undefined, { maximumFractionDigits: digits });
    }

    function fmtPct(n) {
      return (Number(n) * 100).toFixed(1) + "¢";
    }

    function fmtDate(value) {
      if (!value) return "—";
      const d = new Date(value);
      return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
    }

    function pnlClass(n) {
      const v = Number(n) || 0;
      if (v > 0) return "positive";
      if (v < 0) return "negative";
      return "neutral";
    }

    function marketPrices(market) {
      const raw = market.metadata?.outcomePrices;
      if (!raw) return { yes: null, no: null };
      try {
        const prices = typeof raw === "string" ? JSON.parse(raw) : raw;
        return { yes: Number(prices[0]), no: Number(prices[1]) };
      } catch (_) {
        return { yes: null, no: null };
      }
    }

    function marketLookup(markets) {
      const map = new Map();
      for (const m of markets || []) map.set(m.condition_id, m);
      return map;
    }

    function fmtDateTime(value) {
      if (!value) return "";
      const d = new Date(value);
      return Number.isNaN(d.getTime()) ? "" : d.toLocaleString();
    }

    function updatePnlResetNote(pnl) {
      const note = document.getElementById("pnl-reset-note");
      if (!note) return;
      const when = fmtDateTime(pnl.daily_pnl_reset_at);
      note.textContent = when ? `Baseline set ${when}` : "Baseline not set yet";
    }

    async function resetDailyPnl() {
      const button = document.getElementById("reset-daily-pnl");
      const note = document.getElementById("pnl-reset-note");
      button.disabled = true;
      if (note) note.textContent = "Resetting…";
      try {
        const res = await apiFetch("/pnl/reset-daily", { method: "POST" });
        const body = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(body.detail || "Reset failed");
        if (note) note.textContent = "Reset — waiting for bot sync…";
        await refreshOverview();
      } catch (err) {
        if (note) note.textContent = String(err.message || err);
      } finally {
        button.disabled = false;
      }
    }

    document.getElementById("reset-daily-pnl").onclick = resetDailyPnl;

    function updateTradingControls(health) {
      const stopBtn = document.getElementById("stop-trading");
      const resumeBtn = document.getElementById("resume-trading");
      const note = document.getElementById("trading-control-note");
      const enabled = health.trading_enabled !== false;
      const botActive = health.bot_trading_enabled !== false;
      stopBtn.style.display = enabled ? "" : "none";
      resumeBtn.style.display = enabled ? "none" : "";
      const when = fmtDateTime(health.trading_updated_at);
      if (!enabled) {
        note.textContent = when ? `Trading paused · updated ${when}` : "Trading paused — no new quotes or fills.";
      } else if (!botActive) {
        note.textContent = when
          ? `Resume requested · waiting for bot sync · updated ${when}`
          : "Resume requested — waiting for bot sync.";
      } else {
        note.textContent = when ? `Trading active · updated ${when}` : "Trading active — quoting and fills enabled.";
      }
    }

    async function setTradingEnabled(enabled) {
      const stopBtn = document.getElementById("stop-trading");
      const resumeBtn = document.getElementById("resume-trading");
      const note = document.getElementById("trading-control-note");
      stopBtn.disabled = true;
      resumeBtn.disabled = true;
      if (note) note.textContent = enabled ? "Resuming…" : "Stopping…";
      try {
        const path = enabled ? "/trading/resume" : "/trading/stop";
        const res = await apiFetch(path, { method: "POST" });
        const body = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(body.detail || "Request failed");
        if (note) note.textContent = enabled ? "Resumed — waiting for bot sync…" : "Stopped — canceling open orders…";
        await refreshOverview();
      } catch (err) {
        if (note) note.textContent = String(err.message || err);
      } finally {
        stopBtn.disabled = false;
        resumeBtn.disabled = false;
      }
    }

    document.getElementById("stop-trading").onclick = () => setTradingEnabled(false);
    document.getElementById("resume-trading").onclick = () => setTradingEnabled(true);

    function fmtSignedMoney(n, invertSign) {
      const v = Number(n) || 0;
      const signed = invertSign ? -v : v;
      const sign = signed < 0 ? "−" : signed > 0 ? "+" : "";
      return sign + fmtMoney(Math.abs(signed));
    }

    function renderPnlSummary(pnl, health) {
      const wrap = document.getElementById("pnl-summary");
      if (!wrap) return;
      const isPaper = String(health.mode_warning || "").toLowerCase().includes("paper");
      const realized = Number(pnl.realized_pnl) || 0;
      const unrealized = Number(pnl.unrealized_pnl) || 0;
      const total = Number(pnl.total_pnl);
      const net = Number.isFinite(total) ? total : realized + unrealized;
      const profit = Number(pnl.profit) || 0;
      const loss = Number(pnl.loss) || 0;
      const capital = Number(pnl.capital_deployed) || 0;
      const positionCredit = Number(pnl.position_credit) || 0;
      const orderCredit = Number(pnl.open_order_credit) || 0;
      const bought = Number(pnl.total_bought) || 0;
      const sold = Number(pnl.total_sold) || 0;
      const starting = Number(pnl.starting_capital) || 0;
      const available = Number(pnl.available_credit);
      const daily = Number(pnl.daily_pnl) || 0;
      const modeLabel = isPaper ? "paper bankroll" : "starting capital";
      const cards = [
        {
          cls: "highlight",
          label: "Net P&L",
          value: fmtMoney(net),
          valueCls: pnlClass(net),
          sub: `${fmtMoney(daily)} today · ${isPaper ? "simulated" : "live"}`,
          tip: "Total profit or loss: realized (closed) plus unrealized (open positions marked to market).",
        },
        {
          cls: "profit",
          label: "Profit",
          value: fmtMoney(profit),
          valueCls: profit > 0 ? "positive" : "neutral",
          sub: profit > 0 ? `${fmtMoney(Math.max(0, realized))} realized · ${fmtMoney(Math.max(0, unrealized))} unrealized` : "No gains yet",
          tip: "Sum of all positive PnL — locked-in gains plus open mark-to-market gains.",
        },
        {
          cls: "loss",
          label: "Loss",
          value: fmtMoney(loss),
          valueCls: loss > 0 ? "negative" : "neutral",
          sub: loss > 0 ? `${fmtMoney(Math.abs(Math.min(0, realized)))} realized · ${fmtMoney(Math.abs(Math.min(0, unrealized)))} unrealized` : "No losses yet",
          tip: "Sum of all negative PnL — locked-in and open mark-to-market losses.",
        },
        {
          cls: "credit",
          label: "Credit at work",
          value: fmtMoney(capital),
          valueCls: "neutral",
          sub: `${fmtMoney(positionCredit)} in positions · ${fmtMoney(orderCredit)} in open buys`,
          tip: "Capital currently deployed: cost of held shares plus cash resting in open buy orders.",
        },
        {
          cls: "",
          label: "Available credit",
          value: Number.isFinite(available) ? fmtMoney(available) : "—",
          valueCls: Number.isFinite(available) ? pnlClass(available - starting) : "neutral",
          sub: `${fmtMoney(starting)} ${modeLabel}`,
          tip: "Estimated cash left to deploy: starting capital plus net P&L minus credit currently at work.",
        },
        {
          cls: "",
          label: "Trade volume",
          value: fmtMoney(bought + sold),
          valueCls: "neutral",
          sub: `${fmtMoney(bought)} bought · ${fmtMoney(sold)} sold`,
          tip: "Total cash that changed hands in recent fills (rolling feed, not lifetime history).",
        },
      ];
      wrap.innerHTML = cards.map((c) =>
        `<div class="pnl-card ${escapeHtml(c.cls)}" title="${escapeHtml(c.tip)}">`
        + `<div class="pnl-card-label">${escapeHtml(c.label)}</div>`
        + `<div class="pnl-card-value ${escapeHtml(c.valueCls)}">${escapeHtml(c.value)}</div>`
        + `<div class="pnl-card-sub">${escapeHtml(c.sub)}</div>`
        + `</div>`
      ).join("");
    }

    function renderStats(health, pnl, markets, orders, positions, risk, fills) {
      const row = document.getElementById("stats-row");
      const isPaper = String(health.mode_warning || "").toLowerCase().includes("paper");
      const realized = Number(pnl.realized_pnl) || 0;
      const unrealized = Number(pnl.unrealized_pnl) || 0;
      const total = Number(pnl.total_pnl);
      const portfolioTotal = Number.isFinite(total) ? total : realized + unrealized;
      const daily = Number(pnl.daily_pnl) || 0;
      const portfolioSub = isPaper ? "paper · realized + unrealized" : "realized + unrealized";
      const openPositionCount = (positions || []).filter((p) => Number(p.yes_size) > 0 || Number(p.no_size) > 0).length;
      const missingMarks = (positions || []).filter((p) => p.mark_missing).length;
      const positionSub = missingMarks
        ? `${openPositionCount} open, ${missingMarks} missing mark`
        : `${openPositionCount} open`;
      // [label, value, class, sub, tooltip]
      const cards = [
        ["Bot status", String(health.status || "idle").replaceAll("_", " "), "neutral", "", "What the bot is doing right now. paper trading/live trading = quoting; trading paused/risk paused/live unavailable = not trading."],
        ["Portfolio PnL", fmtMoney(portfolioTotal), pnlClass(portfolioTotal), portfolioSub, "Total profit/loss since start: realized (closed) plus unrealized (open, marked to current price)."],
        ["Today's change", fmtMoney(daily), pnlClass(daily), "since last reset", "How much PnL moved since the daily baseline was last reset."],
        ["Realized", fmtMoney(realized), pnlClass(realized), "closed trades", "Locked-in profit/loss from shares that have been sold/closed."],
        ["Unrealized", fmtMoney(unrealized), pnlClass(unrealized), "open positions", "Paper profit/loss on shares still held, valued at the current mark price."],
        ["Trades", String((fills || []).length), "neutral", "recent fills", "Number of fills (actual buys/sells) in the recent trade feed below."],
        ["Open orders", String((orders || []).length), "neutral", "open + partial", "Quotes resting on the book, not yet fully filled."],
        ["Positions", String((positions || []).length), "neutral", positionSub, "Markets the bot currently holds shares in."],
        ["Markets", String((markets || []).length), "neutral", "quoting", "Markets that passed the scanner and are being quoted."],
        ["Risk events", String((risk || []).length), "neutral", "recent", "How many times a safety rule blocked or paused trading recently."],
      ];
      row.innerHTML = cards.map(([label, value, cls, sub, tip]) =>
        `<div class="stat" ${tip ? `title="${escapeHtml(tip)}"` : ""}>`
        + `<div class="stat-label">${escapeHtml(label)}${tip ? '<span class="info">ⓘ</span>' : ""}</div>`
        + `<div class="stat-value ${cls}">${escapeHtml(value)}</div>`
        + (sub ? `<div class="stat-sub">${escapeHtml(sub)}</div>` : "")
        + `</div>`
      ).join("");
    }

    function fmtFee(maker, taker, orderSize) {
      const makerText = fmtMoney(maker) + " maker";
      if (!taker || taker <= 0) return makerText;
      return makerText + `<span class="fee-sub"> · taker ~${fmtMoney(taker)} / ${fmtNum(orderSize, 0)} sh</span>`;
    }

    function renderMarkets(markets) {
      const grid = document.getElementById("markets-grid");
      document.getElementById("markets-count").textContent = `${(markets || []).length} active`;
      if (!markets || !markets.length) {
        grid.innerHTML = '<div class="empty">No markets selected yet.</div>';
        return;
      }
      grid.innerHTML = markets.map((m) => {
        const prices = marketPrices(m);
        const orderSize = Number(m.fee_order_size) || 10;
        const botBuy = m.bot_buy_price != null ? fmtPct(m.bot_buy_price) : "—";
        const botSell = m.bot_sell_price != null ? fmtPct(m.bot_sell_price) : "—";
        const chips = [
          m.active ? '<span class="chip">Active</span>' : "",
          m.paused ? '<span class="chip warn">Paused</span>' : "",
          m.closed ? '<span class="chip warn">Closed</span>' : "",
          prices.yes != null ? `<span class="chip yes">Yes ${fmtPct(prices.yes)}</span>` : "",
          prices.no != null ? `<span class="chip no">No ${fmtPct(prices.no)}</span>` : "",
        ].filter(Boolean).join("");
        return `<article class="market-card">
          <h3>${escapeHtml(m.question || m.slug || "Unknown market")}</h3>
          <div class="market-meta">${chips}</div>
          <dl class="market-stats">
            <dt>Bot buy</dt><dd>${escapeHtml(botBuy)}</dd>
            <dt>Bot sell</dt><dd>${escapeHtml(botSell)}</dd>
            <dt>Buy fee</dt><dd>${fmtFee(m.buy_fee_maker ?? 0, m.buy_fee_taker, orderSize)}</dd>
            <dt>Sell fee</dt><dd>${fmtFee(m.sell_fee_maker ?? 0, m.sell_fee_taker, orderSize)}</dd>
            <dt>Volume</dt><dd>$${fmtNum(m.volume, 0)}</dd>
            <dt>Liquidity</dt><dd>$${fmtNum(m.liquidity, 0)}</dd>
            <dt>Ends</dt><dd>${escapeHtml(fmtDate(m.end_date))}</dd>
            <dt>Category</dt><dd>${escapeHtml(m.category || "—")}</dd>
          </dl>
        </article>`;
      }).join("");
    }

    function fmtTime(value) {
      if (!value) return "—";
      const d = new Date(value);
      return Number.isNaN(d.getTime()) ? "—" : d.toLocaleTimeString();
    }

    function renderTrades(fills, marketsById) {
      const wrap = document.getElementById("trades-wrap");
      document.getElementById("trades-count").textContent = `${(fills || []).length} recent`;
      if (!fills || !fills.length) {
        wrap.innerHTML = '<div class="empty">No fills yet. When a resting order trades, it shows up here.</div>';
        return;
      }
      const rows = fills.map((f) => {
        const market = marketsById.get(f.market_id);
        const label = market?.question || (f.market_id ? String(f.market_id).slice(0, 10) + "…" : "—");
        const side = String(f.side || "").toLowerCase();
        const sideCls = side === "buy" ? "side-buy" : "side-sell";
        const status = String(f.status || "").toLowerCase();
        const action = `${side.toUpperCase()} ${String(f.outcome || "").toUpperCase()}`.trim();
        const notional = Number(f.value ?? (Number(f.size) * Number(f.price))) || 0;
        const cashFlow = side === "buy"
          ? `<span class="negative">${escapeHtml(fmtSignedMoney(notional, true))}</span><div class="stat-sub">credit out</div>`
          : `<span class="positive">${escapeHtml(fmtSignedMoney(notional, false))}</span><div class="stat-sub">proceeds</div>`;
        return `<tr>
          <td>${escapeHtml(fmtTime(f.at))}</td>
          <td>${escapeHtml(label)}</td>
          <td class="${sideCls}">${escapeHtml(action)}</td>
          <td class="num">${fmtPct(f.price)}</td>
          <td class="num">${fmtNum(f.size)}</td>
          <td class="num">${cashFlow}</td>
          <td><span class="status-pill ${escapeHtml(status)}">${escapeHtml(status.replaceAll("_", " "))}</span></td>
        </tr>`;
      }).join("");
      wrap.innerHTML = `<table class="data"><thead><tr>
        <th title="When this fill happened">Time</th>
        <th>Market</th>
        <th title="BUY puts credit out, SELL brings proceeds back">Action</th>
        <th title="Price paid per share, in cents (0–100¢)">Price</th>
        <th title="Number of shares that traded in this fill">Shares</th>
        <th title="Cash spent on buys (−) or received on sells (+)">Cash flow</th>
        <th title="The order's state after this fill">Order</th>
      </tr></thead><tbody>${rows}</tbody></table>`;
    }

    function renderOrders(orders, marketsById) {
      const wrap = document.getElementById("orders-wrap");
      document.getElementById("orders-count").textContent = `${(orders || []).length} open`;
      if (!orders || !orders.length) {
        wrap.innerHTML = '<div class="empty">No open orders.</div>';
        return;
      }
      const rows = orders.map((o) => {
        const market = marketsById.get(o.market_id);
        const label = market?.question || o.market_id?.slice(0, 10) + "…";
        const status = String(o.status || "open").toLowerCase();
        return `<tr>
          <td>${escapeHtml(label)}</td>
          <td>${escapeHtml(String(o.side || "").toUpperCase())}</td>
          <td class="num">${fmtPct(o.price)}</td>
          <td class="num">${fmtNum(o.size)}</td>
          <td class="num">${fmtNum(o.filled_size)}</td>
          <td class="num">${fmtNum(o.remaining_size ?? (o.size - o.filled_size))}</td>
          <td class="num">${fmtMoney(o.remaining_notional ?? ((o.size - o.filled_size) * o.price))}</td>
          <td><span class="status-pill ${escapeHtml(status)}">${escapeHtml(status.replaceAll("_", " "))}</span></td>
        </tr>`;
      }).join("");
      wrap.innerHTML = `<table class="data"><thead><tr>
        <th>Market</th>
        <th title="BUY = bid, SELL = ask">Side</th>
        <th title="Quoted price per share, in cents (0–100¢)">Price</th>
        <th title="Total shares the order is for">Size</th>
        <th title="Shares filled so far">Filled</th>
        <th title="Shares still waiting to fill">Remaining</th>
        <th title="Remaining shares × price — cash still working">Open value</th>
        <th title="open = resting, partially filled = some traded">Status</th>
      </tr></thead><tbody>${rows}</tbody></table>`;
    }

    function renderPositions(positions, marketsById) {
      const wrap = document.getElementById("positions-wrap");
      const openCount = (positions || []).filter((p) => Number(p.yes_size) > 0 || Number(p.no_size) > 0).length;
      document.getElementById("positions-count").textContent = `${openCount} open / ${(positions || []).length} records`;
      if (!positions || !positions.length) {
        wrap.innerHTML = '<div class="empty">No position records.</div>';
        return;
      }
      const rows = positions.map((p) => {
        const mark = p.mark_price == null ? (p.mark_missing ? "missing" : "--") : fmtPct(p.mark_price);
        const market = marketsById.get(p.market_id);
        const label = market?.question || p.market_id?.slice(0, 10) + "…";
        return `<tr>
          <td>${escapeHtml(label)}</td>
          <td class="num">${fmtNum(p.yes_size)}</td>
          <td class="num">${fmtNum(p.no_size)}</td>
          <td class="num">${fmtNum(p.net_yes ?? (p.yes_size - p.no_size))}</td>
          <td class="num">${fmtMoney(p.gross_exposure ?? 0)}</td>
          <td class="num">${escapeHtml(mark)}</td>
          <td class="num ${pnlClass(p.realized_pnl)}">${fmtMoney(p.realized_pnl)}</td>
          <td class="num ${pnlClass(p.unrealized_pnl)}">${fmtMoney(p.unrealized_pnl ?? 0)}</td>
          <td class="num ${pnlClass(p.total_pnl ?? p.realized_pnl)}">${fmtMoney(p.total_pnl ?? p.realized_pnl)}</td>
        </tr>`;
      }).join("");
      wrap.innerHTML = `<table class="data"><thead><tr>
        <th>Market</th>
        <th title="YES shares held">Yes</th>
        <th title="NO shares held">No</th>
        <th title="YES minus NO — net directional exposure">Net yes</th>
        <th title="Cash value currently at risk in this market">Exposure</th>
        <th title="Current fair price used to value the position (cents)">Mark</th>
        <th title="Locked-in profit/loss from closed shares">Realized</th>
        <th title="Paper profit/loss on shares still held">Unrealized</th>
        <th title="Realized + unrealized for this market">Total</th>
      </tr></thead><tbody>${rows}</tbody></table>`;
    }

    function renderRiskEvents(risk) {
      const list = document.getElementById("risk-list");
      document.getElementById("risk-count").textContent = `${(risk || []).length} recent`;
      if (!risk || !risk.length) {
        list.innerHTML = '<li class="empty">No risk events.</li>';
        return;
      }
      list.innerHTML = risk.slice().reverse().slice(0, 10).map((evt) => {
        const market = evt.market_id ? `Market ${String(evt.market_id).slice(0, 10)}...` : "Portfolio";
        const code = evt.code || evt.reason || evt.event || "risk_event";
        const msg = evt.message || `${market}: ${code}`;
        const when = evt.timestamp || evt.created_at || "";
        return `<li class="risk-item">${escapeHtml(msg)}${when ? `<time>${escapeHtml(fmtDate(when))}</time>` : ""}</li>`;
      }).join("");
    }

    function renderDailyPnlChart(days) {
      const wrap = document.getElementById("daily-pnl-chart");
      const count = document.getElementById("daily-pnl-count");
      if (!wrap || !count) return;
      const rows = Array.isArray(days) ? days : [];
      count.textContent = `${rows.length} days`;
      if (!rows.length) {
        wrap.innerHTML = '<div class="empty">No daily PnL snapshots yet.</div>';
        return;
      }
      const width = 720;
      const height = 230;
      const pad = { left: 52, right: 18, top: 16, bottom: 38 };
      const innerW = width - pad.left - pad.right;
      const innerH = height - pad.top - pad.bottom;
      const dailyValues = rows.map((d) => Number(d.daily_pnl) || 0);
      const totalValues = rows.map((d) => Number(d.total_pnl) || 0);
      const minVal = Math.min(0, ...dailyValues, ...totalValues);
      const maxVal = Math.max(0, ...dailyValues, ...totalValues);
      const range = Math.max(maxVal - minVal, 1);
      const y = (value) => pad.top + (maxVal - value) / range * innerH;
      const x = (i) => pad.left + (rows.length === 1 ? innerW / 2 : i / (rows.length - 1) * innerW);
      const barW = Math.max(8, Math.min(34, innerW / rows.length * 0.52));
      const zeroY = y(0);
      const line = rows.map((d, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(Number(d.total_pnl) || 0).toFixed(1)}`).join(" ");
      const bars = rows.map((d, i) => {
        const value = Number(d.daily_pnl) || 0;
        const top = Math.min(y(value), zeroY);
        const h = Math.max(Math.abs(y(value) - zeroY), 1);
        const cls = value >= 0 ? "positive" : "negative";
        return `<rect class="chart-bar ${cls}" x="${(x(i) - barW / 2).toFixed(1)}" y="${top.toFixed(1)}" width="${barW.toFixed(1)}" height="${h.toFixed(1)}"><title>${escapeHtml(d.date)} daily ${fmtMoney(value)} · total ${fmtMoney(d.total_pnl)}</title></rect>`;
      }).join("");
      const dots = rows.map((d, i) =>
        `<circle class="chart-dot" cx="${x(i).toFixed(1)}" cy="${y(Number(d.total_pnl) || 0).toFixed(1)}" r="3"><title>${escapeHtml(d.date)} total ${fmtMoney(d.total_pnl)}</title></circle>`
      ).join("");
      const labels = rows.map((d, i) => {
        const show = rows.length <= 10 || i === 0 || i === rows.length - 1 || i % Math.ceil(rows.length / 8) === 0;
        if (!show) return "";
        const label = String(d.date || "").slice(5);
        return `<text class="chart-label" x="${x(i).toFixed(1)}" y="${height - 14}" text-anchor="middle">${escapeHtml(label)}</text>`;
      }).join("");
      wrap.innerHTML = `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Daily profit chart">
        <line class="chart-axis" x1="${pad.left}" y1="${zeroY.toFixed(1)}" x2="${width - pad.right}" y2="${zeroY.toFixed(1)}"></line>
        <line class="chart-axis" x1="${pad.left}" y1="${pad.top}" x2="${pad.left}" y2="${height - pad.bottom}"></line>
        <text class="chart-label" x="6" y="${y(maxVal).toFixed(1)}">${escapeHtml(fmtMoney(maxVal))}</text>
        <text class="chart-label" x="6" y="${zeroY.toFixed(1)}">${escapeHtml(fmtMoney(0))}</text>
        <text class="chart-label" x="6" y="${y(minVal).toFixed(1)}">${escapeHtml(fmtMoney(minVal))}</text>
        ${bars}
        <path class="chart-line" d="${line}"></path>
        ${dots}
        ${labels}
      </svg>`;
    }

    function renderStrategyProfiles(profiles) {
      const wrap = document.getElementById("profiles-wrap");
      const count = document.getElementById("profiles-count");
      if (!wrap || !count) return;
      count.textContent = `${(profiles || []).length} profiles`;
      if (!profiles || !profiles.length) {
        wrap.innerHTML = '<div class="empty">No strategy profile data yet. Wait one bot loop after deployment.</div>';
        return;
      }
      const rows = profiles.map((p) => {
        const settings = p.settings || {};
        const daily = Number(p.daily_pnl) || 0;
        const progress = Number(p.target_progress_pct) || 0;
        const width = Math.max(0, Math.min(Math.abs(progress), 100));
        const progressCls = progress < 0 ? "negative" : "";
        const active = p.active ? '<div class="profile-active">Active trading</div>' : '<div class="stat-sub">Shadow paper</div>';
        const settingsText = [
          `size ${fmtNum(settings.order_size, 0)}`,
          `pos ${fmtNum(settings.max_position_per_market, 0)}`,
          `liq ${fmtMoney(settings.min_liquidity || 0)}`,
          `spread ${fmtPct(settings.target_spread || 0)}`,
        ].join(" · ");
        return `<tr>
          <td>
            <div class="profile-name">${escapeHtml(p.name || "profile")}</div>
            ${active}
            <div class="profile-desc">${escapeHtml(p.description || "")}</div>
          </td>
          <td class="num ${pnlClass(daily)}">
            ${fmtMoney(daily)}
            <div class="progress-track"><div class="progress-bar ${progressCls}" style="width:${width}%"></div></div>
            <div class="stat-sub">${fmtNum(progress, 2)}% of ${fmtMoney(p.target_daily_pnl || 100)}/day</div>
          </td>
          <td class="num ${pnlClass(p.total_pnl)}">${fmtMoney(p.total_pnl || 0)}</td>
          <td class="num">${fmtNum(p.open_orders || 0, 0)}</td>
          <td class="num">${fmtMoney(p.open_buy_credit || 0)}</td>
          <td class="num">${fmtNum(p.recent_fills || 0, 0)}</td>
          <td><div class="profile-settings">${escapeHtml(settingsText)}</div></td>
        </tr>`;
      }).join("");
      wrap.innerHTML = `<table class="data"><thead><tr>
        <th>Profile</th>
        <th title="Today versus the $100/day target">Today</th>
        <th title="Total paper PnL in this profile ledger">Total PnL</th>
        <th title="Open profile orders">Orders</th>
        <th title="Cash resting in open buy orders">Buy credit</th>
        <th title="Recent simulated fills">Fills</th>
        <th>Settings</th>
      </tr></thead><tbody>${rows}</tbody></table>`;
    }

    function renderOptimizer(report) {
      const wrap = document.getElementById("optimizer-wrap");
      const count = document.getElementById("optimizer-count");
      if (!wrap || !count) return;
      const summary = report && report.summary ? report.summary : {};
      const rows = Array.isArray(report && report.markets) ? report.markets : [];
      count.textContent = `${summary.fills || 0} fills · ${summary.markets || 0} markets`;
      if (!rows.length) {
        wrap.innerHTML = '<div class="empty">No persisted fill analytics yet.</div>';
        return;
      }
      const html = rows.slice(0, 8).map((m) => {
        const rec = String(m.recommendation || "keep_observing").replaceAll("_", " ");
        const title = m.question || m.market_id || "";
        return `<tr>
          <td>${escapeHtml(title)}</td>
          <td>${escapeHtml(rec)}</td>
          <td class="num ${pnlClass(m.realized_pnl)}">${fmtMoney(m.realized_pnl || 0)}</td>
          <td class="num">${fmtNum(m.roi_pct || 0, 2)}%</td>
          <td class="num">${fmtNum(m.fills || 0, 0)}</td>
          <td class="num">${fmtMoney(m.bought_notional || 0)}</td>
        </tr>`;
      }).join("");
      wrap.innerHTML = `<table class="data"><thead><tr>
        <th>Market</th><th>Recommendation</th><th>Realized</th><th>ROI</th><th>Fills</th><th>Bought</th>
      </tr></thead><tbody>${html}</tbody></table>`;
    }

    async function refreshOverview() {
      try {
        const healthRes = await apiFetch("/health");
        const health = await readObjectJson(healthRes, {});
        document.getElementById("mode").innerText = health.mode_warning || health.status || "Unknown";
        const categories = (health.allowed_categories || []).join(", ");
        const hint = document.querySelector("#overview .hint");
        const isPaper = String(health.mode_warning || "").toLowerCase().includes("paper");
        if (hint) {
          let text = isPaper
            ? "Paper trading — simulated quotes and fills only. No real Polymarket orders."
            : "Live bot metrics are synced from the worker every loop.";
          text += " PnL includes unrealized mark-to-market on open positions.";
          if (categories) text += " Categories: " + categories + ".";
          if (health.updated_at) {
            const when = new Date(health.updated_at);
            if (!Number.isNaN(when.getTime())) {
              text += " Last bot sync: " + when.toLocaleTimeString() + ".";
            }
          }
          if (health.snapshot_age_seconds != null && health.snapshot_age_seconds > 45) {
            text += " Dashboard cache is stale — check bot is running.";
          }
          hint.textContent = text;
        }

        const [markets, positions, orders, pnl, risk, fills, profiles, dailyHistory, optimizer] = await Promise.all([
          apiFetch("/selected-markets").then(readListJson),
          apiFetch("/positions").then(readListJson),
          apiFetch("/orders").then(readListJson),
          apiFetch("/pnl").then((res) => readObjectJson(res)),
          apiFetch("/risk-events").then(readListJson),
          apiFetch("/fills").then(readListJson),
          apiFetch("/strategy-profiles").then(readListJson),
          apiFetch("/pnl/daily").then((res) => readObjectJson(res, { days: [] })),
          apiFetch("/performance/optimizer").then((res) => readObjectJson(res)),
        ]);
        const marketsById = marketLookup(markets);
        renderPnlSummary(pnl, health);
        renderStats(health, pnl, markets, orders, positions, risk, fills);
        updateTradingControls(health);
        updatePnlResetNote(pnl);
        renderDailyPnlChart(dailyHistory.days);
        renderStrategyProfiles(profiles);
        renderOptimizer(optimizer);
        renderTrades(fills, marketsById);
        renderMarkets(markets);
        renderOrders(orders, marketsById);
        renderPositions(positions, marketsById);
        renderRiskEvents(risk);
      } catch (err) {
        console.error("refreshOverview failed", err);
        document.getElementById("mode").innerText = "Load error";
      }
    }

    refreshOverview();
    setInterval(refreshOverview, 10000);
  </script>
</body>
</html>"""
