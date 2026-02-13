# Barcode Tracking Online

This dashboard is designed for Zoho Forms barcode delivery tracking data.

## What it does
- Loads initial records from CSV export (`BARCODEDELIVERYTRACKING_Report.csv`)
- Applies inheritance for blank CSV cells from the row above
- Receives live Zoho webhook events
- Lets users search by `ORDER`, `PICK` or `PO. NUMBER`

## Business rule
If a row has blank columns, each blank value inherits the value from the previous row.

## Endpoints
- `GET /api/barcode/records`
- `POST /api/barcode/webhook`
- `GET /api/barcode/health`

## Run locally
```bash
python3 barcode_dashboard/server.py
```

Open:
- `http://127.0.0.1:8000/barcode_dashboard/index.html`

## Environment variables
- `ZB_WEBHOOK_SECRET`: optional webhook secret
- `ZB_BOOTSTRAP_CSV`: bootstrap CSV path (default `BARCODEDELIVERYTRACKING_Report.csv`)
- `ZB_ORDER_KEYS`: alternate order field labels
- `ZB_DROPPED_BY_KEYS`: alternate dropped-by field labels
- `ZB_DATETIME_KEYS`: alternate datetime field labels
- `ZB_ADDED_TIME_KEYS`: alternate added-time field labels

## Zoho webhook URL
`https://YOUR_RENDER_URL/api/barcode/webhook?secret=YOUR_SECRET`

Use `POST` with JSON payload.

## Render deployment (new service)
Use a separate Render web service for this dashboard with:
- Build command: `echo "No build step required"`
- Start command: `python3 barcode_dashboard/server.py`

Set env vars in Render:
- `ZB_WEBHOOK_SECRET`
- `ZB_BOOTSTRAP_CSV=BARCODEDELIVERYTRACKING_Report.csv`
