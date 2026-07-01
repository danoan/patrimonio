# Alembic — dev guide

Alembic is the database migration tool for this project. It tracks schema changes as versioned Python scripts so that every change can be reviewed, applied incrementally, and rolled back.

## What it is

Alembic sits between SQLModel (which defines the schema in Python classes) and the live database. Instead of letting SQLModel recreate tables on startup, Alembic generates numbered *revision* files that each describe one schema change (`upgrade`) and how to undo it (`downgrade`). The database keeps a `alembic_version` table with the current revision ID so Alembic knows where it is.

## Project layout

```
alembic.ini           # connection string, script location
migrations/
  env.py              # imports our SQLModel metadata; Alembic calls this
  script.py.mako      # template for new revision files
  versions/           # one .py file per revision, in order
```

`migrations/env.py` imports all SQLModel table classes so their metadata is available when Alembic auto-generates diffs. **If you add a new table, import it there.**

## Initialization

Already done. If you ever need to recreate it from scratch:

```bash
alembic init migrations
```

Then edit `migrations/env.py` to point at `SQLModel.metadata` and read `settings.database_url` from `app/config.py` (see the existing file for the pattern).

## Common workflows

### Create the first revision from the current models

```bash
alembic revision --autogenerate -m "initial schema"
```

Alembic compares `SQLModel.metadata` against the live DB (empty at first) and writes a revision file under `migrations/versions/`. **Always review the generated file before applying** — autogenerate misses some things (e.g. `CHECK` constraints, index names).

### Apply all pending migrations

```bash
alembic upgrade head
```

Runs every revision that hasn't been applied yet, in order.

### Check current state

```bash
alembic current      # revision the DB is at
alembic history      # all revisions, newest first
alembic heads        # unreachable heads (should be just one)
```

### Roll back one step

```bash
alembic downgrade -1
```

### Roll back to a specific revision

```bash
alembic downgrade <revision_id>
```

Use `alembic history` to find the ID (first 12 chars are enough).

### Create a manual revision (for data migrations or complex DDL)

```bash
alembic revision -m "add sort_order default backfill"
```

Writes an empty revision; fill in `upgrade()` and `downgrade()` by hand.

## Rules for this project

1. **Every schema change is a revision.** Never call `SQLModel.metadata.create_all()` on a live DB (that's only for the test fixture). In production, `alembic upgrade head` is the only path.
2. **Review before applying.** Autogenerate is a starting point, not ground truth. Check for missing constraints or wrong column types before committing.
3. **One revision per logical change.** A migration that adds a table, renames a column, and seeds a row is three separate concerns — split it unless they must be atomic.
4. **Downgrade must work.** Write `downgrade()` properly; a migration that can't be reversed is a liability.
5. **Commit the revision file with the code change** that necessitated it — they should be in the same PR so reviewers see schema and code together.

## Batch mode on SQLite

SQLite can't `ALTER COLUMN` or `DROP COLUMN` directly — Alembic works around this with **batch mode**, which recreates the table under the hood (new table, copy rows, drop old, rename):

```python
def upgrade() -> None:
    with op.batch_alter_table("person") as batch_op:
        batch_op.add_column(sa.Column("ir_rate", sa.Float(), nullable=True))
    op.execute("UPDATE person SET ir_rate = ...")  # data backfill goes between the two batches
    with op.batch_alter_table("person") as batch_op:
        batch_op.alter_column("ir_rate", nullable=False)
        batch_op.drop_column("ir_cents")
```

Use `op.batch_alter_table(...)` (not plain `op.alter_column`/`op.drop_column`) whenever a revision changes a column's type/nullability or drops a column. See `migrations/versions/c2e5ec2655b5_person_ir_rate_replaces_ir_cents_and_.py` for a full example, including a data backfill sandwiched between the "add" and "finalize" batches.

## Running in tests

Tests use `SQLModel.metadata.create_all()` on a fresh in-memory SQLite database (see `tests/conftest.py`). Alembic is not involved — the test schema is always in sync with the models. This means: if a migration and the model diverge, tests still pass but the live DB breaks. Keep them in sync.
