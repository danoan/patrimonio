from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str = "EUR"

    @classmethod
    def from_cents(cls, cents: int, currency: str = "EUR") -> "Money":
        return cls(Decimal(cents) / 100, currency)

    def to_cents(self) -> int:
        return int((self.amount * 100).to_integral_value(ROUND_HALF_UP))

    def __add__(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValueError(f"Cannot add {self.currency} and {other.currency}")
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValueError(f"Cannot subtract {self.currency} and {other.currency}")
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, factor: Decimal | int | float) -> "Money":
        return Money(self.amount * Decimal(str(factor)), self.currency)

    def __neg__(self) -> "Money":
        return Money(-self.amount, self.currency)


def fmt_eur(cents: int) -> str:
    """Format cents as fr-FR EUR string: 1 234,56 €"""
    amount = Decimal(cents) / 100
    negative = amount < 0
    amount = abs(amount)
    integer_part, _, decimal_part = f"{amount:.2f}".partition(".")
    # Add thousands separator (narrow no-break space)
    groups: list[str] = []
    s = integer_part
    while len(s) > 3:
        groups.append(s[-3:])
        s = s[:-3]
    groups.append(s)
    formatted_int = " ".join(reversed(groups))
    result = f"{formatted_int},{decimal_part} €"
    return f"-{result}" if negative else result


def fmt_usd(cents: int) -> str:
    """Format cents as USD string: $1,234.56"""
    amount = Decimal(cents) / 100
    negative = amount < 0
    amount = abs(amount)
    formatted = f"{amount:,.2f}"
    result = f"${formatted}"
    return f"-{result}" if negative else result


def fmt_pct(rate: float, decimals: int = 1) -> str:
    """Format a float rate as percentage: 0.1234 → '12,3 %'"""
    value = rate * 100
    formatted = f"{value:.{decimals}f}".replace(".", ",")
    return f"{formatted} %"
