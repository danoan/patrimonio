from collections.abc import Generator

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def set_wal(dbapi_conn: object, _: object) -> None:
    import sqlite3

    if isinstance(dbapi_conn, sqlite3.Connection):
        dbapi_conn.execute("PRAGMA journal_mode=WAL")


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
