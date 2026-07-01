import pytest
from app.models.tables import Account
from app.schemas.forms import TxnCreate
from app.services.ledger import (
    account_statement,
    add_txn_note,
    create_txn,
    delete_txn,
    delete_txn_note,
    is_resolved,
    list_pending_txns,
    list_txn_notes,
    list_txns,
    note_counts_for_txns,
    recent_txns,
    resolve_txn,
    search_txns,
    set_needs_resolution,
    txn_note_counts,
    unresolve_txn,
    update_txn_field,
)
from sqlmodel import Session


def _make_account(session: Session, code: str, opening: int = 0) -> Account:
    a = Account(
        code=code, name=code, tier="Imediato", opening_cents=opening, opening_date="2024-01-01"
    )
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


@pytest.mark.unit
def test_create_txn_inflow(session: Session) -> None:
    acc = _make_account(session, "L1")
    data = TxnCreate(date="2024-06-01", to_account=acc.id, amount_cents=5000)
    txn = create_txn(data, session)
    assert txn.id is not None
    assert txn.amount_cents == 5000
    assert txn.to_account == acc.id


@pytest.mark.unit
def test_create_txn_missing_account_raises(session: Session) -> None:
    data = TxnCreate(date="2024-06-01", to_account=9999, amount_cents=100)
    with pytest.raises(ValueError, match="not found"):
        create_txn(data, session)


@pytest.mark.unit
def test_account_statement_running_balance(session: Session) -> None:
    acc = _make_account(session, "L2", opening=10000)
    create_txn(TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=2000), session)
    create_txn(TxnCreate(date="2024-01-02", from_account=acc.id, amount_cents=500), session)

    rows = account_statement(acc.id, session)  # type: ignore[arg-type]
    assert len(rows) == 2
    # After inflow: 10000 + 2000 = 12000
    assert rows[0].running_balance == 12000
    assert rows[0].direction == "in"
    # After outflow: 12000 - 500 = 11500
    assert rows[1].running_balance == 11500
    assert rows[1].direction == "out"


@pytest.mark.unit
def test_account_statement_empty(session: Session) -> None:
    acc = _make_account(session, "L3", opening=5000)
    rows = account_statement(acc.id, session)  # type: ignore[arg-type]
    assert rows == []


@pytest.mark.unit
def test_account_statement_missing_account_raises(session: Session) -> None:
    with pytest.raises(ValueError, match="not found"):
        account_statement(9999, session)


@pytest.mark.unit
def test_recent_txns_order(session: Session) -> None:
    acc = _make_account(session, "L4")
    create_txn(TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100), session)
    create_txn(TxnCreate(date="2024-06-01", to_account=acc.id, amount_cents=200), session)
    create_txn(TxnCreate(date="2024-03-01", to_account=acc.id, amount_cents=300), session)

    txns = recent_txns(session, limit=10)
    dates = [t.date for t in txns]
    assert dates == sorted(dates, reverse=True)


@pytest.mark.unit
def test_list_txns_filters_by_date_range(session: Session) -> None:
    acc = _make_account(session, "L5")
    create_txn(TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100), session)
    create_txn(TxnCreate(date="2024-06-01", to_account=acc.id, amount_cents=200), session)
    create_txn(TxnCreate(date="2024-12-01", to_account=acc.id, amount_cents=300), session)

    result = list_txns(session, date_from="2024-02-01", date_to="2024-11-01")
    assert [t.date for t in result.txns] == ["2024-06-01"]
    assert result.total == 1
    assert result.total_pages == 1


@pytest.mark.unit
def test_list_txns_pagination(session: Session) -> None:
    acc = _make_account(session, "L6")
    for i in range(5):
        create_txn(
            TxnCreate(date=f"2024-01-0{i + 1}", to_account=acc.id, amount_cents=100), session
        )

    page1 = list_txns(session, page=1, page_size=2)
    assert len(page1.txns) == 2
    assert page1.total == 5
    assert page1.total_pages == 3
    assert page1.txns[0].date == "2024-01-05"

    page3 = list_txns(session, page=3, page_size=2)
    assert len(page3.txns) == 1
    assert page3.txns[0].date == "2024-01-01"


@pytest.mark.unit
def test_list_txns_page_out_of_range_clamps_to_last(session: Session) -> None:
    acc = _make_account(session, "L7")
    create_txn(TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100), session)

    result = list_txns(session, page=99, page_size=10)
    assert result.page == 1
    assert len(result.txns) == 1


@pytest.mark.unit
def test_list_txns_empty(session: Session) -> None:
    result = list_txns(session)
    assert result.txns == []
    assert result.total == 0
    assert result.total_pages == 1
    assert result.page == 1


@pytest.mark.unit
def test_list_txns_excludes_pending(session: Session) -> None:
    acc = _make_account(session, "L9")
    create_txn(TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100), session)
    pending = create_txn(
        TxnCreate(date="2024-01-02", to_account=acc.id, amount_cents=200, needs_resolution=True),
        session,
    )

    result = list_txns(session)
    assert pending.id not in [t.id for t in result.txns]
    assert result.total == 1


@pytest.mark.unit
def test_list_pending_txns_returns_unresolved_flagged_only(session: Session) -> None:
    acc = _make_account(session, "L10")
    regular = create_txn(TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100), session)
    pending = create_txn(
        TxnCreate(date="2024-01-02", to_account=acc.id, amount_cents=200, needs_resolution=True),
        session,
    )
    flagged_and_resolved = create_txn(
        TxnCreate(date="2024-01-03", to_account=acc.id, amount_cents=300, needs_resolution=True),
        session,
    )
    resolve_txn(flagged_and_resolved.id, session, resolution_note="done")  # type: ignore[arg-type]

    result = list_pending_txns(session)

    ids = [t.id for t in result]
    assert ids == [pending.id]
    assert regular.id not in ids
    assert flagged_and_resolved.id not in ids


@pytest.mark.unit
def test_list_pending_txns_order_by_date_desc(session: Session) -> None:
    acc = _make_account(session, "L11")
    older = create_txn(
        TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100, needs_resolution=True),
        session,
    )
    newer = create_txn(
        TxnCreate(date="2024-02-01", to_account=acc.id, amount_cents=100, needs_resolution=True),
        session,
    )

    result = list_pending_txns(session)
    assert [t.id for t in result] == [newer.id, older.id]


@pytest.mark.unit
def test_delete_txn_removes_it(session: Session) -> None:
    acc = _make_account(session, "L8", opening=10000)
    txn = create_txn(TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=2000), session)

    delete_txn(txn.id, session)  # type: ignore[arg-type]

    rows = account_statement(acc.id, session)  # type: ignore[arg-type]
    assert rows == []


@pytest.mark.unit
def test_delete_txn_missing_raises(session: Session) -> None:
    with pytest.raises(ValueError, match="not found"):
        delete_txn(9999, session)


@pytest.mark.unit
def test_update_txn_field_date(session: Session) -> None:
    acc = _make_account(session, "U1")
    txn = create_txn(TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100), session)
    updated = update_txn_field(txn.id, "date", "2024-02-15", session)  # type: ignore[arg-type]
    assert updated.date == "2024-02-15"


@pytest.mark.unit
def test_update_txn_field_amount(session: Session) -> None:
    acc = _make_account(session, "U2")
    txn = create_txn(TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100), session)
    updated = update_txn_field(txn.id, "amount_cents", "12,34", session)  # type: ignore[arg-type]
    assert updated.amount_cents == 1234


@pytest.mark.unit
def test_update_txn_field_category_and_comment(session: Session) -> None:
    acc = _make_account(session, "U3")
    txn = create_txn(TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100), session)
    updated = update_txn_field(txn.id, "category", "Despesa fixa", session)  # type: ignore[arg-type]
    assert updated.category == "Despesa fixa"
    updated = update_txn_field(txn.id, "comment", "", session)  # type: ignore[arg-type]
    assert updated.comment is None


@pytest.mark.unit
def test_update_txn_field_tags(session: Session) -> None:
    acc = _make_account(session, "U3B")
    txn = create_txn(TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100), session)
    updated = update_txn_field(txn.id, "tags", "casa, mercado", session)  # type: ignore[arg-type]
    assert updated.tags == "casa, mercado"
    updated = update_txn_field(txn.id, "tags", "", session)  # type: ignore[arg-type]
    assert updated.tags is None


@pytest.mark.unit
def test_update_txn_field_invalid_field_raises(session: Session) -> None:
    acc = _make_account(session, "U4")
    txn = create_txn(TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100), session)
    with pytest.raises(ValueError, match="not editable"):
        update_txn_field(txn.id, "from_account", "1", session)  # type: ignore[arg-type]


@pytest.mark.unit
def test_update_txn_field_missing_txn_raises(session: Session) -> None:
    with pytest.raises(ValueError, match="not found"):
        update_txn_field(9999, "date", "2024-01-01", session)


@pytest.mark.unit
def test_update_txn_field_invalid_amount_raises(session: Session) -> None:
    acc = _make_account(session, "U5")
    txn = create_txn(TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100), session)
    with pytest.raises(ValueError, match="invalid amount"):
        update_txn_field(txn.id, "amount_cents", "abc", session)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="positive"):
        update_txn_field(txn.id, "amount_cents", "0", session)  # type: ignore[arg-type]


@pytest.mark.unit
def test_update_txn_field_empty_date_raises(session: Session) -> None:
    acc = _make_account(session, "U6")
    txn = create_txn(TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100), session)
    with pytest.raises(ValueError, match="required"):
        update_txn_field(txn.id, "date", "", session)  # type: ignore[arg-type]


@pytest.mark.unit
def test_create_txn_with_needs_resolution_flag(session: Session) -> None:
    acc = _make_account(session, "R1")
    data = TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100, needs_resolution=True)
    txn = create_txn(data, session)
    assert txn.needs_resolution == 1


@pytest.mark.unit
def test_create_txn_defaults_needs_resolution_false(session: Session) -> None:
    acc = _make_account(session, "R2")
    txn = create_txn(TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100), session)
    assert txn.needs_resolution == 0


@pytest.mark.unit
def test_is_resolved_combinations(session: Session) -> None:
    acc = _make_account(session, "R3")
    a = create_txn(TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100), session)
    b = create_txn(TxnCreate(date="2024-01-02", to_account=acc.id, amount_cents=100), session)
    assert is_resolved(a) is False

    a.resolved_txn_id = b.id
    assert is_resolved(a) is True
    a.resolved_txn_id = None

    a.resolution_note = "forgiven"
    assert is_resolved(a) is True

    a.resolved_txn_id = b.id
    assert is_resolved(a) is True


@pytest.mark.unit
def test_set_needs_resolution_toggle(session: Session) -> None:
    acc = _make_account(session, "R4")
    txn = create_txn(TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100), session)
    updated = set_needs_resolution(txn.id, True, session)  # type: ignore[arg-type]
    assert updated.needs_resolution == 1
    updated = set_needs_resolution(txn.id, False, session)  # type: ignore[arg-type]
    assert updated.needs_resolution == 0


@pytest.mark.unit
def test_set_needs_resolution_missing_raises(session: Session) -> None:
    with pytest.raises(ValueError, match="not found"):
        set_needs_resolution(9999, True, session)


@pytest.mark.unit
def test_resolve_txn_with_pair(session: Session) -> None:
    acc = _make_account(session, "R5")
    a = create_txn(TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100), session)
    b = create_txn(TxnCreate(date="2024-01-02", to_account=acc.id, amount_cents=100), session)
    resolved = resolve_txn(a.id, session, resolved_txn_id=b.id)  # type: ignore[arg-type]
    assert resolved.resolved_txn_id == b.id
    assert is_resolved(resolved) is True


@pytest.mark.unit
def test_resolve_txn_with_note_only(session: Session) -> None:
    acc = _make_account(session, "R6")
    a = create_txn(TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100), session)
    resolved = resolve_txn(a.id, session, resolution_note="forgiven")  # type: ignore[arg-type]
    assert resolved.resolution_note == "forgiven"
    assert is_resolved(resolved) is True


@pytest.mark.unit
def test_resolve_txn_requires_at_least_one(session: Session) -> None:
    acc = _make_account(session, "R7")
    a = create_txn(TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100), session)
    with pytest.raises(ValueError, match="at least one"):
        resolve_txn(a.id, session)  # type: ignore[arg-type]


@pytest.mark.unit
def test_resolve_txn_rejects_self_reference(session: Session) -> None:
    acc = _make_account(session, "R8")
    a = create_txn(TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100), session)
    with pytest.raises(ValueError, match="own pair"):
        resolve_txn(a.id, session, resolved_txn_id=a.id)  # type: ignore[arg-type]


@pytest.mark.unit
def test_resolve_txn_rejects_missing_pair(session: Session) -> None:
    acc = _make_account(session, "R9")
    a = create_txn(TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100), session)
    with pytest.raises(ValueError, match="not found"):
        resolve_txn(a.id, session, resolved_txn_id=9999)  # type: ignore[arg-type]


@pytest.mark.unit
def test_resolve_txn_missing_txn_raises(session: Session) -> None:
    with pytest.raises(ValueError, match="not found"):
        resolve_txn(9999, session, resolution_note="x")


@pytest.mark.unit
def test_unresolve_txn_clears_fields(session: Session) -> None:
    acc = _make_account(session, "R10")
    a = create_txn(TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100), session)
    b = create_txn(TxnCreate(date="2024-01-02", to_account=acc.id, amount_cents=100), session)
    resolve_txn(a.id, session, resolved_txn_id=b.id, resolution_note="note")  # type: ignore[arg-type]
    cleared = unresolve_txn(a.id, session)  # type: ignore[arg-type]
    assert cleared.resolved_txn_id is None
    assert cleared.resolution_note is None
    assert is_resolved(cleared) is False


@pytest.mark.unit
def test_unresolve_txn_missing_raises(session: Session) -> None:
    with pytest.raises(ValueError, match="not found"):
        unresolve_txn(9999, session)


@pytest.mark.unit
def test_delete_txn_clears_dangling_resolved_txn_id(session: Session) -> None:
    acc = _make_account(session, "R11")
    a = create_txn(TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100), session)
    b = create_txn(TxnCreate(date="2024-01-02", to_account=acc.id, amount_cents=100), session)
    resolve_txn(a.id, session, resolved_txn_id=b.id)  # type: ignore[arg-type]

    delete_txn(b.id, session)  # type: ignore[arg-type]

    session.refresh(a)
    assert a.resolved_txn_id is None


@pytest.mark.unit
def test_search_txns_matches_comment_category_date(session: Session) -> None:
    acc = _make_account(session, "R12")
    a = create_txn(
        TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100, comment="Aluguel"),
        session,
    )
    create_txn(
        TxnCreate(date="2024-02-01", to_account=acc.id, amount_cents=200, comment="Mercado"),
        session,
    )
    results = search_txns("Aluguel", 9999, session)
    assert [t.id for t in results] == [a.id]


@pytest.mark.unit
def test_search_txns_excludes_self(session: Session) -> None:
    acc = _make_account(session, "R13")
    a = create_txn(
        TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100, comment="Aluguel"),
        session,
    )
    results = search_txns("Aluguel", a.id, session)  # type: ignore[arg-type]
    assert results == []


@pytest.mark.unit
def test_search_txns_blank_query_returns_recent(session: Session) -> None:
    acc = _make_account(session, "R14")
    a = create_txn(TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100), session)
    b = create_txn(TxnCreate(date="2024-02-01", to_account=acc.id, amount_cents=100), session)
    results = search_txns("", 9999, session)
    ids = [t.id for t in results]
    assert a.id in ids
    assert b.id in ids


@pytest.mark.unit
def test_add_txn_note_and_list(session: Session) -> None:
    acc = _make_account(session, "N1")
    txn = create_txn(TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100), session)
    note = add_txn_note(txn.id, "Primeira nota", session)  # type: ignore[arg-type]
    assert note.id is not None
    assert note.text == "Primeira nota"

    notes = list_txn_notes(txn.id, session)  # type: ignore[arg-type]
    assert [n.text for n in notes] == ["Primeira nota"]


@pytest.mark.unit
def test_add_txn_note_orders_newest_first(session: Session) -> None:
    acc = _make_account(session, "N2")
    txn = create_txn(TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100), session)
    first = add_txn_note(txn.id, "Primeira", session)  # type: ignore[arg-type]
    second = add_txn_note(txn.id, "Segunda", session)  # type: ignore[arg-type]

    notes = list_txn_notes(txn.id, session)  # type: ignore[arg-type]
    assert [n.id for n in notes] == [second.id, first.id]


@pytest.mark.unit
def test_add_txn_note_rejects_blank_text(session: Session) -> None:
    acc = _make_account(session, "N3")
    txn = create_txn(TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100), session)
    with pytest.raises(ValueError, match="required"):
        add_txn_note(txn.id, "   ", session)  # type: ignore[arg-type]


@pytest.mark.unit
def test_add_txn_note_missing_txn_raises(session: Session) -> None:
    with pytest.raises(ValueError, match="not found"):
        add_txn_note(9999, "nota", session)


@pytest.mark.unit
def test_delete_txn_note_removes_it(session: Session) -> None:
    acc = _make_account(session, "N4")
    txn = create_txn(TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100), session)
    note = add_txn_note(txn.id, "Para remover", session)  # type: ignore[arg-type]

    delete_txn_note(note.id, session)  # type: ignore[arg-type]

    assert list_txn_notes(txn.id, session) == []  # type: ignore[arg-type]


@pytest.mark.unit
def test_delete_txn_note_missing_raises(session: Session) -> None:
    with pytest.raises(ValueError, match="not found"):
        delete_txn_note(9999, session)


@pytest.mark.unit
def test_delete_txn_cascades_notes(session: Session) -> None:
    acc = _make_account(session, "N5")
    txn = create_txn(TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100), session)
    add_txn_note(txn.id, "Nota", session)  # type: ignore[arg-type]

    delete_txn(txn.id, session)  # type: ignore[arg-type]

    assert list_txn_notes(txn.id, session) == []  # type: ignore[arg-type]


@pytest.mark.unit
def test_txn_note_counts_groups_by_txn(session: Session) -> None:
    acc = _make_account(session, "N6")
    a = create_txn(TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100), session)
    b = create_txn(TxnCreate(date="2024-01-02", to_account=acc.id, amount_cents=100), session)
    add_txn_note(a.id, "n1", session)  # type: ignore[arg-type]
    add_txn_note(a.id, "n2", session)  # type: ignore[arg-type]
    add_txn_note(b.id, "n1", session)  # type: ignore[arg-type]

    counts = txn_note_counts(session, [a.id, b.id])  # type: ignore[arg-type]
    assert counts == {a.id: 2, b.id: 1}


@pytest.mark.unit
def test_txn_note_counts_empty_list_returns_empty_dict(session: Session) -> None:
    assert txn_note_counts(session, []) == {}


@pytest.mark.unit
def test_note_counts_for_txns_skips_txns_without_notes(session: Session) -> None:
    acc = _make_account(session, "N7")
    a = create_txn(TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=100), session)
    b = create_txn(TxnCreate(date="2024-01-02", to_account=acc.id, amount_cents=100), session)
    add_txn_note(a.id, "n1", session)  # type: ignore[arg-type]

    counts = note_counts_for_txns([a, b], session)
    assert counts == {a.id: 1}
