# uTopia AIS prototype

Minimal working prototype of the billing / collections / electronic payments
core from the AIS proposal: one FastAPI service, one double-entry ledger
table, SQLite locally and Postgres on Render via `DATABASE_URL`.

## Run locally

```
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Docs at `http://localhost:8000/docs`.

## Deploy to Render

Push this repo to GitHub, then on Render: New > Blueprint, point it at the
repo (`render.yaml` is already set up), and add a Postgres database whose
connection string you paste into the `DATABASE_URL` env var it asks for.

## Endpoints, mapped to the proposal

| Area | Endpoint |
|---|---|
| Master data | `POST /owners`, `POST /properties` |
| Billing | `POST /billing/run?period=2026-11` (idempotent, one invoice per property per period) |
| Late fees | `POST /billing/late-fees?period=2026-11` (20%, only on invoices past due date, only once) |
| Billing outputs | `GET /invoices`, `GET /reports/aging` |
| Collections | `POST /payments` (FIFO allocation across open invoices; unmatched excess goes to an unapplied-cash account instead of being guessed) |
| Electronic payments | `POST /vendors`, `POST /vendor-invoices` (rejects a duplicate vendor+invoice-number pair with 409), `POST /vendor-payments` |
| Ledger | `GET /ledger/trial-balance` |

Every billing, payment, and disbursement action writes a balanced
debit/credit pair to `ledgerentry`, so the trial balance should always tie
out. That is the one control from the paper this prototype actually
enforces in code; the rest (maker-checker, role separation, MFA, callback
verification, etc.) are process controls layered on top in a real
deployment, not something a single-service prototype can demonstrate.

## What's deliberately left out

No auth, no roles, no portal, no mailing integration, no ADP feed. This is
the accounting core only, built to be extended, not the full system in the
proposal.
