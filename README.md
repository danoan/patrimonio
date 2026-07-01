# Patrimônio

A private household wealth tracker for two people, built to replace a shared Google Sheet with a proper auditable ledger. FastAPI + SQLModel on the backend, server-rendered Jinja2 + HTMX on the front — no SPA, no JS build step.

## What it does

- **Accounts & ledger** — every account balance is derived from `opening + Σ inflows − Σ outflows`, never stored. Accounts marked with recorded valuations (e.g. an assurance-vie wrapper) use the latest manual valuation instead, with cost basis and unrealized gain computed against the ledger.
- **Recurring rules** — recurring income/expenses post automatically each period; edits apply to future posts only, skips are one-month-only, and installment plans auto-stop.
- **Dashboard / Overview** — net worth by tier (`Imediato`, `Diferido`, `Alocado`) and a net-worth history chart.
- **Couple split** — splits this period's fixed costs between two people proportionally to net income, using the PAS (prélèvement à la source) withholding model.
- **EUR stocks** — weighted-average-cost position tracking with realized gain and PFU reserve computed per sell.
- **USD equity events** — vesting and sale events with withholding, FX conversion to EUR, and net proceeds tracking.
- **Projection** — forward projection of net worth.
- **IR (income tax estimate)** — annual income tax estimate from gross income and marginal brackets.
- **Settings** — accounts, persons, PFU rate, and other configuration.

## Stack

- Python 3.12, FastAPI + Uvicorn
- SQLModel (SQLAlchemy + Pydantic) over SQLite (WAL mode), migrations via Alembic
- Jinja2 + HTMX for server-rendered, partial-swap UI
- `pyright` in strict mode, `ruff` for lint/format, `pytest` + `pytest-cov`

### Architecture

```
routers/  →  services/  →  models/ + db
templates/  (no logic)        ↑
                           schemas/ (at router boundary)
```

- `app/services/` — pure functions, no HTTP or template concerns
- `app/routers/` — HTTP + Jinja2 rendering only, no domain logic
- `app/templates/` — no Python logic; formatting via Jinja2 filters (`| eur`, `| usd`)
- `app/money.py` — `Money` dataclass; amounts are `INTEGER` cents in the DB and `Decimal` in Python, never `float`

## Getting started

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# apply migrations
alembic upgrade head

# run the dev server
uvicorn app.main:app --reload
```

The app serves at `http://127.0.0.1:8000`. The UI defaults to Portuguese, with an English toggle in the sidebar (cookie-based).

## Checks

```bash
ruff check . && ruff format --check . && pytest   # what must pass before committing
tox                                                 # authoritative gate, same as CI
```

Tests are split by marker: `unit` (pure service tests, no DB) and `integration` (routers + DB via `TestClient`). Coverage floor is 85%; current coverage is ~92% across 366 tests.

## Documentation

- [`docs/alembic.md`](docs/alembic.md) — Alembic migration workflows

## Conventions

- Money is never a float — cents as `INTEGER` in the DB, `Decimal` via the `Money` dataclass.
- Tier values are exactly `"Imediato"`, `"Diferido"`, `"Alocado"`.
- Periods use `"YYYY-MM"` format; `day_of_month` is capped at 28.
- Currencies are `"EUR"` (default) or `"USD"`, with no implicit cross-currency arithmetic.
- All user-facing strings go through the `t()` i18n helper (`app/i18n/pt.json`, `app/i18n/en.json`) — templates never contain literal text.
