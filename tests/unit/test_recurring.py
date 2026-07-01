from datetime import date

import pytest
from app.models.tables import Account
from app.schemas.forms import RecurringRuleCreate
from app.services.ledger import account_statement
from app.services.recurring import (
    backfill_past_periods,
    create_rule,
    current_period,
    delete_rule,
    edit_rule,
    group_active_rules_by_account,
    installment_progress,
    is_rule_finished,
    list_rules,
    pending_for_period,
    post_all_pending,
    post_rule,
    rules_by_status,
    skip_rule,
    update_field,
    update_notes,
    update_tags,
)
from sqlmodel import Session


def _make_account(session: Session, code: str = "ACC") -> Account:
    a = Account(code=code, name=code, tier="Imediato", opening_cents=0, opening_date="2024-01-01")
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


def _shift_period(period: str, months: int) -> str:
    year, month = (int(p) for p in period.split("-"))
    total = year * 12 + (month - 1) + months
    return f"{total // 12}-{total % 12 + 1:02d}"


def _make_rule(
    session: Session, account_id: int, amount: int = 10000, kind: str = "fixed"
) -> object:
    data = RecurringRuleCreate(
        kind=kind,
        description="Test rule",
        to_account=account_id,
        amount_cents=amount,
    )
    return create_rule(data, session)


@pytest.mark.unit
def test_pending_for_period(session: Session) -> None:
    acc = _make_account(session)
    rule = _make_rule(session, acc.id)  # type: ignore[arg-type]
    pending = pending_for_period("2024-01", session)
    assert any(r.id == rule.id for r in pending)  # type: ignore[union-attr]


@pytest.mark.unit
def test_post_removes_from_pending(session: Session) -> None:
    acc = _make_account(session, "P2")
    rule = _make_rule(session, acc.id)  # type: ignore[arg-type]
    post_rule(rule.id, "2024-01", session)  # type: ignore[union-attr]
    pending = pending_for_period("2024-01", session)
    assert not any(r.id == rule.id for r in pending)  # type: ignore[union-attr]


@pytest.mark.unit
def test_post_rule_copies_tags_to_txn(session: Session) -> None:
    from app.models.tables import Txn

    acc = _make_account(session, "P1B")
    data = RecurringRuleCreate(
        kind="fixed",
        description="Test rule",
        to_account=acc.id,  # type: ignore[arg-type]
        amount_cents=10000,
        tags="casa, fixo",
    )
    rule = create_rule(data, session)
    event = post_rule(rule.id, "2024-01", session)  # type: ignore[arg-type]
    txn = session.get(Txn, event.txn_id)
    assert txn is not None
    assert txn.tags == "casa, fixo"


@pytest.mark.unit
def test_post_all_pending_posts_every_rule(session: Session) -> None:
    acc = _make_account(session, "P2A")
    rule1 = _make_rule(session, acc.id, amount=1000)  # type: ignore[arg-type]
    rule2 = _make_rule(session, acc.id, amount=2000)  # type: ignore[arg-type]
    events = post_all_pending("2024-01", session)
    assert {e.rule_id for e in events} == {rule1.id, rule2.id}  # type: ignore[union-attr]
    assert pending_for_period("2024-01", session) == []


@pytest.mark.unit
def test_post_all_pending_skips_already_acted_rules(session: Session) -> None:
    acc = _make_account(session, "P2B")
    rule = _make_rule(session, acc.id)  # type: ignore[arg-type]
    skip_rule(rule.id, "2024-01", session)  # type: ignore[union-attr]
    events = post_all_pending("2024-01", session)
    assert events == []


@pytest.mark.unit
def test_post_all_pending_empty_when_nothing_pending(session: Session) -> None:
    assert post_all_pending("2024-01", session) == []


@pytest.mark.unit
def test_skip_removes_from_pending(session: Session) -> None:
    acc = _make_account(session, "P3")
    rule = _make_rule(session, acc.id)  # type: ignore[arg-type]
    skip_rule(rule.id, "2024-01", session)  # type: ignore[union-attr]
    pending = pending_for_period("2024-01", session)
    assert not any(r.id == rule.id for r in pending)  # type: ignore[union-attr]


@pytest.mark.unit
def test_skip_only_one_month(session: Session) -> None:
    """Skipping one month does not affect a different month."""
    acc = _make_account(session, "P4")
    rule = _make_rule(session, acc.id)  # type: ignore[arg-type]
    skip_rule(rule.id, "2024-01", session)  # type: ignore[union-attr]
    # Should still be pending in February
    pending = pending_for_period("2024-02", session)
    assert any(r.id == rule.id for r in pending)  # type: ignore[union-attr]


@pytest.mark.unit
def test_edit_applies_only_next_post(session: Session) -> None:
    """Editing amount does not change already-posted events."""
    acc = _make_account(session, "P5")
    rule = _make_rule(session, acc.id, amount=5000)  # type: ignore[arg-type]
    event = post_rule(rule.id, "2024-01", session)  # type: ignore[union-attr]
    assert event.amount_cents == 5000

    # Edit rule: new amount for future posts
    edit_rule(rule.id, 9000, session)  # type: ignore[union-attr]

    # Previous event is unchanged
    assert event.amount_cents == 5000

    # Next post uses new amount
    event2 = post_rule(rule.id, "2024-02", session)  # type: ignore[union-attr]
    assert event2.amount_cents == 9000


@pytest.mark.unit
def test_update_field_description_category_day(session: Session) -> None:
    acc = _make_account(session, "UF1")
    rule = _make_rule(session, acc.id)  # type: ignore[arg-type]
    updated = update_field(rule.id, "description", "New desc", session)  # type: ignore[union-attr]
    assert updated.description == "New desc"
    updated = update_field(rule.id, "category", "Despesa fixa", session)  # type: ignore[union-attr]
    assert updated.category == "Despesa fixa"
    updated = update_field(rule.id, "day_of_month", "15", session)  # type: ignore[union-attr]
    assert updated.day_of_month == 15


@pytest.mark.unit
def test_update_field_amount_reuses_edit_rule(session: Session) -> None:
    acc = _make_account(session, "UF2")
    rule = _make_rule(session, acc.id, amount=5000)  # type: ignore[arg-type]
    updated = update_field(rule.id, "amount_cents", "70,00", session)  # type: ignore[union-attr]
    assert updated.amount_cents == 7000


@pytest.mark.unit
def test_update_field_from_and_to_account(session: Session) -> None:
    acc1 = _make_account(session, "UF5A")
    acc2 = _make_account(session, "UF5B")
    rule = _make_rule(session, acc1.id)  # type: ignore[arg-type]
    updated = update_field(rule.id, "from_account", str(acc2.id), session)  # type: ignore[union-attr]
    assert updated.from_account == acc2.id
    updated = update_field(rule.id, "to_account", str(acc1.id), session)  # type: ignore[union-attr]
    assert updated.to_account == acc1.id


@pytest.mark.unit
def test_update_field_account_cleared_to_external(session: Session) -> None:
    acc = _make_account(session, "UF6")
    rule = _make_rule(session, acc.id)  # type: ignore[arg-type]
    updated = update_field(rule.id, "to_account", "", session)  # type: ignore[union-attr]
    assert updated.to_account is None


@pytest.mark.unit
def test_update_field_invalid_account_raises(session: Session) -> None:
    acc = _make_account(session, "UF7")
    rule = _make_rule(session, acc.id)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="invalid account"):
        update_field(rule.id, "from_account", "abc", session)  # type: ignore[union-attr]
    with pytest.raises(ValueError, match="not found"):
        update_field(rule.id, "from_account", "9999", session)  # type: ignore[union-attr]


@pytest.mark.unit
def test_update_field_day_out_of_range_raises(session: Session) -> None:
    acc = _make_account(session, "UF3")
    rule = _make_rule(session, acc.id)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="between 1 and 28"):
        update_field(rule.id, "day_of_month", "31", session)  # type: ignore[union-attr]


@pytest.mark.unit
def test_update_field_invalid_field_raises(session: Session) -> None:
    acc = _make_account(session, "UF4")
    rule = _make_rule(session, acc.id)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="not editable"):
        update_field(rule.id, "kind", "installment", session)  # type: ignore[union-attr]


@pytest.mark.unit
def test_update_field_missing_rule_raises(session: Session) -> None:
    with pytest.raises(ValueError, match="not found"):
        update_field(9999, "description", "X", session)


@pytest.mark.unit
def test_installment_auto_stops(session: Session) -> None:
    """Installment rule stops appearing in pending after full count is reached."""
    acc = _make_account(session, "P6")
    data = RecurringRuleCreate(
        kind="installment",
        description="3-month installment",
        to_account=acc.id,  # type: ignore[arg-type]
        amount_cents=1000,
        installments=3,
    )
    rule = create_rule(data, session)

    post_rule(rule.id, "2024-01", session)  # type: ignore[union-attr]
    post_rule(rule.id, "2024-02", session)  # type: ignore[union-attr]
    post_rule(rule.id, "2024-03", session)  # type: ignore[union-attr]

    # Fully paid — should not appear in pending
    pending = pending_for_period("2024-04", session)
    assert not any(r.id == rule.id for r in pending)  # type: ignore[union-attr]


@pytest.mark.unit
def test_installment_progress(session: Session) -> None:
    acc = _make_account(session, "P7")
    data = RecurringRuleCreate(
        kind="installment",
        description="5-month installment",
        to_account=acc.id,  # type: ignore[arg-type]
        amount_cents=2000,
        installments=5,
    )
    rule = create_rule(data, session)
    post_rule(rule.id, "2024-01", session)  # type: ignore[union-attr]
    post_rule(rule.id, "2024-02", session)  # type: ignore[union-attr]

    posted, total = installment_progress(rule.id, session)  # type: ignore[union-attr]
    assert posted == 2
    assert total == 5


@pytest.mark.unit
def test_installment_progress_derives_total_from_start_end_period(session: Session) -> None:
    """Installments can be set either as a count or as a start/end period range;
    remaining-count display must work for both."""
    acc = _make_account(session, "P7B")
    data = RecurringRuleCreate(
        kind="installment",
        description="4-month range",
        to_account=acc.id,  # type: ignore[arg-type]
        amount_cents=2000,
        start_period="2024-01",
        end_period="2024-04",
    )
    rule = create_rule(data, session)
    assert rule.installments is None

    post_rule(rule.id, "2024-01", session)  # type: ignore[union-attr]

    posted, total = installment_progress(rule.id, session)  # type: ignore[union-attr]
    assert posted == 1
    assert total == 4


@pytest.mark.unit
def test_installment_progress_zero_when_neither_available(session: Session) -> None:
    acc = _make_account(session, "P7C")
    rule = _make_rule(session, acc.id, kind="installment")  # type: ignore[arg-type]
    posted, total = installment_progress(rule.id, session)  # type: ignore[union-attr]
    assert total == 0


@pytest.mark.unit
def test_current_period_matches_today() -> None:
    today = date.today()
    assert current_period() == f"{today.year}-{today.month:02d}"


@pytest.mark.unit
def test_create_rule_stores_end_period(session: Session) -> None:
    acc = _make_account(session, "P8")
    this_period = current_period()
    data = RecurringRuleCreate(
        kind="fixed",
        description="Bounded rule",
        to_account=acc.id,  # type: ignore[arg-type]
        amount_cents=1000,
        start_period=this_period,
        end_period=_shift_period(this_period, 2),
    )
    rule = create_rule(data, session)
    assert rule.start_period == this_period
    assert rule.end_period == _shift_period(this_period, 2)


@pytest.mark.unit
def test_pending_for_period_respects_start_period_bound(session: Session) -> None:
    acc = _make_account(session, "P9")
    this_period = current_period()
    future_start = _shift_period(this_period, 2)
    data = RecurringRuleCreate(
        kind="fixed",
        description="Future start",
        to_account=acc.id,  # type: ignore[arg-type]
        amount_cents=1000,
        start_period=future_start,
    )
    rule = create_rule(data, session)
    assert not any(r.id == rule.id for r in pending_for_period(this_period, session))  # type: ignore[union-attr]
    assert any(r.id == rule.id for r in pending_for_period(future_start, session))  # type: ignore[union-attr]


@pytest.mark.unit
def test_pending_for_period_respects_end_period_bound(session: Session) -> None:
    acc = _make_account(session, "P10")
    this_period = current_period()
    data = RecurringRuleCreate(
        kind="fixed",
        description="Past end",
        to_account=acc.id,  # type: ignore[arg-type]
        amount_cents=1000,
        start_period=_shift_period(this_period, -3),
        end_period=_shift_period(this_period, -1),
    )
    rule = create_rule(data, session)
    assert not any(r.id == rule.id for r in pending_for_period(this_period, session))  # type: ignore[union-attr]


@pytest.mark.unit
def test_backfill_past_periods_creates_txns(session: Session) -> None:
    acc = _make_account(session, "P11")
    this_period = current_period()
    start = _shift_period(this_period, -2)
    data = RecurringRuleCreate(
        kind="fixed",
        description="Backfilled deposit",
        to_account=acc.id,  # type: ignore[arg-type]
        amount_cents=2500,
        start_period=start,
    )
    rule = create_rule(data, session)
    events = backfill_past_periods(rule.id, session)  # type: ignore[arg-type]

    assert [e.period for e in events] == [start, _shift_period(this_period, -1)]
    rows = account_statement(acc.id, session)  # type: ignore[arg-type]
    assert len(rows) == 2

    # The current period itself is left as a normal pending item, not backfilled.
    assert any(r.id == rule.id for r in pending_for_period(this_period, session))  # type: ignore[union-attr]


@pytest.mark.unit
def test_backfill_future_start_period_does_nothing(session: Session) -> None:
    acc = _make_account(session, "P12")
    this_period = current_period()
    data = RecurringRuleCreate(
        kind="fixed",
        description="Future rule",
        to_account=acc.id,  # type: ignore[arg-type]
        amount_cents=1000,
        start_period=_shift_period(this_period, 1),
    )
    rule = create_rule(data, session)
    events = backfill_past_periods(rule.id, session)  # type: ignore[arg-type]
    assert events == []


@pytest.mark.unit
def test_backfill_no_start_period_does_nothing(session: Session) -> None:
    acc = _make_account(session, "P13")
    rule = _make_rule(session, acc.id)  # type: ignore[arg-type]
    events = backfill_past_periods(rule.id, session)  # type: ignore[union-attr]
    assert events == []


@pytest.mark.unit
def test_backfill_respects_end_period(session: Session) -> None:
    acc = _make_account(session, "P14")
    this_period = current_period()
    start = _shift_period(this_period, -3)
    end = _shift_period(this_period, -2)
    data = RecurringRuleCreate(
        kind="fixed",
        description="Bounded backfill",
        to_account=acc.id,  # type: ignore[arg-type]
        amount_cents=1500,
        start_period=start,
        end_period=end,
    )
    rule = create_rule(data, session)
    events = backfill_past_periods(rule.id, session)  # type: ignore[arg-type]
    assert [e.period for e in events] == [start, end]


@pytest.mark.unit
def test_backfill_stops_when_installments_exhausted(session: Session) -> None:
    acc = _make_account(session, "P15")
    this_period = current_period()
    start = _shift_period(this_period, -3)
    data = RecurringRuleCreate(
        kind="installment",
        description="Short installment plan",
        to_account=acc.id,  # type: ignore[arg-type]
        amount_cents=1000,
        installments=1,
        start_period=start,
    )
    rule = create_rule(data, session)
    events = backfill_past_periods(rule.id, session)  # type: ignore[arg-type]
    assert [e.period for e in events] == [start]


@pytest.mark.unit
def test_installment_rule_derives_end_period_from_start_and_count(session: Session) -> None:
    acc = _make_account(session, "P16")
    this_period = current_period()
    data = RecurringRuleCreate(
        kind="installment",
        description="Derived end",
        to_account=acc.id,  # type: ignore[arg-type]
        amount_cents=1000,
        installments=4,
        start_period=this_period,
    )
    rule = create_rule(data, session)
    assert rule.end_period == _shift_period(this_period, 3)


@pytest.mark.unit
def test_installment_rule_without_start_period_has_no_end_period(session: Session) -> None:
    acc = _make_account(session, "P17")
    data = RecurringRuleCreate(
        kind="installment",
        description="Open installment",
        to_account=acc.id,  # type: ignore[arg-type]
        amount_cents=1000,
        installments=4,
    )
    rule = create_rule(data, session)
    assert rule.end_period is None


@pytest.mark.unit
def test_is_rule_finished_by_end_period(session: Session) -> None:
    acc = _make_account(session, "P18")
    this_period = current_period()
    data = RecurringRuleCreate(
        kind="fixed",
        description="Ended rule",
        to_account=acc.id,  # type: ignore[arg-type]
        amount_cents=1000,
        start_period=_shift_period(this_period, -3),
        end_period=_shift_period(this_period, -1),
    )
    rule = create_rule(data, session)
    assert is_rule_finished(rule, session)


@pytest.mark.unit
def test_is_rule_finished_open_ended_is_false(session: Session) -> None:
    acc = _make_account(session, "P19")
    rule = _make_rule(session, acc.id)  # type: ignore[arg-type]
    assert not is_rule_finished(rule, session)  # type: ignore[arg-type]


@pytest.mark.unit
def test_is_rule_finished_by_installment_count(session: Session) -> None:
    acc = _make_account(session, "P20")
    data = RecurringRuleCreate(
        kind="installment",
        description="Exhausted",
        to_account=acc.id,  # type: ignore[arg-type]
        amount_cents=1000,
        installments=1,
    )
    rule = create_rule(data, session)
    post_rule(rule.id, "2024-01", session)  # type: ignore[union-attr]
    assert is_rule_finished(rule, session)


@pytest.mark.unit
def test_rules_by_status_splits_active_and_finished(session: Session) -> None:
    acc = _make_account(session, "P21")
    this_period = current_period()
    active_rule = _make_rule(session, acc.id)  # type: ignore[arg-type]
    finished_rule = create_rule(
        RecurringRuleCreate(
            kind="fixed",
            description="Ended",
            to_account=acc.id,  # type: ignore[arg-type]
            amount_cents=1000,
            start_period=_shift_period(this_period, -3),
            end_period=_shift_period(this_period, -1),
        ),
        session,
    )
    active, finished = rules_by_status(session)
    assert any(r.id == active_rule.id for r in active)  # type: ignore[union-attr]
    assert any(r.id == finished_rule.id for r in finished)
    assert not any(r.id == finished_rule.id for r in active)
    assert not any(r.id == active_rule.id for r in finished)  # type: ignore[union-attr]


@pytest.mark.unit
def test_delete_rule_keeps_txns_by_default(session: Session) -> None:
    acc = _make_account(session, "P22")
    rule = _make_rule(session, acc.id)  # type: ignore[arg-type]
    txn_event = post_rule(rule.id, "2024-01", session)  # type: ignore[union-attr]

    delete_rule(rule.id, session)  # type: ignore[union-attr, arg-type]

    rows = account_statement(acc.id, session)  # type: ignore[arg-type]
    assert len(rows) == 1
    assert rows[0].txn.id == txn_event.txn_id
    assert rows[0].txn.recurring_id is None


@pytest.mark.unit
def test_delete_rule_with_delete_txns_removes_them(session: Session) -> None:
    acc = _make_account(session, "P23")
    rule = _make_rule(session, acc.id)  # type: ignore[arg-type]
    post_rule(rule.id, "2024-01", session)  # type: ignore[union-attr]

    delete_rule(rule.id, session, delete_txns=True)  # type: ignore[union-attr, arg-type]

    rows = account_statement(acc.id, session)  # type: ignore[arg-type]
    assert rows == []


@pytest.mark.unit
def test_delete_rule_missing_raises(session: Session) -> None:
    with pytest.raises(ValueError, match="not found"):
        delete_rule(9999, session)


@pytest.mark.unit
def test_list_rules_orders_by_kind_then_category(session: Session) -> None:
    acc = _make_account(session, "P24")
    create_rule(
        RecurringRuleCreate(
            kind="installment",
            description="Z installment",
            to_account=acc.id,  # type: ignore[arg-type]
            amount_cents=1000,
            category="Zeta",
        ),
        session,
    )
    create_rule(
        RecurringRuleCreate(
            kind="fixed",
            description="B fixed",
            to_account=acc.id,  # type: ignore[arg-type]
            amount_cents=1000,
            category="Beta",
        ),
        session,
    )
    create_rule(
        RecurringRuleCreate(
            kind="fixed",
            description="A fixed",
            to_account=acc.id,  # type: ignore[arg-type]
            amount_cents=1000,
            category="Alfa",
        ),
        session,
    )

    rules = list_rules(session)
    ordering = [(r.kind, r.category) for r in rules]
    assert ordering == [
        ("fixed", "Alfa"),
        ("fixed", "Beta"),
        ("installment", "Zeta"),
    ]


@pytest.mark.unit
def test_group_active_rules_by_account_sums_inflow(session: Session) -> None:
    acc1 = _make_account(session, "G1")
    acc2 = _make_account(session, "G2")
    create_rule(
        RecurringRuleCreate(kind="fixed", description="R1", to_account=acc1.id, amount_cents=1000),
        session,
    )
    create_rule(
        RecurringRuleCreate(kind="fixed", description="R2", to_account=acc1.id, amount_cents=2000),
        session,
    )
    create_rule(
        RecurringRuleCreate(kind="fixed", description="R3", to_account=acc2.id, amount_cents=500),
        session,
    )

    groups = {g.account: g for g in group_active_rules_by_account(session)}
    assert groups[acc1.id].total_cents == 3000
    assert len(groups[acc1.id].flows) == 2
    assert all(f.direction == "in" for f in groups[acc1.id].flows)
    assert groups[acc2.id].total_cents == 500
    assert len(groups[acc2.id].flows) == 1


@pytest.mark.unit
def test_group_active_rules_by_account_nets_inflow_against_outflow(session: Session) -> None:
    acc = _make_account(session, "G7")
    other = _make_account(session, "G8")
    create_rule(
        RecurringRuleCreate(
            kind="fixed", description="Salary", to_account=acc.id, amount_cents=3000
        ),
        session,
    )
    create_rule(
        RecurringRuleCreate(
            kind="fixed", description="Rent", from_account=acc.id, amount_cents=1000
        ),
        session,
    )
    create_rule(
        RecurringRuleCreate(
            kind="fixed",
            description="Transfer to savings",
            from_account=acc.id,
            to_account=other.id,
            amount_cents=500,
        ),
        session,
    )

    groups = {g.account: g for g in group_active_rules_by_account(session)}
    # 3000 in - 1000 out - 500 out (transfer) = 1500
    assert groups[acc.id].total_cents == 1500
    assert len(groups[acc.id].flows) == 3
    # The transfer counts as inflow for the destination account too.
    assert groups[other.id].total_cents == 500
    assert groups[other.id].flows[0].direction == "in"


@pytest.mark.unit
def test_group_active_rules_by_account_can_be_negative(session: Session) -> None:
    acc = _make_account(session, "G9")
    create_rule(
        RecurringRuleCreate(
            kind="fixed", description="Big bill", from_account=acc.id, amount_cents=5000
        ),
        session,
    )
    create_rule(
        RecurringRuleCreate(
            kind="fixed", description="Small credit", to_account=acc.id, amount_cents=1000
        ),
        session,
    )

    groups = {g.account: g for g in group_active_rules_by_account(session)}
    assert groups[acc.id].total_cents == -4000


@pytest.mark.unit
def test_group_active_rules_by_account_external_bucket(session: Session) -> None:
    acc = _make_account(session, "G3")
    create_rule(
        RecurringRuleCreate(
            kind="fixed",
            description="External",
            from_account=acc.id,
            amount_cents=750,
        ),
        session,
    )

    groups = {g.account: g for g in group_active_rules_by_account(session)}
    assert None in groups
    assert groups[None].total_cents == 750
    assert groups[acc.id].total_cents == -750


@pytest.mark.unit
def test_group_active_rules_by_account_excludes_finished(session: Session) -> None:
    acc = _make_account(session, "G4")
    this_period = current_period()
    create_rule(
        RecurringRuleCreate(
            kind="fixed",
            description="Ended",
            to_account=acc.id,
            amount_cents=999,
            start_period=_shift_period(this_period, -3),
            end_period=_shift_period(this_period, -1),
        ),
        session,
    )

    groups = group_active_rules_by_account(session)
    total = sum(g.total_cents for g in groups)
    assert total == 0


@pytest.mark.unit
def test_group_active_rules_by_account_sorted_descending(session: Session) -> None:
    acc1 = _make_account(session, "G5")
    acc2 = _make_account(session, "G6")
    create_rule(
        RecurringRuleCreate(
            kind="fixed", description="Small", to_account=acc1.id, amount_cents=100
        ),
        session,
    )
    create_rule(
        RecurringRuleCreate(kind="fixed", description="Big", to_account=acc2.id, amount_cents=5000),
        session,
    )

    groups = group_active_rules_by_account(session)
    totals = [g.total_cents for g in groups]
    assert totals == sorted(totals, reverse=True)


@pytest.mark.unit
def test_create_rule_with_notes(session: Session) -> None:
    acc = _make_account(session, "N1")
    data = RecurringRuleCreate(
        kind="fixed",
        description="Aluguel",
        to_account=acc.id,  # type: ignore[arg-type]
        amount_cents=1000,
        notes="Reajuste de 3% ao ano",
    )
    rule = create_rule(data, session)
    assert rule.notes == "Reajuste de 3% ao ano"


@pytest.mark.unit
def test_create_rule_without_notes_defaults_none(session: Session) -> None:
    acc = _make_account(session, "N2")
    rule = _make_rule(session, acc.id)  # type: ignore[arg-type]
    assert rule.notes is None


@pytest.mark.unit
def test_update_notes_sets_and_clears(session: Session) -> None:
    acc = _make_account(session, "N3")
    rule = _make_rule(session, acc.id)  # type: ignore[arg-type]

    updated = update_notes(rule.id, "Pago via transferência", session)  # type: ignore[union-attr]
    assert updated.notes == "Pago via transferência"

    cleared = update_notes(rule.id, "", session)  # type: ignore[union-attr]
    assert cleared.notes is None


@pytest.mark.unit
def test_update_notes_missing_rule_raises(session: Session) -> None:
    with pytest.raises(ValueError, match="not found"):
        update_notes(9999, "x", session)


@pytest.mark.unit
def test_create_rule_without_tags_defaults_none(session: Session) -> None:
    acc = _make_account(session, "TG1")
    rule = _make_rule(session, acc.id)  # type: ignore[arg-type]
    assert rule.tags is None


@pytest.mark.unit
def test_update_tags_sets_and_clears(session: Session) -> None:
    acc = _make_account(session, "TG2")
    rule = _make_rule(session, acc.id)  # type: ignore[arg-type]

    updated = update_tags(rule.id, "casa, fixo", session)  # type: ignore[union-attr]
    assert updated.tags == "casa, fixo"

    cleared = update_tags(rule.id, "", session)  # type: ignore[union-attr]
    assert cleared.tags is None


@pytest.mark.unit
def test_update_tags_missing_rule_raises(session: Session) -> None:
    with pytest.raises(ValueError, match="not found"):
        update_tags(9999, "x", session)
