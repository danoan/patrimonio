from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlmodel import Session, select

from app.models.tables import ExpectedYield, RecurringEvent, RecurringRule
from app.services.accounts import list_accounts
from app.services.balances import balance


@dataclass
class MonthProjection:
    period: str  # 'YYYY-MM'
    balances: dict[int, int]  # account_id → cents (snapshot)
    tier_totals: dict[str, int]
    grand_total: int


def _posted_count(rule_id: int, session: Session) -> int:
    return len(
        session.exec(
            select(RecurringEvent).where(
                RecurringEvent.rule_id == rule_id,
                RecurringEvent.status == "posted",
            )
        ).all()
    )


def _advance_period(year: int, month: int) -> tuple[int, int]:
    month += 1
    if month > 12:
        month = 1
        year += 1
    return year, month


def project(session: Session, months: int = 24) -> list[MonthProjection]:
    """
    Forward net-worth projection.

    For each future month:
    - Apply recurring rule cash flows (installments stop when exhausted).
    - Compound each account by its expected annual yield (monthly rate).
    """
    accounts = list_accounts(session)
    current: dict[int, int] = {
        a.id: balance(a.id, session)  # type: ignore[arg-type]
        for a in accounts
        if a.id is not None
    }
    tier_map: dict[int, str] = {a.id: a.tier for a in accounts if a.id is not None}  # type: ignore[arg-type]

    rules = session.exec(select(RecurringRule).where(RecurringRule.active == 1)).all()

    # Remaining posts per installment rule (None = fixed/infinite)
    remaining: dict[int, int | None] = {}
    for rule in rules:
        if rule.id is None:
            continue
        if rule.kind == "installment" and rule.installments is not None:
            remaining[rule.id] = max(0, rule.installments - _posted_count(rule.id, session))
        else:
            remaining[rule.id] = None

    yields: dict[int, Decimal] = {
        ey.account_id: Decimal(str(ey.annual_rate))
        for ey in session.exec(select(ExpectedYield)).all()
    }

    today = date.today()
    year, month = today.year, today.month
    result: list[MonthProjection] = []

    for _ in range(months):
        year, month = _advance_period(year, month)
        period = f"{year}-{month:02d}"

        # Apply yield (monthly compounding)
        for account_id, annual_rate in yields.items():
            if account_id in current:
                monthly = annual_rate / 12
                current[account_id] = int(Decimal(current[account_id]) * (1 + monthly))

        # Apply recurring cash flows
        for rule in rules:
            if rule.id is None:
                continue
            rem = remaining.get(rule.id)
            if rem is not None and rem <= 0:
                continue  # installment exhausted

            if rule.from_account is not None and rule.from_account in current:
                current[rule.from_account] -= rule.amount_cents
            if rule.to_account is not None and rule.to_account in current:
                current[rule.to_account] += rule.amount_cents

            if rem is not None:
                remaining[rule.id] = rem - 1

        # Snapshot tier totals
        tier_totals: dict[str, int] = {"Imediato": 0, "Diferido": 0, "Alocado": 0}
        for account_id, bal in current.items():
            tier = tier_map.get(account_id)
            if tier:
                tier_totals[tier] = tier_totals.get(tier, 0) + bal

        result.append(
            MonthProjection(
                period=period,
                balances=dict(current),
                tier_totals=dict(tier_totals),
                grand_total=sum(tier_totals.values()),
            )
        )

    return result


@dataclass
class ChartPoint:
    period: str
    grand_total: int
    x_pct: float  # 0–100, for SVG positioning
    y_pct: float  # 0–100, inverted (0 = top in SVG)


def to_chart_points(projections: list[MonthProjection]) -> list[ChartPoint]:
    """Convert projection data to normalised SVG coordinates."""
    if not projections:
        return []
    totals = [p.grand_total for p in projections]
    min_val = min(totals)
    max_val = max(totals)
    span = max_val - min_val or 1
    n = len(projections)
    return [
        ChartPoint(
            period=p.period,
            grand_total=p.grand_total,
            x_pct=i / (n - 1) * 100 if n > 1 else 50.0,
            y_pct=(1 - (p.grand_total - min_val) / span) * 100,
        )
        for i, p in enumerate(projections)
    ]
