from sqlmodel import Session, col, func, select

from app.models.tables import Account, AccountValuation, Txn


def ledger_balance(account_id: int, session: Session, as_of_period: str | None = None) -> int:
    """Raw ledger balance: opening + inflows − outflows, ignoring any recorded valuation.

    If `as_of_period` ('YYYY-MM') is given, only counts txns posted at or
    before the end of that month — used to reconstruct a historical balance.
    """
    account = session.get(Account, account_id)
    if account is None:
        raise ValueError(f"Account {account_id} not found")

    inflow_stmt = select(func.coalesce(func.sum(col(Txn.amount_cents)), 0)).where(
        Txn.to_account == account_id
    )
    outflow_stmt = select(func.coalesce(func.sum(col(Txn.amount_cents)), 0)).where(
        Txn.from_account == account_id
    )
    if as_of_period is not None:
        cutoff = f"{as_of_period}-31"
        inflow_stmt = inflow_stmt.where(col(Txn.date) <= cutoff)
        outflow_stmt = outflow_stmt.where(col(Txn.date) <= cutoff)

    inflow = session.exec(inflow_stmt).one()
    outflow = session.exec(outflow_stmt).one()

    return account.opening_cents + int(inflow) - int(outflow)


def balance(account_id: int, session: Session, as_of_period: str | None = None) -> int:
    """
    Return balance in cents.

    Accounts with at least one recorded valuation (app/services/valuations.py)
    use the latest one as-is — e.g. market-priced wrappers whose value moves
    independently of ledger flows. Otherwise: opening + inflows − outflows.

    If `as_of_period` ('YYYY-MM') is given, returns the balance as it stood at
    the end of that month: the latest valuation at or before that period, or
    else the historical ledger balance as of that period.
    """
    account = session.get(Account, account_id)
    if account is None:
        raise ValueError(f"Account {account_id} not found")
    if as_of_period is not None and as_of_period < account.opening_date[:7]:
        return 0  # account didn't exist yet as of this period

    valuation_stmt = select(AccountValuation).where(AccountValuation.account_id == account_id)
    if as_of_period is not None:
        valuation_stmt = valuation_stmt.where(col(AccountValuation.period) <= as_of_period)
    valuation_stmt = valuation_stmt.order_by(col(AccountValuation.period).desc())

    latest = session.exec(valuation_stmt).first()
    if latest is not None:
        return latest.balance_cents

    return ledger_balance(account_id, session, as_of_period=as_of_period)


def all_balances(session: Session) -> dict[int, int]:
    """Return {account_id: balance_cents} for all active accounts."""
    accounts = session.exec(select(Account).where(Account.active == 1)).all()
    return {a.id: balance(a.id, session) for a in accounts if a.id is not None}


def tier_totals(session: Session, as_of_period: str | None = None) -> dict[str, int]:
    """Return {'Imediato': cents, 'Diferido': cents, 'Alocado': cents}."""
    accounts = session.exec(select(Account).where(Account.active == 1)).all()
    totals: dict[str, int] = {"Imediato": 0, "Diferido": 0, "Alocado": 0}
    for account in accounts:
        if account.id is None:
            continue
        b = balance(account.id, session, as_of_period=as_of_period)
        totals[account.tier] = totals.get(account.tier, 0) + b
    return totals


def grand_total(session: Session, as_of_period: str | None = None) -> int:
    """Return sum of all active account balances in cents."""
    return sum(tier_totals(session, as_of_period=as_of_period).values())
