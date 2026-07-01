from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlmodel import Session, col, select

from app.models.tables import Account, RecurringEvent, RecurringRule, Txn
from app.schemas.forms import RecurringRuleCreate


def current_period() -> str:
    today = date.today()
    return f"{today.year}-{today.month:02d}"


def _periods_between(start_period: str, end_period: str) -> list[str]:
    """Inclusive list of 'YYYY-MM' periods from start_period to end_period."""
    start_year, start_month = (int(p) for p in start_period.split("-"))
    end_year, end_month = (int(p) for p in end_period.split("-"))
    periods = []
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        periods.append(f"{year}-{month:02d}")
        month += 1
        if month > 12:
            month = 1
            year += 1
    return periods


def _shift_period(period: str, months: int) -> str:
    year, month = (int(p) for p in period.split("-"))
    total = year * 12 + (month - 1) + months
    return f"{total // 12}-{total % 12 + 1:02d}"


def create_rule(data: RecurringRuleCreate, session: Session) -> RecurringRule:
    end_period = data.end_period
    if data.kind == "installment" and data.start_period and data.installments:
        # Installment rules are registered by date range like any other rule;
        # the installment count just derives that range's length. Remaining
        # installments is still tracked and surfaced separately for display.
        end_period = _shift_period(data.start_period, data.installments - 1)

    rule = RecurringRule(
        kind=data.kind,
        description=data.description,
        from_account=data.from_account,
        to_account=data.to_account,
        amount_cents=data.amount_cents,
        category=data.category,
        day_of_month=data.day_of_month,
        start_period=data.start_period,
        end_period=end_period,
        installments=data.installments,
        notes=data.notes,
        tags=data.tags,
        created_at=datetime.now(UTC).isoformat(),
    )
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule


def backfill_past_periods(rule_id: int, session: Session) -> list[RecurringEvent]:
    """Auto-post any periods from start_period up to (but excluding) the current
    period that fall within the rule's range. Used right after creating a rule
    whose start_period is already in the past, so history isn't left dangling
    as forever-pending.
    """
    rule = session.get(RecurringRule, rule_id)
    if rule is None:
        raise ValueError(f"Rule {rule_id} not found")
    if not rule.start_period:
        return []

    this_period = current_period()
    if rule.start_period >= this_period:
        return []

    range_end = min(rule.end_period, this_period) if rule.end_period else this_period
    periods = [p for p in _periods_between(rule.start_period, range_end) if p < this_period]

    events: list[RecurringEvent] = []
    for period in periods:
        if _is_finished(rule, session):
            break
        events.append(post_rule(rule_id, period, session))
    return events


def _posted_count(rule_id: int, session: Session) -> int:
    events = session.exec(
        select(RecurringEvent).where(
            RecurringEvent.rule_id == rule_id,
            RecurringEvent.status == "posted",
        )
    ).all()
    return len(events)


def _is_finished(rule: RecurringRule, session: Session) -> bool:
    if rule.kind == "installment" and rule.installments is not None:
        return _posted_count(rule.id, session) >= rule.installments  # type: ignore[arg-type]
    return False


def pending_for_period(period: str, session: Session) -> list[RecurringRule]:
    """Active rules with no event for the period, excluding finished installments."""
    active_rules = session.exec(select(RecurringRule).where(RecurringRule.active == 1)).all()

    acted_rule_ids: set[int] = {
        e.rule_id
        for e in session.exec(select(RecurringEvent).where(RecurringEvent.period == period)).all()
    }

    result: list[RecurringRule] = []
    for rule in active_rules:
        if rule.id in acted_rule_ids:
            continue
        if _is_finished(rule, session):
            continue
        if rule.start_period and period < rule.start_period:
            continue
        if rule.end_period and period > rule.end_period:
            continue
        result.append(rule)
    return result


def post_rule(rule_id: int, period: str, session: Session) -> RecurringEvent:
    """Create txn + event; snapshot amount at post time."""
    rule = session.get(RecurringRule, rule_id)
    if rule is None:
        raise ValueError(f"Rule {rule_id} not found")

    existing = session.exec(
        select(RecurringEvent).where(
            RecurringEvent.rule_id == rule_id,
            RecurringEvent.period == period,
        )
    ).first()
    if existing is not None:
        raise ValueError(f"Rule {rule_id} already acted on for period {period}")

    year, month = period.split("-")
    day = min(rule.day_of_month, 28)
    txn_date = f"{year}-{month}-{day:02d}"

    txn = Txn(
        date=txn_date,
        from_account=rule.from_account,
        to_account=rule.to_account,
        amount_cents=rule.amount_cents,
        category=rule.category,
        comment=rule.description,
        tags=rule.tags,
        recurring_id=rule_id,
        created_at=datetime.now(UTC).isoformat(),
    )
    session.add(txn)
    session.flush()

    event = RecurringEvent(
        rule_id=rule_id,
        period=period,
        status="posted",
        amount_cents=rule.amount_cents,
        txn_id=txn.id,
        created_at=datetime.now(UTC).isoformat(),
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def post_all_pending(period: str, session: Session) -> list[RecurringEvent]:
    """Post every rule still pending for the period, in day-of-month order."""
    pending = sorted(pending_for_period(period, session), key=lambda r: r.day_of_month)
    return [post_rule(rule.id, period, session) for rule in pending]  # type: ignore[arg-type]


def skip_rule(rule_id: int, period: str, session: Session) -> RecurringEvent:
    """Mark one month as skipped (no txn)."""
    rule = session.get(RecurringRule, rule_id)
    if rule is None:
        raise ValueError(f"Rule {rule_id} not found")

    existing = session.exec(
        select(RecurringEvent).where(
            RecurringEvent.rule_id == rule_id,
            RecurringEvent.period == period,
        )
    ).first()
    if existing is not None:
        raise ValueError(f"Rule {rule_id} already acted on for period {period}")

    event = RecurringEvent(
        rule_id=rule_id,
        period=period,
        status="skipped",
        amount_cents=None,
        txn_id=None,
        created_at=datetime.now(UTC).isoformat(),
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def edit_rule(rule_id: int, amount_cents: int, session: Session) -> RecurringRule:
    """Edit the rule's amount; takes effect on next post, not retroactively."""
    if amount_cents <= 0:
        raise ValueError("amount_cents must be positive")
    rule = session.get(RecurringRule, rule_id)
    if rule is None:
        raise ValueError(f"Rule {rule_id} not found")
    rule.amount_cents = amount_cents
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule


def update_notes(rule_id: int, notes: str, session: Session) -> RecurringRule:
    rule = session.get(RecurringRule, rule_id)
    if rule is None:
        raise ValueError(f"Rule {rule_id} not found")
    rule.notes = notes or None
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule


def update_tags(rule_id: int, tags: str, session: Session) -> RecurringRule:
    rule = session.get(RecurringRule, rule_id)
    if rule is None:
        raise ValueError(f"Rule {rule_id} not found")
    rule.tags = tags or None
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule


_EDITABLE_FIELDS = {
    "description",
    "category",
    "day_of_month",
    "amount_cents",
    "from_account",
    "to_account",
}


def update_field(rule_id: int, field: str, raw_value: str, session: Session) -> RecurringRule:
    if field not in _EDITABLE_FIELDS:
        raise ValueError(f"field '{field}' is not editable")
    if field == "amount_cents":
        try:
            amount_cents = int(float(raw_value.replace(",", ".")) * 100)
        except ValueError as exc:
            raise ValueError("invalid amount") from exc
        return edit_rule(rule_id, amount_cents, session)

    rule = session.get(RecurringRule, rule_id)
    if rule is None:
        raise ValueError(f"Rule {rule_id} not found")

    if field == "description":
        if not raw_value:
            raise ValueError("description is required")
        rule.description = raw_value
    elif field == "category":
        rule.category = raw_value or None
    elif field == "day_of_month":
        try:
            day = int(raw_value)
        except ValueError as exc:
            raise ValueError("day_of_month must be an integer") from exc
        if not 1 <= day <= 28:
            raise ValueError("day_of_month must be between 1 and 28")
        rule.day_of_month = day
    elif field in ("from_account", "to_account"):
        if not raw_value:
            setattr(rule, field, None)
        else:
            try:
                account_id = int(raw_value)
            except ValueError as exc:
                raise ValueError("invalid account") from exc
            if session.get(Account, account_id) is None:
                raise ValueError(f"Account {account_id} not found")
            setattr(rule, field, account_id)

    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule


def installment_progress(rule_id: int, session: Session) -> tuple[int, int]:
    """Return (posted_count, total_installments).

    total comes from the rule's explicit installments count when set, or is
    derived from the start/end period range otherwise (a rule can be created
    either way). 0 if neither is available.
    """
    rule = session.get(RecurringRule, rule_id)
    if rule is None:
        raise ValueError(f"Rule {rule_id} not found")
    posted = _posted_count(rule_id, session)
    total = rule.installments
    if total is None and rule.kind == "installment" and rule.start_period and rule.end_period:
        total = len(_periods_between(rule.start_period, rule.end_period))
    return posted, total or 0


def list_rules(session: Session, active_only: bool = True) -> list[RecurringRule]:
    stmt = select(RecurringRule)
    if active_only:
        stmt = stmt.where(RecurringRule.active == 1)
    stmt = stmt.order_by(col(RecurringRule.kind), col(RecurringRule.category))
    return list(session.exec(stmt).all())


def is_rule_finished(rule: RecurringRule, session: Session) -> bool:
    """True once the rule's date range has passed or its installments are used up."""
    if _is_finished(rule, session):
        return True
    return bool(rule.end_period and rule.end_period < current_period())


def rules_by_status(session: Session) -> tuple[list[RecurringRule], list[RecurringRule]]:
    """Split rules into (ongoing, finished) buckets for display."""
    rules = list_rules(session)
    active: list[RecurringRule] = []
    finished: list[RecurringRule] = []
    for rule in rules:
        (finished if is_rule_finished(rule, session) else active).append(rule)
    return active, finished


@dataclass
class AccountRuleFlow:
    rule: RecurringRule
    direction: str  # 'in' | 'out', relative to the enclosing AccountNetGroup


@dataclass
class AccountNetGroup:
    account: int | None
    total_cents: int  # net: sum(to_account == account) - sum(from_account == account)
    flows: list[AccountRuleFlow]


def group_active_rules_by_account(session: Session) -> list[AccountNetGroup]:
    """Group currently-active rules by account, netting inflow against outflow.

    Each account that appears as either a rule's from_account or to_account
    gets one group; its total is the sum of rules paying into it minus the
    sum of rules paying out of it (an internal transfer between two of the
    user's own accounts therefore counts as an outflow for one and an
    inflow for the other). Rules with no account on a given side (external)
    are grouped under the None key. Sorted by net total descending.
    """
    active_rules, _ = rules_by_status(session)
    accounts_seen: set[int | None] = set()
    for rule in active_rules:
        accounts_seen.add(rule.to_account)
        accounts_seen.add(rule.from_account)

    result: list[AccountNetGroup] = []
    for account in accounts_seen:
        flows: list[AccountRuleFlow] = []
        net = 0
        for rule in active_rules:
            if rule.to_account == account:
                flows.append(AccountRuleFlow(rule=rule, direction="in"))
                net += rule.amount_cents
            if rule.from_account == account:
                flows.append(AccountRuleFlow(rule=rule, direction="out"))
                net -= rule.amount_cents
        result.append(AccountNetGroup(account=account, total_cents=net, flows=flows))

    result.sort(key=lambda g: g.total_cents, reverse=True)
    return result


def delete_rule(rule_id: int, session: Session, delete_txns: bool = False) -> None:
    """Delete a rule and its events. Attached txns are either deleted too
    (delete_txns=True) or kept but detached from the (now gone) rule.
    """
    rule = session.get(RecurringRule, rule_id)
    if rule is None:
        raise ValueError(f"Rule {rule_id} not found")

    events = session.exec(select(RecurringEvent).where(RecurringEvent.rule_id == rule_id)).all()
    for event in events:
        session.delete(event)

    txns = session.exec(select(Txn).where(Txn.recurring_id == rule_id)).all()
    for txn in txns:
        if delete_txns:
            session.delete(txn)
        else:
            txn.recurring_id = None
            session.add(txn)

    session.delete(rule)
    session.commit()
