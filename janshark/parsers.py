"""
JanShark Log Parsers
Re-engineers the core Tableau Server Logshark plugins into fast, clean Python parsers:
1. ApachePlugin -> Apache HTTP Gateway access/error logs (`apache_requests`)
2. BackgrounderPlugin -> Backgrounder job lifecycle & error logs (`backgrounder_jobs`)
3. VizqlServerPlugin & ArtPlugin -> VizQL native JSON logs & Activity Resource Tracing (`vizql_events`, `art_events`)
4. HyperPlugin -> Tableau Hyper Data Engine query & lifecycle logs (`hyper_events`)
5. ResourceManagerPlugin (SRM) -> Server Resource Manager CPU, Memory & limit telemetry (`srm_metrics`)
"""

import json
import re
from datetime import datetime
from typing import Any, Optional

from .extractor import LogFileEntry


def normalize_timestamp(ts_str: str) -> str:
    """Normalize various Tableau log timestamp formats into ISO-8601 'YYYY-MM-DD HH:MM:SS.mmm'."""
    if not ts_str:
        return "2026-10-28 00:00:00.000"
    s = ts_str.strip()
    # Replace 'T' with space and strip timezone offsets for clean DuckDB TIMESTAMP parsing
    s = s.replace("T", " ")
    # Remove trailing timezone like +0100, -04:00, Z, etc.
    s = re.sub(r"\s*[+-]\d{2}:?\d{2}$", "", s)
    s = s.rstrip("Z")
    # Convert comma milliseconds (Java log4j style: 2026-10-28 08:15:23,456) to dot
    s = s.replace(",", ".")
    return s[:23]


# ============================================================================
# 1. APACHE PLUGIN PARSER (Mirrors LogShark/Plugins/Shared/ApacheEventParser.cs)
# ============================================================================
# Tableau Server Apache access.log format (modern & legacy variants):
# Example 1 (Tableau custom format):
# 10.24.1.15 - jdoe 2026-10-28T08:12:04.120 "+0100" 8000 "GET /views/SalesOverview/ExecutiveKPI?:embed=y HTTP/1.1" "-" 200 18452 "1420" 4251000 Y9xK2wAAAJcAAFCf_01 "-"
# Example 2 (Standard / Extended format):
# 10.24.1.15 - jdoe [28/Oct/2026:08:12:04 +0100] 8000 "GET /vizql/w/Finance/v/PL/bootstrapSession/sessions/1A2B HTTP/1.1" 200 45120 1850 1850000 "Y9xK2wAAAJcAAFCf_02"
APACHE_TS_ISO_REGEX = re.compile(
    r'^(?P<client_ip>\S+)\s+-\s+(?P<requester>\S+)\s+'
    r'(?P<ts>\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+'
    r'(?:"[^"]*"\s+)?'
    r'(?P<port>\d+)\s+'
    r'"(?P<method>[A-Z]+)\s+(?P<uri>\S+)\s+(?P<protocol>[^"]+)"\s+'
    r'(?:"(?P<xff>[^"]*)"\s+)?'
    r'(?P<status>\d{3})\s+'
    r'(?P<bytes>\d+|-)\s+'
    r'"?(?P<content_len>[^"\s]*)"?\s+'
    r'(?P<request_time_us>\d+)\s+'
    r'"?(?P<request_id>[A-Za-z0-9_\-@]+)"?'
)

VIEW_URI_REGEX = re.compile(
    r"(?:/t/(?P<site>[^/]+))?/(?:views|vizql/w)/(?P<workbook>[^/?#]+)/(?:v/)?(?P<view>[^/?#]+)",
    re.IGNORECASE,
)


def classify_apache_endpoint(uri: str) -> tuple[str, str, Optional[str], Optional[str]]:
    """Categorize an Apache URI into traffic class, site, workbook, and view."""
    site = "Default"
    workbook = None
    view = None

    m = VIEW_URI_REGEX.search(uri)
    if m:
        if m.group("site"):
            site = m.group("site")
        workbook = m.group("workbook")
        view = m.group("view")

    u_low = uri.lower()
    if "bootstrapsession" in u_low:
        category = "VizQL Bootstrap"
    elif "/views/" in u_low:
        category = "View Load"
    elif "/vizql/" in u_low:
        category = "VizQL Interaction"
    elif "/api/" in u_low:
        category = "REST API"
    elif "/vizportal/" in u_low:
        category = "Vizportal API"
    elif "/auth" in u_low or "/signin" in u_low or "/login" in u_low:
        category = "Authentication"
    else:
        category = "Static / Other"

    return category, site, workbook, view


def parse_apache_file(entry: LogFileEntry) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(entry.content_lines, start=1):
        line_s = line.strip()
        if not line_s:
            continue

        # Support JSON-formatted Apache logs if present
        if line_s.startswith("{"):
            try:
                obj = json.loads(line_s)
                uri = obj.get("uri", obj.get("request_uri", "/"))
                category, site, wb, vw = classify_apache_endpoint(uri)
                req_ms = float(obj.get("request_time_ms", obj.get("duration_us", 0) / 1000.0))
                status = int(obj.get("status", obj.get("status_code", 200)))
                rows.append({
                    "ts": normalize_timestamp(obj.get("ts", "")),
                    "worker_node": entry.worker_node,
                    "service_instance": entry.service_instance,
                    "client_ip": obj.get("client_ip", "127.0.0.1"),
                    "requester": obj.get("requester", obj.get("user", "-")),
                    "method": obj.get("method", "GET"),
                    "uri": uri,
                    "endpoint_category": category,
                    "site": obj.get("site", site),
                    "workbook": obj.get("workbook", wb),
                    "view_name": obj.get("view", vw),
                    "status_code": status,
                    "status_class": f"{status // 100}xx",
                    "response_bytes": int(obj.get("bytes", 0)),
                    "request_time_ms": round(req_ms, 2),
                    "request_id": obj.get("request_id", "-"),
                    "file_name": entry.file_name,
                    "line_number": line_no,
                })
                continue
            except (ValueError, TypeError):
                pass

        m = APACHE_TS_ISO_REGEX.match(line_s)
        if m:
            gd = m.groupdict()
            uri = gd["uri"]
            category, site, wb, vw = classify_apache_endpoint(uri)
            status = int(gd["status"])
            bytes_val = 0 if gd["bytes"] == "-" else int(gd["bytes"])
            req_us = int(gd["request_time_us"])
            # Tableau logs request_time in microseconds (or milliseconds if small; Logshark treats >=1000 as us or has port/offset rules)
            req_ms = round(req_us / 1000.0, 2)
            rows.append({
                "ts": normalize_timestamp(gd["ts"]),
                "worker_node": entry.worker_node,
                "service_instance": entry.service_instance,
                "client_ip": gd["client_ip"],
                "requester": gd["requester"] if gd["requester"] != "-" else "anonymous",
                "method": gd["method"],
                "uri": uri,
                "endpoint_category": category,
                "site": site,
                "workbook": wb,
                "view_name": vw,
                "status_code": status,
                "status_class": f"{status // 100}xx",
                "response_bytes": bytes_val,
                "request_time_ms": req_ms,
                "request_id": gd["request_id"],
                "file_name": entry.file_name,
                "line_number": line_no,
            })
    return rows


# ============================================================================
# 2. BACKGROUNDER PLUGIN PARSER (Mirrors LogShark/Plugins/Backgrounder)
# ============================================================================
# Tableau Backgrounder Java log line format:
# 2026-10-28 08:15:10.234 +0100 (Default,jdoe,_,10421,:refresh_extracts,c81d4e2e) scheduled-background-job-runner-1 backgrounder: INFO  com.tableausoftware.model.workgroup.service.VqlSessionService - ...
JAVA_BG_LINE_REGEX = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}[.,]\d{3})\s+"
    r"(?:[+-]\d{4}\s+)?"
    r"(?:\d+\s+)?"  # optional PID in 2024.2+
    r"\((?P<site>[^,]*),(?P<user>[^,]*),(?P<sess>[^,]*),(?P<job_id>[^,]*),(?P<job_type>[^,]*),(?P<req_id>[^)]*)\)\s+"
    r"(?P<thread>\S+)\s+"
    r"(?P<service>\S+?):\s+"
    r"(?P<severity>INFO|WARN|ERROR|FATAL|DEBUG)\s+"
    r"(?P<class>\S+)\s+-\s+(?P<message>.*)$"
)

KV_EXTRACT_REGEX = re.compile(r'(\w+)=(?:"([^"]*)"|([^\s,;]+))')


def parse_backgrounder_file(entry: LogFileEntry) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Parse Backgrounder log files into:
    - jobs_list: aggregated/completed job execution records (`backgrounder_jobs`)
    - events_list: individual backgrounder log events & errors (`backgrounder_events`)
    """
    jobs_by_id: dict[str, dict[str, Any]] = {}
    events_list: list[dict[str, Any]] = []

    for line_no, line in enumerate(entry.content_lines, start=1):
        line_s = line.strip()
        if not line_s:
            continue

        # Handle structured JSON backgrounder events if present
        if line_s.startswith("{"):
            try:
                obj = json.loads(line_s)
                ts = normalize_timestamp(obj.get("ts", ""))
                sev = str(obj.get("sev", obj.get("severity", "INFO"))).upper()
                job_id = str(obj.get("job_id", obj.get("jobId", "")))
                job_type = str(obj.get("job_type", obj.get("jobType", "refresh_extracts"))).lstrip(":")
                status = str(obj.get("status", "Success"))
                msg = str(obj.get("msg", obj.get("message", obj.get("v", ""))))
                if job_id and job_id != "_":
                    jobs_by_id[job_id] = {
                        "job_id": int(job_id) if job_id.isdigit() else abs(hash(job_id)) % 1000000,
                        "worker_node": entry.worker_node,
                        "backgrounder_instance": entry.service_instance,
                        "site": obj.get("site", "Default") or "Default",
                        "job_type": job_type,
                        "target_name": obj.get("target_name", obj.get("datasource", obj.get("workbook", "Unknown"))),
                        "priority": int(obj.get("priority", 50)),
                        "queued_ts": normalize_timestamp(obj.get("queued_ts", ts)),
                        "start_ts": normalize_timestamp(obj.get("start_ts", ts)),
                        "end_ts": ts,
                        "queue_wait_sec": float(obj.get("queue_wait_sec", 0.0)),
                        "run_time_sec": float(obj.get("run_time_sec", 0.0)),
                        "total_time_sec": float(obj.get("total_time_sec", 0.0)),
                        "status": status,
                        "error_message": obj.get("error_message", msg if status != "Success" else None),
                        "args": obj.get("args", ""),
                        "file_name": entry.file_name,
                    }
                if sev in ("WARN", "ERROR", "FATAL") or "job" in msg.lower():
                    events_list.append({
                        "ts": ts,
                        "worker_node": entry.worker_node,
                        "backgrounder_instance": entry.service_instance,
                        "severity": sev,
                        "job_id": int(job_id) if job_id.isdigit() else None,
                        "job_type": job_type,
                        "component": obj.get("k", "Backgrounder"),
                        "message": msg[:500],
                        "file_name": entry.file_name,
                        "line_number": line_no,
                    })
                continue
            except (ValueError, TypeError):
                pass

        m = JAVA_BG_LINE_REGEX.match(line_s)
        if not m:
            continue

        gd = m.groupdict()
        ts = normalize_timestamp(gd["ts"])
        site = gd["site"] if gd["site"] and gd["site"] != "_" else "Default"
        job_id_raw = gd["job_id"].strip()
        job_type_raw = gd["job_type"].strip().lstrip(":") or "system_task"
        sev = gd["severity"].upper()
        msg = gd["message"]

        # Extract key=value pairs from message
        kvs = {k: (v1 if v1 != "" else v2) for k, v1, v2 in KV_EXTRACT_REGEX.findall(msg)}

        if job_id_raw and job_id_raw != "_":
            j_rec = jobs_by_id.get(job_id_raw)
            if not j_rec:
                j_rec = {
                    "job_id": int(job_id_raw) if job_id_raw.isdigit() else abs(hash(job_id_raw)) % 1000000,
                    "worker_node": entry.worker_node,
                    "backgrounder_instance": entry.service_instance,
                    "site": site,
                    "job_type": kvs.get("jobType", job_type_raw),
                    "target_name": kvs.get("target", kvs.get("workbook", kvs.get("datasource", "Extract / Task"))),
                    "priority": int(kvs.get("priority", 50)),
                    "queued_ts": kvs.get("queuedTime", ts),
                    "start_ts": ts,
                    "end_ts": ts,
                    "queue_wait_sec": float(kvs.get("queueWaitSec", 0.0)),
                    "run_time_sec": float(kvs.get("runTimeSec", 0.0)),
                    "total_time_sec": float(kvs.get("totalTimeSec", 0.0)),
                    "status": "Running",
                    "error_message": None,
                    "args": kvs.get("args", ""),
                    "file_name": entry.file_name,
                }
                jobs_by_id[job_id_raw] = j_rec

            # Update fields as we see job progress/completion lines
            j_rec["end_ts"] = ts
            if "target" in kvs or "workbook" in kvs or "datasource" in kvs:
                j_rec["target_name"] = kvs.get("target", kvs.get("workbook", kvs.get("datasource", j_rec["target_name"])))
            if "priority" in kvs and kvs["priority"].isdigit():
                j_rec["priority"] = int(kvs["priority"])
            if "queueWaitSec" in kvs:
                j_rec["queue_wait_sec"] = float(kvs["queueWaitSec"])
            if "runTimeSec" in kvs:
                j_rec["run_time_sec"] = float(kvs["runTimeSec"])
            if "totalTimeSec" in kvs:
                j_rec["total_time_sec"] = float(kvs["totalTimeSec"])
            elif j_rec["run_time_sec"] or j_rec["queue_wait_sec"]:
                j_rec["total_time_sec"] = round(j_rec["queue_wait_sec"] + j_rec["run_time_sec"], 2)

            if "args" in kvs:
                j_rec["args"] = kvs["args"]

            msg_low = msg.lower()
            if "job finished: success" in msg_low or kvs.get("status", "").lower() == "success":
                j_rec["status"] = "Success"
            elif sev in ("ERROR", "FATAL") or "error" in msg_low or "failed" in msg_low or kvs.get("status", "").lower() == "failed":
                j_rec["status"] = "Failed"
                j_rec["error_message"] = kvs.get("error", msg[:400])
            elif "cancelled" in msg_low or kvs.get("status", "").lower() == "cancelled":
                j_rec["status"] = "Cancelled"
                j_rec["error_message"] = kvs.get("error", msg[:400])

        # Record event row for errors, warnings, or lifecycle milestones
        if sev in ("WARN", "ERROR", "FATAL") or "starting" in msg.lower() or "finished" in msg.lower():
            events_list.append({
                "ts": ts,
                "worker_node": entry.worker_node,
                "backgrounder_instance": entry.service_instance,
                "severity": sev,
                "job_id": int(job_id_raw) if job_id_raw.isdigit() else None,
                "job_type": job_type_raw,
                "component": gd["class"].split(".")[-1],
                "message": msg[:500],
                "file_name": entry.file_name,
                "line_number": line_no,
            })

    # Finalize any still-"Running" jobs as Success if no error occurred
    for j in jobs_by_id.values():
        if j["status"] == "Running":
            j["status"] = "Success" if not j["error_message"] else "Failed"

    return list(jobs_by_id.values()), events_list


# ============================================================================
# 3. VIZQL SERVER & ART PLUGIN PARSER (Mirrors VizqlServerPlugin & ArtPlugin)
# ============================================================================
# Native JSON log format used by `vizqlserver_*.txt` / `.log`:
# {"ts":"2026-10-28T08:12:05.112","pid":14200,"tid":"3a8c","sev":"info","req":"Y9xK2wAAAJcAAFCf_01","sess":"9F2A1B3C-01","site":"Default","user":"jdoe","k":"end-query","v":{"elapsed":1.42,"protocol-id":4,"query-Lite":"SELECT ...","rows":1250},"art":{...}}
# Or ART record where "k": "art-data" or "art" object is embedded:
# {"art": {"act":"bootstrap-session","depth":1,"id":"a1","sponsor":"root","type":"end","vw":"ExecutiveKPI","wb":"SalesOverview","elapsed":2.45,"res":{"cputime":{"i":1250,"e":340},"allocated":{"i":48500000,"e":12400000}}}}
def parse_vizql_file(entry: LogFileEntry) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Parse VizQL Server native JSON logs into:
    - vizql_events: queries, bootstrap sessions, rendering, caching, and error events (`vizql_events`)
    - art_events: Activity and Resource Tracing telemetry (`art_events`)
    """
    vizql_events: list[dict[str, Any]] = []
    art_events: list[dict[str, Any]] = []

    for line_no, line in enumerate(entry.content_lines, start=1):
        line_s = line.strip()
        if not line_s or not line_s.startswith("{"):
            continue
        try:
            obj = json.loads(line_s)
        except ValueError:
            continue

        ts = normalize_timestamp(obj.get("ts", ""))
        sev = str(obj.get("sev", "info")).upper()
        req = str(obj.get("req", "-"))
        sess = str(obj.get("sess", "-"))
        site = str(obj.get("site", "Default")) if obj.get("site") not in (None, "-", "") else "Default"
        user = str(obj.get("user", "anonymous")) if obj.get("user") not in (None, "-", "") else "anonymous"
        k = str(obj.get("k", "msg"))
        v = obj.get("v")

        # 1. Check for ART (Activity and Resource Tracing) payload
        art_payload = obj.get("art")
        if not art_payload and k in ("art-data", "art-event") and isinstance(v, dict):
            art_payload = v

        if isinstance(art_payload, dict):
            res = art_payload.get("res", {})
            cputime = res.get("cputime", res.get("cpu", {}))
            allocated = res.get("allocated", res.get("mem", {}))
            elapsed_s = float(art_payload.get("elapsed", art_payload.get("elapsed-sec", 0.0)))
            cpu_inc_ms = float(cputime.get("i", art_payload.get("cpu_inclusive_ms", 0.0)))
            cpu_exc_ms = float(cputime.get("e", art_payload.get("cpu_exclusive_ms", 0.0)))
            mem_inc_mb = round(float(allocated.get("i", 0.0)) / (1024 * 1024), 2) if "i" in allocated else float(art_payload.get("alloc_inclusive_mb", 0.0))
            mem_exc_mb = round(float(allocated.get("e", 0.0)) / (1024 * 1024), 2) if "e" in allocated else float(art_payload.get("alloc_exclusive_mb", 0.0))

            art_events.append({
                "ts": ts,
                "worker_node": entry.worker_node,
                "vizql_instance": entry.service_instance,
                "session_id": sess,
                "request_id": req,
                "site": site,
                "username": user,
                "workbook": art_payload.get("wb", art_payload.get("workbook", "Unknown")),
                "view_name": art_payload.get("vw", art_payload.get("view", "Unknown")),
                "activity_name": art_payload.get("act", art_payload.get("activity", k)),
                "activity_type": art_payload.get("type", "end"),
                "depth": int(art_payload.get("depth", 1)),
                "activity_id": str(art_payload.get("id", f"art-{line_no}")),
                "sponsor_id": str(art_payload.get("sponsor", "root")),
                "elapsed_ms": round(elapsed_s * 1000.0 if elapsed_s < 500 else elapsed_s, 2),
                "cpu_inclusive_ms": round(cpu_inc_ms, 2),
                "cpu_exclusive_ms": round(cpu_exc_ms, 2),
                "alloc_inclusive_mb": round(mem_inc_mb, 2),
                "alloc_exclusive_mb": round(mem_exc_mb, 2),
                "file_name": entry.file_name,
                "line_number": line_no,
            })

        # 2. Extract VizQL Server event (`end-query`, `qp-query-end`, `bootstrap-session`, `compute-layout`, errors, etc.)
        if isinstance(v, dict):
            elapsed_val = v.get("elapsed", v.get("elapsed-ms", 0.0))
            # In VizQL native logs, `elapsed` is in seconds (float) unless key is elapsed-ms
            elapsed_ms = float(elapsed_val) * 1000.0 if "elapsed" in v and float(elapsed_val) < 600 else float(elapsed_val)
            wb = v.get("wb", v.get("workbook", (art_payload or {}).get("wb")))
            vw = v.get("vw", v.get("view", (art_payload or {}).get("vw")))
            query_txt = v.get("query-trunc", v.get("query", v.get("query-Lite")))
            rows_ret = int(v.get("rows", v.get("row-count", 0))) if str(v.get("rows", "0")).isdigit() else 0
            is_cache_hit = bool(v.get("cached", v.get("cache-hit", False)))
            msg_txt = v.get("msg", v.get("message", v.get("error", json.dumps(v)[:300])))
        else:
            elapsed_ms = 0.0
            wb = (art_payload or {}).get("wb")
            vw = (art_payload or {}).get("vw")
            query_txt = None
            rows_ret = 0
            is_cache_hit = False
            msg_txt = str(v) if v is not None else k

        vizql_events.append({
            "ts": ts,
            "worker_node": entry.worker_node,
            "vizql_instance": entry.service_instance,
            "process_id": int(obj.get("pid", 0)),
            "thread_id": str(obj.get("tid", "")),
            "severity": sev,
            "session_id": sess,
            "request_id": req,
            "site": site,
            "username": user,
            "workbook": wb,
            "view_name": vw,
            "event_key": k,
            "elapsed_ms": round(elapsed_ms, 2),
            "rows_returned": rows_ret,
            "is_cache_hit": is_cache_hit,
            "query_text": str(query_txt)[:500] if query_txt else None,
            "message": str(msg_txt)[:500],
            "file_name": entry.file_name,
            "line_number": line_no,
        })

    return vizql_events, art_events


# ============================================================================
# 4. HYPER PLUGIN PARSER (Mirrors LogShark/Plugins/Hyper)
# ============================================================================
# Hyper logs (`hyperd.log`) are JSON lines:
# {"ts":"2026-10-28T08:12:06.210","pid":8812,"tid":"104a","sev":"info","req":"Y9xK2wAAAJcAAFCf_01","sess":"9F2A1B3C-01","k":"query-end","v":{"query-trunc":"SELECT ...","elapsed":0.185,"rows":1250,"peak-result-buffer-memory-mb":14.2,"spooling":false,"client-session-id":"9F2A1B3C-01"}}
def parse_hyper_file(entry: LogFileEntry) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(entry.content_lines, start=1):
        line_s = line.strip()
        if not line_s or not line_s.startswith("{"):
            continue
        try:
            obj = json.loads(line_s)
        except ValueError:
            continue

        ts = normalize_timestamp(obj.get("ts", ""))
        sev = str(obj.get("sev", "info")).upper()
        k = str(obj.get("k", "hyper-event"))
        v = obj.get("v", {})
        if not isinstance(v, dict):
            v = {"message": str(v)}

        elapsed_sec = float(v.get("elapsed", v.get("total-time", v.get("execution-time", 0.0))))
        elapsed_ms = round(elapsed_sec * 1000.0 if elapsed_sec < 1000 else elapsed_sec, 2)

        peak_mem_mb = float(
            v.get(
                "peak-result-buffer-memory-mb",
                v.get("peak-memory-mb", float(v.get("peak-memory-bytes", 0)) / (1024 * 1024)),
            )
        )
        rows_affected = int(v.get("rows", v.get("row-count", v.get(" affected-rows", 0))))
        cpu_time_ms = round(float(v.get("cpu-time", v.get("cpu-time-sec", 0.0))) * 1000.0, 2)
        spooling = bool(v.get("spooling", v.get("spooled", False)))
        db_path = v.get("db-path", v.get("database", v.get("extract", "extract.hyper")))
        query_txt = v.get("query-trunc", v.get("query", None))
        err_msg = v.get("error", v.get("message", None)) if sev in ("WARN", "ERROR", "FATAL") else None

        rows.append({
            "ts": ts,
            "worker_node": entry.worker_node,
            "hyper_instance": entry.service_instance,
            "severity": sev,
            "request_id": str(obj.get("req", v.get("request-id", "-"))),
            "session_id": str(obj.get("sess", v.get("client-session-id", "-"))),
            "event_key": k,
            "database_path": str(db_path),
            "elapsed_ms": elapsed_ms,
            "cpu_time_ms": cpu_time_ms,
            "rows_affected": rows_affected,
            "peak_memory_mb": round(peak_mem_mb, 2),
            "spooled_to_disk": spooling,
            "query_text": str(query_txt)[:500] if query_txt else None,
            "error_message": str(err_msg)[:500] if err_msg else None,
            "file_name": entry.file_name,
            "line_number": line_no,
        })
    return rows


# ============================================================================
# 5. RESOURCE MANAGER (SRM) PLUGIN PARSER (Mirrors ResourceManagerPlugin)
# ============================================================================
# SRM logs (`srm_*.log` or JSON telemetry) track process and node CPU % and Memory MB, plus threshold/recycle actions:
# Supports both JSON telemetry lines and text SRM log lines:
# e.g. 2026-10-28 08:12:00.000 +0100 srm: INFO  ResourceManager - ProcessUsage: process=vizqlserver_0-0 pid=14200 cpu_pct=42.5 memory_mb=4120.4 system_cpu_pct=68.2 system_memory_mb=24500.0 limit_mb=16384 action=None
SRM_TEXT_REGEX = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:[.,]\d{3})?)\s+"
    r"(?:[+-]\d{4}\s+)?"
    r".*?(?P<severity>INFO|WARN|ERROR|FATAL)\s+.*?-\s+(?P<message>.*)$"
)


def parse_srm_file(entry: LogFileEntry) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(entry.content_lines, start=1):
        line_s = line.strip()
        if not line_s:
            continue

        if line_s.startswith("{"):
            try:
                obj = json.loads(line_s)
                v = obj.get("v", obj)
                if not isinstance(v, dict):
                    continue
                rows.append({
                    "ts": normalize_timestamp(obj.get("ts", v.get("ts", ""))),
                    "worker_node": entry.worker_node,
                    "process_name": str(v.get("process_name", v.get("process", "vizqlserver"))),
                    "process_id": int(v.get("pid", v.get("process_id", 0))),
                    "cpu_pct": round(float(v.get("cpu_pct", v.get("cpu", 0.0))), 2),
                    "memory_mb": round(float(v.get("memory_mb", v.get("mem_mb", 0.0))), 2),
                    "memory_limit_mb": round(float(v.get("memory_limit_mb", v.get("limit_mb", 16384.0))), 2),
                    "node_cpu_pct": round(float(v.get("node_cpu_pct", v.get("system_cpu_pct", 0.0))), 2),
                    "node_memory_mb": round(float(v.get("node_memory_mb", v.get("system_memory_mb", 0.0))), 2),
                    "node_total_memory_mb": round(float(v.get("node_total_memory_mb", 65536.0)), 2),
                    "srm_action": str(v.get("srm_action", v.get("action", "Monitor"))),
                    "severity": str(obj.get("sev", v.get("severity", "INFO"))).upper(),
                    "notes": str(v.get("notes", v.get("message", "")))[:300],
                    "file_name": entry.file_name,
                    "line_number": line_no,
                })
                continue
            except (ValueError, TypeError):
                pass

        m = SRM_TEXT_REGEX.match(line_s)
        if m:
            gd = m.groupdict()
            msg = gd["message"]
            kvs = {k: (v1 if v1 != "" else v2) for k, v1, v2 in KV_EXTRACT_REGEX.findall(msg)}
            if not kvs and "cpu" not in msg.lower() and "memory" not in msg.lower():
                continue
            rows.append({
                "ts": normalize_timestamp(gd["ts"]),
                "worker_node": entry.worker_node,
                "process_name": kvs.get("process", kvs.get("service", "system")),
                "process_id": int(kvs.get("pid", 0)) if kvs.get("pid", "0").isdigit() else 0,
                "cpu_pct": round(float(kvs.get("cpu_pct", kvs.get("cpu", 0.0))), 2),
                "memory_mb": round(float(kvs.get("memory_mb", kvs.get("mem_mb", 0.0))), 2),
                "memory_limit_mb": round(float(kvs.get("limit_mb", 16384.0)), 2),
                "node_cpu_pct": round(float(kvs.get("system_cpu_pct", kvs.get("node_cpu_pct", 0.0))), 2),
                "node_memory_mb": round(float(kvs.get("system_memory_mb", kvs.get("node_memory_mb", 0.0))), 2),
                "node_total_memory_mb": round(float(kvs.get("total_memory_mb", 65536.0)), 2),
                "srm_action": kvs.get("action", "Monitor"),
                "severity": gd["severity"].upper(),
                "notes": kvs.get("notes", msg[:250]),
                "file_name": entry.file_name,
                "line_number": line_no,
            })
    return rows
