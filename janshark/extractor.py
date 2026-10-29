"""
JanShark Extractor & Log File Classifier
Mirrors Tableau Logshark's TableauLogsExtractor and KnownLogLocations for Server logs.
Supports .zip archives (including nested worker zips) and unzipped directories.
"""

import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional, Tuple


@dataclass
class LogFileEntry:
    """Metadata and content stream handle for a discovered Tableau Server log file."""
    plugin_domain: str        # 'apache', 'backgrounder', 'vizql', 'hyper', 'srm'
    worker_node: str          # e.g. 'node1', 'node2', 'worker1'
    service_instance: str     # e.g. 'vizqlserver_0-0', 'backgrounder_0-1', 'httpd'
    file_name: str            # e.g. 'access.2026_10_28_00_00_00.log', 'nativeapi_vizqlserver_1-0.txt'
    relative_path: str        # full path inside archive/folder
    content_lines: list[str]  # decoded log lines


# Node extraction pattern: matches node1, node2, worker0, worker1, localhost, etc.
NODE_PATTERN = re.compile(r"(?:^|/)(node\d+|worker\d+|localhost)(?:/|$)", re.IGNORECASE)

# Service instance pattern: e.g. vizqlserver_1-0, backgrounder_0-1, hyper_0, srm_0
INSTANCE_PATTERN = re.compile(
    r"(vizqlserver[_-]\d+(?:[_-]\d+)?|backgrounder[_-]\d+(?:[_-]\d+)?|hyper[_-]?\d*|srm[_-]?\d*|httpd|apache)",
    re.IGNORECASE,
)


def classify_server_log(rel_path: str) -> Optional[str]:
    """
    Classify a file path from a Tableau Server ziplogs archive into one of the target domains:
    - 'apache': Apache/HTTPD access and error logs
    - 'backgrounder': Backgrounder native Java logs and JSON logs
    - 'vizql': VizQL Server native JSON logs (including ART telemetry) and C++/Java logs
    - 'hyper': Hyper data engine JSON logs
    - 'srm': Server Resource Manager (SRM) & Resource Monitor telemetry logs
    Excludes Desktop logs, Vizportal, ClusterController, TabadminController, etc.
    """
    norm = rel_path.replace("\\", "/").lower()
    fname = os.path.basename(norm)

    # Skip non-log files, binary dumps, crash dumps, directories
    if not fname or fname.endswith((".dmp", ".zip", ".gz", ".tar", ".png", ".twb", ".twbx", ".hyper")):
        return None

    # 1. Apache / HTTPD Gateway logs
    if "/httpd/" in norm or "/apache/" in norm or fname.startswith("access.") or fname.startswith("error."):
        if fname.startswith(("access", "error")) or "httpd" in norm:
            return "apache"

    # 2. Backgrounder logs
    if "/backgrounder/" in norm or fname.startswith("backgrounder") or "nativeapi_backgrounder" in fname:
        return "backgrounder"

    # 3. VizQL Server & ART (Activity Resource Tracing) logs
    if "/vizqlserver/" in norm or "vizqlserver" in fname or fname.startswith("tabprotosrv"):
        return "vizql"

    # 4. Hyper Data Engine logs
    if "/hyper/" in norm or fname.startswith("hyperd") or "hyper" in fname:
        return "hyper"

    # 5. Server Resource Manager (SRM) / ResourceManager logs
    if (
        "/srm/" in norm
        or "/resourcemanager/" in norm
        or "srm" in fname
        or "resourcemanager" in fname
        or "resource_manager" in fname
    ):
        return "srm"

    return None


def extract_node_and_instance(rel_path: str, default_domain: str) -> Tuple[str, str]:
    """Extract the worker node ID and service instance name from a log file's relative path."""
    norm = rel_path.replace("\\", "/")

    node_match = NODE_PATTERN.search(norm)
    worker_node = node_match.group(1).lower() if node_match else "node1"

    inst_match = INSTANCE_PATTERN.search(norm)
    service_instance = inst_match.group(1).lower() if inst_match else default_domain

    return worker_node, service_instance


def iter_log_files(source_path: str | Path) -> Iterator[LogFileEntry]:
    """
    Iterate over all relevant Tableau Server log files in a .zip archive or directory.
    Supports nested .zip archives inside the main ziplogs bundle.
    """
    path = Path(source_path)
    if not path.exists():
        raise FileNotFoundError(f"Log source not found: {source_path}")

    if path.is_file() and zipfile.is_zipfile(path):
        yield from _iter_from_zip(path)
    elif path.is_dir():
        yield from _iter_from_dir(path)
    else:
        raise ValueError(f"Unsupported log source (must be a .zip file or directory): {source_path}")


def _iter_from_zip(zip_path: Path, parent_prefix: str = "") -> Iterator[LogFileEntry]:
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            rel_path = f"{parent_prefix}/{info.filename}".lstrip("/")

            # Handle nested worker zip archives if present
            if info.filename.lower().endswith(".zip"):
                import io
                nested_bytes = io.BytesIO(zf.read(info.filename))
                if zipfile.is_zipfile(nested_bytes):
                    nested_prefix = rel_path[:-4]
                    with zipfile.ZipFile(nested_bytes, "r") as nested_zf:
                        for ninfo in nested_zf.infolist():
                            if ninfo.is_dir():
                                continue
                            nrel = f"{nested_prefix}/{ninfo.filename}".lstrip("/")
                            domain = classify_server_log(nrel)
                            if domain:
                                raw = nested_zf.read(ninfo.filename)
                                lines = raw.decode("utf-8", errors="replace").splitlines()
                                node, inst = extract_node_and_instance(nrel, domain)
                                yield LogFileEntry(
                                    plugin_domain=domain,
                                    worker_node=node,
                                    service_instance=inst,
                                    file_name=os.path.basename(ninfo.filename),
                                    relative_path=nrel,
                                    content_lines=lines,
                                )
                continue

            domain = classify_server_log(rel_path)
            if domain:
                raw = zf.read(info.filename)
                lines = raw.decode("utf-8", errors="replace").splitlines()
                node, inst = extract_node_and_instance(rel_path, domain)
                yield LogFileEntry(
                    plugin_domain=domain,
                    worker_node=node,
                    service_instance=inst,
                    file_name=os.path.basename(info.filename),
                    relative_path=rel_path,
                    content_lines=lines,
                )


def _iter_from_dir(root_dir: Path) -> Iterator[LogFileEntry]:
    for dirpath, _, filenames in os.walk(root_dir):
        for fname in filenames:
            full_path = Path(dirpath) / fname
            rel_path = str(full_path.relative_to(root_dir)).replace("\\", "/")
            if fname.lower().endswith(".zip") and zipfile.is_zipfile(full_path):
                yield from _iter_from_zip(full_path, parent_prefix=rel_path[:-4])
                continue

            domain = classify_server_log(rel_path)
            if domain:
                try:
                    lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()
                except OSError:
                    continue
                node, inst = extract_node_and_instance(rel_path, domain)
                yield LogFileEntry(
                    plugin_domain=domain,
                    worker_node=node,
                    service_instance=inst,
                    file_name=fname,
                    relative_path=rel_path,
                    content_lines=lines,
                )

