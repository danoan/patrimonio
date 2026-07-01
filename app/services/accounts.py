from sqlmodel import Session, select

from app.models.tables import Account
from app.schemas.forms import AccountCreate


def list_accounts(session: Session, active_only: bool = True) -> list[Account]:
    stmt = select(Account)
    if active_only:
        stmt = stmt.where(Account.active == 1)
    stmt = stmt.order_by(Account.sort_order, Account.code)  # type: ignore[arg-type]
    return list(session.exec(stmt).all())


def get_account(code: str, session: Session) -> Account | None:
    return session.exec(select(Account).where(Account.code == code)).first()


def get_account_by_id(account_id: int, session: Session) -> Account | None:
    return session.get(Account, account_id)


def create_account(data: AccountCreate, session: Session) -> Account:
    existing = get_account(data.code, session)
    if existing is not None:
        raise ValueError(f"Account code '{data.code}' already exists")
    account = Account(
        code=data.code,
        name=data.name,
        tier=data.tier,
        account_type=data.account_type,
        currency=data.currency,
        opening_cents=data.opening_cents,
        opening_date=data.opening_date,
    )
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


def rename_account(account_id: int, name: str, session: Session) -> Account:
    account = session.get(Account, account_id)
    if account is None:
        raise ValueError(f"Account {account_id} not found")
    account.name = name
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


def retier_account(account_id: int, tier: str, session: Session) -> Account:
    allowed = {"Imediato", "Diferido", "Alocado"}
    if tier not in allowed:
        raise ValueError(f"tier must be one of {allowed}")
    account = session.get(Account, account_id)
    if account is None:
        raise ValueError(f"Account {account_id} not found")
    account.tier = tier
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


def retype_account(account_id: int, account_type: str, session: Session) -> Account:
    allowed = {"checking", "savings", "variable"}
    if account_type not in allowed:
        raise ValueError(f"account_type must be one of {allowed}")
    account = session.get(Account, account_id)
    if account is None:
        raise ValueError(f"Account {account_id} not found")
    account.account_type = account_type
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


_EDITABLE_FIELDS = {"name", "tier", "account_type", "currency", "opening_cents", "opening_date"}


def update_field(account_id: int, field: str, raw_value: str, session: Session) -> Account:
    if field not in _EDITABLE_FIELDS:
        raise ValueError(f"field '{field}' is not editable")
    if field == "name":
        return rename_account(account_id, raw_value, session)
    if field == "tier":
        return retier_account(account_id, raw_value, session)
    if field == "account_type":
        return retype_account(account_id, raw_value, session)

    account = session.get(Account, account_id)
    if account is None:
        raise ValueError(f"Account {account_id} not found")

    if field == "currency":
        if raw_value not in {"EUR", "USD"}:
            raise ValueError("currency must be EUR or USD")
        account.currency = raw_value
    elif field == "opening_cents":
        try:
            account.opening_cents = int(float(raw_value.replace(",", ".")) * 100)
        except ValueError as exc:
            raise ValueError("invalid amount") from exc
    elif field == "opening_date":
        if not raw_value:
            raise ValueError("opening_date is required")
        account.opening_date = raw_value

    session.add(account)
    session.commit()
    session.refresh(account)
    return account


def deactivate_account(account_id: int, session: Session) -> Account:
    account = session.get(Account, account_id)
    if account is None:
        raise ValueError(f"Account {account_id} not found")
    account.active = 0
    session.add(account)
    session.commit()
    session.refresh(account)
    return account
