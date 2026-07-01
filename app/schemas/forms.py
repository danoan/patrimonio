from pydantic import BaseModel, field_validator, model_validator


class AccountCreate(BaseModel):
    code: str
    name: str
    tier: str
    account_type: str = "checking"
    currency: str = "EUR"
    opening_cents: int = 0
    opening_date: str  # YYYY-MM-DD

    @field_validator("tier")
    @classmethod
    def validate_tier(cls, v: str) -> str:
        allowed = {"Imediato", "Diferido", "Alocado"}
        if v not in allowed:
            raise ValueError(f"tier must be one of {allowed}")
        return v

    @field_validator("account_type")
    @classmethod
    def validate_account_type(cls, v: str) -> str:
        allowed = {"checking", "savings", "variable"}
        if v not in allowed:
            raise ValueError(f"account_type must be one of {allowed}")
        return v

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        if v not in {"EUR", "USD"}:
            raise ValueError("currency must be EUR or USD")
        return v


class AccountValuationCreate(BaseModel):
    period: str  # YYYY-MM
    balance_cents: int

    @field_validator("balance_cents")
    @classmethod
    def non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("balance_cents must not be negative")
        return v


class AccountUpdate(BaseModel):
    name: str | None = None
    tier: str | None = None

    @field_validator("tier")
    @classmethod
    def validate_tier(cls, v: str | None) -> str | None:
        if v is not None and v not in {"Imediato", "Diferido", "Alocado"}:
            raise ValueError("tier must be one of Imediato, Diferido, Alocado")
        return v


class TxnCreate(BaseModel):
    date: str  # YYYY-MM-DD
    from_account: int | None = None
    to_account: int | None = None
    amount_cents: int
    category: str | None = None
    comment: str | None = None
    tags: str | None = None
    needs_resolution: bool = False

    @field_validator("amount_cents")
    @classmethod
    def positive_amount(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("amount_cents must be positive")
        return v

    @model_validator(mode="after")
    def at_least_one_account(self) -> "TxnCreate":
        if self.from_account is None and self.to_account is None:
            raise ValueError("at least one of from_account or to_account must be set")
        return self


class RecurringRuleCreate(BaseModel):
    kind: str
    description: str
    from_account: int | None = None
    to_account: int | None = None
    amount_cents: int
    category: str | None = None
    day_of_month: int = 1
    start_period: str | None = None
    end_period: str | None = None
    installments: int | None = None
    notes: str | None = None
    tags: str | None = None

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, v: str) -> str:
        if v not in {"fixed", "installment"}:
            raise ValueError("kind must be 'fixed' or 'installment'")
        return v

    @field_validator("amount_cents")
    @classmethod
    def positive_amount(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("amount_cents must be positive")
        return v

    @field_validator("day_of_month")
    @classmethod
    def valid_day(cls, v: int) -> int:
        if not 1 <= v <= 28:
            raise ValueError("day_of_month must be between 1 and 28")
        return v

    @model_validator(mode="after")
    def end_not_before_start(self) -> "RecurringRuleCreate":
        if self.start_period and self.end_period and self.end_period < self.start_period:
            raise ValueError("end_period must not be before start_period")
        return self


class TradeCreate(BaseModel):
    instrument_id: int
    kind: str  # 'buy' | 'sell'
    date: str
    qty: int
    price_cents: int
    order_cost_cents: int = 0

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, v: str) -> str:
        if v not in {"buy", "sell"}:
            raise ValueError("kind must be 'buy' or 'sell'")
        return v

    @field_validator("qty")
    @classmethod
    def positive_qty(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("qty must be positive")
        return v


class UsdEventCreate(BaseModel):
    instrument_id: int | None = None
    date: str
    kind: str  # 'vesting' | 'sale'
    gross_usd_cents: int
    net_usd_cents: int
    fx_eur_per_usd: float

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, v: str) -> str:
        if v not in {"vesting", "sale"}:
            raise ValueError("kind must be 'vesting' or 'sale'")
        return v

    @field_validator("gross_usd_cents", "net_usd_cents")
    @classmethod
    def non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("amounts must be non-negative")
        return v
