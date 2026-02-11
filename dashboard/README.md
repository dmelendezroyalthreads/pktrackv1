# Order Dashboard

This dashboard shows order groups by `Prefix + Ref Number` in 3 categories:
- `Paperwork Only`
- `Product Only`
- `Both Received`

It supports:
- Initial bootstrap from a Zoho-export CSV file
- Live updates from Zoho Forms webhook posts
- A live sync status panel showing the latest webhook received time

## Business rule implemented

When processing CSV rows, if **both `USER` and `Stage` are blank** on a row, that row inherits `USER` and `Stage` from the previous row.

## Files
- `dashboard/index.html`: UI
- `dashboard/styles.css`: styles
- `dashboard/app.js`: filtering/table/detail logic
- `dashboard/server.py`: live server + Zoho webhook endpoint (`/api/zoho/webhook`)
- `dashboard/live_events.jsonl`: webhook event storage

## Local run

From the project root:

```bash
python3 dashboard/server.py
```

Open:

`http://127.0.0.1:8000/dashboard/index.html`

Live API endpoints:
- `GET /api/orders`
- `POST /api/zoho/webhook`
- `GET /api/health`

## Configure CSV source

Default bootstrap CSV:
- `PKTracker_Report (2)_filled.csv`

Set a different CSV path:

```bash
export ZP_BOOTSTRAP_CSV="/full/path/to/your_zoho_export.csv"
python3 dashboard/server.py
```

## Webhook security (recommended)

```bash
export ZP_WEBHOOK_SECRET="replace-with-long-secret"
python3 dashboard/server.py
```

Use webhook URL:

`https://YOUR_PUBLIC_URL/api/zoho/webhook?secret=replace-with-long-secret`

## Field mapping (if Zoho labels differ)

```bash
export ZP_PREFIX_KEYS="Prefix,Order Prefix"
export ZP_REF_KEYS="Ref Number,Order Number"
export ZP_STAGE_KEYS="Stage,Current Stage"
export ZP_USER_KEYS="USER,Submitted By"
export ZP_TIME_KEYS="Added Time,Submitted Time"
python3 dashboard/server.py
```

## Deploy online (Render example)

1. Push this project to GitHub.
2. In Render, create a new `Web Service` from that repo.
3. Set:
- Runtime: `Python 3`
- Build Command: *(leave empty)*
- Start Command: `python3 dashboard/server.py`
4. Add environment variables in Render:
- `ZP_WEBHOOK_SECRET`: your secret token
- `ZP_BOOTSTRAP_CSV`: `PKTracker_Report (2)_filled.csv` (or your uploaded CSV name)
5. Deploy.
6. In Zoho Forms webhook settings, set method `POST`, payload `JSON`, and URL:
- `https://<your-render-service>.onrender.com/api/zoho/webhook?secret=<same-secret>`

After this, your team can use:
- `https://<your-render-service>.onrender.com/dashboard/index.html`

## Notes for cloud hosting
- Server now defaults to `0.0.0.0` and uses `PORT` automatically when provided by platforms like Render.
- Webhook events are stored in `dashboard/live_events.jsonl`. If your host has ephemeral disk, use a persistent disk volume.
