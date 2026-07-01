from dataclasses import dataclass
from decimal import Decimal

from sqlmodel import Session, col, select

from app.models.tables import Person, RecurringRule, Setting, Txn
from app.services.recurring import current_period


def _ir_cents(person: Person) -> int:
    return int(Decimal(person.net_before_taxes_cents) * Decimal(str(person.ir_rate)))


@dataclass
class PersonNetIncome:
    person: Person
    ir_cents: int
    net_income_cents: int


def person_net_incomes(session: Session) -> list[PersonNetIncome]:
    people = session.exec(select(Person)).all()
    result: list[PersonNetIncome] = []
    for person in people:
        ir_cents = _ir_cents(person)
        result.append(
            PersonNetIncome(
                person=person,
                ir_cents=ir_cents,
                net_income_cents=person.net_before_taxes_cents - ir_cents,
            )
        )
    return result


@dataclass
class PersonSplit:
    person: Person
    ir_cents: int
    net_income_cents: int
    proportion: Decimal
    contribution_cents: int
    personal_cents: int


@dataclass
class Split:
    people: list[PersonSplit]
    total_net_income_cents: int
    total_fixed_cents: int
    contribution_rate: Decimal


def _split_tags(raw: str | None) -> set[str]:
    if not raw:
        return set()
    return {t.strip() for t in raw.split(",") if t.strip()}


def list_rule_tags(session: Session) -> list[str]:
    """Distinct tags in use across recurring rules, for the fixed-expense-tag picker."""
    raw_values = session.exec(select(RecurringRule.tags)).all()
    tags: set[str] = set()
    for raw in raw_values:
        tags |= _split_tags(raw)
    return sorted(tags)


def fixed_expense_tag(session: Session) -> str | None:
    setting = session.get(Setting, "fixed_expense_tag")
    return setting.value if setting and setting.value else None


def _fixed_costs_cents(session: Session, period: str) -> int:
    tag = fixed_expense_tag(session)
    if tag is None:
        return 0

    txns = session.exec(select(Txn).where(col(Txn.date).like(f"{period}%"))).all()
    return sum(txn.amount_cents for txn in txns if tag in _split_tags(txn.tags))


def compute_split(session: Session, period: str | None = None) -> Split:
    """
    Each person contributes the same percentage of their net income toward
    this period's fixed costs (postings tagged with the fixed-expense tag
    configured on the Settings page; 0 if no tag is configured). What's left
    over is their inferred personal spending money.
    """
    if period is None:
        period = current_period()

    net_incomes = person_net_incomes(session)
    if not net_incomes:
        return Split(
            people=[], total_net_income_cents=0, total_fixed_cents=0, contribution_rate=Decimal(0)
        )

    total_net = sum(ni.net_income_cents for ni in net_incomes)
    total_fixed = _fixed_costs_cents(session, period)
    contribution_rate = Decimal(total_fixed) / Decimal(total_net) if total_net > 0 else Decimal(0)

    result: list[PersonSplit] = []
    for ni in net_incomes:
        proportion = (
            Decimal(ni.net_income_cents) / Decimal(total_net) if total_net > 0 else Decimal(0)
        )
        contribution_cents = round(Decimal(ni.net_income_cents) * contribution_rate)
        result.append(
            PersonSplit(
                person=ni.person,
                ir_cents=ni.ir_cents,
                net_income_cents=ni.net_income_cents,
                proportion=proportion,
                contribution_cents=contribution_cents,
                personal_cents=ni.net_income_cents - contribution_cents,
            )
        )

    return Split(
        people=result,
        total_net_income_cents=total_net,
        total_fixed_cents=total_fixed,
        contribution_rate=contribution_rate,
    )
