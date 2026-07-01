from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, col, func, select

from app.models.tables import Account, Txn, TxnNote
from app.schemas.forms import TxnCreate


def create_txn(data: TxnCreate, session: Session) -> Txn:
    if data.from_account is not None and session.get(Account, data.from_account) is None:
        raise ValueError(f"from_account {data.from_account} not found")
    if data.to_account is not None and session.get(Account, data.to_account) is None:
        raise ValueError(f"to_account {data.to_account} not found")

    txn = Txn(
        date=data.date,
        from_account=data.from_account,
        to_account=data.to_account,
        amount_cents=data.amount_cents,
        category=data.category,
        comment=data.comment,
        tags=data.tags,
        needs_resolution=int(data.needs_resolution),
        created_at=datetime.now(UTC).isoformat(),
    )
    session.add(txn)
    session.commit()
    session.refresh(txn)
    return txn


@dataclass
class StatementRow:
    txn: Txn
    running_balance: int
    direction: str  # 'in' | 'out'


def account_statement(account_id: int, session: Session) -> list[StatementRow]:
    """Return txns for account ordered by date ASC with running balance."""
    account = session.get(Account, account_id)
    if account is None:
        raise ValueError(f"Account {account_id} not found")

    txns = session.exec(
        select(Txn)
        .where((Txn.from_account == account_id) | (Txn.to_account == account_id))
        .order_by(col(Txn.date), col(Txn.id))  # type: ignore[arg-type]
    ).all()

    running = account.opening_cents
    rows: list[StatementRow] = []
    for txn in txns:
        if txn.to_account == account_id:
            running += txn.amount_cents
            direction = "in"
        else:
            running -= txn.amount_cents
            direction = "out"
        rows.append(StatementRow(txn=txn, running_balance=running, direction=direction))
    return rows


_EDITABLE_FIELDS = {"date", "category", "comment", "tags", "amount_cents"}


def update_txn_field(txn_id: int, field: str, raw_value: str, session: Session) -> Txn:
    if field not in _EDITABLE_FIELDS:
        raise ValueError(f"field '{field}' is not editable")
    txn = session.get(Txn, txn_id)
    if txn is None:
        raise ValueError(f"Txn {txn_id} not found")

    if field == "date":
        if not raw_value:
            raise ValueError("date is required")
        txn.date = raw_value
    elif field == "category":
        txn.category = raw_value or None
    elif field == "comment":
        txn.comment = raw_value or None
    elif field == "tags":
        txn.tags = raw_value or None
    elif field == "amount_cents":
        try:
            amount_cents = int(float(raw_value.replace(",", ".")) * 100)
        except ValueError as exc:
            raise ValueError("invalid amount") from exc
        if amount_cents <= 0:
            raise ValueError("amount must be positive")
        txn.amount_cents = amount_cents

    session.add(txn)
    session.commit()
    session.refresh(txn)
    return txn


def delete_txn(txn_id: int, session: Session) -> None:
    txn = session.get(Txn, txn_id)
    if txn is None:
        raise ValueError(f"Txn {txn_id} not found")
    for dependent in session.exec(select(Txn).where(Txn.resolved_txn_id == txn_id)).all():
        dependent.resolved_txn_id = None
        session.add(dependent)
    for note in session.exec(select(TxnNote).where(TxnNote.txn_id == txn_id)).all():
        session.delete(note)
    session.delete(txn)
    session.commit()


def is_resolved(txn: Txn) -> bool:
    return txn.resolved_txn_id is not None or bool(txn.resolution_note)


def list_txn_notes(txn_id: int, session: Session) -> list[TxnNote]:
    stmt = (
        select(TxnNote)
        .where(TxnNote.txn_id == txn_id)
        .order_by(col(TxnNote.created_at).desc(), col(TxnNote.id).desc())  # type: ignore[arg-type]
    )
    return list(session.exec(stmt).all())


def add_txn_note(txn_id: int, text: str, session: Session) -> TxnNote:
    if session.get(Txn, txn_id) is None:
        raise ValueError(f"Txn {txn_id} not found")
    text = text.strip()
    if not text:
        raise ValueError("note text is required")
    note = TxnNote(txn_id=txn_id, text=text, created_at=datetime.now(UTC).isoformat())
    session.add(note)
    session.commit()
    session.refresh(note)
    return note


def delete_txn_note(note_id: int, session: Session) -> None:
    note = session.get(TxnNote, note_id)
    if note is None:
        raise ValueError(f"TxnNote {note_id} not found")
    session.delete(note)
    session.commit()


def txn_note_counts(session: Session, txn_ids: list[int]) -> dict[int, int]:
    if not txn_ids:
        return {}
    stmt = (
        select(TxnNote.txn_id, func.count())
        .where(col(TxnNote.txn_id).in_(txn_ids))
        .group_by(col(TxnNote.txn_id))
    )
    return dict(session.exec(stmt).all())  # type: ignore[arg-type]


def note_counts_for_txns(txns: list[Txn], session: Session) -> dict[int, int]:
    return txn_note_counts(session, [t.id for t in txns if t.id is not None])


def _pending_filter() -> ColumnElement[bool]:
    return (
        (col(Txn.needs_resolution) == 1)
        & col(Txn.resolved_txn_id).is_(None)
        & (col(Txn.resolution_note).is_(None) | (col(Txn.resolution_note) == ""))
    )


def list_pending_txns(session: Session) -> list[Txn]:
    """Return every txn flagged for tracking that hasn't been resolved yet."""
    stmt = (
        select(Txn).where(_pending_filter()).order_by(col(Txn.date).desc(), col(Txn.id).desc())  # type: ignore[arg-type]
    )
    return list(session.exec(stmt).all())


def set_needs_resolution(txn_id: int, needs_resolution: bool, session: Session) -> Txn:
    txn = session.get(Txn, txn_id)
    if txn is None:
        raise ValueError(f"Txn {txn_id} not found")
    txn.needs_resolution = int(needs_resolution)
    session.add(txn)
    session.commit()
    session.refresh(txn)
    return txn


def resolve_txn(
    txn_id: int,
    session: Session,
    resolved_txn_id: int | None = None,
    resolution_note: str | None = None,
) -> Txn:
    txn = session.get(Txn, txn_id)
    if txn is None:
        raise ValueError(f"Txn {txn_id} not found")

    resolution_note = resolution_note or None
    if resolved_txn_id is None and resolution_note is None:
        raise ValueError("at least one of resolved_txn_id or resolution_note must be set")
    if resolved_txn_id is not None:
        if resolved_txn_id == txn_id:
            raise ValueError("a transaction cannot be its own pair")
        if session.get(Txn, resolved_txn_id) is None:
            raise ValueError(f"Txn {resolved_txn_id} not found")

    txn.resolved_txn_id = resolved_txn_id
    txn.resolution_note = resolution_note
    session.add(txn)
    session.commit()
    session.refresh(txn)
    return txn


def unresolve_txn(txn_id: int, session: Session) -> Txn:
    txn = session.get(Txn, txn_id)
    if txn is None:
        raise ValueError(f"Txn {txn_id} not found")
    txn.resolved_txn_id = None
    txn.resolution_note = None
    session.add(txn)
    session.commit()
    session.refresh(txn)
    return txn


def search_txns(query: str, exclude_id: int, session: Session, limit: int = 20) -> list[Txn]:
    stmt = select(Txn).where(col(Txn.id) != exclude_id)
    if query:
        like = f"%{query}%"
        stmt = stmt.where(
            col(Txn.comment).like(like) | col(Txn.category).like(like) | col(Txn.date).like(like)
        )
    stmt = stmt.order_by(col(Txn.date).desc(), col(Txn.id).desc()).limit(limit)  # type: ignore[arg-type]
    return list(session.exec(stmt).all())


def recent_txns(session: Session, limit: int = 50) -> list[Txn]:
    return list(
        session.exec(
            select(Txn).order_by(col(Txn.date).desc(), col(Txn.id).desc()).limit(limit)  # type: ignore[arg-type]
        ).all()
    )


@dataclass
class TxnPage:
    txns: list[Txn]
    page: int
    page_size: int
    total: int
    total_pages: int


def list_txns(
    session: Session,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> TxnPage:
    """Return a page of non-pending txns filtered by an optional [date_from, date_to] range.

    Pending txns (flagged for tracking, not yet resolved) are excluded — they're
    listed separately via `list_pending_txns` and shown in their own table.
    """
    filters = [~_pending_filter()]
    if date_from:
        filters.append(col(Txn.date) >= date_from)
    if date_to:
        filters.append(col(Txn.date) <= date_to)

    count_stmt = select(func.count()).select_from(Txn)
    for f in filters:
        count_stmt = count_stmt.where(f)
    total = session.exec(count_stmt).one()
    total_pages = max(1, -(-total // page_size))  # ceil division
    page = min(max(page, 1), total_pages)

    stmt = select(Txn)
    for f in filters:
        stmt = stmt.where(f)
    stmt = stmt.order_by(col(Txn.date).desc(), col(Txn.id).desc())  # type: ignore[arg-type]
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    txns = list(session.exec(stmt).all())

    return TxnPage(txns=txns, page=page, page_size=page_size, total=total, total_pages=total_pages)
