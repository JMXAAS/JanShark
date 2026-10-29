"""
JanShark Static HTML Analytics Dashboard Generator
Generates a single-file, zero-server HTML application (`index.html`) that:
1. Embeds the parsed log bundle (or loads any `.duckdb` / `.parquet` file dropped into the browser)
2. Boots DuckDB-WASM directly in the browser so the user can run instant SQL & interactive filters
3. Provides dedicated Logshark Server Workbooks as tabs:
   - Overview & Error Triage
   - Apache (HTTP Gateway, View Loads, Status Codes, Slow Requests)
   - Backgrounder (Extract Refreshes, Subscriptions, Queue vs Run Time, Failures)
   - VizQL & ART (Activity Resource Tracing, CPU vs Memory Allocation, Sponsorship Tree, Cache Hits)
   - Hyper Data Engine (Query Performance, Peak Memory, Disk Spooling)
   - Resource Manager / SRM (Node & Process CPU %, Memory MB vs Limits, Recycle/Throttle Events)
   - DuckDB SQL Workbench (Run custom SQL directly against the tables in-browser)
"""

import json
from pathlib import Path
from typing import Any


def build_static_dashboard(
    bundle: dict[str, list[dict[str, Any]]],
    output_html_path: str | Path = "dashboard.html",
) -> Path:
    out_path = Path(output_html_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Serialize bundle cleanly into JSON for instant embedding & registration into DuckDB-WASM
    bundle_json = json.dumps(bundle, separators=(",", ":"))

    html_content = HTML_TEMPLATE.replace("__JANSHARK_DATA_BUNDLE__", bundle_json)
    out_path.write_text(html_content, encoding="utf-8")
    return out_path


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>JanShark — Tableau Server Log Analytics (DuckDB Engine)</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
  <style>
    :root {
      --bg-base: #0b0f17;
      --bg-surface: #111827;
      --bg-elevated: #1e293b;
      --bg-hover: #283548;
      --border: #26334d;
      --text-main: #f1f5f9;
      --text-muted: #94a3b8;
      --accent: #38bdf8;
      --accent-indigo: #6366f1;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --purple: #a855f7;
      --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      --font-mono: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg-base);
      color: var(--text-main);
      font-family: var(--font-sans);
      font-size: 13.5px;
      line-height: 1.5;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }

    /* Top Header */
    .topbar {
      background: linear-gradient(90deg, #0f172a 0%, #162038 100%);
      border-bottom: 1px solid var(--border);
      padding: 12px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      flex-wrap: wrap;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .brand-icon {
      width: 36px;
      height: 36px;
      border-radius: 9px;
      background: linear-gradient(135deg, var(--accent), var(--accent-indigo));
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 800;
      font-size: 18px;
      color: #0b0f17;
      box-shadow: 0 0 16px rgba(56, 189, 248, 0.35);
    }
    .brand-title {
      font-size: 17px;
      font-weight: 700;
      letter-spacing: -0.02em;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .badge-engine {
      font-size: 11px;
      font-weight: 600;
      padding: 2px 8px;
      border-radius: 999px;
      background: rgba(56, 189, 248, 0.14);
      color: var(--accent);
      border: 1px solid rgba(56, 189, 248, 0.3);
      font-family: var(--font-mono);
    }
    .brand-sub {
      font-size: 11.5px;
      color: var(--text-muted);
    }

    .topbar-actions {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    .btn {
      background: var(--bg-elevated);
      color: var(--text-main);
      border: 1px solid var(--border);
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 500;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s ease;
    }
    .btn:hover { background: var(--bg-hover); border-color: var(--accent); }
    .btn-primary {
      background: linear-gradient(135deg, #0284c7, #4f46e5);
      border-color: #38bdf8;
      color: #fff;
    }
    .btn-primary:hover { opacity: 0.92; }

    /* Global Filter Bar */
    .filter-bar {
      background: var(--bg-surface);
      border-bottom: 1px solid var(--border);
      padding: 10px 24px;
      display: flex;
      align-items: center;
      gap: 14px;
      flex-wrap: wrap;
      position: sticky;
      top: 0;
      z-index: 40;
    }
    .filter-group {
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .filter-label {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      font-weight: 600;
    }
    select, input[type="text"], input[type="search"] {
      background: var(--bg-base);
      color: var(--text-main);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 5px 10px;
      font-size: 12.5px;
      font-family: var(--font-sans);
      outline: none;
    }
    select:focus, input:focus { border-color: var(--accent); }

    /* Navigation Tabs */
    .nav-tabs {
      background: var(--bg-surface);
      border-bottom: 1px solid var(--border);
      padding: 0 24px;
      display: flex;
      gap: 4px;
      overflow-x: auto;
    }
    .tab-btn {
      background: transparent;
      color: var(--text-muted);
      border: none;
      border-bottom: 2px solid transparent;
      padding: 11px 16px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 8px;
      white-space: nowrap;
      transition: all 0.15s;
    }
    .tab-btn:hover { color: var(--text-main); background: rgba(255,255,255,0.02); }
    .tab-btn.active {
      color: var(--accent);
      border-bottom-color: var(--accent);
      background: rgba(56, 189, 248, 0.06);
    }
    .tab-count {
      font-size: 10.5px;
      padding: 1px 6px;
      border-radius: 99px;
      background: var(--bg-elevated);
      color: var(--text-muted);
      font-family: var(--font-mono);
    }
    .tab-btn.active .tab-count {
      background: rgba(56, 189, 248, 0.2);
      color: var(--accent);
    }

    /* Main Content Container */
    .main-content {
      padding: 20px 24px 40px;
      max-width: 1680px;
      width: 100%;
      margin: 0 auto;
      flex: 1;
    }
    .tab-pane { display: none; }
    .tab-pane.active { display: block; }

    /* KPI Grid */
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 14px;
      margin-bottom: 18px;
    }
    .kpi-card {
      background: var(--bg-surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 14px 16px;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .kpi-title {
      font-size: 11.5px;
      color: var(--text-muted);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .kpi-value {
      font-size: 24px;
      font-weight: 700;
      font-family: var(--font-mono);
      letter-spacing: -0.02em;
    }
    .kpi-sub {
      font-size: 11.5px;
      color: var(--text-muted);
    }

    /* Charts & Panels Grid */
    .grid-2 {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(460px, 1fr));
      gap: 16px;
      margin-bottom: 18px;
    }
    .panel {
      background: var(--bg-surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px;
      margin-bottom: 18px;
    }
    .panel-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 12px;
      gap: 12px;
    }
    .panel-title {
      font-size: 14px;
      font-weight: 600;
      color: var(--text-main);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .panel-subtitle {
      font-size: 11.5px;
      color: var(--text-muted);
    }
    .chart-box {
      position: relative;
      height: 250px;
      width: 100%;
    }

    /* Data Tables */
    .table-wrap {
      overflow-x: auto;
      max-height: 420px;
      overflow-y: auto;
      border: 1px solid var(--border);
      border-radius: 8px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 12.5px;
    }
    thead th {
      background: var(--bg-elevated);
      color: var(--text-muted);
      font-weight: 600;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      padding: 9px 12px;
      position: sticky;
      top: 0;
      z-index: 10;
      border-bottom: 1px solid var(--border);
    }
    tbody tr {
      border-bottom: 1px solid rgba(38, 51, 77, 0.55);
      transition: background 0.1s;
    }
    tbody tr:hover { background: var(--bg-hover); }
    td {
      padding: 8px 12px;
      vertical-align: top;
    }
    .mono { font-family: var(--font-mono); font-size: 12px; }

    /* Pills & Status Badges */
    .pill {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 99px;
      font-size: 11px;
      font-weight: 600;
      font-family: var(--font-mono);
    }
    .pill-success { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
    .pill-warn { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }
    .pill-danger { background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }
    .pill-info { background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); }

    .clickable-id {
      color: var(--accent);
      cursor: pointer;
      text-decoration: underline;
      text-underline-offset: 2px;
    }
    .clickable-id:hover { color: #7dd3fc; }

    /* SQL Workbench */
    .sql-editor {
      width: 100%;
      min-height: 110px;
      background: #070a10;
      color: #38bdf8;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px;
      font-family: var(--font-mono);
      font-size: 13px;
      resize: vertical;
      margin-bottom: 10px;
    }
    .preset-pills {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 12px;
    }
  </style>
</head>
<body>

  <!-- Top Header -->
  <header class="topbar">
    <div class="brand">
      <div class="brand-icon">JS</div>
      <div>
        <div class="brand-title">
          JanShark
          <span class="badge-engine" id="engineStatusBadge">DuckDB In-Browser Ready</span>
        </div>
        <div class="brand-sub" id="runMetaSub">Reengineered Tableau Server Logshark • Zero-Server Static Web Analytics</div>
      </div>
    </div>
    <div class="topbar-actions">
      <label class="btn" title="Load a .duckdb, .parquet, or JanShark .json bundle directly in browser">
        📂 Load .duckdb / .json / .parquet
        <input type="file" id="fileInput" accept=".duckdb,.db,.parquet,.json" style="display:none" />
      </label>
      <button class="btn" id="btnResetFilters" title="Reset all global filters">↺ Reset Filters</button>
      <button class="btn btn-primary" onclick="switchTab('sql')">⚡ DuckDB SQL Workbench</button>
    </div>
  </header>

  <!-- Global Interactive Filter Bar -->
  <section class="filter-bar">
    <div class="filter-group">
      <span class="filter-label">Worker Node</span>
      <select id="filterNode">
        <option value="ALL">All Nodes</option>
      </select>
    </div>
    <div class="filter-group">
      <span class="filter-label">Site</span>
      <select id="filterSite">
        <option value="ALL">All Sites</option>
      </select>
    </div>
    <div class="filter-group">
      <span class="filter-label">Workbook</span>
      <select id="filterWorkbook">
        <option value="ALL">All Workbooks</option>
      </select>
    </div>
    <div class="filter-group">
      <span class="filter-label">Severity / Status</span>
      <select id="filterSeverity">
        <option value="ALL">All Levels</option>
        <option value="ERRORS_ONLY">Errors & Failures Only (5xx / ERROR / Failed)</option>
        <option value="WARN_AND_UP">Warnings & Errors (4xx / 5xx / WARN / ERROR)</option>
      </select>
    </div>
    <div class="filter-group">
      <span class="filter-label">Request / Session ID</span>
      <input type="text" id="filterReqId" placeholder="e.g. Y9xK2w... or SESS-..." style="width: 175px;" />
    </div>
    <div class="filter-group" style="flex:1; min-width: 190px;">
      <span class="filter-label">Search</span>
      <input type="search" id="filterSearch" placeholder="Filter URI, SQL query, error message, user, target..." style="width: 100%;" />
    </div>
  </section>

  <!-- Navigation Tabs (Server Logshark Plugins) -->
  <nav class="nav-tabs">
    <button class="tab-btn active" data-tab="overview" onclick="switchTab('overview')">
      📊 Overview & Triage <span class="tab-count" id="cnt-overview">0</span>
    </button>
    <button class="tab-btn" data-tab="apache" onclick="switchTab('apache')">
      🌐 Apache Gateway <span class="tab-count" id="cnt-apache">0</span>
    </button>
    <button class="tab-btn" data-tab="backgrounder" onclick="switchTab('backgrounder')">
      ⚙️ Backgrounder Jobs <span class="tab-count" id="cnt-backgrounder">0</span>
    </button>
    <button class="tab-btn" data-tab="vizql" onclick="switchTab('vizql')">
      📈 VizQL & ART Tracing <span class="tab-count" id="cnt-vizql">0</span>
    </button>
    <button class="tab-btn" data-tab="hyper" onclick="switchTab('hyper')">
      🚀 Hyper Engine <span class="tab-count" id="cnt-hyper">0</span>
    </button>
    <button class="tab-btn" data-tab="srm" onclick="switchTab('srm')">
      🖥️ Resource Manager (CPU/RAM) <span class="tab-count" id="cnt-srm">0</span>
    </button>
    <button class="tab-btn" data-tab="sql" onclick="switchTab('sql')">
      🦆 DuckDB SQL Console
    </button>
  </nav>

  <!-- Main Content -->
  <main class="main-content">

    <!-- 1. OVERVIEW & TRIAGE TAB -->
    <div class="tab-pane active" id="pane-overview">
      <div class="kpi-grid" id="overview-kpis"></div>
      <div class="grid-2">
        <div class="panel">
          <div class="panel-header">
            <div>
              <div class="panel-title">Server Event & Error Timeline Across Components</div>
              <div class="panel-subtitle">Correlates HTTP requests, VizQL queries, Backgrounder jobs, and SRM alerts over time</div>
            </div>
          </div>
          <div class="chart-box"><canvas id="chartOverviewTimeline"></canvas></div>
        </div>
        <div class="panel">
          <div class="panel-header">
            <div>
              <div class="panel-title">Slowest Workbooks & Views (End-to-End Avg Load vs ART CPU)</div>
              <div class="panel-subtitle">Click any Request ID below to trace it across Apache → VizQL/ART → Hyper</div>
            </div>
          </div>
          <div class="chart-box"><canvas id="chartOverviewWorkbooks"></canvas></div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">🚨 Unified Server Error & Bottleneck Triage Feed</div>
            <div class="panel-subtitle">All HTTP 5xx, Backgrounder job failures, VizQL exceptions, Hyper memory errors, and SRM process recycles</div>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Node</th>
                <th>Plugin / Service</th>
                <th>Severity</th>
                <th>Site / Target</th>
                <th>Correlation / ID</th>
                <th>Diagnostic Details</th>
              </tr>
            </thead>
            <tbody id="tbodyOverviewErrors"></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- 2. APACHE GATEWAY TAB -->
    <div class="tab-pane" id="pane-apache">
      <div class="kpi-grid" id="apache-kpis"></div>
      <div class="grid-2">
        <div class="panel">
          <div class="panel-header">
            <div>
              <div class="panel-title">HTTP Request Volume & Status Code Breakdown</div>
              <div class="panel-subtitle">Replaces Logshark Apache.twbx HTTP Status & Request Rate views</div>
            </div>
          </div>
          <div class="chart-box"><canvas id="chartApacheStatus"></canvas></div>
        </div>
        <div class="panel">
          <div class="panel-header">
            <div>
              <div class="panel-title">Latency by Endpoint Category (Avg & Max ms)</div>
              <div class="panel-subtitle">Identifies whether slowness is in View Loads, VizQL Bootstrap, or REST API</div>
            </div>
          </div>
          <div class="chart-box"><canvas id="chartApacheCategory"></canvas></div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">Apache Gateway Requests Log (Sorted by Duration)</div>
            <div class="panel-subtitle">Click a Request ID to filter the entire dashboard to that exact request flow</div>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Node</th>
                <th>User</th>
                <th>Client IP</th>
                <th>Category</th>
                <th>Site / Workbook / View</th>
                <th>Status</th>
                <th>Duration (ms)</th>
                <th>Bytes</th>
                <th>Request ID</th>
                <th>URI</th>
              </tr>
            </thead>
            <tbody id="tbodyApache"></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- 3. BACKGROUNDER JOBS TAB -->
    <div class="tab-pane" id="pane-backgrounder">
      <div class="kpi-grid" id="bg-kpis"></div>
      <div class="grid-2">
        <div class="panel">
          <div class="panel-header">
            <div>
              <div class="panel-title">Queue Wait Time vs Execution Run Time by Job Type (Avg Sec)</div>
              <div class="panel-subtitle">Replaces Logshark Backgrounder.twbx Queue Delay & Execution Analysis</div>
            </div>
          </div>
          <div class="chart-box"><canvas id="chartBgQueueVsRun"></canvas></div>
        </div>
        <div class="panel">
          <div class="panel-header">
            <div>
              <div class="panel-title">Job Outcomes by Task Type (Success / Failed / Cancelled)</div>
              <div class="panel-subtitle">Highlights extract refreshes or flows with high failure rates</div>
            </div>
          </div>
          <div class="chart-box"><canvas id="chartBgStatus"></canvas></div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">Backgrounder Job Executions</div>
            <div class="panel-subtitle">Extract refreshes, Prep flows, subscriptions, and data alerts</div>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Job ID</th>
                <th>Node / Instance</th>
                <th>Site</th>
                <th>Job Type</th>
                <th>Target (Extract / Workbook / Flow)</th>
                <th>Priority</th>
                <th>Queued At</th>
                <th>Queue Wait (s)</th>
                <th>Run Time (s)</th>
                <th>Status</th>
                <th>Error / Notes</th>
              </tr>
            </thead>
            <tbody id="tbodyBgJobs"></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- 4. VIZQL & ART TRACING TAB -->
    <div class="tab-pane" id="pane-vizql">
      <div class="kpi-grid" id="vizql-kpis"></div>
      <div class="grid-2">
        <div class="panel">
          <div class="panel-header">
            <div>
              <div class="panel-title">ART Activity Breakdown: Inclusive CPU (ms) vs Memory Allocated (MB)</div>
              <div class="panel-subtitle">Replaces Logshark Art.twbx Flamechart & Resource Consumption views</div>
            </div>
          </div>
          <div class="chart-box"><canvas id="chartArtActivities"></canvas></div>
        </div>
        <div class="panel">
          <div class="panel-header">
            <div>
              <div class="panel-title">VizQL Workbook Performance & Cache Hit Ratio</div>
              <div class="panel-subtitle">Compares query execution times and cache efficiency across workbooks</div>
            </div>
          </div>
          <div class="chart-box"><canvas id="chartVizqlWorkbooks"></canvas></div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">ART (Activity and Resource Tracing) & VizQL Session Telemetry</div>
            <div class="panel-subtitle">Tracks Sponsor → Sponsee call depth, CPU thread time, and RAM allocations per user action</div>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Node / VizQL</th>
                <th>User / Site</th>
                <th>Workbook / View</th>
                <th>ART Activity</th>
                <th>Depth (Sponsor)</th>
                <th>Elapsed (ms)</th>
                <th>CPU Incl / Excl (ms)</th>
                <th>RAM Incl / Excl (MB)</th>
                <th>Request ID</th>
                <th>Session ID</th>
              </tr>
            </thead>
            <tbody id="tbodyArt"></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- 5. HYPER DATA ENGINE TAB -->
    <div class="tab-pane" id="pane-hyper">
      <div class="kpi-grid" id="hyper-kpis"></div>
      <div class="grid-2">
        <div class="panel">
          <div class="panel-header">
            <div>
              <div class="panel-title">Hyper Query Duration vs Peak Memory Buffer (MB)</div>
              <div class="panel-subtitle">Replaces Logshark Hyper.twbx Query Execution & Spooling analysis</div>
            </div>
          </div>
          <div class="chart-box"><canvas id="chartHyperScatter"></canvas></div>
        </div>
        <div class="panel">
          <div class="panel-header">
            <div>
              <div class="panel-title">Top Extract Databases by Query Time & Memory Load</div>
              <div class="panel-subtitle">Identifies heavy `.hyper` extracts causing disk spooling or CPU contention</div>
            </div>
          </div>
          <div class="chart-box"><canvas id="chartHyperDbs"></canvas></div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">Hyper Data Engine Query & Event Log</div>
            <div class="panel-subtitle">Includes SQL query snippets, rows returned, memory buffers, and spooling flags</div>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Node</th>
                <th>Severity</th>
                <th>Event Key</th>
                <th>Extract Database</th>
                <th>Elapsed (ms)</th>
                <th>CPU Time (ms)</th>
                <th>Peak RAM (MB)</th>
                <th>Spooled?</th>
                <th>Rows</th>
                <th>Request ID</th>
                <th>SQL Query / Error</th>
              </tr>
            </thead>
            <tbody id="tbodyHyper"></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- 6. RESOURCE MANAGER (SRM) TAB -->
    <div class="tab-pane" id="pane-srm">
      <div class="kpi-grid" id="srm-kpis"></div>
      <div class="grid-2">
        <div class="panel">
          <div class="panel-header">
            <div>
              <div class="panel-title">Node CPU Utilization (%) Timeline by Worker Node</div>
              <div class="panel-subtitle">Replaces Logshark ResourceManager.twbx CPU Usage timeline</div>
            </div>
          </div>
          <div class="chart-box"><canvas id="chartSrmCpu"></canvas></div>
        </div>
        <div class="panel">
          <div class="panel-header">
            <div>
              <div class="panel-title">Process Memory Consumption (MB) vs SRM Thresholds</div>
              <div class="panel-subtitle">Highlights VizQL, Hyper, and Backgrounder RAM usage across nodes</div>
            </div>
          </div>
          <div class="chart-box"><canvas id="chartSrmMem"></canvas></div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">Server Resource Manager (SRM) Telemetry & Process Recycle Events</div>
            <div class="panel-subtitle">Shows SRM throttling, memory limit violations, and per-process hardware metrics</div>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Node</th>
                <th>Process Name (PID)</th>
                <th>Process CPU %</th>
                <th>Process RAM (MB)</th>
                <th>SRM Limit (MB)</th>
                <th>Node CPU %</th>
                <th>Node RAM (MB)</th>
                <th>SRM Action</th>
                <th>Notes</th>
              </tr>
            </thead>
            <tbody id="tbodySrm"></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- 7. DUCKDB SQL WORKBENCH TAB -->
    <div class="tab-pane" id="pane-sql">
      <div class="panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">🦆 Interactive DuckDB SQL Workbench</div>
            <div class="panel-subtitle">Query all parsed Logshark tables (`apache_requests`, `backgrounder_jobs`, `vizql_events`, `art_events`, `hyper_events`, `srm_metrics`) directly in your browser using DuckDB SQL</div>
          </div>
          <button class="btn btn-primary" id="btnRunSql">▶ Run SQL Query</button>
        </div>

        <div class="preset-pills">
          <button class="btn" onclick="loadPresetSql(0)">🔗 End-to-End Request Join (Apache ⋈ ART ⋈ Hyper)</button>
          <button class="btn" onclick="loadPresetSql(1)">🐢 Top 10 Slowest Views (P95 & Avg Latency)</button>
          <button class="btn" onclick="loadPresetSql(2)">💥 Failed Backgrounder Jobs & Queue Bottlenecks</button>
          <button class="btn" onclick="loadPresetSql(3)">🧠 SRM Memory Limit Violations & High CPU Spikes</button>
          <button class="btn" onclick="loadPresetSql(4)">📋 Show All DuckDB Tables & Row Counts</button>
        </div>

        <textarea id="sqlEditor" class="sql-editor" spellcheck="false"></textarea>
        <div id="sqlStatus" style="font-size:12px; color:var(--text-muted); margin-bottom:10px;"></div>

        <div class="table-wrap" id="sqlResultWrap">
          <table id="sqlResultTable">
            <thead id="sqlResultThead"></thead>
            <tbody id="sqlResultTbody"></tbody>
          </table>
        </div>
      </div>
    </div>

  </main>

  <!-- Embedded Logshark Data Bundle -->
  <script>
    window.JANSHARK_BUNDLE = __JANSHARK_DATA_BUNDLE__;
  </script>

  <!-- Main Application Logic + DuckDB-WASM Integration -->
  <script type="module">
    let DATA = window.JANSHARK_BUNDLE;
    let charts = {};
    let duckConn = null;
    let duckDbInstance = null;

    const SQL_PRESETS = [
      `-- Cross-Service Correlation: Join Apache HTTP Gateway -> VizQL ART -> Hyper Data Engine by request_id
SELECT
    a.ts,
    a.worker_node AS node,
    a.requester AS username,
    a.site,
    a.workbook,
    a.view_name,
    a.status_code,
    a.request_time_ms AS http_ms,
    art.activity_name AS art_activity,
    art.cpu_inclusive_ms AS art_cpu_ms,
    art.alloc_inclusive_mb AS art_mem_mb,
    h.elapsed_ms AS hyper_query_ms,
    h.peak_memory_mb AS hyper_peak_mb,
    h.spooled_to_disk,
    a.request_id
FROM apache_requests a
LEFT JOIN art_events art ON a.request_id = art.request_id AND art.depth = 1
LEFT JOIN hyper_events h ON a.request_id = h.request_id
WHERE a.workbook IS NOT NULL
ORDER BY a.request_time_ms DESC
LIMIT 25;`,
      `-- Top Views by Average & Max Load Time with Error Count
SELECT
    site,
    workbook,
    view_name,
    COUNT(*) AS requests,
    ROUND(AVG(request_time_ms), 1) AS avg_ms,
    ROUND(MAX(request_time_ms), 1) AS max_ms,
    SUM(CASE WHEN status_code >= 500 THEN 1 ELSE 0 END) AS http_5xx_errors
FROM apache_requests
WHERE workbook IS NOT NULL
GROUP BY site, workbook, view_name
ORDER BY avg_ms DESC;`,
      `-- Backgrounder Job Performance & Failures Summary
SELECT
    job_id,
    worker_node,
    site,
    job_type,
    target_name,
    status,
    queue_wait_sec,
    run_time_sec,
    total_time_sec,
    error_message
FROM backgrounder_jobs
ORDER BY CASE WHEN status = 'Failed' THEN 0 WHEN status = 'Cancelled' THEN 1 ELSE 2 END, total_time_sec DESC;`,
      `-- Server Resource Manager (SRM) Threshold Violations & High Resource Samples
SELECT
    ts,
    worker_node,
    process_name,
    process_id,
    cpu_pct,
    memory_mb,
    memory_limit_mb,
    node_cpu_pct,
    srm_action,
    notes
FROM srm_metrics
WHERE srm_action != 'Monitor' OR node_cpu_pct > 75.0
ORDER BY memory_mb DESC;`,
      `-- Overview of DuckDB Tables in JanShark
SELECT 'apache_requests' AS table_name, COUNT(*) AS row_count FROM apache_requests
UNION ALL SELECT 'backgrounder_jobs', COUNT(*) FROM backgrounder_jobs
UNION ALL SELECT 'backgrounder_events', COUNT(*) FROM backgrounder_events
UNION ALL SELECT 'vizql_events', COUNT(*) FROM vizql_events
UNION ALL SELECT 'art_events', COUNT(*) FROM art_events
UNION ALL SELECT 'hyper_events', COUNT(*) FROM hyper_events
UNION ALL SELECT 'srm_metrics', COUNT(*) FROM srm_metrics;`
    ];

    window.switchTab = function(tabId) {
      document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabId);
      });
      document.querySelectorAll('.tab-pane').forEach(pane => {
        pane.classList.toggle('active', pane.id === `pane-${tabId}`);
      });
      renderAll();
    };

    window.setReqIdFilter = function(reqId, sessId) {
      const input = document.getElementById('filterReqId');
      input.value = (reqId && reqId !== '-') ? reqId : (sessId || '');
      renderAll();
    };

    window.loadPresetSql = function(idx) {
      document.getElementById('sqlEditor').value = SQL_PRESETS[idx];
      runSqlQuery();
    };

    // Initialize Filter Dropdowns from DATA
    function populateDropdowns() {
      const nodes = new Set();
      const sites = new Set();
      const workbooks = new Set();

      (DATA.apache_requests || []).forEach(r => {
        if (r.worker_node) nodes.add(r.worker_node);
        if (r.site) sites.add(r.site);
        if (r.workbook) workbooks.add(r.workbook);
      });
      (DATA.backgrounder_jobs || []).forEach(r => {
        if (r.worker_node) nodes.add(r.worker_node);
        if (r.site) sites.add(r.site);
      });
      (DATA.art_events || []).forEach(r => {
        if (r.worker_node) nodes.add(r.worker_node);
        if (r.site) sites.add(r.site);
        if (r.workbook) workbooks.add(r.workbook);
      });
      (DATA.srm_metrics || []).forEach(r => {
        if (r.worker_node) nodes.add(r.worker_node);
      });

      const fillSelect = (id, label, items) => {
        const el = document.getElementById(id);
        const current = el.value;
        el.innerHTML = `<option value="ALL">${label}</option>` +
          Array.from(items).sort().map(x => `<option value="${x}">${x}</option>`).join('');
        if (Array.from(items).includes(current)) el.value = current;
      };

      fillSelect('filterNode', 'All Nodes', nodes);
      fillSelect('filterSite', 'All Sites', sites);
      fillSelect('filterWorkbook', 'All Workbooks', workbooks);

      const meta = (DATA.run_metadata && DATA.run_metadata[0]) || {};
      if (meta.run_id) {
        document.getElementById('runMetaSub').textContent =
          `Run: ${meta.run_id} • Source: ${meta.source_path} • Nodes: ${meta.worker_nodes} • Parsed: ${meta.files_parsed} files (${meta.total_events} events)`;
      }
    }

    function getFilters() {
      return {
        node: document.getElementById('filterNode').value,
        site: document.getElementById('filterSite').value,
        workbook: document.getElementById('filterWorkbook').value,
        severity: document.getElementById('filterSeverity').value,
        reqId: document.getElementById('filterReqId').value.trim().toLowerCase(),
        search: document.getElementById('filterSearch').value.trim().toLowerCase(),
      };
    }

    function filterData() {
      const f = getFilters();

      const matchText = (obj) => {
        if (!f.search) return true;
        return Object.values(obj).some(v => v !== null && v !== undefined && String(v).toLowerCase().includes(f.search));
      };

      const matchReq = (obj) => {
        if (!f.reqId) return true;
        const req = String(obj.request_id || '').toLowerCase();
        const sess = String(obj.session_id || '').toLowerCase();
        const jid = String(obj.job_id || '').toLowerCase();
        return req.includes(f.reqId) || sess.includes(f.reqId) || jid.includes(f.reqId);
      };

      const apache = (DATA.apache_requests || []).filter(r => {
        if (f.node !== 'ALL' && r.worker_node !== f.node) return false;
        if (f.site !== 'ALL' && r.site !== f.site) return false;
        if (f.workbook !== 'ALL' && r.workbook !== f.workbook) return false;
        if (f.severity === 'ERRORS_ONLY' && r.status_code < 500) return false;
        if (f.severity === 'WARN_AND_UP' && r.status_code < 400) return false;
        return matchReq(r) && matchText(r);
      });

      const bgJobs = (DATA.backgrounder_jobs || []).filter(r => {
        if (f.node !== 'ALL' && r.worker_node !== f.node) return false;
        if (f.site !== 'ALL' && r.site !== f.site) return false;
        if (f.workbook !== 'ALL' && !String(r.target_name || '').includes(f.workbook)) return false;
        if (f.severity === 'ERRORS_ONLY' && r.status !== 'Failed') return false;
        if (f.severity === 'WARN_AND_UP' && r.status === 'Success') return false;
        return matchReq(r) && matchText(r);
      });

      const vizql = (DATA.vizql_events || []).filter(r => {
        if (f.node !== 'ALL' && r.worker_node !== f.node) return false;
        if (f.site !== 'ALL' && r.site !== f.site) return false;
        if (f.workbook !== 'ALL' && r.workbook !== f.workbook) return false;
        if (f.severity === 'ERRORS_ONLY' && r.severity !== 'ERROR' && r.severity !== 'FATAL') return false;
        if (f.severity === 'WARN_AND_UP' && r.severity === 'INFO') return false;
        return matchReq(r) && matchText(r);
      });

      const art = (DATA.art_events || []).filter(r => {
        if (f.node !== 'ALL' && r.worker_node !== f.node) return false;
        if (f.site !== 'ALL' && r.site !== f.site) return false;
        if (f.workbook !== 'ALL' && r.workbook !== f.workbook) return false;
        return matchReq(r) && matchText(r);
      });

      const hyper = (DATA.hyper_events || []).filter(r => {
        if (f.node !== 'ALL' && r.worker_node !== f.node) return false;
        if (f.workbook !== 'ALL' && !String(r.database_path || '').includes(f.workbook)) return false;
        if (f.severity === 'ERRORS_ONLY' && r.severity !== 'ERROR' && r.severity !== 'FATAL') return false;
        if (f.severity === 'WARN_AND_UP' && r.severity === 'INFO' && !r.spooled_to_disk) return false;
        return matchReq(r) && matchText(r);
      });

      const srm = (DATA.srm_metrics || []).filter(r => {
        if (f.node !== 'ALL' && r.worker_node !== f.node) return false;
        if (f.severity === 'ERRORS_ONLY' && r.srm_action === 'Monitor') return false;
        if (f.severity === 'WARN_AND_UP' && r.severity === 'INFO') return false;
        return matchText(r);
      });

      return { apache, bgJobs, vizql, art, hyper, srm };
    }

    function updateChart(key, ctxId, config) {
      const canvas = document.getElementById(ctxId);
      if (!canvas) return;
      if (charts[key]) {
        charts[key].destroy();
      }
      Chart.defaults.color = '#94a3b8';
      Chart.defaults.borderColor = 'rgba(38, 51, 77, 0.6)';
      charts[key] = new Chart(canvas, config);
    }

    function renderAll() {
      const d = filterData();

      // Update Tab Badges
      const errEvents =
        d.apache.filter(x => x.status_code >= 500).length +
        d.bgJobs.filter(x => x.status !== 'Success').length +
        d.vizql.filter(x => x.severity === 'ERROR').length +
        d.srm.filter(x => x.srm_action !== 'Monitor').length;

      document.getElementById('cnt-overview').textContent = `${errEvents} alerts`;
      document.getElementById('cnt-apache').textContent = d.apache.length;
      document.getElementById('cnt-backgrounder').textContent = d.bgJobs.length;
      document.getElementById('cnt-vizql').textContent = d.art.length;
      document.getElementById('cnt-hyper').textContent = d.hyper.length;
      document.getElementById('cnt-srm').textContent = d.srm.length;

      renderOverview(d);
      renderApache(d.apache);
      renderBackgrounder(d.bgJobs);
      renderVizqlArt(d.vizql, d.art);
      renderHyper(d.hyper);
      renderSrm(d.srm);
    }

    // ------------------------------------------------------------------------
    // TAB 1: OVERVIEW & TRIAGE
    // ------------------------------------------------------------------------
    function renderOverview(d) {
      const avgHttp = d.apache.length ? (d.apache.reduce((s, x) => s + x.request_time_ms, 0) / d.apache.length).toFixed(0) : 0;
      const http5xx = d.apache.filter(x => x.status_code >= 500).length;
      const bgFailed = d.bgJobs.filter(x => x.status === 'Failed').length;
      const srmAlerts = d.srm.filter(x => x.srm_action !== 'Monitor').length;
      const maxMem = d.srm.length ? Math.max(...d.srm.map(x => x.memory_mb)).toFixed(0) : 0;

      document.getElementById('overview-kpis').innerHTML = `
        <div class="kpi-card">
          <span class="kpi-title">Gateway Requests</span>
          <span class="kpi-value" style="color:var(--accent)">${d.apache.length}</span>
          <span class="kpi-sub">Avg Latency: ${avgHttp} ms (${http5xx} 5xx errors)</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-title">Backgrounder Jobs</span>
          <span class="kpi-value" style="color:${bgFailed ? 'var(--danger)' : 'var(--success)'}">${d.bgJobs.length}</span>
          <span class="kpi-sub">${bgFailed} Failed • ${d.bgJobs.filter(x => x.status === 'Success').length} Succeeded</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-title">VizQL & ART Traces</span>
          <span class="kpi-value" style="color:var(--purple)">${d.art.length}</span>
          <span class="kpi-sub">${d.vizql.filter(x => x.is_cache_hit).length} Query Cache Hits</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-title">Hyper Engine Queries</span>
          <span class="kpi-value" style="color:var(--warning)">${d.hyper.length}</span>
          <span class="kpi-sub">${d.hyper.filter(x => x.spooled_to_disk).length} Spooled to Disk</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-title">SRM Resource Actions</span>
          <span class="kpi-value" style="color:${srmAlerts ? 'var(--danger)' : 'var(--success)'}">${srmAlerts}</span>
          <span class="kpi-sub">Peak Process RAM: ${maxMem} MB</span>
        </div>
      `;

      // Timeline bucketed by 15-min intervals
      const buckets = {};
      const addB = (ts, key) => {
        if (!ts) return;
        const b = ts.slice(11, 15) + '0'; // e.g. "08:10"
        if (!buckets[b]) buckets[b] = { apache: 0, vizql: 0, bgErr: 0, srmWarn: 0 };
        buckets[b][key]++;
      };
      d.apache.forEach(r => addB(r.ts, 'apache'));
      d.art.forEach(r => addB(r.ts, 'vizql'));
      d.bgJobs.filter(r => r.status !== 'Success').forEach(r => addB(r.end_ts, 'bgErr'));
      d.srm.filter(r => r.srm_action !== 'Monitor').forEach(r => addB(r.ts, 'srmWarn'));

      const labels = Object.keys(buckets).sort();
      updateChart('overviewTimeline', 'chartOverviewTimeline', {
        type: 'line',
        data: {
          labels,
          datasets: [
            { label: 'Apache Requests', data: labels.map(l => buckets[l].apache), borderColor: '#38bdf8', backgroundColor: 'rgba(56,189,248,0.15)', fill: true, tension: 0.3 },
            { label: 'VizQL ART Activities', data: labels.map(l => buckets[l].vizql), borderColor: '#a855f7', tension: 0.3 },
            { label: 'Job Failures & SRM Recycles', data: labels.map(l => buckets[l].bgErr + buckets[l].srmWarn), borderColor: '#ef4444', backgroundColor: '#ef4444', type: 'bar' }
          ]
        },
        options: { responsive: true, maintainAspectRatio: false }
      });

      // Slowest Workbooks Chart
      const wbStats = {};
      d.art.filter(r => r.depth === 1 && r.workbook).forEach(r => {
        const k = `${r.workbook} / ${r.view_name}`;
        if (!wbStats[k]) wbStats[k] = { elapsed: 0, cpu: 0, count: 0 };
        wbStats[k].elapsed += r.elapsed_ms;
        wbStats[k].cpu += r.cpu_inclusive_ms;
        wbStats[k].count++;
      });
      const wbSorted = Object.entries(wbStats)
        .map(([k, v]) => ({ name: k, avgElapsed: Math.round(v.elapsed / v.count), avgCpu: Math.round(v.cpu / v.count) }))
        .sort((a, b) => b.avgElapsed - a.avgElapsed)
        .slice(0, 7);

      updateChart('overviewWorkbooks', 'chartOverviewWorkbooks', {
        type: 'bar',
        data: {
          labels: wbSorted.map(x => x.name),
          datasets: [
            { label: 'Avg Load Elapsed (ms)', data: wbSorted.map(x => x.avgElapsed), backgroundColor: '#38bdf8' },
            { label: 'Avg ART Inclusive CPU (ms)', data: wbSorted.map(x => x.avgCpu), backgroundColor: '#6366f1' }
          ]
        },
        options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false }
      });

      // Unified Triage Feed
      const triage = [];
      d.apache.filter(r => r.status_code >= 400).forEach(r => {
        triage.push({
          ts: r.ts, node: r.worker_node, service: 'Apache Gateway',
          sev: r.status_code >= 500 ? 'ERROR' : 'WARN',
          target: `${r.site} / ${r.workbook || r.endpoint_category}`,
          id: r.request_id,
          msg: `HTTP ${r.status_code} on ${r.method} ${r.uri} (${r.request_time_ms} ms)`
        });
      });
      d.bgJobs.filter(r => r.status !== 'Success').forEach(r => {
        triage.push({
          ts: r.end_ts, node: r.worker_node, service: 'Backgrounder',
          sev: r.status === 'Failed' ? 'ERROR' : 'WARN',
          target: `${r.site} / ${r.target_name}`,
          id: String(r.job_id),
          msg: `[${r.job_type}] ${r.status}: ${r.error_message || 'Job failed'} (Run: ${r.run_time_sec}s, Queue: ${r.queue_wait_sec}s)`
        });
      });
      d.vizql.filter(r => r.severity === 'ERROR').forEach(r => {
        triage.push({
          ts: r.ts, node: r.worker_node, service: 'VizQL Server',
          sev: 'ERROR',
          target: `${r.site} / ${r.workbook || 'Session'}`,
          id: r.request_id,
          msg: r.message
        });
      });
      d.srm.filter(r => r.srm_action !== 'Monitor').forEach(r => {
        triage.push({
          ts: r.ts, node: r.worker_node, service: 'Resource Manager (SRM)',
          sev: r.srm_action.includes('Recycle') ? 'ERROR' : 'WARN',
          target: `${r.process_name} (PID ${r.process_id})`,
          id: r.srm_action,
          msg: r.notes
        });
      });

      triage.sort((a, b) => b.ts.localeCompare(a.ts));
      document.getElementById('tbodyOverviewErrors').innerHTML = triage.map(t => `
        <tr>
          <td class="mono">${t.ts}</td>
          <td class="mono">${t.node}</td>
          <td><span class="pill pill-info">${t.service}</span></td>
          <td><span class="pill ${t.sev === 'ERROR' ? 'pill-danger' : 'pill-warn'}">${t.sev}</span></td>
          <td>${t.target}</td>
          <td class="mono"><span class="clickable-id" onclick="setReqIdFilter('${t.id}')">${t.id}</span></td>
          <td>${t.msg}</td>
        </tr>
      `).join('');
    }

    // ------------------------------------------------------------------------
    // TAB 2: APACHE GATEWAY
    // ------------------------------------------------------------------------
    function renderApache(rows) {
      const total = rows.length;
      const avgMs = total ? (rows.reduce((s, r) => s + r.request_time_ms, 0) / total).toFixed(0) : 0;
      const sortedMs = [...rows].map(r => r.request_time_ms).sort((a, b) => a - b);
      const p95Ms = total ? sortedMs[Math.floor(total * 0.95)].toFixed(0) : 0;
      const err5xx = rows.filter(r => r.status_code >= 500).length;
      const err4xx = rows.filter(r => r.status_code >= 400 && r.status_code < 500).length;

      document.getElementById('apache-kpis').innerHTML = `
        <div class="kpi-card"><span class="kpi-title">Total HTTP Requests</span><span class="kpi-value">${total}</span><span class="kpi-sub">Across Gateway Nodes</span></div>
        <div class="kpi-card"><span class="kpi-title">Avg Response Time</span><span class="kpi-value" style="color:var(--accent)">${avgMs} ms</span><span class="kpi-sub">P95 Latency: ${p95Ms} ms</span></div>
        <div class="kpi-card"><span class="kpi-title">HTTP 5xx Server Errors</span><span class="kpi-value" style="color:${err5xx ? 'var(--danger)' : 'var(--success)'}">${err5xx}</span><span class="kpi-sub">Timeouts & VizQL crashes</span></div>
        <div class="kpi-card"><span class="kpi-title">HTTP 4xx Client Errors</span><span class="kpi-value" style="color:${err4xx ? 'var(--warning)' : 'var(--text-main)'}">${err4xx}</span><span class="kpi-sub">Auth 401 & Missing Views 404</span></div>
      `;

      const statusCounts = {};
      rows.forEach(r => { statusCounts[r.status_code] = (statusCounts[r.status_code] || 0) + 1; });
      const sCodes = Object.keys(statusCounts).sort();

      updateChart('apacheStatus', 'chartApacheStatus', {
        type: 'doughnut',
        data: {
          labels: sCodes.map(c => `HTTP ${c}`),
          datasets: [{
            data: sCodes.map(c => statusCounts[c]),
            backgroundColor: sCodes.map(c => c.startsWith('2') ? '#10b981' : (c.startsWith('4') ? '#f59e0b' : '#ef4444'))
          }]
        },
        options: { responsive: true, maintainAspectRatio: false }
      });

      const catStats = {};
      rows.forEach(r => {
        if (!catStats[r.endpoint_category]) catStats[r.endpoint_category] = { sum: 0, max: 0, n: 0 };
        catStats[r.endpoint_category].sum += r.request_time_ms;
        catStats[r.endpoint_category].max = Math.max(catStats[r.endpoint_category].max, r.request_time_ms);
        catStats[r.endpoint_category].n++;
      });
      const cats = Object.keys(catStats);
      updateChart('apacheCat', 'chartApacheCategory', {
        type: 'bar',
        data: {
          labels: cats,
          datasets: [
            { label: 'Avg Duration (ms)', data: cats.map(c => Math.round(catStats[c].sum / catStats[c].n)), backgroundColor: '#38bdf8' },
            { label: 'Max Duration (ms)', data: cats.map(c => Math.round(catStats[c].max)), backgroundColor: 'rgba(99, 102, 241, 0.5)' }
          ]
        },
        options: { responsive: true, maintainAspectRatio: false }
      });

      const sortedRows = [...rows].sort((a, b) => b.request_time_ms - a.request_time_ms);
      document.getElementById('tbodyApache').innerHTML = sortedRows.map(r => {
        const pillCls = r.status_code >= 500 ? 'pill-danger' : (r.status_code >= 400 ? 'pill-warn' : 'pill-success');
        return `
          <tr>
            <td class="mono">${r.ts}</td>
            <td class="mono">${r.worker_node}</td>
            <td>${r.requester}</td>
            <td class="mono">${r.client_ip}</td>
            <td><span class="pill pill-info">${r.endpoint_category}</span></td>
            <td>${r.site}${r.workbook ? ` / <b>${r.workbook}</b> / ${r.view_name}` : ''}</td>
            <td><span class="pill ${pillCls}">${r.status_code}</span></td>
            <td class="mono" style="font-weight:700; color:${r.request_time_ms > 5000 ? 'var(--danger)' : 'var(--text-main)'}">${r.request_time_ms.toLocaleString()}</td>
            <td class="mono">${(r.response_bytes / 1024).toFixed(1)} KB</td>
            <td class="mono"><span class="clickable-id" onclick="setReqIdFilter('${r.request_id}')">${r.request_id}</span></td>
            <td class="mono" style="max-width:280px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${r.uri}">${r.uri}</td>
          </tr>
        `;
      }).join('');
    }

    // ------------------------------------------------------------------------
    // TAB 3: BACKGROUNDER JOBS
    // ------------------------------------------------------------------------
    function renderBackgrounder(jobs) {
      const total = jobs.length;
      const succ = jobs.filter(j => j.status === 'Success').length;
      const fail = jobs.filter(j => j.status === 'Failed').length;
      const avgQueue = total ? (jobs.reduce((s, j) => s + j.queue_wait_sec, 0) / total).toFixed(1) : 0;
      const avgRun = total ? (jobs.reduce((s, j) => s + j.run_time_sec, 0) / total).toFixed(1) : 0;

      document.getElementById('bg-kpis').innerHTML = `
        <div class="kpi-card"><span class="kpi-title">Total Jobs Parsed</span><span class="kpi-value">${total}</span><span class="kpi-sub">${succ} Succeeded • ${fail} Failed</span></div>
        <div class="kpi-card"><span class="kpi-title">Success Rate</span><span class="kpi-value" style="color:${fail ? 'var(--warning)' : 'var(--success)'}">${total ? ((succ / total) * 100).toFixed(1) : 100}%</span><span class="kpi-sub">Target SLA: 95%+</span></div>
        <div class="kpi-card"><span class="kpi-title">Avg Queue Delay</span><span class="kpi-value" style="color:var(--accent)">${avgQueue} s</span><span class="kpi-sub">Time waiting for free Backgrounder</span></div>
        <div class="kpi-card"><span class="kpi-title">Avg Execution Time</span><span class="kpi-value">${avgRun} s</span><span class="kpi-sub">Active refresh / flow runtime</span></div>
      `;

      const byType = {};
      jobs.forEach(j => {
        if (!byType[j.job_type]) byType[j.job_type] = { q: 0, r: 0, n: 0, succ: 0, fail: 0 };
        byType[j.job_type].q += j.queue_wait_sec;
        byType[j.job_type].r += j.run_time_sec;
        byType[j.job_type].n++;
        if (j.status === 'Success') byType[j.job_type].succ++;
        else byType[j.job_type].fail++;
      });
      const jTypes = Object.keys(byType);

      updateChart('bgQueueRun', 'chartBgQueueVsRun', {
        type: 'bar',
        data: {
          labels: jTypes,
          datasets: [
            { label: 'Avg Queue Wait (sec)', data: jTypes.map(t => Math.round(byType[t].q / byType[t].n)), backgroundColor: '#f59e0b' },
            { label: 'Avg Run Time (sec)', data: jTypes.map(t => Math.round(byType[t].r / byType[t].n)), backgroundColor: '#38bdf8' }
          ]
        },
        options: { responsive: true, maintainAspectRatio: false }
      });

      updateChart('bgStatus', 'chartBgStatus', {
        type: 'bar',
        data: {
          labels: jTypes,
          datasets: [
            { label: 'Success', data: jTypes.map(t => byType[t].succ), backgroundColor: '#10b981' },
            { label: 'Failed / Cancelled', data: jTypes.map(t => byType[t].fail), backgroundColor: '#ef4444' }
          ]
        },
        options: { responsive: true, maintainAspectRatio: false, scales: { x: { stacked: true }, y: { stacked: true } } }
      });

      const sortedJobs = [...jobs].sort((a, b) => (a.status === 'Failed' ? -1 : 1) || (b.total_time_sec - a.total_time_sec));
      document.getElementById('tbodyBgJobs').innerHTML = sortedJobs.map(j => {
        const pCls = j.status === 'Success' ? 'pill-success' : (j.status === 'Failed' ? 'pill-danger' : 'pill-warn');
        return `
          <tr>
            <td class="mono"><b>#${j.job_id}</b></td>
            <td class="mono">${j.worker_node} / ${j.backgrounder_instance}</td>
            <td>${j.site}</td>
            <td><span class="pill pill-info">${j.job_type}</span></td>
            <td><b>${j.target_name}</b></td>
            <td class="mono">${j.priority}</td>
            <td class="mono">${j.queued_ts}</td>
            <td class="mono" style="color:${j.queue_wait_sec > 120 ? 'var(--warning)' : 'inherit'}">${j.queue_wait_sec}s</td>
            <td class="mono">${j.run_time_sec}s</td>
            <td><span class="pill ${pCls}">${j.status}</span></td>
            <td style="color:${j.error_message ? '#f87171' : 'var(--text-muted)'}">${j.error_message || 'Completed normally'}</td>
          </tr>
        `;
      }).join('');
    }

    // ------------------------------------------------------------------------
    // TAB 4: VIZQL & ART TRACING
    // ------------------------------------------------------------------------
    function renderVizqlArt(vizql, art) {
      const totalArt = art.length;
      const avgCpu = totalArt ? (art.reduce((s, a) => s + a.cpu_inclusive_ms, 0) / totalArt).toFixed(0) : 0;
      const peakAlloc = totalArt ? Math.max(...art.map(a => a.alloc_inclusive_mb)).toFixed(1) : 0;
      const queries = vizql.filter(v => v.event_key === 'end-query' || v.query_text);
      const cacheHits = queries.filter(v => v.is_cache_hit).length;
      const cacheRate = queries.length ? ((cacheHits / queries.length) * 100).toFixed(1) : 0;

      document.getElementById('vizql-kpis').innerHTML = `
        <div class="kpi-card"><span class="kpi-title">ART Trace Events</span><span class="kpi-value" style="color:var(--purple)">${totalArt}</span><span class="kpi-sub">Sponsor / Sponsee activities</span></div>
        <div class="kpi-card"><span class="kpi-title">Avg ART CPU Inclusive</span><span class="kpi-value" style="color:var(--accent)">${avgCpu} ms</span><span class="kpi-sub">Per traced VizQL activity</span></div>
        <div class="kpi-card"><span class="kpi-title">Peak Session Memory</span><span class="kpi-value" style="color:var(--warning)">${peakAlloc} MB</span><span class="kpi-sub">ART Inclusive RAM Allocation</span></div>
        <div class="kpi-card"><span class="kpi-title">VizQL Query Cache Hit %</span><span class="kpi-value" style="color:var(--success)">${cacheRate}%</span><span class="kpi-sub">${cacheHits} of ${queries.length} queries cached</span></div>
      `;

      const actMap = {};
      art.forEach(a => {
        if (!actMap[a.activity_name]) actMap[a.activity_name] = { cpu: 0, mem: 0, n: 0 };
        actMap[a.activity_name].cpu += a.cpu_inclusive_ms;
        actMap[a.activity_name].mem += a.alloc_inclusive_mb;
        actMap[a.activity_name].n++;
      });
      const acts = Object.keys(actMap);
      updateChart('artActivities', 'chartArtActivities', {
        type: 'bar',
        data: {
          labels: acts,
          datasets: [
            { label: 'Avg Inclusive CPU (ms)', data: acts.map(k => Math.round(actMap[k].cpu / actMap[k].n)), backgroundColor: '#a855f7' },
            { label: 'Avg Inclusive Memory (MB)', data: acts.map(k => Math.round(actMap[k].mem / actMap[k].n)), backgroundColor: '#38bdf8' }
          ]
        },
        options: { responsive: true, maintainAspectRatio: false }
      });

      const wbCache = {};
      vizql.filter(v => v.workbook).forEach(v => {
        if (!wbCache[v.workbook]) wbCache[v.workbook] = { cached: 0, uncached: 0 };
        if (v.is_cache_hit) wbCache[v.workbook].cached++;
        else wbCache[v.workbook].uncached++;
      });
      const wbs = Object.keys(wbCache);
      updateChart('vizqlWorkbooks', 'chartVizqlWorkbooks', {
        type: 'bar',
        data: {
          labels: wbs,
          datasets: [
            { label: 'Cache Hits', data: wbs.map(w => wbCache[w].cached), backgroundColor: '#10b981' },
            { label: 'Live / Hyper Queries', data: wbs.map(w => wbCache[w].uncached), backgroundColor: '#6366f1' }
          ]
        },
        options: { responsive: true, maintainAspectRatio: false, scales: { x: { stacked: true }, y: { stacked: true } } }
      });

      const sortedArt = [...art].sort((a, b) => b.elapsed_ms - a.elapsed_ms);
      document.getElementById('tbodyArt').innerHTML = sortedArt.map(a => `
        <tr>
          <td class="mono">${a.ts}</td>
          <td class="mono">${a.worker_node} / ${a.vizql_instance}</td>
          <td>${a.username} <span style="color:var(--text-muted)">(${a.site})</span></td>
          <td><b>${a.workbook}</b> / ${a.view_name}</td>
          <td><span class="pill pill-info">${a.activity_name}</span></td>
          <td class="mono">L${a.depth} (${a.sponsor_id})</td>
          <td class="mono" style="font-weight:700; color:${a.elapsed_ms > 4000 ? 'var(--danger)' : 'inherit'}">${a.elapsed_ms} ms</td>
          <td class="mono">${a.cpu_inclusive_ms} / ${a.cpu_exclusive_ms} ms</td>
          <td class="mono">${a.alloc_inclusive_mb} / ${a.alloc_exclusive_mb} MB</td>
          <td class="mono"><span class="clickable-id" onclick="setReqIdFilter('${a.request_id}')">${a.request_id}</span></td>
          <td class="mono"><span class="clickable-id" onclick="setReqIdFilter('${a.session_id}')">${a.session_id}</span></td>
        </tr>
      `).join('');
    }

    // ------------------------------------------------------------------------
    // TAB 5: HYPER DATA ENGINE
    // ------------------------------------------------------------------------
    function renderHyper(rows) {
      const total = rows.length;
      const avgElapsed = total ? (rows.reduce((s, r) => s + r.elapsed_ms, 0) / total).toFixed(0) : 0;
      const maxMem = total ? Math.max(...rows.map(r => r.peak_memory_mb)).toFixed(1) : 0;
      const spooled = rows.filter(r => r.spooled_to_disk).length;
      const errs = rows.filter(r => r.severity === 'ERROR').length;

      document.getElementById('hyper-kpis').innerHTML = `
        <div class="kpi-card"><span class="kpi-title">Hyper Queries Logged</span><span class="kpi-value">${total}</span><span class="kpi-sub">${errs} Query Exceptions</span></div>
        <div class="kpi-card"><span class="kpi-title">Avg Query Elapsed</span><span class="kpi-value" style="color:var(--accent)">${avgElapsed} ms</span><span class="kpi-sub">In-engine execution time</span></div>
        <div class="kpi-card"><span class="kpi-title">Peak Result Buffer RAM</span><span class="kpi-value" style="color:var(--warning)">${maxMem} MB</span><span class="kpi-sub">Single query peak memory</span></div>
        <div class="kpi-card"><span class="kpi-title">Queries Spooled to Disk</span><span class="kpi-value" style="color:${spooled ? 'var(--danger)' : 'var(--success)'}">${spooled}</span><span class="kpi-sub">Indicates memory pressure</span></div>
      `;

      updateChart('hyperScatter', 'chartHyperScatter', {
        type: 'scatter',
        data: {
          datasets: [{
            label: 'Hyper Queries (Elapsed ms vs Peak Memory MB)',
            data: rows.map(r => ({ x: r.elapsed_ms, y: r.peak_memory_mb })),
            backgroundColor: rows.map(r => r.spooled_to_disk ? '#ef4444' : '#38bdf8'),
            pointRadius: 5
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            x: { title: { display: true, text: 'Query Elapsed (ms)' } },
            y: { title: { display: true, text: 'Peak Memory Buffer (MB)' } }
          }
        }
      });

      const dbAgg = {};
      rows.forEach(r => {
        const shortDb = r.database_path.split('/').slice(-2).join('/');
        if (!dbAgg[shortDb]) dbAgg[shortDb] = { ms: 0, mem: 0, n: 0 };
        dbAgg[shortDb].ms += r.elapsed_ms;
        dbAgg[shortDb].mem = Math.max(dbAgg[shortDb].mem, r.peak_memory_mb);
        dbAgg[shortDb].n++;
      });
      const dbs = Object.keys(dbAgg);
      updateChart('hyperDbs', 'chartHyperDbs', {
        type: 'bar',
        data: {
          labels: dbs,
          datasets: [
            { label: 'Avg Query Time (ms)', data: dbs.map(d => Math.round(dbAgg[d].ms / dbAgg[d].n)), backgroundColor: '#38bdf8' },
            { label: 'Max Memory Buffer (MB)', data: dbs.map(d => Math.round(dbAgg[d].mem)), backgroundColor: '#f59e0b' }
          ]
        },
        options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false }
      });

      const sortedHyper = [...rows].sort((a, b) => b.elapsed_ms - a.elapsed_ms);
      document.getElementById('tbodyHyper').innerHTML = sortedHyper.map(r => `
        <tr>
          <td class="mono">${r.ts}</td>
          <td class="mono">${r.worker_node}</td>
          <td><span class="pill ${r.severity === 'ERROR' ? 'pill-danger' : (r.spooled_to_disk ? 'pill-warn' : 'pill-success')}">${r.severity}</span></td>
          <td class="mono">${r.event_key}</td>
          <td class="mono">${r.database_path.split('/').slice(-2).join('/')}</td>
          <td class="mono"><b>${r.elapsed_ms} ms</b></td>
          <td class="mono">${r.cpu_time_ms} ms</td>
          <td class="mono">${r.peak_memory_mb} MB</td>
          <td>${r.spooled_to_disk ? '<span class="pill pill-danger">YES</span>' : '<span class="pill pill-success">No</span>'}</td>
          <td class="mono">${r.rows_affected.toLocaleString()}</td>
          <td class="mono"><span class="clickable-id" onclick="setReqIdFilter('${r.request_id}')">${r.request_id}</span></td>
          <td class="mono" style="font-size:11.5px; color:${r.error_message ? '#f87171' : 'var(--text-muted)'}">${r.error_message || r.query_text || ''}</td>
        </tr>
      `).join('');
    }

    // ------------------------------------------------------------------------
    // TAB 6: RESOURCE MANAGER (SRM)
    // ------------------------------------------------------------------------
    function renderSrm(rows) {
      const total = rows.length;
      const peakCpu = total ? Math.max(...rows.map(r => r.node_cpu_pct)).toFixed(1) : 0;
      const peakNodeMem = total ? (Math.max(...rows.map(r => r.node_memory_mb)) / 1024).toFixed(1) : 0;
      const recycles = rows.filter(r => r.srm_action.includes('Recycle')).length;
      const throttles = rows.filter(r => r.srm_action.includes('Throttle')).length;

      document.getElementById('srm-kpis').innerHTML = `
        <div class="kpi-card"><span class="kpi-title">SRM Telemetry Samples</span><span class="kpi-value">${total}</span><span class="kpi-sub">Across monitored processes</span></div>
        <div class="kpi-card"><span class="kpi-title">Peak Node CPU %</span><span class="kpi-value" style="color:${peakCpu > 85 ? 'var(--danger)' : 'var(--accent)'}">${peakCpu}%</span><span class="kpi-sub">System-wide CPU utilization</span></div>
        <div class="kpi-card"><span class="kpi-title">Peak Node Memory</span><span class="kpi-value" style="color:var(--warning)">${peakNodeMem} GB</span><span class="kpi-sub">Of 64.0 GB Node Capacity</span></div>
        <div class="kpi-card"><span class="kpi-title">SRM Process Recycles</span><span class="kpi-value" style="color:${recycles ? 'var(--danger)' : 'var(--success)'}">${recycles}</span><span class="kpi-sub">${throttles} High-CPU Throttles</span></div>
      `;

      // Node CPU timeline
      const timeNode = {};
      rows.forEach(r => {
        const t = r.ts.slice(11, 16);
        if (!timeNode[t]) timeNode[t] = {};
        timeNode[t][r.worker_node] = r.node_cpu_pct;
      });
      const tLabels = Object.keys(timeNode).sort();
      updateChart('srmCpu', 'chartSrmCpu', {
        type: 'line',
        data: {
          labels: tLabels,
          datasets: [
            { label: 'node1 System CPU %', data: tLabels.map(t => timeNode[t]['node1'] || null), borderColor: '#38bdf8', tension: 0.25 },
            { label: 'node2 System CPU %', data: tLabels.map(t => timeNode[t]['node2'] || null), borderColor: '#a855f7', tension: 0.25 }
          ]
        },
        options: { responsive: true, maintainAspectRatio: false, scales: { y: { min: 0, max: 100 } } }
      });

      // Process Peak & Avg Memory vs SRM Limit
      const procAgg = {};
      rows.forEach(r => {
        const k = `${r.worker_node}:${r.process_name}`;
        if (!procAgg[k]) procAgg[k] = { maxMem: 0, limit: r.memory_limit_mb };
        procAgg[k].maxMem = Math.max(procAgg[k].maxMem, r.memory_mb);
      });
      const pKeys = Object.keys(procAgg).sort();
      updateChart('srmMem', 'chartSrmMem', {
        type: 'bar',
        data: {
          labels: pKeys,
          datasets: [
            { label: 'Peak Process RAM (MB)', data: pKeys.map(k => procAgg[k].maxMem), backgroundColor: pKeys.map(k => procAgg[k].maxMem > procAgg[k].limit ? '#ef4444' : '#38bdf8') },
            { label: 'SRM Memory Limit (MB)', data: pKeys.map(k => procAgg[k].limit), backgroundColor: 'rgba(148, 163, 184, 0.25)' }
          ]
        },
        options: { responsive: true, maintainAspectRatio: false }
      });

      const sortedSrm = [...rows].sort((a, b) => (a.srm_action === 'Monitor' ? 1 : -1) || (b.memory_mb - a.memory_mb));
      document.getElementById('tbodySrm').innerHTML = sortedSrm.map(r => {
        const pCls = r.srm_action.includes('Recycle') ? 'pill-danger' : (r.srm_action !== 'Monitor' ? 'pill-warn' : 'pill-success');
        return `
          <tr>
            <td class="mono">${r.ts}</td>
            <td class="mono">${r.worker_node}</td>
            <td class="mono"><b>${r.process_name}</b> (${r.process_id})</td>
            <td class="mono">${r.cpu_pct}%</td>
            <td class="mono" style="font-weight:700; color:${r.memory_mb > r.memory_limit_mb ? 'var(--danger)' : 'inherit'}">${r.memory_mb.toLocaleString()} MB</td>
            <td class="mono">${r.memory_limit_mb.toLocaleString()} MB</td>
            <td class="mono">${r.node_cpu_pct}%</td>
            <td class="mono">${r.node_memory_mb.toLocaleString()} MB</td>
            <td><span class="pill ${pCls}">${r.srm_action}</span></td>
            <td>${r.notes}</td>
          </tr>
        `;
      }).join('');
    }

    // ------------------------------------------------------------------------
    // TAB 7: DUCKDB-WASM IN-BROWSER SQL ENGINE
    // ------------------------------------------------------------------------
    async function initDuckDBWasm() {
      const badge = document.getElementById('engineStatusBadge');
      try {
        badge.textContent = 'Booting DuckDB-WASM...';
        const duckdb = await import('https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.28.0/+esm');
        const JSDELIVR_BUNDLES = duckdb.getJsDelivrBundles();
        const bundle = await duckdb.selectBundle(JSDELIVR_BUNDLES);
        const worker_url = URL.createObjectURL(
          new Blob([`importScripts("${bundle.mainWorker}");`], { type: 'text/javascript' })
        );
        const worker = new Worker(worker_url);
        const logger = new duckdb.ConsoleLogger();
        duckDbInstance = new duckdb.AsyncDuckDB(logger, worker);
        await duckDbInstance.instantiate(bundle.mainModule, bundle.pthreadWorker);
        URL.revokeObjectURL(worker_url);

        duckConn = await duckDbInstance.connect();
        await registerBundleInDuckDB(DATA);
        badge.textContent = '🦆 DuckDB-WASM Active';
        badge.style.color = '#34d399';
      } catch (err) {
        console.warn('DuckDB-WASM CDN offline or blocked, using built-in JS fallback engine:', err);
        badge.textContent = '⚡ Local Embedded Engine Active';
      }
    }

    async function registerBundleInDuckDB(bundleObj) {
      if (!duckDbInstance || !duckConn) return;
      const tables = ['apache_requests', 'backgrounder_jobs', 'backgrounder_events', 'vizql_events', 'art_events', 'hyper_events', 'srm_metrics'];
      for (const t of tables) {
        const rows = bundleObj[t] || [];
        await duckDbInstance.registerFileText(`${t}.json`, JSON.stringify(rows));
        await duckConn.query(`DROP TABLE IF EXISTS ${t};`);
        await duckConn.query(`CREATE TABLE ${t} AS SELECT * FROM read_json_auto('${t}.json');`);
      }
    }

    async function runSqlQuery() {
      const sql = document.getElementById('sqlEditor').value.trim();
      const statusEl = document.getElementById('sqlStatus');
      const thead = document.getElementById('sqlResultThead');
      const tbody = document.getElementById('sqlResultTbody');

      if (!sql) return;
      const t0 = performance.now();

      if (duckConn) {
        try {
          const result = await duckConn.query(sql);
          const elapsed = (performance.now() - t0).toFixed(1);
          const cols = result.schema.fields.map(f => f.name);
          const rows = result.toArray().map(r => r.toJSON());

          statusEl.textContent = `✅ Executed in ${elapsed} ms via DuckDB-WASM (${rows.length} rows returned)`;
          statusEl.style.color = '#34d399';

          thead.innerHTML = `<tr>${cols.map(c => `<th>${c}</th>`).join('')}</tr>`;
          tbody.innerHTML = rows.map(row => `
            <tr>${cols.map(c => `<td class="mono">${row[c] !== null && row[c] !== undefined ? row[c] : ''}</td>`).join('')}</tr>
          `).join('');
          return;
        } catch (err) {
          statusEl.textContent = `❌ DuckDB SQL Error: ${err.message}`;
          statusEl.style.color = '#f87171';
          return;
        }
      }

      // Offline fallback if CDN is unreachable
      statusEl.textContent = `ℹ️ DuckDB-WASM CDN not loaded; displaying table preview from embedded bundle.`;
      const matchTable = sql.match(/FROM\s+([a-z_]+)/i);
      const tName = (matchTable && DATA[matchTable[1]]) ? matchTable[1] : 'apache_requests';
      const rows = (DATA[tName] || []).slice(0, 30);
      const cols = rows.length ? Object.keys(rows[0]) : [];
      thead.innerHTML = `<tr>${cols.map(c => `<th>${c}</th>`).join('')}</tr>`;
      tbody.innerHTML = rows.map(row => `
        <tr>${cols.map(c => `<td class="mono">${row[c] ?? ''}</td>`).join('')}</tr>
      `).join('');
    }

    // File Loader for custom .json, .duckdb, or .parquet files
    document.getElementById('fileInput').addEventListener('change', async (ev) => {
      const file = ev.target.files[0];
      if (!file) return;

      if (file.name.endsWith('.json')) {
        const txt = await file.text();
        DATA = JSON.parse(txt);
        populateDropdowns();
        renderAll();
        await registerBundleInDuckDB(DATA);
      } else if (duckDbInstance && duckConn && (file.name.endsWith('.duckdb') || file.name.endsWith('.db') || file.name.endsWith('.parquet'))) {
        const buf = new Uint8Array(await file.arrayBuffer());
        await duckDbInstance.registerFileBuffer(file.name, buf);
        if (file.name.endsWith('.parquet')) {
          const tName = file.name.replace('.parquet', '');
          await duckConn.query(`CREATE OR REPLACE TABLE ${tName} AS SELECT * FROM parquet_scan('${file.name}');`);
          const res = await duckConn.query(`SELECT * FROM ${tName}`);
          DATA[tName] = res.toArray().map(r => r.toJSON());
        } else {
          await duckConn.query(`ATTACH '${file.name}' AS uploaded_db (READ_ONLY);`);
          const tables = ['apache_requests', 'backgrounder_jobs', 'vizql_events', 'art_events', 'hyper_events', 'srm_metrics'];
          for (const t of tables) {
            try {
              const res = await duckConn.query(`SELECT * FROM uploaded_db.${t}`);
              DATA[t] = res.toArray().map(r => r.toJSON());
            } catch (_) {}
          }
        }
        populateDropdowns();
        renderAll();
      }
    });

    // Attach Filter Listeners
    ['filterNode', 'filterSite', 'filterWorkbook', 'filterSeverity'].forEach(id => {
      document.getElementById(id).addEventListener('change', renderAll);
    });
    ['filterReqId', 'filterSearch'].forEach(id => {
      document.getElementById(id).addEventListener('input', renderAll);
    });
    document.getElementById('btnResetFilters').addEventListener('click', () => {
      document.getElementById('filterNode').value = 'ALL';
      document.getElementById('filterSite').value = 'ALL';
      document.getElementById('filterWorkbook').value = 'ALL';
      document.getElementById('filterSeverity').value = 'ALL';
      document.getElementById('filterReqId').value = '';
      document.getElementById('filterSearch').value = '';
      renderAll();
    });
    document.getElementById('btnRunSql').addEventListener('click', runSqlQuery);

    // Boot
    populateDropdowns();
    document.getElementById('sqlEditor').value = SQL_PRESETS[0];
    renderAll();
    initDuckDBWasm().then(() => runSqlQuery());
  </script>
</body>
</html>
"""

