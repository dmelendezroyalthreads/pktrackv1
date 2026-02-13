#!/usr/bin/env python3
"""Serve barcode dashboard and ingest live Zoho Form webhook events."""

from __future__ import annotations

import csv
import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP_CSV = Path(os.getenv("ZB_BOOTSTRAP_CSV", str(ROOT / "BARCODEDELIVERYTRACKING_Report.csv")))
EVENTS_FILE = ROOT / "barcode_dashboard" / "live_events.jsonl"


def _split_csv_env(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    if "|" in raw:
        parts = raw.split("|")
    else:
        parts = raw.split(",")
    return [x.strip() for x in parts if x.strip()]


CFG = {
    "host": os.getenv("DASHBOARD_HOST", "0.0.0.0"),
    "port": int(os.getenv("PORT", os.getenv("DASHBOARD_PORT", "8000"))),
    "webhook_secret": os.getenv("ZB_WEBHOOK_SECRET", "").strip(),
    "order_keys": _split_csv_env(
        "ZB_ORDER_KEYS", "ORDER, PICK OR PO. NUMBER|Order|Pick|PO Number|INFORMATION|Information"
    ),
    "dropped_by_keys": _split_csv_env("ZB_DROPPED_BY_KEYS", "Dropped off by:,Dropped off by,Dropped By"),
    "datetime_keys": _split_csv_env("ZB_DATETIME_KEYS", "Date-Time*,Date-Time,Date Time"),
    "added_time_keys": _split_csv_env("ZB_ADDED_TIME_KEYS", "Added Time,added_time,Submitted Time"),
}

LOCK = threading.Lock()


@dataclass
class Entry:
    order_value: str
    dropped_off_by: str
    date_time: str
    added_time: str
    raw: dict[str, Any]


def flatten(data: Any, prefix: str = "", out: dict[str, str] | None = None) -> dict[str, str]:
    if out is None:
        out = {}
    if isinstance(data, dict):
        for key, value in data.items():
            key_s = str(key)
            p = f"{prefix}.{key_s}" if prefix else key_s
            flatten(value, p, out)
            if not isinstance(value, (dict, list)):
                out[key_s] = str(value)
    elif isinstance(data, list):
        for idx, value in enumerate(data):
            p = f"{prefix}[{idx}]"
            flatten(value, p, out)
    else:
        out[prefix] = str(data)
    return out


def first_value(flat: dict[str, str], keys: list[str]) -> str:
    lowered = {k.lower(): v for k, v in flat.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _find_column_index(header: list[str], keys: list[str]) -> int:
    lookup = {c.strip().lower(): i for i, c in enumerate(header) if c.strip()}
    for key in keys:
        idx = lookup.get(key.lower())
        if idx is not None:
            return idx
    return -1


def _cell(row: list[str], idx: int) -> str:
    if idx < 0 or idx >= len(row):
        return ""
    return (row[idx] or "").strip()


def _split_order_values(raw: str) -> list[str]:
    if not raw:
        return []
    normalized = raw.replace("\r", "\n")
    for sep in [",", ";", "\n"]:
        normalized = normalized.replace(sep, "\n")
    items = [x.strip() for x in normalized.split("\n") if x.strip()]
    return items


def load_bootstrap_entries() -> list[Entry]:
    if not BOOTSTRAP_CSV.exists():
        return []

    with BOOTSTRAP_CSV.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    if not rows:
        return []

    header_row = [c.strip() for c in rows[0]]
    second_row = [c.strip() for c in rows[1]] if len(rows) > 1 else []

    order_idx = _find_column_index(second_row, CFG["order_keys"])
    date_time_idx = _find_column_index(header_row, CFG["datetime_keys"])
    dropped_by_idx = _find_column_index(header_row, CFG["dropped_by_keys"])
    added_time_idx = _find_column_index(header_row, CFG["added_time_keys"])

    data_start = 2 if second_row else 1

    entries: list[Entry] = []
    previous_order = ""
    previous_dropped_by = ""
    previous_date_time = ""
    previous_added_time = ""

    for row in rows[data_start:]:
        if not any(c.strip() for c in row):
            continue

        order_value = _cell(row, order_idx)
        dropped_by = _cell(row, dropped_by_idx)
        date_time = _cell(row, date_time_idx)
        added_time = _cell(row, added_time_idx)

        # Business rule: blank columns inherit from previous row.
        if not order_value:
            order_value = previous_order
        if not dropped_by:
            dropped_by = previous_dropped_by
        if not date_time:
            date_time = previous_date_time
        if not added_time:
            added_time = previous_added_time

        if order_value:
            previous_order = order_value
        if dropped_by:
            previous_dropped_by = dropped_by
        if date_time:
            previous_date_time = date_time
        if added_time:
            previous_added_time = added_time

        for item in _split_order_values(order_value):
            entries.append(
                Entry(
                    order_value=item,
                    dropped_off_by=dropped_by,
                    date_time=date_time,
                    added_time=added_time,
                    raw={
                        "order_value": item,
                        "dropped_off_by": dropped_by,
                        "date_time": date_time,
                        "added_time": added_time,
                    },
                )
            )

    return entries


def parse_live_entries_from_payload(payload: dict[str, Any]) -> list[Entry]:
    flat = flatten(payload)
    order_raw = first_value(flat, CFG["order_keys"])
    dropped_by = first_value(flat, CFG["dropped_by_keys"])
    date_time = first_value(flat, CFG["datetime_keys"])
    added_time = first_value(flat, CFG["added_time_keys"])

    entries: list[Entry] = []
    for item in _split_order_values(order_raw):
        entries.append(
            Entry(
                order_value=item,
                dropped_off_by=dropped_by,
                date_time=date_time,
                added_time=added_time,
                raw=payload,
            )
        )
    return entries


def load_live_entries() -> list[Entry]:
    if not EVENTS_FILE.exists():
        return []

    entries: list[Entry] = []
    with EVENTS_FILE.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            payload = item.get("payload", {})
            entries.extend(parse_live_entries_from_payload(payload))
    return entries


def append_live_event(payload: dict[str, Any]) -> None:
    EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    event = {"received_at": datetime.now(timezone.utc).isoformat(), "payload": payload}
    with EVENTS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def last_live_event_received_at() -> str:
    if not EVENTS_FILE.exists():
        return ""

    last = ""
    with EVENTS_FILE.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                last = line

    if not last:
        return ""

    try:
        item = json.loads(last)
    except json.JSONDecodeError:
        return ""
    return str(item.get("received_at") or "")


def build_data(entries: list[Entry]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for idx, entry in enumerate(entries, start=1):
        if not entry.order_value:
            continue
        rows.append(
            {
                "id": idx,
                "order_value": entry.order_value,
                "dropped_off_by": entry.dropped_off_by,
                "date_time": entry.date_time,
                "added_time": entry.added_time,
            }
        )

    rows.sort(key=lambda x: (x["order_value"], x["added_time"]))

    return {
        "summary": {
            "total_records": len(rows),
            "unique_orders": len({r["order_value"] for r in rows}),
        },
        "records": rows,
        "meta": {
            "last_live_event_at": last_live_event_received_at(),
            "bootstrap_csv": str(BOOTSTRAP_CSV),
        },
    }


def parse_post_body(handler: SimpleHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    body = handler.rfile.read(length) if length > 0 else b""
    ctype = (handler.headers.get("Content-Type") or "").lower()

    if "application/json" in ctype:
        if not body:
            return {}
        data = json.loads(body.decode("utf-8"))
        if isinstance(data, dict):
            return data
        return {"items": data}

    if "application/x-www-form-urlencoded" in ctype:
        parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
        return {k: (v[0] if len(v) == 1 else v) for k, v in parsed.items()}

    return {"raw_body": body.decode("utf-8", errors="replace")}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        b = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _auth_ok(self) -> bool:
        expected = CFG["webhook_secret"]
        if not expected:
            return True
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        q_secret = (qs.get("secret") or [""])[0]
        h_secret = self.headers.get("X-Zoho-Webhook-Secret", "")
        bearer = self.headers.get("Authorization", "")
        return expected in (q_secret, h_secret, bearer.replace("Bearer ", ""))

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/barcode/health":
            self._write_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "time": datetime.utcnow().isoformat(),
                    "last_live_event_at": last_live_event_received_at(),
                },
            )
            return

        if parsed.path == "/api/barcode/records":
            with LOCK:
                data = build_data(load_bootstrap_entries() + load_live_entries())
            self._write_json(HTTPStatus.OK, data)
            return

        return super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/barcode/webhook":
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        if not self._auth_ok():
            self._write_json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return

        try:
            payload = parse_post_body(self)
        except Exception as exc:  # pragma: no cover
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_payload", "detail": str(exc)})
            return

        with LOCK:
            append_live_event(payload)
            parsed_entries = parse_live_entries_from_payload(payload)

        self._write_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "received_records": len(parsed_entries),
                "last_live_event_at": last_live_event_received_at(),
            },
        )


def main() -> None:
    server = ThreadingHTTPServer((CFG["host"], CFG["port"]), Handler)
    print(f"Serving barcode dashboard on http://{CFG['host']}:{CFG['port']}/barcode_dashboard/index.html")
    print("Webhook endpoint:", f"http://{CFG['host']}:{CFG['port']}/api/barcode/webhook")
    if CFG["webhook_secret"]:
        print("Webhook secret enabled.")
    server.serve_forever()


if __name__ == "__main__":
    main()
