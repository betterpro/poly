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
    .stat-value { font-size: 1.35rem; font-weight: 600; }
    .stat-value.positive { color: #4ade80; }
    .stat-value.negative { color: #f87171; }
    .stat-value.neutral { color: #e5e7eb; }
    .section { margin-bottom: 1.5rem; }
    .section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.65rem; }
    .section-head h2 { margin: 0; font-size: 1rem; font-weight: 600; color: #f1f5f9; }
    .section-head span { color: #64748b; font-size: 0.85rem; }
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
    .status-pill { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 999px; font-size: 0.72rem; text-transform: uppercase; font-weight: 600; }
    .status-pill.open { background: #1e3a8a; color: #bfdbfe; }
    .status-pill.filled { background: #14532d; color: #bbf7d0; }
    .status-pill.canceled, .status-pill.rejected { background: #450a0a; color: #fecaca; }
    .status-pill.partially_filled { background: #422006; color: #fde68a; }
    form { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; }
    label { display: flex; flex-direction: column; gap: 0.35rem; font-size: 0.9rem; color: #cbd5e1; }
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
          <div class="section-head"><h2>Selected markets</h2><span id="markets-count"></span></div>
          <div class="card-grid" id="markets-grid"></div>
        </div>
        <div class="section">
          <div class="section-head"><h2>Open orders</h2><span id="orders-count"></span></div>
          <div id="orders-wrap"></div>
        </div>
        <div class="section">
          <div class="section-head"><h2>Positions</h2><span id="positions-count"></span></div>
          <div id="positions-wrap"></div>
        </div>
        <div class="section">
          <div class="section-head"><h2>Risk events</h2><span id="risk-count"></span></div>
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
    </section>
  </main>
  <script>
    const fields = [
      ["max_daily_loss", "number", "Max daily loss"],
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

    let categoryOptions = [];

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
        const res = await fetch("/trading/mode");
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
      const res = await fetch("/trading/mode/live", {
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
      const res = await fetch("/trading/mode/paper", { method: "POST" });
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
          title.textContent = label;
          title.style.color = "#cbd5e1";
          title.style.fontSize = "0.9rem";
          wrap.appendChild(title);
          const hint = document.createElement("div");
          hint.className = "hint";
          hint.style.margin = "0.35rem 0 0";
          hint.textContent = "Only trade markets in the selected categories.";
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
        const wrap = document.createElement("label");
        wrap.textContent = label;
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
        wrap.appendChild(input);
        form.appendChild(wrap);
      }
    }

    async function readJsonResponse(res) {
      const text = await res.text();
      if (!text) return {};
      const trimmed = text.trimStart();
      if (trimmed.startsWith("<!DOCTYPE") || trimmed.startsWith("<html")) {
        return {
          detail: "App Platform timeout (" + res.status + "). Database likely unreachable from DigitalOcean. "
            + "Set DATABASE_URL to Supabase Session pooler URI."
        };
      }
      try {
        return JSON.parse(text);
      } catch (_) {
        return { detail: "Unexpected server response (" + res.status + ")." };
      }
    }

    async function loadSettingsStatus() {
      const res = await fetch("/settings/status");
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
        fetch("/settings"),
        fetch("/settings/categories"),
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
      const res = await fetch("/settings", {
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
        const res = await fetch("/pnl/reset-daily", { method: "POST" });
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
      stopBtn.style.display = enabled ? "" : "none";
      resumeBtn.style.display = enabled ? "none" : "";
      const when = fmtDateTime(health.trading_updated_at);
      if (enabled) {
        note.textContent = when ? `Trading active · updated ${when}` : "Trading active — quoting and fills enabled.";
      } else {
        note.textContent = when ? `Trading paused · updated ${when}` : "Trading paused — no new quotes or fills.";
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
        const res = await fetch(path, { method: "POST" });
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

    function renderStats(health, pnl, markets, orders, positions, risk) {
      const row = document.getElementById("stats-row");
      const isPaper = String(health.mode_warning || "").toLowerCase().includes("paper");
      const realized = Number(pnl.realized_pnl) || 0;
      const unrealized = Number(pnl.unrealized_pnl) || 0;
      const total = Number(pnl.total_pnl);
      const portfolioTotal = Number.isFinite(total) ? total : realized + unrealized;
      const daily = Number(pnl.daily_pnl) || 0;
      const portfolioSub = isPaper ? "paper · realized + unrealized" : "realized + unrealized";
      const cards = [
        ["Bot status", health.status || "idle", "neutral", ""],
        ["Portfolio PnL", fmtMoney(portfolioTotal), pnlClass(portfolioTotal), portfolioSub],
        ["Today's change", fmtMoney(daily), pnlClass(daily), "since last reset"],
        ["Realized", fmtMoney(realized), pnlClass(realized), "closed trades"],
        ["Unrealized", fmtMoney(unrealized), pnlClass(unrealized), "open positions"],
        ["Markets", String((markets || []).length), "neutral", ""],
        ["Open orders", String((orders || []).length), "neutral", ""],
        ["Positions", String((positions || []).length), "neutral", ""],
        ["Risk events", String((risk || []).length), "neutral", ""],
      ];
      row.innerHTML = cards.map(([label, value, cls, sub]) =>
        `<div class="stat"><div class="stat-label">${escapeHtml(label)}</div>`
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

    function renderOrders(orders, marketsById) {
      const wrap = document.getElementById("orders-wrap");
      document.getElementById("orders-count").textContent = `${(orders || []).length} total`;
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
          <td><span class="status-pill ${escapeHtml(status)}">${escapeHtml(status.replaceAll("_", " "))}</span></td>
        </tr>`;
      }).join("");
      wrap.innerHTML = `<table class="data"><thead><tr>
        <th>Market</th><th>Side</th><th>Price</th><th>Size</th><th>Filled</th><th>Status</th>
      </tr></thead><tbody>${rows}</tbody></table>`;
    }

    function renderPositions(positions, marketsById) {
      const wrap = document.getElementById("positions-wrap");
      document.getElementById("positions-count").textContent = `${(positions || []).length} total`;
      if (!positions || !positions.length) {
        wrap.innerHTML = '<div class="empty">No open positions.</div>';
        return;
      }
      const rows = positions.map((p) => {
        const market = marketsById.get(p.market_id);
        const label = market?.question || p.market_id?.slice(0, 10) + "…";
        return `<tr>
          <td>${escapeHtml(label)}</td>
          <td class="num">${fmtNum(p.yes_size)}</td>
          <td class="num">${fmtNum(p.no_size)}</td>
          <td class="num">${fmtNum(p.net_yes ?? (p.yes_size - p.no_size))}</td>
          <td class="num ${pnlClass(p.realized_pnl)}">${fmtMoney(p.realized_pnl)}</td>
          <td class="num ${pnlClass(p.unrealized_pnl)}">${fmtMoney(p.unrealized_pnl ?? 0)}</td>
          <td class="num ${pnlClass(p.total_pnl ?? p.realized_pnl)}">${fmtMoney(p.total_pnl ?? p.realized_pnl)}</td>
        </tr>`;
      }).join("");
      wrap.innerHTML = `<table class="data"><thead><tr>
        <th>Market</th><th>Yes</th><th>No</th><th>Net yes</th><th>Realized</th><th>Unrealized</th><th>Total</th>
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
        const msg = evt.message || evt.reason || evt.event || JSON.stringify(evt);
        const when = evt.timestamp || evt.created_at || "";
        return `<li class="risk-item">${escapeHtml(msg)}${when ? `<time>${escapeHtml(fmtDate(when))}</time>` : ""}</li>`;
      }).join("");
    }

    async function refreshOverview() {
      const [health, markets, positions, orders, pnl, risk] = await Promise.all([
        fetch("/health").then(r => r.json()),
        fetch("/selected-markets").then(r => r.json()),
        fetch("/positions").then(r => r.json()),
        fetch("/orders").then(r => r.json()),
        fetch("/pnl").then(r => r.json()),
        fetch("/risk-events").then(r => r.json()),
      ]);
      document.getElementById("mode").innerText = health.mode_warning || health.status;
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
      const marketsById = marketLookup(markets);
      renderStats(health, pnl, markets, orders, positions, risk);
      updateTradingControls(health);
      updatePnlResetNote(pnl);
      renderMarkets(markets);
      renderOrders(orders, marketsById);
      renderPositions(positions, marketsById);
      renderRiskEvents(risk);
    }

    refreshOverview();
    setInterval(refreshOverview, 5000);
  </script>
</body>
</html>"""
