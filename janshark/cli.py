"""
JanShark Command Line Interface
Re-engineers the `Logshark <LogSetLocation> <RunId> [Options]` CLI into a fast, zero-config Python CLI.

Usage Examples:
  # 1. Generate a realistic sample Tableau Server ziplogs archive, parse into DuckDB, and build static HTML dashboard:
  python -m janshark.cli --demo

  # 2. Analyze an existing Tableau Server logs.zip or unzipped log directory:
  python -m janshark.cli path/to/logs.zip --db janshark.duckdb --html dashboard.html

  # 3. Filter to specific Server plugins (just like Logshark --plugins "Apache;Backgrounder"):
  python -m janshark.cli path/to/logs.zip --plugins "apache;backgrounder;vizql;hyper;srm"
"""

import argparse
import json
import sys
import time
import webbrowser
from pathlib import Path

from .dashboard import build_static_dashboard
from .database import parse_logs_to_bundle, write_duckdb_database
from .generator import generate_sample_ziplogs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="janshark",
        description="JanShark — Reengineered Tableau Server Logshark powered by DuckDB & Static Web Analytics",
    )
    parser.add_argument(
        "source",
        nargs="?",
        default=None,
        help="Path to Tableau Server ziplogs archive (.zip) or unzipped logs directory",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Custom Run ID identifier (defaults to timestamped run ID)",
    )
    parser.add_argument(
        "--plugins",
        default="apache;backgrounder;vizql;art;hyper;srm",
        help="Semicolon-separated list of Server plugins to run (default: apache;backgrounder;vizql;art;hyper;srm)",
    )
    parser.add_argument(
        "--db",
        default="output/janshark.duckdb",
        help="Output DuckDB database file path (default: output/janshark.duckdb)",
    )
    parser.add_argument(
        "--parquet-dir",
        default=None,
        help="Optional directory to export Parquet files for each Logshark table",
    )
    parser.add_argument(
        "--html",
        default="output/dashboard.html",
        help="Output static HTML analytics dashboard path (default: output/dashboard.html)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Generate a synthetic Tableau Server `sample_logs.zip` archive and run full analysis",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Automatically open the generated static HTML dashboard in the default browser",
    )

    args = parser.parse_args(argv)

    t0 = time.perf_counter()

    if args.demo or not args.source:
        sample_zip = Path("output/sample_logs.zip")
        print(f"[JanShark] Generating synthetic multi-node Tableau Server log archive: {sample_zip} ...")
        generate_sample_ziplogs(sample_zip)
        source_path = sample_zip
    else:
        source_path = Path(args.source)

    plugin_list = [p.strip().lower() for p in args.plugins.replace(",", ";").split(";") if p.strip()]
    print(f"[JanShark] Parsing Tableau Server logs from: {source_path}")
    print(f"[JanShark] Active Server Plugins: {', '.join(plugin_list)}")

    bundle = parse_logs_to_bundle(source_path, run_id=args.run_id, plugins=plugin_list)
    meta = bundle["run_metadata"][0]

    print(f"[JanShark] Parsed {meta['files_parsed']} log files ({meta['total_events']} structured records across nodes: {meta['worker_nodes']})")
    for table_name, rows in bundle.items():
        if table_name != "run_metadata":
            print(f"  - {table_name:<22}: {len(rows):>6} rows")

    # 1. Write DuckDB database (if duckdb Python package is installed)
    try:
        db_file = write_duckdb_database(bundle, args.db, export_parquet_dir=args.parquet_dir)
        print(f"[JanShark] DuckDB database written to: {db_file.resolve()}")
    except ImportError:
        json_fallback = Path(args.db).with_suffix(".json")
        json_fallback.parent.mkdir(parents=True, exist_ok=True)
        json_fallback.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
        print(f"[JanShark] Note: `duckdb` Python package not installed in current env; saved JSON bundle to {json_fallback.resolve()}")
        print("           (Install via `pip install duckdb` to also emit native `.duckdb` & `.parquet` files)")

    # 2. Build self-contained Static HTML + DuckDB-WASM Dashboard
    html_file = build_static_dashboard(bundle, args.html)
    elapsed = time.perf_counter() - t0
    print(f"[JanShark] Static Web Dashboard ready at: {html_file.resolve()} (completed in {elapsed:.2f}s)")

    if args.open:
        webbrowser.open(html_file.resolve().as_uri())

    return 0


if __name__ == "__main__":
    sys.exit(main())

