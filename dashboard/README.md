# Order Dashboard

This dashboard shows:
- Orders with both `Paperwork Received` and `Product Received`
- Orders with only one of the two statuses

## Files
- `dashboard/index.html`: UI
- `dashboard/styles.css`: styles
- `dashboard/app.js`: filtering/table/detail logic
- `dashboard/build_dashboard_data.py`: converts CSV outputs to `dashboard/dashboard_data.json`
- `dashboard/server.py`: live server + Zoho webhook endpoint (`/api/zoho/webhook`)

## Regenerate data JSON

From the project root:

```bash
python3 dashboard/build_dashboard_data.py
```

## Run locally (static)

From the project root:

```bash
python3 -m http.server 8000
```

Then open:

`http://localhost:8000/dashboard/`

## Run live mode (Zoho webhook + dashboard API)

From the project root:

```bash
python3 dashboard/server.py
```

Then open:

`http://127.0.0.1:8000/dashboard/index.html`

Live API endpoints:
- `GET /api/orders`
- `POST /api/zoho/webhook`
- `GET /api/health`

### Optional webhook security

Set a secret before starting server:

```bash
export ZP_WEBHOOK_SECRET="replace-with-long-secret"
python3 dashboard/server.py
```

Then send Zoho webhook to:

`https://YOUR_PUBLIC_URL/api/zoho/webhook?secret=replace-with-long-secret`

## Zoho Forms webhook fields

Your webhook payload should include these labels (or equivalent):
- `Prefix`
- `Ref Number`
- `Stage`
- `USER`
- `Added Time` (optional)

`Stage` values used for reconciliation:
- `Paperwork Received`
- `Product Received`

If your field labels differ, map them via env vars before starting server:

```bash
export ZP_PREFIX_KEYS="Prefix,Order Prefix"
export ZP_REF_KEYS="Ref Number,Order Number"
export ZP_STAGE_KEYS="Stage,Current Stage"
export ZP_USER_KEYS="USER,Submitted By"
python3 dashboard/server.py
```

## Expected input CSVs

These must exist in project root:
- `orders_complete_both_received.csv`
- `orders_partial_one_received.csv`
