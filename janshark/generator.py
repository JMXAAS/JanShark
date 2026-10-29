"""
JanShark Synthetic Tableau Server Log Archive Generator
Generates a realistic, compact `sample_logs.zip` mimicking `tsm maintenance ziplogs` output
across 2 nodes (`node1`, `node2`) for all 5 target Tableau Server log domains:
- Apache (`httpd/access.*.log`)
- Backgrounder (`backgrounder/backgrounder_0-0.log`)
- VizQL Server & ART (`vizqlserver/nativeapi_vizqlserver_0-0.txt`)
- Hyper (`hyper/hyperd.log`)
- ResourceManager (`srm/srm_0-0.log`)
"""

import json
import random
import zipfile
from datetime import datetime, timedelta
from pathlib import Path


def generate_sample_ziplogs(output_zip_path: str | Path = "sample_logs.zip", seed: int = 42) -> Path:
    rng = random.Random(seed)
    out_path = Path(output_zip_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    base_time = datetime(2026, 10, 28, 8, 0, 0)
    sites = ["Default", "Finance", "GlobalSales", "Operations"]
    users = ["jmerstrand", "asvensson", "klindqvist", "mchen", "rpatel", "system_admin", "dkumar"]
    workbooks = [
        ("SalesOverview", "ExecutiveKPI", "Default"),
        ("SalesOverview", "RegionalDrilldown", "Default"),
        ("QuarterlyFinancials", "ConsolidatedPL", "Finance"),
        ("QuarterlyFinancials", "CashFlowForecast", "Finance"),
        ("SupplyChainTracker", "InventoryBottlenecks", "Operations"),
        ("GlobalPipeline", "AccountExecutiveScorecard", "GlobalSales"),
        ("CustomerChurn", "CohortRetention", "GlobalSales"),
    ]

    apache_node1: list[str] = []
    apache_node2: list[str] = []
    vizql_node1: list[str] = []
    vizql_node2: list[str] = []
    hyper_node1: list[str] = []
    hyper_node2: list[str] = []
    bg_node1: list[str] = []
    bg_node2: list[str] = []
    srm_node1: list[str] = []
    srm_node2: list[str] = []

    # -------------------------------------------------------------------------
    # 1. Generate correlated Apache + VizQL/ART + Hyper requests (90 requests)
    # -------------------------------------------------------------------------
    for i in range(90):
        dt = base_time + timedelta(minutes=i * 2 + rng.randint(0, 1), seconds=rng.randint(0, 55), milliseconds=rng.randint(10, 990))
        ts_iso = dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
        node = "node1" if rng.random() < 0.58 else "node2"
        user = rng.choice(users)
        wb, vw, site = rng.choice(workbooks)
        req_id = f"Y9xK2wAAAJcAAFCf_{i+100:03d}"
        sess_id = f"SESS-{rng.randint(1000, 1025):04d}-{node[-1]}"
        client_ip = f"10.24.{rng.randint(1, 4)}.{rng.randint(10, 95)}"

        # Introduce realistic scenarios: slowExecutiveKPI or CashFlowForecast spikes, occasional 500/404/401
        is_anomaly = (wb == "QuarterlyFinancials" and vw == "CashFlowForecast" and i % 5 == 0)
        is_error = (i in (14, 37, 62, 79))
        is_auth_err = (i in (22, 51))

        if is_error:
            status = 500 if i != 37 else 504
            req_ms = rng.uniform(8500, 18400)
            uri = f"/t/{site}/vizql/w/{wb}/v/{vw}/bootstrapSession/sessions/{sess_id}" if site != "Default" else f"/vizql/w/{wb}/v/{vw}/bootstrapSession/sessions/{sess_id}"
        elif is_auth_err:
            status = 401 if i == 22 else 404
            req_ms = rng.uniform(35, 140)
            uri = f"/api/3.21/sites/{site}/workbooks" if status == 401 else f"/views/{wb}/MissingDashboard"
        elif is_anomaly:
            status = 200
            req_ms = rng.uniform(5200, 11800)
            uri = f"/t/{site}/views/{wb}/{vw}?:embed=y"
        else:
            status = 200
            action_roll = rng.random()
            if action_roll < 0.40:
                uri = f"/views/{wb}/{vw}?:embed=y" if site == "Default" else f"/t/{site}/views/{wb}/{vw}?:embed=y"
                req_ms = rng.uniform(450, 2900)
            elif action_roll < 0.78:
                uri = f"/vizql/w/{wb}/v/{vw}/bootstrapSession/sessions/{sess_id}" if site == "Default" else f"/t/{site}/vizql/w/{wb}/v/{vw}/bootstrapSession/sessions/{sess_id}"
                req_ms = rng.uniform(800, 4100)
            elif action_roll < 0.90:
                uri = f"/api/3.21/sites/{site}/jobs"
                req_ms = rng.uniform(60, 380)
            else:
                uri = "/vizportal/api/web/v1/getSessionInfo"
                req_ms = rng.uniform(25, 160)

        method = "POST" if ("bootstrapSession" in uri or "vizportal" in uri) else "GET"
        resp_bytes = rng.randint(14500, 480000) if status == 200 else rng.randint(450, 2200)
        req_us = int(req_ms * 1000)

        apache_line = (
            f'{client_ip} - {user} {ts_iso} "+0100" 8000 "{method} {uri} HTTP/1.1" '
            f'"-" {status} {resp_bytes} "{rng.randint(200, 1800)}" {req_us} {req_id} "-"'
        )
        if node == "node1":
            apache_node1.append(apache_line)
        else:
            apache_node2.append(apache_line)

        # Generate corresponding VizQL & ART JSON events for view/vizql requests
        if "/views/" in uri or "/vizql/" in uri:
            v_list = vizql_node1 if node == "node1" else vizql_node2
            h_list = hyper_node1 if node == "node1" else hyper_node2

            # 1) Root ART bootstrap/render event
            art_act = "bootstrap-session" if "bootstrap" in uri else "render-view-session"
            cpu_inc = round(req_ms * rng.uniform(0.55, 0.88), 2)
            cpu_exc = round(cpu_inc * rng.uniform(0.20, 0.45), 2)
            alloc_inc_bytes = int(rng.uniform(35, 420 if is_anomaly or is_error else 145) * 1024 * 1024)
            alloc_exc_bytes = int(alloc_inc_bytes * rng.uniform(0.25, 0.55))

            art_record = {
                "ts": ts_iso,
                "pid": 14200 if node == "node1" else 18400,
                "tid": f"{rng.randint(1000, 9999):04x}",
                "sev": "error" if is_error else ("warn" if is_anomaly else "info"),
                "req": req_id,
                "sess": sess_id,
                "site": site,
                "user": user,
                "k": "art-data",
                "v": {
                    "wb": wb,
                    "vw": vw,
                    "elapsed": round(req_ms / 1000.0, 3),
                    "msg": f"Completed {art_act} for {wb}/{vw}" if not is_error else f"VizQL session exception during {art_act}: Hyper query timeout Exceeded memory limit",
                },
                "art": {
                    "act": art_act,
                    "type": "end",
                    "depth": 1,
                    "id": f"art-{i:03d}-1",
                    "sponsor": "root",
                    "wb": wb,
                    "vw": vw,
                    "elapsed": round(req_ms / 1000.0, 3),
                    "res": {
                        "cputime": {"i": cpu_inc, "e": cpu_exc},
                        "allocated": {"i": alloc_inc_bytes, "e": alloc_exc_bytes},
                    },
                },
            }
            v_list.append(json.dumps(art_record))

            # 2) Child VizQL query event (`end-query` or `compute-quick-filters`)
            q_dt = dt + timedelta(milliseconds=int(req_ms * 0.25))
            q_ts = q_dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
            q_elapsed_s = round((req_ms * rng.uniform(0.45, 0.78)) / 1000.0, 3)
            is_cached = (not is_anomaly and not is_error and rng.random() < 0.28)
            rows_ret = rng.randint(120, 85000 if is_anomaly else 12400)
            sql_snippet = (
                f'SELECT "t0"."Region", "t0"."Category", SUM("t0"."Sales") AS "sum_Sales" '
                f'FROM "Extract"."{wb}_Fact" "t0" GROUP BY 1, 2'
            )

            child_act = rng.choice(["qp-query-end", "end-query", "compute-layout-model", "evaluate-quick-filter"])
            query_record = {
                "ts": q_ts,
                "pid": 14200 if node == "node1" else 18400,
                "tid": f"{rng.randint(1000, 9999):04x}",
                "sev": "error" if is_error else "info",
                "req": req_id,
                "sess": sess_id,
                "site": site,
                "user": user,
                "k": "end-query" if not is_error else "vizql-error",
                "v": {
                    "wb": wb,
                    "vw": vw,
                    "elapsed": 0.015 if is_cached else q_elapsed_s,
                    "rows": rows_ret,
                    "cached": is_cached,
                    "query-trunc": sql_snippet,
                    "msg": "Query executed via Hyper Data Engine" if not is_error else "DataSourceException: Hyperd memory limit exceeded while materializing temp table",
                },
                "art": {
                    "act": child_act,
                    "type": "end",
                    "depth": 2,
                    "id": f"art-{i:03d}-2",
                    "sponsor": f"art-{i:03d}-1",
                    "wb": wb,
                    "vw": vw,
                    "elapsed": 0.015 if is_cached else q_elapsed_s,
                    "res": {
                        "cputime": {"i": round(cpu_inc * 0.65, 2), "e": round(cpu_inc * 0.50, 2)},
                        "allocated": {"i": int(alloc_inc_bytes * 0.65), "e": int(alloc_inc_bytes * 0.55)},
                    },
                },
            }
            v_list.append(json.dumps(query_record))

            # 3) Corresponding Hyper query execution event (when not cache hit)
            if not is_cached:
                h_mem = round(rng.uniform(18.5, 920.0 if (is_anomaly or is_error) else 185.0), 2)
                spooled = h_mem > 320.0
                hyper_record = {
                    "ts": q_ts,
                    "pid": 8812 if node == "node1" else 9104,
                    "tid": f"{rng.randint(100, 999):03x}",
                    "sev": "error" if is_error else ("warn" if spooled else "info"),
                    "req": req_id,
                    "sess": sess_id,
                    "k": "query-end" if not is_error else "query-error",
                    "v": {
                        "db-path": f"/var/opt/tableau/data/extracts/{site}/{wb}.hyper",
                        "elapsed": round(q_elapsed_s * 0.92, 4),
                        "cpu-time": round(q_elapsed_s * rng.uniform(1.1, 2.8), 4),
                        "rows": rows_ret,
                        "peak-result-buffer-memory-mb": h_mem,
                        "spooling": spooled,
                        "query-trunc": sql_snippet,
                        "error": "Hyper memory limit exceeded during hash aggregation" if is_error else None,
                    },
                }
                h_list.append(json.dumps(hyper_record))

    # -------------------------------------------------------------------------
    # 2. Generate Backgrounder Jobs & Events (36 jobs across node1 and node2)
    # -------------------------------------------------------------------------
    bg_targets = [
        ("refresh_extracts", "SalesOverview_Extract", "Default", 20),
        ("refresh_extracts", "QuarterlyFinancials_GL", "Finance", 10),
        ("increment_extracts", "GlobalPipeline_CRM", "GlobalSales", 30),
        ("refresh_extracts", "SupplyChain_IoT_Warehouse", "Operations", 50),
        ("single_subscription_notify", "ExecMorningBriefing", "Default", 40),
        ("run_flow", "CustomerChurn_PrepFlow", "GlobalSales", 50),
        ("check_data_alert", "MarginDropThresholdAlert", "Finance", 20),
        ("refresh_extracts", "LegacyERP_Connector", "Operations", 70),
    ]

    for j_idx in range(36):
        job_id = 10400 + j_idx
        node = "node1" if j_idx % 2 == 0 else "node2"
        bg_inst = f"backgrounder_{0 if node == 'node1' else 1}-{j_idx % 2}"
        j_type, target, site, prio = bg_targets[j_idx % len(bg_targets)]

        q_dt = base_time + timedelta(minutes=j_idx * 5)
        queue_wait = round(rng.uniform(2.5, 420.0 if j_idx in (5, 13, 21, 29) else 48.0), 1)
        start_dt = q_dt + timedelta(seconds=queue_wait)

        # Simulate failures on specific jobs
        if j_idx in (7, 15, 23, 31):
            status = "Failed"
            run_sec = round(rng.uniform(45.0, 620.0), 1)
            err_reasons = {
                7: "Connectionless Failure (status code = 10000): Unable to connect to Snowflake warehouse 'PROD_WH' - credentials expired",
                15: "com.tableausoftware.nativeapi.exceptions.DataSourceException: Hyper timeout waiting for lock on QuarterlyFinancials_GL.hyper",
                23: "OutOfMemoryError: Backgrounder process exceeded 8192MB threshold during Prep Flow execution",
                31: "SocketTimeoutException: Read timed out after 600s fetching from LegacyERP_Connector JDBC driver",
            }
            err_msg = err_reasons[j_idx]
        elif j_idx == 19:
            status = "Cancelled"
            run_sec = 905.0
            err_msg = "Job cancelled by Server Resource Manager (SRM) or Administrator due to runtime limit"
        else:
            status = "Success"
            run_sec = round(rng.uniform(18.0, 380.0 if j_type == "refresh_extracts" else 75.0), 1)
            err_msg = None

        end_dt = start_dt + timedelta(seconds=run_sec)
        total_sec = round(queue_wait + run_sec, 1)

        q_ts_str = q_dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        s_ts_str = start_dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        e_ts_str = end_dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        bg_lines = bg_node1 if node == "node1" else bg_node2
        # Start log line
        bg_lines.append(
            f'{s_ts_str} +0100 ({site},system,_,{job_id},:{j_type},req_{job_id}) '
            f'scheduled-background-job-runner-1 {bg_inst}: INFO  '
            f'com.tableausoftware.backgrounder.runner.BackgroundJobRunner - '
            f'Starting job: jobId={job_id} jobType={j_type} target="{target}" priority={prio} '
            f'queuedTime="{q_ts_str}" queueWaitSec={queue_wait} args="[{target}, {site}]"'
        )
        # End log line
        sev = "ERROR" if status == "Failed" else ("WARN" if status == "Cancelled" else "INFO")
        err_kv = f' error="{err_msg}"' if err_msg else ""
        bg_lines.append(
            f'{e_ts_str} +0100 ({site},system,_,{job_id},:{j_type},req_{job_id}) '
            f'scheduled-background-job-runner-1 {bg_inst}: {sev}  '
            f'com.tableausoftware.backgrounder.runner.BackgroundJobRunner - '
            f'Job finished: status={status} jobId={job_id} jobType={j_type} target="{target}" '
            f'queueWaitSec={queue_wait} runTimeSec={run_sec} totalTimeSec={total_sec}{err_kv}'
        )

    # -------------------------------------------------------------------------
    # 3. Generate Server Resource Manager (SRM) CPU & RAM Telemetry
    # -------------------------------------------------------------------------
    processes = [
        ("vizqlserver_0-0", 14200, 16384.0),
        ("backgrounder_0-0", 15100, 8192.0),
        ("hyper_0", 8812, 24576.0),
        ("httpd", 4120, 4096.0),
    ]
    for step in range(36):
        dt = base_time + timedelta(minutes=step * 5)
        ts_str = dt.strftime("%Y-%m-%d %H:%M:%S.000")
        for node in ("node1", "node2"):
            is_spike = (step in (10, 11, 22, 23) and node == "node1") or (step in (15, 16) and node == "node2")
            node_cpu = round(rng.uniform(78.0, 96.5) if is_spike else rng.uniform(22.0, 58.0), 1)
            node_mem = round(rng.uniform(48000.0, 61200.0) if is_spike else rng.uniform(24000.0, 39500.0), 1)

            for proc_base, pid_base, limit_mb in processes:
                proc_name = proc_base.replace("_0", "_1") if node == "node2" else proc_base
                pid = pid_base + (2000 if node == "node2" else 0)

                if "vizql" in proc_name:
                    cpu = round(node_cpu * rng.uniform(0.38, 0.52), 1)
                    mem = round(rng.uniform(12800.0, 16850.0) if is_spike else rng.uniform(4200.0, 9400.0), 1)
                elif "hyper" in proc_name:
                    cpu = round(node_cpu * rng.uniform(0.25, 0.38), 1)
                    mem = round(rng.uniform(14500.0, 21000.0) if is_spike else rng.uniform(6500.0, 12200.0), 1)
                elif "backgrounder" in proc_name:
                    cpu = round(node_cpu * rng.uniform(0.15, 0.30), 1)
                    mem = round(rng.uniform(6200.0, 8450.0) if is_spike else rng.uniform(2100.0, 4800.0), 1)
                else:
                    cpu = round(rng.uniform(1.5, 8.5), 1)
                    mem = round(rng.uniform(420.0, 980.0), 1)

                if mem > limit_mb:
                    action = "MemoryLimitExceeded_Recycle"
                    sev = "WARN"
                    notes = f"Process {proc_name} (PID {pid}) exceeded SRM memory limit ({mem}MB > {limit_mb}MB); scheduled for graceful restart"
                elif cpu > 42.0 and is_spike:
                    action = "HighCpuThrottle"
                    sev = "WARN"
                    notes = f"Sustained high CPU ({cpu}%) detected on {node} for {proc_name}"
                else:
                    action = "Monitor"
                    sev = "INFO"
                    notes = "Normal telemetry sample"

                line = (
                    f'{ts_str} +0100 srm: {sev}  com.tableausoftware.srm.ResourceManager - '
                    f'ProcessUsage: process={proc_name} pid={pid} cpu_pct={cpu} memory_mb={mem} '
                    f'limit_mb={limit_mb} system_cpu_pct={node_cpu} system_memory_mb={node_mem} '
                    f'total_memory_mb=65536.0 action={action} notes="{notes}"'
                )
                if node == "node1":
                    srm_node1.append(line)
                else:
                    srm_node2.append(line)

    # Write all log files into a realistic Tableau Server ziplogs hierarchy
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("node1/httpd/access.2026_10_28_00_00_00.log", "\n".join(apache_node1) + "\n")
        zf.writestr("node2/httpd/access.2026_10_28_00_00_00.log", "\n".join(apache_node2) + "\n")
        zf.writestr("node1/vizqlserver/Logs/nativeapi_vizqlserver_0-0.txt", "\n".join(vizql_node1) + "\n")
        zf.writestr("node2/vizqlserver/Logs/nativeapi_vizqlserver_1-0.txt", "\n".join(vizql_node2) + "\n")
        zf.writestr("node1/hyper/hyperd.log", "\n".join(hyper_node1) + "\n")
        zf.writestr("node2/hyper/hyperd.log", "\n".join(hyper_node2) + "\n")
        zf.writestr("node1/backgrounder/backgrounder_0-0.log", "\n".join(bg_node1) + "\n")
        zf.writestr("node2/backgrounder/backgrounder_1-0.log", "\n".join(bg_node2) + "\n")
        zf.writestr("node1/srm/srm_0-0.log", "\n".join(srm_node1) + "\n")
        zf.writestr("node2/srm/srm_1-0.log", "\n".join(srm_node2) + "\n")

    return out_path

