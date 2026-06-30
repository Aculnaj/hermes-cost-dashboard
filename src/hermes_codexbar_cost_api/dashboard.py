from __future__ import annotations


DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Hermes Cost</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #090909;
      --surface: #111111;
      --surface-2: #151514;
      --surface-3: #1a1918;
      --field: #0b0b0b;
      --border: #2b2926;
      --border-soft: #20201e;
      --border-faint: #191918;
      --muted: #88847d;
      --faint: #65615a;
      --text: #eeeeeb;
      --subtle: #c9c4bb;
      --accent: #c79a52;
      --accent-2: #948566;
      --green: #78a678;
      --red: #cf6d60;
      --amber: #bc8f48;
      --row: rgba(255, 255, 255, .035);
      --row-strong: rgba(199, 154, 82, .07);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      min-height: 100svh;
      background: var(--bg);
      color: var(--text);
      font-size: 13px;
      line-height: 1.5;
      overflow-x: hidden;
      text-rendering: optimizeLegibility;
      -webkit-font-smoothing: antialiased;
    }

    button, input {
      font: inherit;
    }

    button {
      min-height: 30px;
      border: 1px solid var(--border);
      background: var(--surface-2);
      color: var(--subtle);
      padding: 0 10px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 12px;
      font-weight: 560;
      letter-spacing: 0;
    }

    button:hover {
      background: var(--surface-3);
      border-color: #403d38;
      color: var(--text);
    }

    button:active {
      background: #0c0c0c;
    }

    input {
      width: min(300px, 100%);
      min-height: 30px;
      border: 1px solid var(--border);
      background: var(--field);
      color: var(--text);
      border-radius: 6px;
      padding: 0 10px;
      outline: none;
      font-size: 12px;
    }

    input:focus {
      border-color: #5b544a;
    }

    .shell {
      width: 100%;
      max-width: 1440px;
      margin: 0 auto;
      padding: calc(16px + env(safe-area-inset-top)) calc(18px + env(safe-area-inset-right))
        calc(34px + env(safe-area-inset-bottom)) calc(18px + env(safe-area-inset-left));
    }

    .topbar {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 18px;
      align-items: center;
      padding: 2px 0 14px;
      border-bottom: 1px solid var(--border-soft);
      margin-bottom: 16px;
    }

    .brand {
      display: flex;
      gap: 11px;
      align-items: center;
      min-width: 0;
    }

    .brand > div:last-child {
      min-width: 0;
    }

    .mark {
      width: 30px;
      height: 30px;
      border-radius: 6px;
      border: 1px solid var(--border);
      background: #121211;
      position: relative;
      flex: 0 0 auto;
    }

    .mark:before,
    .mark:after {
      content: "";
      position: absolute;
      left: 8px;
      right: 8px;
      height: 1px;
      background: var(--accent);
    }

    .mark:before {
      top: 10px;
    }

    .mark:after {
      bottom: 10px;
    }

    h1 {
      margin: 0;
      font-size: 17px;
      line-height: 1.2;
      font-weight: 680;
      letter-spacing: 0;
    }

    .meta {
      margin-top: 3px;
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .controls {
      display: flex;
      gap: 7px;
      align-items: center;
      justify-content: end;
      flex-wrap: wrap;
      min-width: 0;
    }

    .status {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      min-height: 30px;
      padding: 0 10px;
      border: 1px solid var(--border);
      border-radius: 6px;
      color: var(--subtle);
      background: var(--field);
      font-size: 12px;
      font-weight: 520;
      min-width: 0;
      overflow: hidden;
    }

    .status span:last-child {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--amber);
      flex: 0 0 auto;
    }

    .dot.ok { background: var(--green); }
    .dot.err { background: var(--red); }

    .summary-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 1px;
      margin-bottom: 16px;
      border: 1px solid var(--border-soft);
      border-radius: 7px;
      overflow: hidden;
      background: var(--border-soft);
    }

    .summary-item {
      min-width: 0;
      background: var(--surface);
      padding: 13px 14px 12px;
    }

    .summary-label, .panel-title {
      color: var(--muted);
      font-size: 11px;
      font-weight: 650;
      letter-spacing: 0;
      text-transform: uppercase;
    }

    .summary-value {
      margin-top: 8px;
      font-size: 24px;
      line-height: 1.1;
      font-weight: 690;
      letter-spacing: 0;
      font-variant-numeric: tabular-nums;
    }

    .summary-foot {
      margin-top: 8px;
      color: var(--muted);
      font-size: 12px;
      display: flex;
      gap: 11px;
      flex-wrap: wrap;
    }

    .grid {
      display: grid;
      gap: 16px;
    }

    .main {
      grid-template-columns: minmax(0, 1.55fr) minmax(360px, .85fr);
      align-items: start;
    }

    .stack {
      display: grid;
      gap: 16px;
      min-width: 0;
    }

    .tabs {
      display: flex;
      align-items: center;
      gap: 3px;
      min-width: 0;
      padding: 3px;
      border: 1px solid var(--border-soft);
      border-radius: 7px;
      background: #0b0b0b;
    }

    .tab-button {
      height: 26px;
      min-height: 26px;
      border: 0;
      background: transparent;
      color: var(--muted);
      border-radius: 5px;
      padding: 0 8px;
      font: inherit;
      font-size: 12px;
      font-weight: 590;
      cursor: pointer;
      white-space: nowrap;
    }

    .tab-button.active {
      color: var(--text);
      background: #1b1a18;
    }

    .tab-panel[hidden] {
      display: none;
    }

    .table-actions {
      display: flex;
      justify-content: center;
      padding: 9px 12px;
      border-top: 1px solid var(--border-soft);
      background: #0f0f0f;
    }

    .table-actions button {
      height: 30px;
    }

    .panel {
      min-width: 0;
      border: 1px solid var(--border-soft);
      background: var(--surface);
      border-radius: 7px;
      overflow: hidden;
    }

    .panel-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      min-height: 44px;
      padding: 0 13px;
      border-bottom: 1px solid var(--border-soft);
      background: #0f0f0f;
      min-width: 0;
    }

    .panel-title {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .panel-value {
      color: var(--muted);
      font-size: 12px;
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }

    .chart-wrap {
      min-width: 0;
      overflow: hidden;
      position: relative;
      background: var(--surface);
    }

    .chart {
      width: 100%;
      max-width: 100%;
      height: clamp(248px, 30vw, 330px);
      display: block;
      background: var(--surface);
    }

    .chart-tabs {
      display: flex;
      align-items: center;
      gap: 3px;
      margin-left: auto;
      padding: 3px;
      border: 1px solid var(--border-soft);
      border-radius: 7px;
      background: #0b0b0b;
    }

    .chart-tab {
      height: 24px;
      min-height: 24px;
      border: 0;
      background: transparent;
      color: var(--muted);
      border-radius: 5px;
      padding: 0 8px;
      font: inherit;
      font-size: 12px;
      font-weight: 590;
      cursor: pointer;
    }

    .chart-tab.active {
      color: var(--text);
      background: #1b1a18;
    }

    .chart-tooltip {
      position: absolute;
      pointer-events: none;
      z-index: 3;
      min-width: 170px;
      padding: 8px 9px;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: #0b0b0b;
      color: var(--text);
      font-size: 12px;
      font-variant-numeric: tabular-nums;
      opacity: 0;
      transform: translate(-50%, -100%);
      transition: opacity .08s ease;
    }

    .chart-tooltip.visible {
      opacity: 1;
    }

    .chart-tooltip .muted {
      display: block;
      margin-top: 3px;
    }

    .hover-target {
      cursor: crosshair;
    }

    .table-scroll {
      width: 100%;
      max-width: 100%;
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
      touch-action: pan-x;
      scrollbar-width: thin;
      scrollbar-color: #34312c transparent;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
    }

    th, td {
      padding: 8px 11px;
      border-bottom: 1px solid var(--border-soft);
      text-align: right;
      font-size: 12px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      font-variant-numeric: tabular-nums;
      vertical-align: middle;
    }

    th {
      color: var(--muted);
      font-weight: 670;
      text-transform: uppercase;
      letter-spacing: 0;
      font-size: 10px;
      background: #0d0d0d;
    }

    td:first-child, th:first-child {
      text-align: left;
    }

    tbody tr:nth-child(even) {
      background: rgba(255, 255, 255, .012);
    }

    tbody tr:hover {
      background: var(--row-strong);
    }

    tr:last-child td {
      border-bottom: 0;
    }

    .name {
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 0;
    }

    .name span:last-child {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .swatch {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--accent);
      flex: 0 0 auto;
    }

    .muted {
      color: var(--muted);
    }

    .session-copy {
      color: var(--text);
      cursor: copy;
      border-radius: 5px;
      padding: 2px 4px;
      margin-left: -4px;
      transition: background 120ms ease, color 120ms ease;
    }

    .session-copy:hover {
      background: rgba(255, 255, 255, 0.06);
      color: var(--accent);
    }

    .session-copy.copied {
      background: rgba(94, 234, 212, 0.12);
      color: var(--green);
    }

    .sessions td:first-child, .sessions th:first-child {
      text-align: left;
    }

    .calls-table {
      min-width: 1040px;
    }

    .sessions-table {
      min-width: 900px;
    }

    .empty {
      min-height: 150px;
      display: grid;
      place-items: center;
      color: var(--muted);
      border: 1px dashed var(--border);
      border-radius: 7px;
      margin: 14px;
      background: #0d0d0d;
      font-size: 13px;
    }

    @media (max-width: 1080px) {
      .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .main { grid-template-columns: 1fr; }
    }

    @media (max-width: 720px) {
      .shell {
        padding: calc(12px + env(safe-area-inset-top)) calc(10px + env(safe-area-inset-right))
          calc(24px + env(safe-area-inset-bottom)) calc(10px + env(safe-area-inset-left));
      }
      .topbar {
        grid-template-columns: 1fr;
        gap: 12px;
        margin-bottom: 12px;
        padding-bottom: 12px;
      }
      .controls {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        justify-content: stretch;
        width: 100%;
      }
      .status, .controls input {
        grid-column: 1 / -1;
      }
      .controls input {
        width: 100%;
        min-width: 0;
      }
      .controls button, .controls input, .status {
        min-height: 40px;
      }
      button {
        padding: 0 10px;
      }
      .summary-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
        margin-bottom: 12px;
      }
      .summary-item {
        padding: 10px 11px;
      }
      .summary-value {
        font-size: 18px;
        overflow-wrap: anywhere;
      }
      .summary-foot {
        gap: 7px;
        font-size: 11px;
      }
      .grid, .stack {
        gap: 12px;
      }
      .panel-head {
        min-height: 40px;
        padding: 0 11px;
        gap: 8px;
      }
      .activity-panel .panel-head {
        flex-wrap: wrap;
        padding-block: 8px;
      }
      .activity-panel .tabs {
        width: 100%;
      }
      .tabs {
        max-width: 100%;
        overflow-x: auto;
      }
      .tab-button {
        flex: 1 1 0;
        text-align: center;
      }
      .panel-value {
        font-size: 11px;
      }
      .chart-tabs {
        order: 2;
      }
      .chart { height: 220px; }
      table {
        min-width: 560px;
      }
      .calls-table { min-width: 780px; }
      .sessions-table { min-width: 760px; }
      .table-scroll td:first-child, .table-scroll th:first-child {
        position: sticky;
        left: 0;
        z-index: 1;
        background: var(--surface);
        box-shadow: 1px 0 0 var(--border-soft);
      }
      .table-scroll th:first-child {
        z-index: 2;
        background: #0d0d0d;
      }
      th, td {
        padding: 8px 9px;
      }
    }

    @media (max-width: 480px) {
      body {
        font-size: 12px;
      }
      .shell {
        padding: calc(8px + env(safe-area-inset-top)) calc(7px + env(safe-area-inset-right))
          calc(18px + env(safe-area-inset-bottom)) calc(7px + env(safe-area-inset-left));
      }
      .brand {
        gap: 8px;
      }
      .mark {
        width: 26px;
        height: 26px;
      }
      h1 {
        font-size: 15px;
      }
      .meta {
        font-size: 11px;
      }
      .controls {
        gap: 6px;
      }
      .controls button, .controls input, .status {
        min-height: 38px;
      }
      .summary-item {
        padding: 9px 10px;
      }
      .summary-label, .panel-title {
        font-size: 10px;
      }
      .summary-value {
        font-size: 16px;
      }
      .summary-foot {
        font-size: 10px;
      }
      .panel-head {
        min-height: 38px;
        padding-inline: 9px;
      }
      .chart { height: 200px; }
      .chart-tooltip {
        min-width: 150px;
        font-size: 11px;
      }
      .calls-table { min-width: 720px; }
      .sessions-table { min-width: 700px; }
      table { min-width: 500px; }
      th, td {
        padding: 7px 8px;
        font-size: 11px;
      }
      .session-copy {
        padding: 2px 3px;
      }
    }

    @media (max-width: 340px) {
      .summary-grid {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <main class="shell">
    <header class="topbar">
      <div class="brand">
        <div class="mark" aria-hidden="true"></div>
        <div>
          <h1>Hermes Cost</h1>
          <div id="meta" class="meta">Waiting for API key</div>
        </div>
      </div>
      <div class="controls">
        <span class="status"><span id="statusDot" class="dot"></span><span id="statusText">Disconnected</span></span>
        <input id="apiKey" type="password" autocomplete="off" placeholder="API key" aria-label="API key">
        <button id="saveKey" type="button">Connect</button>
        <button id="refresh" type="button">Refresh</button>
      </div>
    </header>

    <section id="cards" class="summary-grid" aria-label="Spend summary"></section>

    <section class="grid main">
      <div class="stack">
        <section class="panel activity-panel">
          <div class="panel-head">
            <div class="panel-title">Spend</div>
            <div class="chart-tabs" role="tablist" aria-label="Chart range">
              <button id="chart24h" class="chart-tab" type="button" role="tab" aria-selected="false" data-range="24h">24h</button>
              <button id="chart30d" class="chart-tab active" type="button" role="tab" aria-selected="true" data-range="30d">30d</button>
            </div>
            <div id="chartValue" class="panel-value"></div>
          </div>
          <div id="dailyChart" class="chart-wrap"></div>
        </section>

        <section class="panel">
          <div class="panel-head">
            <div class="tabs" role="tablist" aria-label="Recent activity">
              <button id="callsTab" class="tab-button active" type="button" role="tab" aria-selected="true" aria-controls="callsPane" data-tab="calls">Recent calls <span id="callCount"></span></button>
              <button id="sessionsTab" class="tab-button" type="button" role="tab" aria-selected="false" aria-controls="sessionsPane" data-tab="sessions">Recent sessions <span id="sessionCount"></span></button>
            </div>
            <div id="activityHint" class="panel-value">calls</div>
          </div>
          <div id="callsPane" class="tab-panel" role="tabpanel" aria-labelledby="callsTab">
            <div id="calls" class="table-scroll"></div>
            <div class="table-actions"><button id="loadMoreCalls" type="button">Load 100 more calls</button></div>
          </div>
          <div id="sessionsPane" class="tab-panel" role="tabpanel" aria-labelledby="sessionsTab" hidden>
            <div id="sessions" class="table-scroll"></div>
          </div>
        </section>
      </div>

      <div class="stack">
        <section class="panel">
          <div class="panel-head">
            <div class="panel-title">Providers</div>
            <div id="providerCount" class="panel-value"></div>
          </div>
          <div id="providers" class="table-scroll"></div>
        </section>

        <section class="panel">
          <div class="panel-head">
            <div class="panel-title">Models</div>
            <div id="modelCount" class="panel-value"></div>
          </div>
          <div id="models" class="table-scroll"></div>
        </section>

        <section class="panel">
          <div class="panel-head">
            <div class="panel-title">Sources</div>
            <div id="sourceCount" class="panel-value"></div>
          </div>
          <div id="sources" class="table-scroll"></div>
        </section>
      </div>
    </section>
  </main>

  <script>
    const storeKey = "hermes.dashboard.apiKey";
    const callLimitStep = 100;
    const state = { data: null, callLimit: 300, chartRange: "30d" };
    const apiKeyInput = document.getElementById("apiKey");
    const saveKey = document.getElementById("saveKey");
    const refresh = document.getElementById("refresh");
    const loadMoreCalls = document.getElementById("loadMoreCalls");
    const statusDot = document.getElementById("statusDot");
    const statusText = document.getElementById("statusText");
    const meta = document.getElementById("meta");
    const refreshIntervalMs = 1000;
    let refreshInFlight = false;

    apiKeyInput.value = localStorage.getItem(storeKey) || "";
    saveKey.addEventListener("click", () => {
      localStorage.setItem(storeKey, apiKeyInput.value.trim());
      loadOverview();
    });
    refresh.addEventListener("click", loadOverview);
    loadMoreCalls.addEventListener("click", () => {
      state.callLimit += callLimitStep;
      loadOverview();
    });
    apiKeyInput.addEventListener("keydown", event => {
      if (event.key === "Enter") saveKey.click();
    });
    document.querySelectorAll(".tab-button").forEach(button => {
      button.addEventListener("click", () => activateActivityTab(button.dataset.tab));
    });
    document.querySelectorAll(".chart-tab").forEach(button => {
      button.addEventListener("click", () => activateChartRange(button.dataset.range));
    });
    window.setInterval(() => {
      const key = (apiKeyInput.value || localStorage.getItem(storeKey) || "").trim();
      if (key && document.visibilityState !== "hidden") loadOverview({ silent: true });
    }, refreshIntervalMs);

    function activateActivityTab(tab) {
      const callsActive = tab !== "sessions";
      document.getElementById("callsPane").hidden = !callsActive;
      document.getElementById("sessionsPane").hidden = callsActive;
      document.getElementById("callsTab").classList.toggle("active", callsActive);
      document.getElementById("sessionsTab").classList.toggle("active", !callsActive);
      document.getElementById("callsTab").setAttribute("aria-selected", String(callsActive));
      document.getElementById("sessionsTab").setAttribute("aria-selected", String(!callsActive));
      document.getElementById("activityHint").textContent = callsActive ? "calls" : "sessions";
    }

    function activateChartRange(range) {
      state.chartRange = range === "30d" ? "30d" : "24h";
      document.querySelectorAll(".chart-tab").forEach(button => {
        const active = button.dataset.range === state.chartRange;
        button.classList.toggle("active", active);
        button.setAttribute("aria-selected", String(active));
      });
      if (state.data) renderSpendChart(state.data);
    }

    function setStatus(kind, text) {
      statusDot.className = "dot" + (kind === "ok" ? " ok" : kind === "err" ? " err" : "");
      statusText.textContent = text;
    }

    async function loadOverview(options = {}) {
      const key = (apiKeyInput.value || localStorage.getItem(storeKey) || "").trim();
      if (!key) {
        setStatus("warn", "Disconnected");
        renderEmpty("API key required");
        return;
      }

      if (refreshInFlight) return;
      refreshInFlight = true;
      if (!options.silent) setStatus("warn", "Refreshing");
      try {
        const response = await fetch(`/api/overview?call_limit=${state.callLimit}&t=${Date.now()}`, {
          headers: { "Authorization": `Bearer ${key}` },
          cache: "no-store"
        });
        if (!response.ok) throw new Error(response.status === 401 ? "Unauthorized" : `HTTP ${response.status}`);
        const data = await response.json();
        state.data = data;
        setStatus(data.status === "error" ? "err" : "ok", data.status === "error" ? "Data error" : "Connected");
        render(data);
      } catch (error) {
        setStatus("err", error.message);
        renderEmpty(error.message);
      } finally {
        refreshInFlight = false;
      }
    }

    function render(data) {
      meta.textContent = `${fmtDateTime(data.generated_at)} | ${data.timezone} | ${data.lookback_days} days`;
      renderCards(data.summary || {});
      renderSpendChart(data);
      renderTable("providers", data.providers || [], providerRow);
      renderTable("models", data.models || [], modelRow);
      renderTable("sources", data.sources || [], sourceRow);
      renderCalls(data.recent_calls || []);
      renderSessions(data.recent_sessions || []);
      document.getElementById("providerCount").textContent = `${(data.providers || []).length} rows`;
      document.getElementById("modelCount").textContent = `${(data.models || []).length} rows`;
      document.getElementById("sourceCount").textContent = `${(data.sources || []).length} rows`;
      document.getElementById("callCount").textContent = `${(data.recent_calls || []).length} loaded`;
      document.getElementById("sessionCount").textContent = `${(data.recent_sessions || []).length} all`;
      updateCallLoadMore(data.recent_calls || []);
    }

    function updateCallLoadMore(rows) {
      const hasMoreLikely = rows.length >= state.callLimit;
      loadMoreCalls.hidden = !hasMoreLikely;
      loadMoreCalls.disabled = false;
      loadMoreCalls.textContent = `Load ${callLimitStep} more calls`;
    }

    function renderEmpty(message) {
      meta.textContent = message;
      document.getElementById("cards").innerHTML = "";
      for (const id of ["dailyChart", "providers", "models", "sources", "calls", "sessions"]) {
        const node = document.getElementById(id);
        node.innerHTML = "";
        const empty = document.createElement("div");
        empty.className = "empty";
        empty.textContent = message;
        node.appendChild(empty);
      }
      document.getElementById("chartValue").textContent = "";
      document.getElementById("providerCount").textContent = "";
      document.getElementById("modelCount").textContent = "";
      document.getElementById("sourceCount").textContent = "";
      document.getElementById("callCount").textContent = "";
      document.getElementById("sessionCount").textContent = "";
      loadMoreCalls.hidden = true;
    }

    function renderCards(summary) {
      const cards = document.getElementById("cards");
      cards.innerHTML = "";
      const order = ["today", "this_week", "this_month", "lookback_total"];
      for (const key of order) {
        const item = summary[key] || {};
        const card = document.createElement("article");
        card.className = "summary-item";
        card.appendChild(node("div", "summary-label", item.label || key));
        card.appendChild(node("div", "summary-value", fmtMoney(item.approx_cost || 0)));
        const foot = document.createElement("div");
        foot.className = "summary-foot";
        foot.appendChild(node("span", "", `${fmtInt(item.requests || 0)} req`));
        foot.appendChild(node("span", "", `${fmtCompact(item.total_tokens || 0)} tokens`));
        card.appendChild(foot);
        cards.appendChild(card);
      }
    }

    function renderSpendChart(data) {
      const hourly = (data.hourly || []).map(row => ({
        ...row,
        key: row.hour,
        label: hourLabel(row.hour),
        tooltipLabel: fmtDateTime(row.hour)
      }));
      const daily = (data.daily || []).map(row => ({
        ...row,
        key: row.date,
        label: shortDate(row.date),
        tooltipLabel: shortDate(row.date)
      }));
      const rows = state.chartRange === "30d" ? daily : hourly;
      renderChart(rows, state.chartRange === "30d" ? "30 days" : "24 hours");
    }

    function renderChart(rows, label) {
      const host = document.getElementById("dailyChart");
      host.innerHTML = "";
      if (!rows.length) {
        host.appendChild(node("div", "empty", "No chart data"));
        return;
      }

      const maxCost = Math.max(...rows.map(row => row.approx_cost || 0), 0.01);
      const width = 900, height = 320;
      const pad = { left: 54, right: 22, top: 24, bottom: 42 };
      const innerW = width - pad.left - pad.right;
      const innerH = height - pad.top - pad.bottom;
      const slot = innerW / rows.length;
      const lineStep = rows.length > 1 ? innerW / (rows.length - 1) : innerW;
      const points = rows.map((row, index) => {
        const x = pad.left + index * lineStep;
        const y = pad.top + innerH - ((row.approx_cost || 0) / maxCost) * innerH;
        return { x, y, row };
      });
      const line = points.map(point => `${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(" ");
      const area = `${pad.left},${height - pad.bottom} ${line} ${width - pad.right},${height - pad.bottom}`;
      const hoverZones = rows.map((row, index) => {
        const x = pad.left + index * slot;
        return `<rect class="hover-target" data-index="${index}" x="${x.toFixed(2)}" y="${pad.top}" width="${slot.toFixed(2)}" height="${innerH}" fill="transparent"></rect>`;
      }).join("");
      const labels = pickLabels(rows).map(index => {
        const x = pad.left + index * lineStep;
        return `<text x="${x.toFixed(1)}" y="${height - 14}" text-anchor="middle" fill="#88847d" font-size="11">${esc(rows[index].label)}</text>`;
      }).join("");
      const grid = [0, .25, .5, .75, 1].map(value => {
        const y = pad.top + innerH - value * innerH;
        return `<g>
          <line x1="${pad.left}" y1="${y.toFixed(1)}" x2="${width - pad.right}" y2="${y.toFixed(1)}" stroke="#20201e"></line>
          <text x="${pad.left - 9}" y="${(y + 4).toFixed(1)}" text-anchor="end" fill="#65615a" font-size="10">${fmtMoney(maxCost * value)}</text>
        </g>`;
      }).join("");
      const pointNodes = points.map((point, index) => `<circle class="hover-target" data-index="${index}" cx="${point.x.toFixed(2)}" cy="${point.y.toFixed(2)}" r="2.75" fill="#c79a52" stroke="#111111" stroke-width="1.5"></circle>`).join("");
      host.innerHTML = `<svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Spend chart ${esc(label)}">
        <rect x="${pad.left}" y="${pad.top}" width="${innerW}" height="${innerH}" fill="#0f0f0f"></rect>
        ${grid}
        <line x1="${pad.left}" y1="${height - pad.bottom}" x2="${width - pad.right}" y2="${height - pad.bottom}" stroke="#2b2926"></line>
        <polygon points="${area}" fill="#6f5430" opacity=".16"></polygon>
        <polyline points="${line}" fill="none" stroke="#c79a52" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"></polyline>
        ${pointNodes}
        ${hoverZones}
        ${labels}
      </svg><div id="chartTooltip" class="chart-tooltip"></div>`;
      const total = rows.reduce((sum, row) => sum + (row.approx_cost || 0), 0);
      document.getElementById("chartValue").textContent = `${label} · ${fmtMoney(total)}`;
      wireChartHover(host, rows, pad, width, height, slot, lineStep);
    }

    function wireChartHover(host, rows, pad, width, height, slot, lineStep) {
      const tooltip = document.getElementById("chartTooltip");
      if (!tooltip) return;
      const show = (event) => {
        const index = Number(event.target.dataset.index);
        const row = rows[index];
        if (!row) return;
        const x = pad.left + index * lineStep;
        const y = event.offsetY || 0;
        tooltip.innerHTML = `${esc(row.tooltipLabel)}<span class="muted">${fmtMoney(row.approx_cost || 0)} · ${fmtCompact(row.total_tokens || 0)} tokens · ${fmtInt(row.requests || 0)} req</span>`;
        tooltip.style.left = `${(Math.min(Math.max(x, 88), width - 88) / width) * 100}%`;
        tooltip.style.top = `${Math.max(52, Math.min(y, height - 26))}px`;
        tooltip.classList.add("visible");
      };
      host.querySelectorAll(".hover-target").forEach(target => {
        target.addEventListener("mousemove", show);
        target.addEventListener("mouseenter", show);
        target.addEventListener("mouseleave", () => tooltip.classList.remove("visible"));
      });
    }

    function renderTable(targetId, rows, rowRenderer) {
      const host = document.getElementById(targetId);
      host.innerHTML = "";
      if (!rows.length) {
        host.appendChild(node("div", "empty", "No data"));
        return;
      }
      const table = document.createElement("table");
      table.className = "metrics-table";
      appendColGroup(table, ["46%", "18%", "18%", "18%"]);
      const thead = document.createElement("thead");
      const headRow = document.createElement("tr");
      for (const column of ["Name", "Cost", "Tokens", "Requests"]) headRow.appendChild(node("th", "", column));
      thead.appendChild(headRow);
      table.appendChild(thead);
      const tbody = document.createElement("tbody");
      rows.slice(0, 10).forEach((row, index) => tbody.appendChild(rowRenderer(row, index)));
      table.appendChild(tbody);
      host.appendChild(table);
    }

    function providerRow(row, index) {
      return metricRow(row, index, row.kind === "aggregate" ? "Hermes" : row.label);
    }

    function modelRow(row, index) {
      return metricRow(row, index, row.label);
    }

    function sourceRow(row, index) {
      return metricRow(row, index, row.label);
    }

    function metricRow(row, index, label) {
      const tr = document.createElement("tr");
      const nameCell = document.createElement("td");
      const wrap = document.createElement("div");
      wrap.className = "name";
      const swatch = document.createElement("span");
      swatch.className = "swatch";
      swatch.style.background = index % 3 === 0 ? "var(--accent)" : index % 3 === 1 ? "var(--green)" : "var(--accent-2)";
      wrap.appendChild(swatch);
      wrap.appendChild(node("span", "", label || "unknown"));
      nameCell.appendChild(wrap);
      tr.appendChild(nameCell);
      tr.appendChild(node("td", "", fmtMoney(row.approx_cost || 0)));
      tr.appendChild(node("td", "muted", fmtCompact(row.total_tokens || 0)));
      tr.appendChild(node("td", "muted", fmtInt(row.requests || 0)));
      return tr;
    }

    function renderCalls(rows) {
      const host = document.getElementById("calls");
      host.innerHTML = "";
      if (!rows.length) {
        host.appendChild(node("div", "empty", "No calls"));
        return;
      }
      const table = document.createElement("table");
      table.className = "sessions calls-table";
      appendColGroup(table, ["15%", "22%", "11%", "12%", "18%", "8%", "7%", "7%"]);
      const thead = document.createElement("thead");
      const head = document.createElement("tr");
      ["Time", "Session", "Source", "Provider", "Model", "Cost", "Tokens", "Finish"].forEach(label => head.appendChild(node("th", "", label)));
      thead.appendChild(head);
      table.appendChild(thead);
      const tbody = document.createElement("tbody");
      rows.forEach(row => {
        const tr = document.createElement("tr");
        tr.title = row.session_title || row.session_id || "";
        tr.appendChild(node("td", "muted", fmtDateTime(row.occurred_at)));
        tr.appendChild(sessionCell(row));
        tr.appendChild(node("td", "muted", row.source || "unknown"));
        tr.appendChild(node("td", "", row.provider || "unknown"));
        tr.appendChild(node("td", "muted", row.model || "unknown"));
        tr.appendChild(node("td", "", fmtMoneyTable(row.approx_cost || 0)));
        tr.appendChild(node("td", "muted", fmtCompact(row.total_tokens || 0)));
        tr.appendChild(node("td", "", row.finish_reason || "unknown"));
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      host.appendChild(table);
    }

    function renderSessions(rows) {
      const host = document.getElementById("sessions");
      host.innerHTML = "";
      if (!rows.length) {
        host.appendChild(node("div", "empty", "No sessions"));
        return;
      }
      const table = document.createElement("table");
      table.className = "sessions sessions-table";
      appendColGroup(table, ["28%", "16%", "12%", "12%", "18%", "7%", "7%"]);
      const thead = document.createElement("thead");
      const head = document.createElement("tr");
      ["Session", "Time", "Source", "Provider", "Model", "Cost", "Tokens"].forEach(label => head.appendChild(node("th", "", label)));
      thead.appendChild(head);
      table.appendChild(thead);
      const tbody = document.createElement("tbody");
      rows.forEach(row => {
        const tr = document.createElement("tr");
        tr.title = row.session_title || row.session_id || "";
        tr.appendChild(sessionCell(row));
        tr.appendChild(node("td", "muted", fmtDateTime(row.occurred_at)));
        tr.appendChild(node("td", "muted", row.source || "unknown"));
        tr.appendChild(node("td", "", row.provider || "unknown"));
        tr.appendChild(node("td", "muted", row.model || "unknown"));
        tr.appendChild(node("td", "", fmtMoneyTable(row.approx_cost || 0)));
        tr.appendChild(node("td", "muted", fmtCompact(row.total_tokens || 0)));
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      host.appendChild(table);
    }

    function appendColGroup(table, widths) {
      const colgroup = document.createElement("colgroup");
      widths.forEach(width => {
        const col = document.createElement("col");
        col.style.width = width;
        colgroup.appendChild(col);
      });
      table.appendChild(colgroup);
    }

    function node(tag, className, text) {
      const element = document.createElement(tag);
      if (className) element.className = className;
      element.textContent = text;
      return element;
    }

    function sessionCell(row) {
      const cell = document.createElement("td");
      const button = document.createElement("span");
      const label = sessionLabel(row);
      button.className = "session-copy";
      button.textContent = label;
      button.title = row.session_id ? `Click to copy session: ${row.session_id}` : `Click to copy: ${label}`;
      button.addEventListener("click", event => {
        event.preventDefault();
        event.stopPropagation();
        copySessionText(row, button);
      });
      cell.appendChild(button);
      return cell;
    }

    async function copySessionText(row, element) {
      const value = row.session_id || row.session_title || sessionLabel(row);
      if (!value || value === "unknown") return;
      try {
        await navigator.clipboard.writeText(value);
      } catch (_) {
        const textarea = document.createElement("textarea");
        textarea.value = value;
        textarea.setAttribute("readonly", "");
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        textarea.remove();
      }
      element.classList.add("copied");
      const original = element.textContent;
      element.textContent = "Copied";
      window.clearTimeout(element._copyTimer);
      element._copyTimer = window.setTimeout(() => {
        element.textContent = original;
        element.classList.remove("copied");
      }, 900);
    }

    function sessionLabel(row) {
      if (row.session_title) return row.session_title;
      if (row.client === "codex" && row.session_id) return `Codex ${String(row.session_id).slice(0, 8)}`;
      if (row.session_id) return `#${String(row.session_id).slice(0, 10)}`;
      return "unknown";
    }

    function fmtMoney(value) {
      return new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);
    }

    function fmtMoneyTable(value) {
      return new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", minimumFractionDigits: 4, maximumFractionDigits: 4 }).format(value || 0);
    }

    function fmtInt(value) {
      return new Intl.NumberFormat().format(value || 0);
    }

    function fmtCompact(value) {
      return new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(value || 0);
    }

    function fmtDateTime(value) {
      if (!value) return "unknown";
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return "unknown";
      return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
    }

    function shortDate(value) {
      const date = new Date(`${value}T00:00:00`);
      if (Number.isNaN(date.getTime())) return value;
      return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(date);
    }

    function hourLabel(value) {
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return value;
      return new Intl.DateTimeFormat(undefined, { hour: "2-digit" }).format(date);
    }

    function pickLabels(rows) {
      if (rows.length <= 6) return rows.map((_, index) => index);
      const indexes = new Set([0, rows.length - 1]);
      const parts = 4;
      for (let i = 1; i < parts; i++) indexes.add(Math.round((rows.length - 1) * i / parts));
      return [...indexes].sort((a, b) => a - b);
    }

    function esc(value) {
      return String(value).replace(/[&<>"']/g, character => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
      }[character]));
    }

    loadOverview();
  </script>
</body>
</html>
"""
