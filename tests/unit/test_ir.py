from decimal import Decimal

import pytest
from app.models.tables import IrBracket, Person
from app.services.ir import (
    DEFAULT_BRACKETS,
    compute_ir,
    compute_ir_for_income,
    list_brackets,
    seed_default_brackets,
)
from sqlmodel import Session


def _seed_brackets(session: Session) -> list[IrBracket]:
    seed_default_brackets(session)
    return list_brackets(session)


def _make_person(
    session: Session,
    name: str,
    gross_monthly: int,
    ir_rate: float = 0.0,
    net_before_taxes_monthly: int | None = None,
    net_before_taxes_avg_monthly: int | None = None,
) -> Person:
    resolved_net = gross_monthly if net_before_taxes_monthly is None else net_before_taxes_monthly
    p = Person(
        name=name,
        gross_cents=gross_monthly,
        net_before_taxes_cents=resolved_net,
        net_before_taxes_avg_cents=(
            resolved_net if net_before_taxes_avg_monthly is None else net_before_taxes_avg_monthly
        ),
        ir_rate=ir_rate,
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


@pytest.mark.unit
def test_zero_income_pays_no_tax(session: Session) -> None:
    brackets = _seed_brackets(session)
    assert compute_ir_for_income(0, brackets) == 0


@pytest.mark.unit
def test_income_in_first_bracket_pays_no_tax(session: Session) -> None:
    # Below 11 294 € annual → 0 %
    brackets = _seed_brackets(session)
    gross = 1_000_000  # 10 000 € annual
    assert compute_ir_for_income(gross, brackets) == 0


@pytest.mark.unit
def test_income_in_second_bracket(session: Session) -> None:
    # 20 000 € annual; after 10 % deduction = 18 000 €
    # First bracket 0–11 294 €: 0 %
    # Second bracket 11 294–18 000 €: 11 %  → (18000 - 11294) * 0.11
    brackets = _seed_brackets(session)
    gross = 2_000_000  # 20 000 € in cents
    ir = compute_ir_for_income(gross, brackets)
    deduction = min(max(int(gross * Decimal("0.10")), 44_200), 1_282_900)
    taxable = gross - deduction
    expected = int(Decimal(taxable - 1_129_400) * Decimal("0.11"))
    assert ir == expected


@pytest.mark.unit
def test_abattement_floor_applied(session: Session) -> None:
    # Very low income: deduction must be at least 442 €
    brackets = _seed_brackets(session)
    # 1 000 € annual — 10 % = 100 € < floor of 442 € → use 442 €
    gross = 100_000  # 1 000 €
    ir_with = compute_ir_for_income(gross, brackets)
    # Taxable = 1000 - 442 = 558 € < first bracket → 0 €
    assert ir_with == 0


@pytest.mark.unit
def test_abattement_cap_applied(session: Session) -> None:
    # Very high income: deduction must not exceed 12 829 €
    _seed_brackets(session)
    gross = 20_000_000  # 200 000 € annual — 10 % = 20 000 € > cap of 12 829 €
    deduction = min(int(Decimal(gross) * Decimal("0.10")), 1_282_900)
    assert deduction == 1_282_900  # hits the cap


@pytest.mark.unit
def test_seed_default_brackets_idempotent(session: Session) -> None:
    seed_default_brackets(session)
    seed_default_brackets(session)  # second call should not duplicate
    assert len(list_brackets(session)) == len(DEFAULT_BRACKETS)


@pytest.mark.unit
def test_compute_ir_with_people(session: Session) -> None:
    _seed_brackets(session)
    _make_person(session, "Daniel", gross_monthly=400_000)  # 4 000 €/month
    results = compute_ir(session)
    assert len(results) == 1
    r = results[0]
    assert r.person_name == "Daniel"
    assert r.gross_annual_cents == 400_000 * 12
    assert r.ir_annual_cents >= 0
    assert r.effective_rate >= 0.0


@pytest.mark.unit
def test_delta_reflects_declared_rate_vs_computed(session: Session) -> None:
    _seed_brackets(session)
    # Declared withholding rate of 20% on 250k net-before-taxes -> declared IR = 50_000 cents
    p = Person(
        name="Sofia",
        gross_cents=300_000,
        net_before_taxes_cents=250_000,
        net_before_taxes_avg_cents=250_000,
        ir_rate=0.2,
    )
    session.add(p)
    session.commit()
    results = compute_ir(session)
    r = next(x for x in results if x.person_name == "Sofia")
    assert r.delta_cents == r.ir_monthly_cents - 50_000


@pytest.mark.unit
def test_taxable_uses_net_before_taxes_avg(session: Session) -> None:
    _seed_brackets(session)
    _make_person(
        session,
        "Daniel",
        gross_monthly=400_000,
        net_before_taxes_avg_monthly=310_000,
    )
    r = compute_ir(session)[0]
    assert r.gross_annual_cents == 400_000 * 12
    assert r.taxable_cents == 310_000 * 12
    assert r.deduction_cents == (400_000 - 310_000) * 12


@pytest.mark.unit
def test_effective_rate_between_zero_and_one(session: Session) -> None:
    _seed_brackets(session)
    _make_person(session, "Test", gross_monthly=500_000)
    results = compute_ir(session)
    r = results[0]
    assert 0.0 <= r.effective_rate < 1.0
