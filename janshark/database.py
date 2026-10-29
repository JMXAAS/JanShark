"""
JanShark DuckDB Storage & Parquet Export Engine
Replaces Logshark's MongoDB + PostgreSQL + Hyper pipeline with a single fast DuckDB database.
Also supports exporting tables to Parquet / JSON bundles for instant browser-based DuckDB-WASM querying.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .extractor import iter_log_files
from .parsers import (
    parse_apache_file,
    parse_backgrounder_file,
    parse_hyper_file,
    parse_srm_file,
    parse_vizql_file,
)


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS run_metadata (
    run_id VARCHAR,
    source_path VARCHAR,
    processed_at TIMESTAMP,
    files_parsed INTEGER,
    total_events INTEGER,
    worker_nodes VARCHAR
);

CREATE TABLE IF NOT EXISTS apache_requests (
    ts TIMESTAMP,
    worker_node VARCHAR,
    service_instance VARCHAR,
    client_ip VARCHAR,
    requester VARCHAR,
    method VARCHAR,
    uri VARCHAR,
    endpoint_category VARCHAR,
    site VARCHAR,
    workbook VARCHAR,
    view_name VARCHAR,
    status_code INTEGER,
    status_class VARCHAR,
    response_bytes BIGINT,
    request_time_ms DOUBLE,
    request_id VARCHAR,
    file_name VARCHAR,
    line_number INTEGER
);

CREATE TABLE IF NOT EXISTS backgrounder_jobs (
    job_id BIGINT,
    worker_node VARCHAR,
    backgrounder_instance VARCHAR,
    site VARCHAR,
    job_type VARCHAR,
    target_name VARCHAR,
    priority INTEGER,
    queued_ts TIMESTAMP,
    start_ts TIMESTAMP,
    end_ts TIMESTAMP,
    queue_wait_sec DOUBLE,
    run_time_sec DOUBLE,
    total_time_sec DOUBLE,
    status VARCHAR,
    error_message VARCHAR,
    args VARCHAR,
    file_name VARCHAR
);

CREATE TABLE IF NOT EXISTS backgrounder_events (
    ts TIMESTAMP,
    worker_node VARCHAR,
    backgrounder_instance VARCHAR,
    severity VARCHAR,
    job_id BIGINT,
    job_type VARCHAR,
    component VARCHAR,
    message VARCHAR,
    file_name VARCHAR,
    line_number INTEGER
);

CREATE TABLE IF NOT EXISTS vizql_events (
    ts TIMESTAMP,
    worker_node VARCHAR,
    vizql_instance VARCHAR,
    process_id INTEGER,
    thread_id VARCHAR,
    severity VARCHAR,
    session_id VARCHAR,
    request_id VARCHAR,
    site VARCHAR,
    username VARCHAR,
    workbook VARCHAR,
    view_name VARCHAR,
    event_key VARCHAR,
    elapsed_ms DOUBLE,
    rows_returned BIGINT,
    is_cache_hit BOOLEAN,
    query_text VARCHAR,
    message VARCHAR,
    file_name VARCHAR,
    line_number INTEGER
);

CREATE TABLE IF NOT EXISTS art_events (
    ts TIMESTAMP,
    worker_node VARCHAR,
    vizql_instance VARCHAR,
    session_id VARCHAR,
    request_id VARCHAR,
    site VARCHAR,
    username VARCHAR,
    workbook VARCHAR,
    view_name VARCHAR,
    activity_name VARCHAR,
    activity_type VARCHAR,
    depth INTEGER,
    activity_id VARCHAR,
    sponsor_id VARCHAR,
    elapsed_ms DOUBLE,
    cpu_inclusive_ms DOUBLE,
    cpu_exclusive_ms DOUBLE,
    alloc_inclusive_mb DOUBLE,
    alloc_exclusive_mb DOUBLE,
    file_name VARCHAR,
    line_number INTEGER
);

CREATE TABLE IF NOT EXISTS hyper_events (
    ts TIMESTAMP,
    worker_node VARCHAR,
    hyper_instance VARCHAR,
    severity VARCHAR,
    request_id VARCHAR,
    session_id VARCHAR,
    event_key VARCHAR,
    database_path VARCHAR,
    elapsed_ms DOUBLE,
    cpu_time_ms DOUBLE,
    rows_affected BIGINT,
    peak_memory_mb DOUBLE,
    spooled_to_disk BOOLEAN,
    query_text VARCHAR,
    error_message VARCHAR,
    file_name VARCHAR,
    line_number INTEGER
);

CREATE TABLE IF NOT EXISTS srm_metrics (
    ts TIMESTAMP,
    worker_node VARCHAR,
    process_name VARCHAR,
    process_id INTEGER,
    cpu_pct DOUBLE,
    memory_mb DOUBLE,
    memory_limit_mb DOUBLE,
    node_cpu_pct DOUBLE,
    node_memory_mb DOUBLE,
    node_total_memory_mb DOUBLE,
    srm_action VARCHAR,
    severity VARCHAR,
    notes VARCHAR,
    file_name VARCHAR,
    line_number INTEGER
);
"""


def parse_logs_to_bundle(
    source_path: str | Path,
    run_id: Optional[str] = None,
    plugins: Optional[list[str]] = None,
) -> dict[str, Any]:
    """
    Parse a Tableau Server ziplogs archive or folder into structured table lists.
    """
    active_plugins = {p.lower() for p in plugins} if plugins else {"apache", "backgrounder", "vizql", "art", "hyper", "srm"}
    if "art" in active_plugins:
        active_plugins.add("vizql")

    apache_rows: list[dict[str, Any]] = []
    bg_jobs: list[dict[str, Any]] = []
    bg_events: list[dict[str, Any]] = []
    vizql_rows: list[dict[str, Any]] = []
    art_rows: list[dict[str, Any]] = []
    hyper_rows: list[dict[str, Any]] = []
    srm_rows: list[dict[str, Any]] = []
    nodes_seen: set[str] = set()
    files_parsed = 0

    for entry in iter_log_files(source_path):
        if entry.plugin_domain not in active_plugins:
            continue
        files_parsed += 1
        nodes_seen.add(entry.worker_node)

        if entry.plugin_domain == "apache":
            apache_rows.extend(parse_apache_file(entry))
        elif entry.plugin_domain == "backgrounder":
            jobs, evs = parse_backgrounder_file(entry)
            bg_jobs.extend(jobs)
            bg_events.extend(evs)
        elif entry.plugin_domain == "vizql":
            vevs, aevs = parse_vizql_file(entry)
            vizql_rows.extend(vevs)
            art_rows.extend(aevs)
        elif entry.plugin_domain == "hyper":
            hyper_rows.extend(parse_hyper_file(entry))
        elif entry.plugin_domain == "srm":
            srm_rows.extend(parse_srm_file(entry))

    total_events = (
        len(apache_rows)
        + len(bg_jobs)
        + len(bg_events)
        + len(vizql_rows)
        + len(art_rows)
        + len(hyper_rows)
        + len(srm_rows)
    )

    resolved_run_id = run_id or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    metadata = {
        "run_id": resolved_run_id,
        "source_path": str(source_path),
        "processed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "files_parsed": files_parsed,
        "total_events": total_events,
        "worker_nodes": ", ".join(sorted(nodes_seen)) if nodes_seen else "node1",
    }

    return {
        "run_metadata": [metadata],
        "apache_requests": apache_rows,
        "backgrounder_jobs": bg_jobs,
        "backgrounder_events": bg_events,
        "vizql_events": vizql_rows,
        "art_events": art_rows,
        "hyper_events": hyper_rows,
        "srm_metrics": srm_rows,
    }


def write_duckdb_database(
    bundle: dict[str, list[dict[str, Any]]],
    db_path: str | Path,
    export_parquet_dir: Optional[str | Path] = None,
) -> Path:
    """
    Write the parsed log bundle into a `.duckdb` database file (and optionally `.parquet` files).
    Uses the `duckdb` Python package.
    """
    import duckdb

    db_file = Path(db_path)
    if db_file.exists():
        db_file.unlink()
    db_file.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(db_file))
    try:
        con.execute(SCHEMA_SQL)

        for table_name, rows in bundle.items():
            if not rows:
                continue
            cols = list(rows[0].keys())
            placeholders = ", ".join(["?"] * len(cols))
            col_list = ", ".join(cols)
            values = [tuple(r[c] for c in cols) for r in rows]
            con.executemany(
                f"INSERT INTO {table_name} ({col_list}) VALUES ({placeholders})",
                values,
            )

        if export_parquet_dir:
            pdir = Path(export_parquet_dir)
            pdir.mkdir(parents=True, exist_ok=True)
            for table_name in bundle.keys():
                parquet_file = pdir / f"{table_name}.parquet"
                con.execute(f"COPY {table_name} TO '{parquet_file.as_posix()}' (FORMAT PARQUET)")
    finally:
        con.close()

    return db_file

