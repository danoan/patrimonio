"""Bring the database schema up to date on container start.

The recorded baseline Alembic revision is a no-op (it was generated against a dev
database that already had tables from SQLModel's `create_all`), so `alembic upgrade
head` alone fails against a genuinely fresh, empty database — the first real schema
migration tries to ALTER tables that were never created. On a fresh database we build
the current schema directly via `create_db_and_tables()` (the same call `app.main`'s
lifespan already makes on every startup) and stamp it as up to date; on a database
that's already tracked by Alembic, we just apply any pending migrations as usual.
"""

from alembic import command
from alembic.config import Config
from app.db import create_db_and_tables, engine
from sqlalchemy import inspect


def main() -> None:
    cfg = Config("alembic.ini")
    is_fresh = "alembic_version" not in inspect(engine).get_table_names()
    if is_fresh:
        create_db_and_tables()
        command.stamp(cfg, "head")
    else:
        command.upgrade(cfg, "head")


if __name__ == "__main__":
    main()
