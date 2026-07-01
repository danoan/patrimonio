import pytest
from app.models.tables import Account, AccountValuation, Txn
from app.services.balances import balance, grand_total, ledger_balance, tier_totals
from sqlmodel import Session


def _make_account(
    session: Session,
    code: str,
    tier: str,
    opening: int = 0,
) -> Account:
    a = Account(code=code, name=code, tier=tier, opening_cents=opening, opening_date="2024-01-01")
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


def _inflow(session: Session, account_id: int, amount: int) -> None:
    t = Txn(
        date="2024-02-01",
        to_account=account_id,
        amount_cents=amount,
        created_at="2024-02-01T00:00:00",
    )
    session.add(t)
    session.commit()


def _outflow(session: Session, account_id: int, amount: int) -> None:
    t = Txn(
        date="2024-02-01",
        from_account=account_id,
        amount_cents=amount,
        created_at="2024-02-01T00:00:00",
    )
    session.add(t)
    session.commit()


@pytest.mark.unit
def test_balance_opening_only(session: Session) -> None:
    a = _make_account(session, "T1", "Imediato", opening=10_000)
    assert balance(a.id, session) == 10_000  # type: ignore[arg-type]


@pytest.mark.unit
def test_balance_opening_plus_inflow(session: Session) -> None:
    a = _make_account(session, "T2", "Imediato", opening=5_000)
    _inflow(session, a.id, 3_000)  # type: ignore[arg-type]
    assert balance(a.id, session) == 8_000  # type: ignore[arg-type]


@pytest.mark.unit
def test_balance_formula(session: Session) -> None:
    """balance = opening + Σ inflows − Σ outflows"""
    a = _make_account(session, "T3", "Imediato", opening=10_000)
    _inflow(session, a.id, 2_000)  # type: ignore[arg-type]
    _inflow(session, a.id, 3_000)  # type: ignore[arg-type]
    _outflow(session, a.id, 1_500)  # type: ignore[arg-type]
    expected = 10_000 + 2_000 + 3_000 - 1_500
    assert balance(a.id, session) == expected  # type: ignore[arg-type]


@pytest.mark.unit
def test_tier_totals(session: Session) -> None:
    _make_account(session, "I1", "Imediato", opening=100_00)
    _make_account(session, "D1", "Diferido", opening=200_00)
    _make_account(session, "A1", "Alocado", opening=300_00)
    totals = tier_totals(session)
    assert totals["Imediato"] == 10000
    assert totals["Diferido"] == 20000
    assert totals["Alocado"] == 30000


@pytest.mark.unit
def test_grand_total(session: Session) -> None:
    _make_account(session, "X1", "Imediato", opening=1_000)
    _make_account(session, "X2", "Diferido", opening=2_000)
    assert grand_total(session) == 3_000


@pytest.mark.unit
def test_balance_nonexistent_account_raises(session: Session) -> None:
    with pytest.raises(ValueError, match="not found"):
        balance(9999, session)


@pytest.mark.unit
def test_balance_uses_latest_valuation_when_present(session: Session) -> None:
    a = _make_account(session, "V1", "Diferido", opening=10_000)
    _inflow(session, a.id, 5_000)  # type: ignore[arg-type]
    session.add(AccountValuation(account_id=a.id, period="2024-01", balance_cents=9_000))
    session.add(AccountValuation(account_id=a.id, period="2024-02", balance_cents=12_500))
    session.commit()
    # ledger says 15_000; the latest recorded valuation wins instead
    assert balance(a.id, session) == 12_500  # type: ignore[arg-type]


@pytest.mark.unit
def test_ledger_balance_ignores_valuations(session: Session) -> None:
    a = _make_account(session, "V2", "Diferido", opening=10_000)
    session.add(AccountValuation(account_id=a.id, period="2024-01", balance_cents=1))
    session.commit()
    assert ledger_balance(a.id, session) == 10_000  # type: ignore[arg-type]


@pytest.mark.unit
def test_transfer_between_accounts(session: Session) -> None:
    """A transfer: no net change in grand total."""
    src = _make_account(session, "SRC", "Imediato", opening=5_000)
    dst = _make_account(session, "DST", "Imediato", opening=0)
    t = Txn(
        date="2024-02-01",
        from_account=src.id,
        to_account=dst.id,
        amount_cents=2_000,
        created_at="2024-02-01T00:00:00",
    )
    session.add(t)
    session.commit()

    assert balance(src.id, session) == 3_000  # type: ignore[arg-type]
    assert balance(dst.id, session) == 2_000  # type: ignore[arg-type]
    assert grand_total(session) == 5_000  # net unchanged


@pytest.mark.unit
def test_ledger_balance_as_of_period_excludes_later_txns(session: Session) -> None:
    a = _make_account(session, "H1", "Imediato", opening=1_000)
    t1 = Txn(date="2024-02-15", to_account=a.id, amount_cents=500, created_at="2024-02-15T00:00:00")
    t2 = Txn(date="2024-03-15", to_account=a.id, amount_cents=700, created_at="2024-03-15T00:00:00")
    session.add(t1)
    session.add(t2)
    session.commit()

    assert ledger_balance(a.id, session, as_of_period="2024-02") == 1_500  # type: ignore[arg-type]
    assert ledger_balance(a.id, session, as_of_period="2024-03") == 2_200  # type: ignore[arg-type]
    assert ledger_balance(a.id, session) == 2_200  # type: ignore[arg-type]


@pytest.mark.unit
def test_balance_as_of_period_ignores_future_valuations(session: Session) -> None:
    a = _make_account(session, "H2", "Diferido", opening=10_000)
    session.add(AccountValuation(account_id=a.id, period="2024-01", balance_cents=9_000))
    session.add(AccountValuation(account_id=a.id, period="2024-03", balance_cents=12_500))
    session.commit()

    assert balance(a.id, session, as_of_period="2024-01") == 9_000  # type: ignore[arg-type]
    assert balance(a.id, session, as_of_period="2024-02") == 9_000  # type: ignore[arg-type]
    assert balance(a.id, session, as_of_period="2024-03") == 12_500  # type: ignore[arg-type]


@pytest.mark.unit
def test_balance_as_of_period_before_opening_is_zero(session: Session) -> None:
    a = Account(
        code="H3", name="H3", tier="Imediato", opening_cents=5_000, opening_date="2024-06-15"
    )
    session.add(a)
    session.commit()
    session.refresh(a)

    assert balance(a.id, session, as_of_period="2024-05") == 0  # type: ignore[arg-type]
    assert balance(a.id, session, as_of_period="2024-06") == 5_000  # type: ignore[arg-type]


@pytest.mark.unit
def test_tier_totals_as_of_period(session: Session) -> None:
    a = _make_account(session, "H4", "Imediato", opening=1_000)
    _inflow(session, a.id, 500)  # dated 2024-02-01, see _inflow helper  # type: ignore[arg-type]
    totals_before = tier_totals(session, as_of_period="2024-01")
    totals_after = tier_totals(session, as_of_period="2024-02")
    assert totals_before["Imediato"] == 1_000
    assert totals_after["Imediato"] == 1_500


@pytest.mark.unit
def test_grand_total_as_of_period(session: Session) -> None:
    a = _make_account(session, "H5", "Imediato", opening=1_000)
    _inflow(session, a.id, 500)  # type: ignore[arg-type]
    assert grand_total(session, as_of_period="2024-01") == 1_000
    assert grand_total(session, as_of_period="2024-02") == 1_500
