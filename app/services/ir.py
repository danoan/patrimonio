from dataclasses import dataclass
from decimal import Decimal

from sqlmodel import Session, col, select

from app.models.tables import IrBracket, Person

# French IR 2024 — professional expense deduction
_ABATTEMENT_RATE = Decimal("0.10")
_ABATTEMENT_MIN_CENTS = 44_200  # 442 €
_ABATTEMENT_MAX_CENTS = 1_282_900  # 12 829 €

# Default French IR 2024 brackets (single person, no quotient familial)
DEFAULT_BRACKETS: list[tuple[int, int, float]] = [
    (0, 1_129_400, 0.00),
    (1_129_400, 2_879_700, 0.11),
    (2_879_700, 8_234_100, 0.30),
    (8_234_100, 17_710_600, 0.41),
    (17_710_600, 9_999_999_99, 0.45),
]


@dataclass
class IrResult:
    person_name: str
    gross_annual_cents: int
    deduction_cents: int
    taxable_cents: int
    ir_annual_cents: int
    ir_monthly_cents: int
    effective_rate: float
    delta_cents: int  # ir_monthly_cents − declared PAS: bracket calc vs. declared rate


def _abattement(gross: int) -> int:
    raw = int(Decimal(gross) * _ABATTEMENT_RATE)
    return min(max(raw, _ABATTEMENT_MIN_CENTS), _ABATTEMENT_MAX_CENTS)


def _marginal_tax(taxable_cents: int, brackets: list[IrBracket]) -> int:
    ir = 0
    for bracket in sorted(brackets, key=lambda b: b.lower_cents):
        if taxable_cents <= bracket.lower_cents:
            break
        slice_top = min(taxable_cents, bracket.upper_cents)
        ir += int(Decimal(slice_top - bracket.lower_cents) * Decimal(str(bracket.rate)))
    return ir


def compute_ir_for_income(gross_annual_cents: int, brackets: list[IrBracket]) -> int:
    """
    Flat bracket calc, no quotient familial.
    Applies 10 % professional deduction first, then marginal brackets.
    """
    deduction = _abattement(gross_annual_cents)
    taxable = gross_annual_cents - deduction
    return _marginal_tax(taxable, brackets)


def compute_ir(session: Session) -> list[IrResult]:
    people = session.exec(select(Person)).all()
    brackets = list(
        session.exec(select(IrBracket).order_by(col(IrBracket.lower_cents)))  # type: ignore[arg-type]
    )

    results: list[IrResult] = []
    for person in people:
        annual = person.gross_cents * 12
        # Taxable income is estimated from the 12-month average of net
        # before taxes (net imposable), annualized; the deduction shown is
        # just gross − taxable, i.e. an estimate of the professional
        # expenses already netted out on the payslip, not a separate input.
        taxable = person.net_before_taxes_avg_cents * 12
        deduction = annual - taxable
        ir_annual = _marginal_tax(taxable, brackets)
        ir_monthly = ir_annual // 12
        effective = ir_annual / annual if annual > 0 else 0.0
        declared_ir_monthly = int(
            Decimal(person.net_before_taxes_cents) * Decimal(str(person.ir_rate))
        )
        results.append(
            IrResult(
                person_name=person.name,
                gross_annual_cents=annual,
                deduction_cents=deduction,
                taxable_cents=taxable,
                ir_annual_cents=ir_annual,
                ir_monthly_cents=ir_monthly,
                effective_rate=effective,
                delta_cents=ir_monthly - declared_ir_monthly,
            )
        )
    return results


def seed_default_brackets(session: Session) -> None:
    """Insert the default French IR 2024 brackets if the table is empty."""
    existing = session.exec(select(IrBracket)).first()
    if existing is not None:
        return
    for lower, upper, rate in DEFAULT_BRACKETS:
        session.add(IrBracket(lower_cents=lower, upper_cents=upper, rate=rate))
    session.commit()


def list_brackets(session: Session) -> list[IrBracket]:
    return list(
        session.exec(select(IrBracket).order_by(col(IrBracket.lower_cents)))  # type: ignore[arg-type]
    )


def replace_brackets(new_brackets: list[tuple[int, int, float]], session: Session) -> None:
    """Replace all brackets with a new set (used from the config form)."""
    for b in session.exec(select(IrBracket)).all():
        session.delete(b)
    session.flush()
    for lower, upper, rate in new_brackets:
        session.add(IrBracket(lower_cents=lower, upper_cents=upper, rate=rate))
    session.commit()
