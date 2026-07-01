from dataclasses import dataclass
from datetime import UTC, datetime

from sqlmodel import Session, col, func, select

from app.models.tables import Account, AccountValuation, Txn
from app.schemas.forms import AccountValuationCreate
from app.services.balances import ledger_balance


def record_valuation(
    account_id: int, data: AccountValuationCreate, session: Session
) -> AccountValuation:
    account = session.get(Account, account_id)
    if account is None:
        raise ValueError(f"Account {account_id} not found")

    existing = session.get(AccountValuation, (account_id, data.period))
    if existing is not None:
        existing.balance_cents = data.balance_cents
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    valuation = AccountValuation(
        account_id=account_id,
        period=data.period,
        balance_cents=data.balance_cents,
        created_at=datetime.now(UTC).isoformat(),
    )
    session.add(valuation)
    session.commit()
    session.refresh(valuation)
    return valuation


def delete_valuation(account_id: int, period: str, session: Session) -> None:
    valuation = session.get(AccountValuation, (account_id, period))
    if valuation is None:
        raise ValueError(f"No valuation for account {account_id} in {period}")
    session.delete(valuation)
    session.commit()


def list_valuations(account_id: int, session: Session) -> list[AccountValuation]:
    return list(
        session.exec(
            select(AccountValuation)
            .where(AccountValuation.account_id == account_id)
            .order_by(col(AccountValuation.period))
        ).all()
    )


def latest_valuation(account_id: int, session: Session) -> AccountValuation | None:
    return session.exec(
        select(AccountValuation)
        .where(AccountValuation.account_id == account_id)
        .order_by(col(AccountValuation.period).desc())
    ).first()


def _net_flow_cents(account_id: int, session: Session, period: str) -> int:
    """Net ledger flow into the account (inflows − outflows) during one period."""
    inflow = session.exec(
        select(func.coalesce(func.sum(col(Txn.amount_cents)), 0)).where(
            Txn.to_account == account_id, col(Txn.date).like(f"{period}%")
        )
    ).one()
    outflow = session.exec(
        select(func.coalesce(func.sum(col(Txn.amount_cents)), 0)).where(
            Txn.from_account == account_id, col(Txn.date).like(f"{period}%")
        )
    ).one()
    return int(inflow) - int(outflow)


def net_contributed_cents(account_id: int, session: Session) -> int:
    """Cost basis: opening balance + all-time net ledger flow (money actually put in/taken out)."""
    return ledger_balance(account_id, session)


@dataclass
class AccountPerformance:
    market_value_cents: int
    net_contributed_cents: int
    unrealized_gain_cents: int
    unrealized_gain_pct: float | None  # None if nothing has been contributed yet


def performance(account_id: int, session: Session) -> AccountPerformance | None:
    """None if the account has no recorded valuation yet."""
    latest = latest_valuation(account_id, session)
    if latest is None:
        return None
    contributed = net_contributed_cents(account_id, session)
    gain = latest.balance_cents - contributed
    pct = gain / contributed if contributed > 0 else None
    return AccountPerformance(
        market_value_cents=latest.balance_cents,
        net_contributed_cents=contributed,
        unrealized_gain_cents=gain,
        unrealized_gain_pct=pct,
    )


@dataclass
class ValuationPoint:
    period: str
    balance_cents: int
    contributions_cents: int  # net ledger flow during this period
    gain_cents: int  # (balance − prev_balance) − contributions: market-driven change
    gain_pct: float | None  # gain / prev_balance


def valuation_history(account_id: int, session: Session) -> list[ValuationPoint]:
    rows = list_valuations(account_id, session)
    result: list[ValuationPoint] = []
    prev_balance: int | None = None
    for row in rows:
        contributions = _net_flow_cents(account_id, session, row.period)
        if prev_balance is None:
            gain = 0
            gain_pct = None
        else:
            gain = (row.balance_cents - prev_balance) - contributions
            gain_pct = gain / prev_balance if prev_balance > 0 else None
        result.append(
            ValuationPoint(
                period=row.period,
                balance_cents=row.balance_cents,
                contributions_cents=contributions,
                gain_cents=gain,
                gain_pct=gain_pct,
            )
        )
        prev_balance = row.balance_cents
    return result


@dataclass
class ValuationChartPoint:
    period: str
    balance_cents: int
    x_pct: float
    y_pct: float


def to_chart_points(rows: list[AccountValuation]) -> list[ValuationChartPoint]:
    if not rows:
        return []
    values = [r.balance_cents for r in rows]
    min_val = min(values)
    max_val = max(values)
    span = max_val - min_val or 1
    n = len(rows)
    return [
        ValuationChartPoint(
            period=r.period,
            balance_cents=r.balance_cents,
            x_pct=i / (n - 1) * 100 if n > 1 else 50.0,
            y_pct=(1 - (r.balance_cents - min_val) / span) * 100,
        )
        for i, r in enumerate(rows)
    ]
