#!/usr/bin/env python3
"""
PharmaLink Connector - the middleman that sits inside the pharmacy.

Most Lebanese pharmacies run a local Windows POS with no API. Asking them to migrate is how
onboarding dies. Instead this agent runs on their counter PC, watches whatever their software
can already produce (a CSV/Excel export, a SQLite read, or a read-only SQL Server query -
e.g. against SoftPharm, the dominant Lebanese pharmacy POS), and pushes deltas to PharmaLink.
Nothing about their workflow changes.

  - stdlib only, so it runs on a bare Python install with no pip access
  - stores a local snapshot and only sends what changed
  - signs every request (HMAC-SHA256) so no session or password is stored
  - idempotency keys + retry with backoff, because counter PCs lose their connection
  - pulls incoming platform orders and writes them to a file the pharmacist already watches

Usage:
    python pharmalink_connector.py --config connector.config.json
    python pharmalink_connector.py --config connector.config.json --once
    python pharmalink_connector.py --config connector.config.json --check
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import json
import logging
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

LOG = logging.getLogger("pharmalink.connector")
DEFAULT_STATE_FILE = "connector.state.json"
MAX_ATTEMPTS = 5


# --------------------------------------------------------------------------------------
# Config and state
# --------------------------------------------------------------------------------------
def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        config = json.load(handle)
    for required in ("api_base_url", "key_id", "secret", "source"):
        if not config.get(required):
            raise SystemExit(f"Config is missing '{required}'. See connector.config.example.json.")
    # An env var beats the file, so the secret never has to sit on disk in a shared folder.
    config["secret"] = os.environ.get("PHARMALINK_SECRET", config["secret"])
    return config


def load_state(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"stock_snapshot": {}, "last_sync": None}


def save_state(path: str, state: dict) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)
    os.replace(tmp, path)  # atomic: a power cut mid-write cannot corrupt the snapshot


# --------------------------------------------------------------------------------------
# Signed transport
# --------------------------------------------------------------------------------------
def sign_request(*, secret: str, method: str, path: str, body: bytes) -> dict:
    timestamp = str(int(time.time()))
    nonce = uuid.uuid4().hex
    canonical = "\n".join([method.upper(), path, timestamp, nonce, hashlib.sha256(body or b"").hexdigest()])
    signature = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "X-PharmaLink-Timestamp": timestamp,
        "X-PharmaLink-Nonce": nonce,
        "X-PharmaLink-Signature": signature,
    }


def call(config: dict, method: str, endpoint: str, payload: dict | None = None) -> dict:
    """One signed call, with backoff on transient failures. 4xx is not retried: it will not fix itself."""
    base = config["api_base_url"].rstrip("/")
    url = f"{base}{endpoint}"
    # The signature covers the path only, so query strings stay out of the canonical string.
    path = urllib.parse.urlsplit(url).path
    body = json.dumps(payload).encode("utf-8") if payload is not None else b""

    for attempt in range(1, MAX_ATTEMPTS + 1):
        headers = {"Content-Type": "application/json", "X-PharmaLink-Key": config["key_id"]}
        headers.update(sign_request(secret=config["secret"], method=method, path=path, body=body))
        request = urllib.request.Request(url, data=body or None, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(request, timeout=config.get("timeout_seconds", 30)) as response:
                return json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")
            if 400 <= error.code < 500:
                raise SystemExit(f"{method} {endpoint} rejected ({error.code}): {detail}")
            LOG.warning("Server error %s on attempt %s: %s", error.code, attempt, detail[:200])
        except (urllib.error.URLError, TimeoutError) as error:
            LOG.warning("Network problem on attempt %s: %s", attempt, error)
        if attempt < MAX_ATTEMPTS:
            time.sleep(min(60, 2**attempt))
    raise SystemExit(f"{method} {endpoint} failed after {MAX_ATTEMPTS} attempts.")


# --------------------------------------------------------------------------------------
# Readers: whatever the pharmacy's software can already produce
# --------------------------------------------------------------------------------------
def read_csv_source(source: dict) -> list[dict]:
    path = Path(source["path"])
    if not path.exists():
        raise SystemExit(f"Export file not found: {path}")
    columns = source.get("columns", {})
    rows = []
    with path.open("r", encoding=source.get("encoding", "utf-8-sig"), newline="") as handle:
        for raw in csv.DictReader(handle, delimiter=source.get("delimiter", ",")):
            normalised = {key.strip().lower(): (value or "").strip() for key, value in raw.items() if key}
            code = normalised.get(columns.get("external_code", "code").lower(), "")
            if not code:
                continue
            rows.append(
                {
                    "external_code": code,
                    "name": normalised.get(columns.get("name", "name").lower(), ""),
                    "quantity": _as_int(normalised.get(columns.get("quantity", "quantity").lower())),
                    "selling_price": _as_float(normalised.get(columns.get("selling_price", "price").lower())),
                    "purchase_cost": _as_float(normalised.get(columns.get("purchase_cost", "cost").lower())),
                    "expiry_date": normalised.get(columns.get("expiry_date", "expiry").lower()) or None,
                    "supplier_name": normalised.get(columns.get("supplier_name", "supplier").lower(), ""),
                }
            )
    return rows


def read_sqlite_source(source: dict) -> list[dict]:
    """For POS products that keep a local SQLite/Access-exported DB. Read-only, never written to."""
    path = Path(source["path"])
    if not path.exists():
        raise SystemExit(f"Database not found: {path}")
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        connection.row_factory = sqlite3.Row
        rows = []
        for record in connection.execute(source["query"]):
            data = {key.lower(): record[key] for key in record.keys()}
            if not data.get("external_code"):
                continue
            rows.append(
                {
                    "external_code": str(data["external_code"]).strip(),
                    "name": str(data.get("name") or "").strip(),
                    "quantity": _as_int(data.get("quantity")),
                    "selling_price": _as_float(data.get("selling_price")),
                    "purchase_cost": _as_float(data.get("purchase_cost")),
                    "expiry_date": data.get("expiry_date") or None,
                    "supplier_name": str(data.get("supplier_name") or ""),
                }
            )
        return rows
    finally:
        connection.close()


def read_mssql_source(source: dict) -> list[dict]:
    """
    For POS products backed by SQL Server (e.g. SoftPharm), read via a read-only account.
    Not stdlib: needs `pyodbc` + the "ODBC Driver 17/18 for SQL Server" installed on the
    counter PC. The connector otherwise avoids third-party deps on purpose, but there is
    no stdlib path into SQL Server, so this import is deferred and only required if a
    pharmacy actually configures an mssql source.
    """
    try:
        import pyodbc  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "This pharmacy's source is type 'mssql', which needs the 'pyodbc' package "
            "and a SQL Server ODBC driver installed. Run: pip install pyodbc"
        ) from exc

    driver = source.get("driver", "ODBC Driver 17 for SQL Server")
    parts = [f"DRIVER={{{driver}}}", f"SERVER={source['server']}", f"DATABASE={source['database']}"]
    if source.get("trusted_connection", True) and "username" not in source:
        parts.append("Trusted_Connection=yes")
    else:
        # A dedicated read-only SQL login, never the pharmacy's own POS credentials.
        password = os.environ.get("PHARMALINK_SQL_PASSWORD", source.get("password", ""))
        parts.append(f"UID={source['username']};PWD={password}")
    parts.append("Encrypt=yes")
    if source.get("trust_server_certificate", True):
        parts.append("TrustServerCertificate=yes")
    connection_string = ";".join(parts)

    connection = pyodbc.connect(connection_string, timeout=source.get("connect_timeout_seconds", 15))
    try:
        connection.autocommit = False  # belt-and-braces: this connector never issues writes
        cursor = connection.cursor()
        cursor.execute(source["query"])
        columns = [column[0].lower() for column in cursor.description]
        rows = []
        for record in cursor.fetchall():
            data = dict(zip(columns, record))
            if not data.get("external_code"):
                continue
            expiry = data.get("expiry_date")
            rows.append(
                {
                    "external_code": str(data["external_code"]).strip(),
                    "name": str(data.get("name") or "").strip(),
                    "quantity": _as_int(data.get("quantity")),
                    "selling_price": _as_float(data.get("selling_price")),
                    "purchase_cost": _as_float(data.get("purchase_cost")),
                    "expiry_date": expiry.isoformat() if hasattr(expiry, "isoformat") else (expiry or None),
                    "supplier_name": str(data.get("supplier_name") or ""),
                }
            )
        return rows
    finally:
        connection.close()


def read_source(source: dict) -> list[dict]:
    kind = source.get("type", "csv")
    if kind == "csv":
        return read_csv_source(source)
    if kind == "sqlite":
        return read_sqlite_source(source)
    if kind == "mssql":
        return read_mssql_source(source)
    raise SystemExit(f"Unsupported source type '{kind}'. Use 'csv', 'sqlite', or 'mssql'.")


def _as_int(value) -> int:
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return 0


def _as_float(value):
    try:
        return round(float(str(value).replace(",", "")), 2)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------------------
# Delta computation
# --------------------------------------------------------------------------------------
def row_fingerprint(row: dict) -> str:
    material = json.dumps({key: row.get(key) for key in ("quantity", "selling_price", "purchase_cost", "expiry_date")}, sort_keys=True)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def compute_delta(rows: list[dict], snapshot: dict, *, full: bool = False) -> tuple[list[dict], dict]:
    """
    Only rows whose quantity or price actually moved are sent. A 4000-line pharmacy
    typically changes 30-80 lines a day, so this turns a heavy sync into a tiny one.
    """
    changed = []
    new_snapshot = {}
    for row in rows:
        digest = row_fingerprint(row)
        new_snapshot[row["external_code"]] = digest
        if full or snapshot.get(row["external_code"]) != digest:
            changed.append(row)
    # Items the POS no longer lists are pushed to zero rather than left stale online.
    for code in snapshot:
        if code not in new_snapshot:
            changed.append({"external_code": code, "quantity": 0, "name": ""})
    return changed, new_snapshot


# --------------------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------------------
def do_check(config: dict) -> int:
    result = call(config, "GET", "/api/integration/v1/ping/")
    LOG.info("Connected as %s (pharmacy: %s)", result.get("key"), result.get("pharmacy"))
    LOG.info("Granted scopes: %s", ", ".join(result.get("scopes", [])))
    rows = read_source(config["source"])
    LOG.info("Read %s row(s) from %s source at %s", len(rows), config["source"].get("type"), config["source"].get("path"))
    unnamed = sum(1 for row in rows if not row.get("name"))
    if unnamed:
        LOG.warning("%s row(s) have no product name; auto-matching will be weaker for those.", unnamed)
    return 0


def do_sync(config: dict, state_path: str, *, full: bool = False) -> int:
    state = load_state(state_path)
    rows = read_source(config["source"])
    changed, snapshot = compute_delta(rows, state.get("stock_snapshot", {}), full=full)

    if not changed:
        LOG.info("Nothing changed since the last sync (%s rows checked).", len(rows))
    else:
        chunk_size = config.get("chunk_size", 500)
        applied = unmapped = failed = 0
        for start in range(0, len(changed), chunk_size):
            chunk = changed[start : start + chunk_size]
            # Idempotency key is derived from the content, so a retry of the same chunk is a no-op.
            key = hashlib.sha256(json.dumps(chunk, sort_keys=True).encode("utf-8")).hexdigest()[:40]
            result = call(config, "POST", "/api/integration/v1/stock/sync/", {"idempotency_key": key, "rows": chunk})
            applied += result.get("rows_applied", 0)
            unmapped += result.get("rows_unmapped", 0)
            failed += result.get("rows_failed", 0)
            LOG.info("Chunk %s-%s: %s applied, %s unmapped, %s failed (%s)", start + 1, start + len(chunk), result.get("rows_applied"), result.get("rows_unmapped"), result.get("rows_failed"), result.get("status"))
        LOG.info("Stock sync done: %s applied, %s unmapped, %s failed.", applied, unmapped, failed)
        if unmapped:
            LOG.warning("%s product code(s) still need a one-time mapping in the PharmaLink pharmacy workspace.", unmapped)
        state["stock_snapshot"] = snapshot

    orders = call(config, "GET", "/api/integration/v1/orders/?open=true")
    if orders:
        LOG.info("%s open platform order(s) waiting.", len(orders))
        _write_orders_file(config, orders)
    state["last_sync"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    save_state(state_path, state)
    return 0


def _write_orders_file(config: dict, orders: list) -> None:
    """
    Drops incoming orders into a plain CSV in a folder the pharmacist already looks at.
    Deliberately low-tech: it works even when nobody at the counter opens a browser.
    """
    target = config.get("orders_out_file")
    if not target:
        return
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["order", "status", "customer", "area", "scheduled_for", "handover_code", "item", "quantity"])
        for order in orders:
            for line in order.get("lines", []):
                writer.writerow(
                    [
                        order.get("order_reference", ""),
                        order.get("status", ""),
                        order.get("contact_name", ""),
                        order.get("order_area", ""),
                        order.get("scheduled_for", "") or "ASAP",
                        order.get("handover_code", ""),
                        (line.get("medicine_detail") or {}).get("display_name", ""),
                        line.get("quantity", ""),
                    ]
                )
    LOG.info("Wrote %s open order(s) to %s", len(orders), path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PharmaLink pharmacy connector")
    parser.add_argument("--config", default="connector.config.json")
    parser.add_argument("--state", default=DEFAULT_STATE_FILE)
    parser.add_argument("--once", action="store_true", help="Run a single sync and exit (use with Task Scheduler/cron).")
    parser.add_argument("--full", action="store_true", help="Ignore the local snapshot and push every row.")
    parser.add_argument("--check", action="store_true", help="Verify credentials and the export file, change nothing.")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
    )
    config = load_config(args.config)

    if args.check:
        return do_check(config)
    if args.once or args.full:
        return do_sync(config, args.state, full=args.full)

    interval = config.get("interval_seconds", 300)
    LOG.info("Connector running. Syncing every %s seconds. Ctrl+C to stop.", interval)
    while True:
        try:
            do_sync(config, args.state)
        except SystemExit as exc:
            LOG.error("Sync aborted: %s", exc)
        except Exception:  # noqa: BLE001 - a daemon must survive a bad export file
            LOG.exception("Unexpected error; will retry next cycle.")
        time.sleep(interval)


if __name__ == "__main__":
    sys.exit(main())
