#!/usr/bin/env python3
"""Build dashboard JSON from classified order CSV files."""

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
COMPLETE_CSV = ROOT / "orders_complete_both_received.csv"
PARTIAL_CSV = ROOT / "orders_partial_one_received.csv"
OUT_JSON = ROOT / "dashboard" / "dashboard_data.json"


def load_rows(path: Path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def normalize_row(row):
    paperwork = row.get("paperwork_received", "").strip().lower() == "yes"
    product = row.get("product_received", "").strip().lower() == "yes"
    order_type = "complete" if paperwork and product else "partial"

    partial_type = ""
    if order_type == "partial":
        if paperwork and not product:
            partial_type = "paperwork_only"
        elif product and not paperwork:
            partial_type = "product_only"

    return {
        "order_key": row.get("order_key", "").strip(),
        "prefix": row.get("prefix", "").strip(),
        "ref_number": row.get("ref_number", "").strip(),
        "paperwork_received": paperwork,
        "product_received": product,
        "users_seen": row.get("users_seen", "").strip(),
        "stages_seen": row.get("stages_seen", "").strip(),
        "latest_added_time": row.get("latest_added_time", "").strip(),
        "rows_for_order": int(row.get("rows_for_order", "0") or "0"),
        "order_type": order_type,
        "partial_type": partial_type,
    }


def main():
    complete_rows = [normalize_row(r) for r in load_rows(COMPLETE_CSV)]
    partial_rows = [normalize_row(r) for r in load_rows(PARTIAL_CSV)]
    orders = complete_rows + partial_rows

    summary = {
        "total_orders_in_view": len(orders),
        "complete_both": len(complete_rows),
        "partial_one": len(partial_rows),
        "paperwork_only": sum(1 for r in partial_rows if r["partial_type"] == "paperwork_only"),
        "product_only": sum(1 for r in partial_rows if r["partial_type"] == "product_only"),
    }

    payload = {
        "summary": summary,
        "orders": orders,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with OUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"Wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
