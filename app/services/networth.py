from dataclasses import dataclass
from datetime import date

from sqlmodel import Session, col, select

from app.models.tables import Account, NetworthSnapshot, Txn
from app.services import balances

_TIERS = ("Imediato", "Diferido", "Alocado")


@dataclass
class MonthlyNetworth:
    period: str  # 'YYYY-MM'
    tier_totals: dict[str, int]
    grand_total: int


def _current_period() -> str:
    today = date.today()
    return f"{today.year}-{today.month:02d}"


def _periods_between(start_period: str, end_period: str) -> list[str]:
    """Inclusive list of 'YYYY-MM' periods from start_period to end_period."""
    start_year, start_month = (int(p) for p in start_period.split("-"))
    end_year, end_month = (int(p) for p in end_period.split("-"))
    periods: list[str] = []
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        periods.append(f"{year}-{month:02d}")
        month += 1
        if month > 12:
            month = 1
            year += 1
    return periods


def _cached_totals(period: str, session: Session) -> dict[str, int] | None:
    rows = session.exec(select(NetworthSnapshot).where(NetworthSnapshot.period == period)).all()
    totals = {row.tier: row.total_cents for row in rows}
    if all(tier in totals for tier in _TIERS):
        return totals
    return None


def _store_snapshot(period: str, totals: dict[str, int], session: Session) -> None:
    for tier in _TIERS:
        existing = session.get(NetworthSnapshot, (period, tier))
        if existing is not None:
            existing.total_cents = totals[tier]
            session.add(existing)
        else:
            session.add(NetworthSnapshot(period=period, tier=tier, total_cents=totals[tier]))
    session.commit()


def monthly_history(session: Session) -> list[MonthlyNetworth]:
    """
    Historical net worth by month, from the earliest account/txn to the current month.

    Closed (past) months are cached in `NetworthSnapshot` after first
    computation. The current, still-open month is always recomputed live.
    """
    earliest_txn_date = session.exec(select(Txn.date).order_by(col(Txn.date)).limit(1)).first()
    earliest_account_date = session.exec(
        select(Account.opening_date).order_by(col(Account.opening_date)).limit(1)
    ).first()
    candidates = [d for d in (earliest_txn_date, earliest_account_date) if d is not None]
    if not candidates:
        return []

    start_period = min(candidates)[:7]
    end_period = _current_period()
    result: list[MonthlyNetworth] = []

    for period in _periods_between(start_period, end_period):
        if period == end_period:
            totals = balances.tier_totals(session, as_of_period=period)
        else:
            totals = _cached_totals(period, session)
            if totals is None:
                totals = balances.tier_totals(session, as_of_period=period)
                _store_snapshot(period, totals, session)

        result.append(
            MonthlyNetworth(period=period, tier_totals=totals, grand_total=sum(totals.values()))
        )

    return result


@dataclass
class ChartPoint:
    period: str
    grand_total: int
    x_pct: float  # 0–100, for SVG positioning
    y_pct: float  # 0–100, inverted (0 = top in SVG)


def to_chart_points(history: list[MonthlyNetworth]) -> list[ChartPoint]:
    """Convert monthly history to normalised SVG coordinates."""
    if not history:
        return []
    totals = [m.grand_total for m in history]
    min_val = min(totals)
    max_val = max(totals)
    span = max_val - min_val or 1
    n = len(history)
    return [
        ChartPoint(
            period=m.period,
            grand_total=m.grand_total,
            x_pct=i / (n - 1) * 100 if n > 1 else 50.0,
            y_pct=(1 - (m.grand_total - min_val) / span) * 100,
        )
        for i, m in enumerate(history)
    ]
