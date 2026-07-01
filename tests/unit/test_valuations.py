import pytest
from app.models.tables import Account, Txn
from app.schemas.forms import AccountCreate, AccountValuationCreate
from app.services.accounts import create_account
from app.services.valuations import (
    delete_valuation,
    latest_valuation,
    list_valuations,
    net_contributed_cents,
    performance,
    record_valuation,
    to_chart_points,
    valuation_history,
)
from sqlmodel import Session


def _seed_account(session: Session, code: str = "AV1", opening: int = 0) -> Account:
    return create_account(
        AccountCreate(
            code=code, name=code, tier="Diferido", opening_date="2024-01-01", opening_cents=opening
        ),
        session,
    )


def _deposit(session: Session, account_id: int, date: str, amount: int) -> None:
    session.add(Txn(date=date, to_account=account_id, amount_cents=amount))
    session.commit()


@pytest.mark.unit
def test_record_valuation_creates_row(session: Session) -> None:
    acc = _seed_account(session)
    v = record_valuation(
        acc.id, AccountValuationCreate(period="2024-01", balance_cents=10_000), session
    )  # type: ignore[arg-type]
    assert v.account_id == acc.id
    assert v.period == "2024-01"
    assert v.balance_cents == 10_000


@pytest.mark.unit
def test_record_valuation_upserts_same_period(session: Session) -> None:
    acc = _seed_account(session)
    record_valuation(
        acc.id, AccountValuationCreate(period="2024-01", balance_cents=10_000), session
    )  # type: ignore[arg-type]
    record_valuation(
        acc.id, AccountValuationCreate(period="2024-01", balance_cents=12_000), session
    )  # type: ignore[arg-type]
    rows = list_valuations(acc.id, session)  # type: ignore[arg-type]
    assert len(rows) == 1
    assert rows[0].balance_cents == 12_000


@pytest.mark.unit
def test_record_valuation_missing_account_raises(session: Session) -> None:
    with pytest.raises(ValueError, match="not found"):
        record_valuation(
            9999, AccountValuationCreate(period="2024-01", balance_cents=1_000), session
        )


@pytest.mark.unit
def test_delete_valuation_removes_row(session: Session) -> None:
    acc = _seed_account(session)
    record_valuation(
        acc.id, AccountValuationCreate(period="2024-01", balance_cents=10_000), session
    )  # type: ignore[arg-type]
    delete_valuation(acc.id, "2024-01", session)  # type: ignore[arg-type]
    assert list_valuations(acc.id, session) == []  # type: ignore[arg-type]


@pytest.mark.unit
def test_delete_valuation_missing_raises(session: Session) -> None:
    acc = _seed_account(session)
    with pytest.raises(ValueError, match="No valuation"):
        delete_valuation(acc.id, "2024-01", session)  # type: ignore[arg-type]


@pytest.mark.unit
def test_list_valuations_ordered_by_period(session: Session) -> None:
    acc = _seed_account(session)
    record_valuation(acc.id, AccountValuationCreate(period="2024-03", balance_cents=3_000), session)  # type: ignore[arg-type]
    record_valuation(acc.id, AccountValuationCreate(period="2024-01", balance_cents=1_000), session)  # type: ignore[arg-type]
    record_valuation(acc.id, AccountValuationCreate(period="2024-02", balance_cents=2_000), session)  # type: ignore[arg-type]
    rows = list_valuations(acc.id, session)  # type: ignore[arg-type]
    assert [r.period for r in rows] == ["2024-01", "2024-02", "2024-03"]


@pytest.mark.unit
def test_latest_valuation_returns_most_recent(session: Session) -> None:
    acc = _seed_account(session)
    record_valuation(acc.id, AccountValuationCreate(period="2024-01", balance_cents=1_000), session)  # type: ignore[arg-type]
    record_valuation(acc.id, AccountValuationCreate(period="2024-02", balance_cents=2_000), session)  # type: ignore[arg-type]
    latest = latest_valuation(acc.id, session)  # type: ignore[arg-type]
    assert latest is not None
    assert latest.period == "2024-02"


@pytest.mark.unit
def test_latest_valuation_none_when_empty(session: Session) -> None:
    acc = _seed_account(session)
    assert latest_valuation(acc.id, session) is None  # type: ignore[arg-type]


@pytest.mark.unit
def test_net_contributed_cents_matches_ledger(session: Session) -> None:
    acc = _seed_account(session, opening=5_000)
    _deposit(session, acc.id, "2024-01-10", 2_000)  # type: ignore[arg-type]
    assert net_contributed_cents(acc.id, session) == 7_000  # type: ignore[arg-type]


@pytest.mark.unit
def test_performance_none_without_valuation(session: Session) -> None:
    acc = _seed_account(session)
    assert performance(acc.id, session) is None  # type: ignore[arg-type]


@pytest.mark.unit
def test_performance_computes_unrealized_gain(session: Session) -> None:
    acc = _seed_account(session, opening=10_000)
    record_valuation(
        acc.id, AccountValuationCreate(period="2024-01", balance_cents=11_000), session
    )  # type: ignore[arg-type]
    perf = performance(acc.id, session)  # type: ignore[arg-type]
    assert perf is not None
    assert perf.market_value_cents == 11_000
    assert perf.net_contributed_cents == 10_000
    assert perf.unrealized_gain_cents == 1_000
    assert perf.unrealized_gain_pct == pytest.approx(0.1)


@pytest.mark.unit
def test_valuation_history_first_point_has_no_gain(session: Session) -> None:
    acc = _seed_account(session, opening=10_000)
    record_valuation(
        acc.id, AccountValuationCreate(period="2024-01", balance_cents=10_500), session
    )  # type: ignore[arg-type]
    history = valuation_history(acc.id, session)  # type: ignore[arg-type]
    assert len(history) == 1
    assert history[0].gain_cents == 0
    assert history[0].gain_pct is None


@pytest.mark.unit
def test_valuation_history_gain_excludes_contributions(session: Session) -> None:
    """Deposit 1000 mid-month; the rest of the delta is market gain."""
    acc = _seed_account(session, opening=10_000)
    record_valuation(
        acc.id, AccountValuationCreate(period="2024-01", balance_cents=10_000), session
    )  # type: ignore[arg-type]
    _deposit(session, acc.id, "2024-02-10", 1_000)  # type: ignore[arg-type]
    record_valuation(
        acc.id, AccountValuationCreate(period="2024-02", balance_cents=11_500), session
    )  # type: ignore[arg-type]
    history = valuation_history(acc.id, session)  # type: ignore[arg-type]
    feb = history[1]
    assert feb.contributions_cents == 1_000
    assert feb.gain_cents == 500  # 11500 - 10000 - 1000
    assert feb.gain_pct == pytest.approx(500 / 10_000)


@pytest.mark.unit
def test_to_chart_points_empty() -> None:
    assert to_chart_points([]) == []


@pytest.mark.unit
def test_to_chart_points_single_point_centered(session: Session) -> None:
    acc = _seed_account(session)
    record_valuation(acc.id, AccountValuationCreate(period="2024-01", balance_cents=1_000), session)  # type: ignore[arg-type]
    points = to_chart_points(list_valuations(acc.id, session))  # type: ignore[arg-type]
    assert len(points) == 1
    assert points[0].x_pct == 50.0
    assert points[0].y_pct == 100.0


@pytest.mark.unit
def test_to_chart_points_normalizes_range(session: Session) -> None:
    acc = _seed_account(session)
    record_valuation(acc.id, AccountValuationCreate(period="2024-01", balance_cents=1_000), session)  # type: ignore[arg-type]
    record_valuation(acc.id, AccountValuationCreate(period="2024-02", balance_cents=2_000), session)  # type: ignore[arg-type]
    points = to_chart_points(list_valuations(acc.id, session))  # type: ignore[arg-type]
    assert points[0].x_pct == 0.0
    assert points[0].y_pct == 100.0
    assert points[1].x_pct == 100.0
    assert points[1].y_pct == 0.0
