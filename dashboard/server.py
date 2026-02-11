#!/usr/bin/env python3
"""Serve dashboard and ingest live Zoho Form webhook events."""

from __future__ import annotations

import csv
import json
import os
import threading
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = ROOT / "dashboard"
BOOTSTRAP_CSV = ROOT / "PKTracker_Report (2)_filled.csv"
EVENTS_FILE = DASHBOARD_DIR / "live_events.jsonl"


def _split_csv_env(name: str, default: str) -> list[str]:
    return [x.strip() for x in os.getenv(name, default).split(",") if x.strip()]


CFG = {
    "host": os.getenv("DASHBOARD_HOST", "127.0.0.1"),
    "port": int(os.getenv("DASHBOARD_PORT", "8000")),
    "webhook_secret": os.getenv("ZP_WEBHOOK_SECRET", "").strip(),
    "prefix_keys": _split_csv_env("ZP_PREFIX_KEYS", "Prefix,prefix"),
    "ref_keys": _split_csv_env("ZP_REF_KEYS", "Ref Number,Reference Number,Ref_Number,ref_number"),
    "stage_keys": _split_csv_env("ZP_STAGE_KEYS", "Stage,stage,Status,status"),
    "user_keys": _split_csv_env("ZP_USER_KEYS", "USER,User,user"),
    "time_keys": _split_csv_env("ZP_TIME_KEYS", "Added Time,added_time,Submitted Time,Submission Time"),
}


LOCK = threading.Lock()


@dataclass
class Entry:
    prefix: str
    ref_number: str
    stage: str
    user: str
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
        v = lowered.get(key.lower())
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def normalize_payload(payload: dict[str, Any]) -> Entry:
    flat = flatten(payload)
    prefix = first_value(flat, CFG["prefix_keys"])
    ref_number = first_value(flat, CFG["ref_keys"])
    stage = first_value(flat, CFG["stage_keys"])
    user = first_value(flat, CFG["user_keys"])
    added_time = first_value(flat, CFG["time_keys"])
    return Entry(prefix=prefix, ref_number=ref_number, stage=stage, user=user, added_time=added_time, raw=payload)


def load_bootstrap_entries() -> list[Entry]:
    if not BOOTSTRAP_CSV.exists():
        return []
    entries: list[Entry] = []
    with BOOTSTRAP_CSV.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            prefix = (row.get("Reference Numbers") or "").strip()
            ref_number = (row.get("") or "").strip()
            if not ref_number:
                continue
            entries.append(
                Entry(
                    prefix=prefix,
                    ref_number=ref_number,
                    stage=(row.get("Stage") or "").strip(),
                    user=(row.get("USER") or "").strip(),
                    added_time=(row.get("Added Time") or "").strip(),
                    raw=row,
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
            entries.append(normalize_payload(payload))
    return entries


def append_live_event(payload: dict[str, Any]) -> None:
    EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "received_at": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }
    with EVENTS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def classify(entries: list[Entry]) -> dict[str, Any]:
    orders = defaultdict(
        lambda: {
            "prefix": "",
            "ref_number": "",
            "paperwork_received": False,
            "product_received": False,
            "users_seen": set(),
            "stages_seen": set(),
            "latest_added_time": "",
            "rows_for_order": 0,
        }
    )

    for e in entries:
        if not e.ref_number:
            continue
        order_key = f"{e.prefix}-{e.ref_number}" if e.prefix else e.ref_number
        o = orders[order_key]
        o["prefix"] = e.prefix
        o["ref_number"] = e.ref_number
        if e.user:
            o["users_seen"].add(e.user)
        if e.stage:
            o["stages_seen"].add(e.stage)
            s = e.stage.strip().lower()
            if s == "paperwork received":
                o["paperwork_received"] = True
            if s == "product received":
                o["product_received"] = True
        if e.added_time:
            o["latest_added_time"] = e.added_time
        o["rows_for_order"] += 1

    rows: list[dict[str, Any]] = []
    for order_key, o in orders.items():
        partial_type = ""
        if not (o["paperwork_received"] and o["product_received"]):
            if o["paperwork_received"] and not o["product_received"]:
                partial_type = "paperwork_only"
            elif o["product_received"] and not o["paperwork_received"]:
                partial_type = "product_only"
        order_type = "complete" if (o["paperwork_received"] and o["product_received"]) else "partial_or_other"
        if partial_type:
            order_type = "partial"
        elif order_type == "partial_or_other":
            continue

        rows.append(
            {
                "order_key": order_key,
                "prefix": o["prefix"],
                "ref_number": o["ref_number"],
                "paperwork_received": o["paperwork_received"],
                "product_received": o["product_received"],
                "users_seen": "; ".join(sorted(o["users_seen"])),
                "stages_seen": "; ".join(sorted(o["stages_seen"])),
                "latest_added_time": o["latest_added_time"],
                "rows_for_order": o["rows_for_order"],
                "order_type": order_type,
                "partial_type": partial_type,
            }
        )

    rows.sort(key=lambda x: (x["prefix"], x["ref_number"]))

    summary = {
        "total_orders_in_view": len(rows),
        "complete_both": sum(1 for r in rows if r["order_type"] == "complete"),
        "partial_one": sum(1 for r in rows if r["order_type"] == "partial"),
        "paperwork_only": sum(1 for r in rows if r["partial_type"] == "paperwork_only"),
        "product_only": sum(1 for r in rows if r["partial_type"] == "product_only"),
    }
    return {"summary": summary, "orders": rows}


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
        if parsed.path == "/api/health":
            self._write_json(HTTPStatus.OK, {"ok": True, "time": datetime.utcnow().isoformat()})
            return
        if parsed.path == "/api/orders":
            with LOCK:
                data = classify(load_bootstrap_entries() + load_live_entries())
            self._write_json(HTTPStatus.OK, data)
            return
        return super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/zoho/webhook":
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
            data = classify(load_bootstrap_entries() + load_live_entries())

        self._write_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "received_ref_number": normalize_payload(payload).ref_number,
                "summary": data["summary"],
            },
        )


def main() -> None:
    server = ThreadingHTTPServer((CFG["host"], CFG["port"]), Handler)
    print(f"Serving dashboard on http://{CFG['host']}:{CFG['port']}/dashboard/index.html")
    print("Webhook endpoint:", f"http://{CFG['host']}:{CFG['port']}/api/zoho/webhook")
    if CFG["webhook_secret"]:
        print("Webhook secret enabled.")
    server.serve_forever()


if __name__ == "__main__":
    main()
