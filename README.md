# JanShark 🦈🦆

**JanShark** is a lightweight, re-engineered replacement for [Tableau Logshark](https://github.com/tableau/Logshark) focused exclusively on **Tableau Server** logs.

Instead of requiring a heavy .NET runtime, MongoDB staging, PostgreSQL warehousing, and Tableau Desktop workbooks (`.twbx` / `.hyper`), JanShark parses raw Tableau Server `ziplogs` archives directly into **DuckDB** and generates a **zero-server static HTML analytics application** powered by **DuckDB-WASM**.

---

## Architecture Comparison: Legacy Logshark vs. JanShark

| Layer | Legacy Tableau Logshark | JanShark (Re-engineered) |
| :--- | :--- | :--- |
| **Input** | `tsm maintenance ziplogs` (`.zip` or folder) | `tsm maintenance ziplogs` (`.zip`, nested worker zips, or folder) |
| **Staging & ETL** | C# .NET + Temporary **MongoDB** + **PostgreSQL** | Fast Python streaming parser ([`extractor.py`](janshark/extractor.py), [`parsers.py`](janshark/parsers.py)) |
| **Storage Engine** | `.hyper` extracts + `.twbx` templates | **DuckDB** (`.duckdb` / `.parquet`) + in-browser **DuckDB-WASM** |
| **Analytics UI** | Requires paid **Tableau Desktop** license to open `.twbx` | **Single-file Static HTML** (`dashboard.html`) with global cross-filtering & SQL console |

---

## Included Tableau Server Plugins & DuckDB Tables

JanShark focuses on the 5 most impactful **Tableau Server** diagnostic domains (excluding Desktop, Vizportal, ClusterController, and TabadminController):

1. **Apache (`apache_requests`)** — Replaces `Apache.twbx`
   - Parses `httpd/access.*.log` across worker nodes.
   - Extracts client IPs, users, HTTP methods, status codes (`2xx`/`4xx`/`5xx`), response bytes, microsecond durations (`request_time_ms`), endpoint categories (`View Load`, `VizQL Bootstrap`, `VizQL Interaction`, `REST API`), and `request_id` correlation tokens.
2. **Backgrounder (`backgrounder_jobs`, `backgrounder_events`)** — Replaces `Backgrounder.twbx`
   - Parses `backgrounder_*.log` Java log lines and native JSON events.
   - Reconstructs full job lifecycles (`refresh_extracts`, `increment_extracts`, `single_subscription_notify`, `run_flow`, `check_data_alert`), comparing **Queue Wait Time (s)** vs. **Execution Run Time (s)**, priority, and root-cause error stack traces.
3. **VizQL Server & ART (`vizql_events`, `art_events`)** — Replaces `VizqlServer.twbx` & `Art.twbx`
   - Parses `vizqlserver/Logs/nativeapi_vizqlserver_*.txt` structured JSON logs.
   - Captures **Activity and Resource Tracing (ART)** call trees (`depth`, `activity_id`, `sponsor_id`), **Inclusive & Exclusive CPU time (ms)**, **Inclusive & Exclusive Memory Allocations (MB)**, session IDs, SQL queries, and query cache hit ratios.
4. **Hyper Data Engine (`hyper_events`)** — Replaces `Hyper.twbx`
   - Parses `hyper/hyperd.log` JSON telemetry.
   - Tracks query execution times, CPU time, rows returned, **peak result buffer memory (MB)**, **disk spooling** events, and `.hyper` extract database paths.
5. **Resource Manager / SRM (`srm_metrics`)** — Replaces `ResourceManager.twbx`
   - Parses `srm/srm_*.log` Server Resource Manager logs.
   - Tracks per-process and node-wide **CPU utilization (%)** and **Memory consumption (MB)** against configured SRM limits, highlighting `MemoryLimitExceeded_Recycle` and `HighCpuThrottle` events.

---

## Quick Start

### 1. Install Dependencies
```bash
pip install duckdb
```

### 2. Run with Synthetic Demo Logs (Generates `sample_logs.zip`, `janshark.duckdb`, and `dashboard.html`)
```bash
python -m janshark.cli --demo --open
```

### 3. Analyze Your Own Tableau Server `logs.zip`
```bash
# Parse a Tableau Server ziplogs archive into DuckDB and generate the static HTML dashboard
python -m janshark.cli C:\path\to\logs.zip --db output/server_logs.duckdb --html output/dashboard.html --open

# Or run only specific plugins and also export Parquet tables
python -m janshark.cli C:\path\to\logs.zip --plugins "apache;backgrounder;vizql;hyper;srm" --parquet-dir output/parquet
```

---

## Using the Static HTML Dashboard

Open `output/dashboard.html` in any browser (no web server or Tableau license required):
- **Global Filter Bar**: Filter all tabs simultaneously by **Worker Node**, **Site**, **Workbook**, **Severity/Status**, **Request / Session ID**, or free-text search.
- **One-Click Request Correlation**: Click any `request_id` or `session_id` badge in any table to trace that exact user transaction from the **Apache HTTP Gateway** → **VizQL ART Activity Tree** → **Hyper Data Engine SQL Query**.
- **In-Browser DuckDB-WASM SQL Workbench**: Switch to the **DuckDB SQL Console** tab to run arbitrary analytical SQL queries (or one-click preset joins) directly in your browser, or load additional `.duckdb`, `.parquet`, or `.json` files via the file picker.

