# Patrimônio

Private household wealth tracker for two people. FastAPI + SQLModel + HTMX, deployed on a personal server.

## Dev commands

```bash
# Bootstrap (first time)
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run
uvicorn app.main:app --reload

# Check (all three must pass before committing)
ruff check . && ruff format --check . && pytest

# Authoritative gate (same as CI)
tox
```

## Architecture

```
routers/  →  services/  →  models/ + db
templates/  (no logic)        ↑
                           schemas/ (at router boundary)
```

- **`services/`** — pure functions that take data and return data. No HTTP, no templates.
- **`routers/`** — HTTP + Jinja2 only. No domain logic.
- **`templates/`** — no Python logic; use Jinja2 filters for formatting.

## Design decisions

**Money is never a float.** DB stores `INTEGER` cents. Python uses `Decimal`. The `Money` dataclass in `app/money.py` wraps this. Format at the edge with `| eur` / `| usd` / `| pct` Jinja2 filters.

**The ledger is the source of truth — except for accounts with recorded valuations.**
```
balance(account) = opening_cents + Σ inflows − Σ outflows
```
Balances, tier totals, and grand total are always computed — never stored (except the optional `networth_snapshot` cache). **Exception:** if an account has any `AccountValuation` row (a manually recorded monthly mark-to-market balance — for wrappers like assurance-vie whose value moves with the market, not with ledger flows), `balance()` returns the latest one instead. `app/services/valuations.py` also derives, per account: `net_contributed_cents` (the ledger-only formula above, i.e. cost basis) and `unrealized_gain_cents` (latest valuation − cost basis), plus a per-period `valuation_history` that nets out that period's ledger contributions from the raw balance delta to isolate market-driven gain/loss.

**Recurring rules:**
- `edit_rule` changes the amount for *future* posts only — already-posted events are immutable.
- `skip_rule` affects one month only and does not carry forward.
- Installment rules auto-stop when `posted_count == installments`.

**Stock positions** use weighted average cost (not FIFO). Realized gain and PFU reserve are computed and stored on the sell row for auditability.

**USD equity events** (vesting/sale): `withholding = gross − net`; `euro_net = net_usd × fx`. FX rate stored per event.

**Couple split:** `Person` tracks `gross_cents` (informational) separately from `net_before_taxes_cents` (net imposable — after social contributions, before income tax). The `prélèvement à la source` (PAS) withholding applies to `net_before_taxes_cents`, not gross: `IR = net_before_taxes_cents × ir_rate`. Net income = `net_before_taxes_cents − IR`. Each person's proportion = `net_income_i / Σ net_income`. Each person contributes the same percentage of their net income toward this period's fixed costs; what's left over is their inferred personal spending money (`app/services/division.py`). "Fixed costs" = this period's posted `Txn` rows carrying the fixed-expense tag configured on the Settings page (a `Setting` row, key `fixed_expense_tag`, picked from tags in use on recurring rules — `post_rule` copies a rule's `tags` onto the `Txn` it posts). If no tag is configured, fixed costs are 0.

**Annual IR estimate** (`app/services/ir.py`): `annual_gross = gross_cents × 12`. Taxable income is estimated as `net_before_taxes_avg_cents × 12` (the person's 12-month average net-before-taxes, a separate manually maintained field from the current-month `net_before_taxes_cents` used for the PAS split above). `deduction = annual_gross − taxable` is a derived display figure only (an estimate of professional expenses already netted out on the payslip), not an input to the bracket calc. `compute_ir_for_income` (the standalone marginal-bracket calculator, used independently of `Person`) still applies the flat 10 % professional abattement to whatever gross figure it's given.

## Testing

Two layers separated by pytest markers:

- `@pytest.mark.unit` — pure service tests, no DB fixture (uses in-memory SQLite). One module per service under `tests/unit/`.
- `@pytest.mark.integration` — routers + DB via FastAPI `TestClient`. Under `tests/integration/`.

Coverage floor is 85%. Services should approach 100%; routers are lighter.

## Documentation

Project docs live in `docs/`. Current guides:

- [`docs/alembic.md`](docs/alembic.md) — Alembic workflows (initialization, migrations, rollback)

When working on a feature, if a workflow, tool, or non-obvious process seems worth documenting, ask the user whether to add a guide before writing it.

Note: the one-off spreadsheet-migration pipeline (`scripts/` — CSV readers and `ingest.py`) has been removed from the working tree; it did its job seeding the ledger from the original Google Sheet and isn't part of the running app.

## Conventions

- **Language:** UI supports Portuguese (default) and English via a cookie-based toggle in the sidebar. Every user-facing string is a dotted key resolved through the `t()` Jinja global (`app/templates_env.py`), backed by `app/i18n/pt.json` and `app/i18n/en.json` — templates never contain literal text. Code (identifiers, comments, commit messages) stays English.
- **Tier values:** exactly `"Imediato"`, `"Diferido"`, `"Alocado"` — no aliases.
- **Period format:** `"YYYY-MM"` (e.g. `"2024-01"`). `day_of_month` capped at 28.
- **Currency:** `"EUR"` (default) or `"USD"`. No cross-currency arithmetic without explicit FX.
- Full type hints everywhere. `pyright` strict mode — a PR that doesn't type-check doesn't merge.
- No `print` — use stdlib `logging`.
