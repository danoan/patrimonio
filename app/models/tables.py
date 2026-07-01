from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class Account(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(unique=True)
    name: str
    tier: str  # 'Imediato' | 'Diferido' | 'Alocado'
    account_type: str = Field(default="checking")  # 'checking' | 'savings' | 'variable'
    currency: str = Field(default="EUR")
    opening_cents: int = Field(default=0)
    opening_date: str  # ISO date YYYY-MM-DD
    active: int = Field(default=1)
    sort_order: int = Field(default=0)


class AccountValuation(SQLModel, table=True):
    # Manually recorded mark-to-market balance, for accounts whose value moves
    # independently of ledger flows (e.g. assurance-vie wrappers).
    account_id: int = Field(foreign_key="account.id", primary_key=True)
    period: str = Field(primary_key=True)  # 'YYYY-MM'
    balance_cents: int
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class Txn(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    date: str  # ISO date YYYY-MM-DD
    from_account: int | None = Field(default=None, foreign_key="account.id")
    to_account: int | None = Field(default=None, foreign_key="account.id")
    amount_cents: int = Field(gt=0)
    category: str | None = Field(default=None)
    comment: str | None = Field(default=None)
    tags: str | None = Field(default=None)  # comma-separated, free text
    recurring_id: int | None = Field(default=None, foreign_key="recurringrule.id")
    trade_id: int | None = Field(default=None, foreign_key="trade.id")
    source_year: int | None = Field(default=None)
    needs_resolution: int = Field(default=0)
    resolved_txn_id: int | None = Field(default=None, foreign_key="txn.id")
    resolution_note: str | None = Field(default=None)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class TxnNote(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    txn_id: int = Field(foreign_key="txn.id")
    text: str
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class RecurringRule(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    kind: str  # 'fixed' | 'installment'
    description: str
    from_account: int | None = Field(default=None, foreign_key="account.id")
    to_account: int | None = Field(default=None, foreign_key="account.id")
    amount_cents: int
    category: str | None = Field(default=None)
    day_of_month: int = Field(default=1)
    start_period: str | None = Field(default=None)  # 'YYYY-MM'
    end_period: str | None = Field(default=None)  # 'YYYY-MM', inclusive; None = open-ended
    installments: int | None = Field(default=None)
    active: int = Field(default=1)
    notes: str | None = Field(default=None)
    tags: str | None = Field(default=None)  # comma-separated, free text
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class RecurringEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    rule_id: int = Field(foreign_key="recurringrule.id")
    period: str  # 'YYYY-MM'
    status: str  # 'posted' | 'skipped'
    amount_cents: int | None = Field(default=None)
    txn_id: int | None = Field(default=None, foreign_key="txn.id")
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class Instrument(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    ticker: str = Field(unique=True)
    name: str | None = Field(default=None)
    currency: str = Field(default="EUR")


# Re-export with lowercase alias used in __init__.py
instrument = Instrument


class Trade(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    instrument_id: int = Field(foreign_key="instrument.id")
    kind: str  # 'buy' | 'sell'
    date: str  # ISO date YYYY-MM-DD
    qty: int
    price_cents: int
    order_cost_cents: int = Field(default=0)
    realized_cents: int | None = Field(default=None)
    tax_reserved_cents: int | None = Field(default=None)
    is_opening: int = Field(default=0)
    source_year: int | None = Field(default=None)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class Price(SQLModel, table=True):
    instrument_id: int = Field(foreign_key="instrument.id", primary_key=True)
    price_cents: int
    as_of: str = Field(primary_key=True)  # ISO date


class UsdEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    instrument_id: int | None = Field(default=None, foreign_key="instrument.id")
    date: str  # ISO date
    kind: str  # 'vesting' | 'sale'
    gross_usd_cents: int
    net_usd_cents: int
    fx_eur_per_usd: float
    landed_txn_id: int | None = Field(default=None, foreign_key="txn.id")
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class Person(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    gross_cents: int
    net_before_taxes_cents: int  # net imposable — base for the prélèvement à la source
    net_before_taxes_avg_cents: int  # 12-month average net imposable — base for the IR estimate
    ir_rate: float  # taux de prélèvement à la source, e.g. 0.224 for 22.4%


class IrBracket(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    lower_cents: int
    upper_cents: int
    rate: float


class ExpectedYield(SQLModel, table=True):
    account_id: int = Field(foreign_key="account.id", primary_key=True)
    annual_rate: float


class Setting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str


class NetworthSnapshot(SQLModel, table=True):
    period: str = Field(primary_key=True)  # 'YYYY-MM'
    tier: str = Field(primary_key=True)
    total_cents: int
