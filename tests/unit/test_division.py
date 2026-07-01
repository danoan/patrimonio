from decimal import Decimal

import pytest
from app.models.tables import Person, RecurringRule, Setting
from app.schemas.forms import AccountCreate, TxnCreate
from app.services.accounts import create_account
from app.services.division import compute_split, fixed_expense_tag, list_rule_tags
from app.services.ledger import create_txn
from app.services.recurring import current_period
from sqlmodel import Session


def _add_person(
    session: Session, name: str, gross: int, ir_rate: float, net_before_taxes: int | None = None
) -> Person:
    resolved_net = gross if net_before_taxes is None else net_before_taxes
    p = Person(
        name=name,
        gross_cents=gross,
        net_before_taxes_cents=resolved_net,
        net_before_taxes_avg_cents=resolved_net,
        ir_rate=ir_rate,
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def _seed_fixed_cost(session: Session, amount_cents: int, tag: str = "despesa-fixa") -> None:
    account = create_account(
        AccountCreate(
            code="FIXED-COSTS",
            name="Fixed costs",
            tier="Imediato",
            opening_date="2024-01-01",
        ),
        session,
    )
    session.add(Setting(key="fixed_expense_tag", value=tag))
    create_txn(
        TxnCreate(
            date=f"{current_period()}-05",
            from_account=account.id,
            amount_cents=amount_cents,
            category="Despesa fixa",
            tags=tag,
        ),
        session,
    )


@pytest.mark.unit
def test_proportions_sum_to_one(session: Session) -> None:
    _add_person(session, "Daniel", gross=400000, ir_rate=0.2)
    _add_person(session, "Sofia", gross=300000, ir_rate=0.1)
    split = compute_split(session)
    total_prop = sum(ps.proportion for ps in split.people)
    assert total_prop == Decimal("1")


@pytest.mark.unit
def test_proportions_reflect_net_income(session: Session) -> None:
    # Daniel net = 400k - 20% * 400k = 320k
    # Sofia  net = 300k - 10% * 300k = 270k
    # Total = 590k
    _add_person(session, "D", gross=400000, ir_rate=0.2)
    _add_person(session, "S", gross=300000, ir_rate=0.1)
    split = compute_split(session)
    d_split = next(ps for ps in split.people if ps.person.name == "D")
    s_split = next(ps for ps in split.people if ps.person.name == "S")
    assert d_split.net_income_cents == 320000
    assert s_split.net_income_cents == 270000
    assert d_split.proportion + s_split.proportion == Decimal("1")


@pytest.mark.unit
def test_empty_split(session: Session) -> None:
    split = compute_split(session)
    assert split.people == []
    assert split.total_net_income_cents == 0
    assert split.total_fixed_cents == 0
    assert split.contribution_rate == Decimal(0)


@pytest.mark.unit
def test_single_person_no_fixed_costs(session: Session) -> None:
    _add_person(session, "Solo", gross=200000, ir_rate=0.15)
    split = compute_split(session)
    assert len(split.people) == 1
    ps = split.people[0]
    assert ps.proportion == Decimal("1")
    assert ps.contribution_cents == 0
    assert ps.personal_cents == ps.net_income_cents


@pytest.mark.unit
def test_contribution_and_personal_split_with_fixed_costs(session: Session) -> None:
    # Daniel net = 320k, Sofia net = 270k, total net = 590k
    # Fixed costs posted this period = 59k -> contribution_rate = 10%
    _add_person(session, "Daniel", gross=400000, ir_rate=0.2)
    _add_person(session, "Sofia", gross=300000, ir_rate=0.1)
    _seed_fixed_cost(session, 59_000)

    split = compute_split(session)
    assert split.total_fixed_cents == 59_000
    assert split.contribution_rate == Decimal(59_000) / Decimal(590_000)

    daniel = next(ps for ps in split.people if ps.person.name == "Daniel")
    sofia = next(ps for ps in split.people if ps.person.name == "Sofia")
    assert daniel.contribution_cents == round(Decimal(320_000) * split.contribution_rate)
    assert sofia.contribution_cents == round(Decimal(270_000) * split.contribution_rate)
    assert daniel.personal_cents == daniel.net_income_cents - daniel.contribution_cents
    assert sofia.personal_cents == sofia.net_income_cents - sofia.contribution_cents


@pytest.mark.unit
def test_fixed_expense_tag_unset_returns_none(session: Session) -> None:
    assert fixed_expense_tag(session) is None


@pytest.mark.unit
def test_fixed_expense_tag_reads_setting(session: Session) -> None:
    session.add(Setting(key="fixed_expense_tag", value="casa"))
    session.commit()
    assert fixed_expense_tag(session) == "casa"


@pytest.mark.unit
def test_fixed_expense_tag_blank_setting_is_none(session: Session) -> None:
    session.add(Setting(key="fixed_expense_tag", value=""))
    session.commit()
    assert fixed_expense_tag(session) is None


@pytest.mark.unit
def test_list_rule_tags_dedupes_and_sorts(session: Session) -> None:
    session.add(RecurringRule(kind="fixed", description="A", amount_cents=100, tags="casa, fixo"))
    session.add(RecurringRule(kind="fixed", description="B", amount_cents=200, tags="viagem"))
    session.add(RecurringRule(kind="fixed", description="C", amount_cents=300, tags="fixo"))
    session.add(RecurringRule(kind="fixed", description="D", amount_cents=400, tags=None))
    session.commit()
    assert list_rule_tags(session) == ["casa", "fixo", "viagem"]


@pytest.mark.unit
def test_compute_split_uses_tag_when_configured(session: Session) -> None:
    account = create_account(
        AccountCreate(
            code="TAG-FIXED", name="Tag fixed", tier="Imediato", opening_date="2024-01-01"
        ),
        session,
    )
    period = current_period()
    create_txn(
        TxnCreate(
            date=f"{period}-05",
            from_account=account.id,
            amount_cents=50_000,
            category="Despesa fixa",
            tags="casa",
        ),
        session,
    )
    # This one should be ignored: no "casa" tag, even though category matches.
    create_txn(
        TxnCreate(
            date=f"{period}-06",
            from_account=account.id,
            amount_cents=9_000,
            category="Despesa fixa",
        ),
        session,
    )
    session.add(Setting(key="fixed_expense_tag", value="casa"))
    session.commit()

    _add_person(session, "Daniel", gross=400000, ir_rate=0.2)
    split = compute_split(session)
    assert split.total_fixed_cents == 50_000


@pytest.mark.unit
def test_no_posted_costs_means_all_personal(session: Session) -> None:
    _add_person(session, "Daniel", gross=400000, ir_rate=0.2)
    split = compute_split(session)
    ps = split.people[0]
    assert split.contribution_rate == Decimal(0)
    assert ps.contribution_cents == 0
    assert ps.personal_cents == ps.net_income_cents
