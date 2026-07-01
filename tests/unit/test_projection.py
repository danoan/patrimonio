import pytest
from app.models.tables import Account, ExpectedYield, RecurringRule
from app.schemas.forms import AccountCreate, RecurringRuleCreate
from app.services.accounts import create_account
from app.services.balances import balance
from app.services.projection import project, to_chart_points
from app.services.recurring import create_rule, post_rule
from sqlmodel import Session


def _make_account(session: Session, code: str, opening: int, tier: str = "Imediato") -> Account:
    return create_account(
        AccountCreate(
            code=code,
            name=code,
            tier=tier,
            opening_cents=opening,
            opening_date="2024-01-01",
        ),
        session,
    )


def _make_rule(
    session: Session,
    to_id: int | None = None,
    from_id: int | None = None,
    amount: int = 100_000,
    kind: str = "fixed",
    installments: int | None = None,
) -> RecurringRule:
    return create_rule(
        RecurringRuleCreate(
            kind=kind,
            description="test",
            to_account=to_id,
            from_account=from_id,
            amount_cents=amount,
            installments=installments,
        ),
        session,
    )


@pytest.mark.unit
def test_projection_returns_correct_month_count(session: Session) -> None:
    _make_account(session, "P1", opening=1_000_000)
    result = project(session, months=12)
    assert len(result) == 12


@pytest.mark.unit
def test_projection_periods_are_sequential(session: Session) -> None:
    _make_account(session, "P2", opening=500_000)
    result = project(session, months=6)
    periods = [p.period for p in result]
    # Each period should be later than the previous
    for i in range(1, len(periods)):
        assert periods[i] > periods[i - 1]


@pytest.mark.unit
def test_fixed_inflow_increases_balance_each_month(session: Session) -> None:
    acc = _make_account(session, "P3", opening=0)
    _make_rule(session, to_id=acc.id, amount=50_000)  # +500 €/month
    result = project(session, months=3)
    totals = [p.grand_total for p in result]
    assert totals[0] == 50_000
    assert totals[1] == 100_000
    assert totals[2] == 150_000


@pytest.mark.unit
def test_fixed_outflow_decreases_balance_each_month(session: Session) -> None:
    acc = _make_account(session, "P4", opening=300_000)
    _make_rule(session, from_id=acc.id, amount=100_000)  # -1 000 €/month
    result = project(session, months=3)
    totals = [p.grand_total for p in result]
    assert totals[0] == 200_000
    assert totals[1] == 100_000
    assert totals[2] == 0


@pytest.mark.unit
def test_installment_stops_after_count(session: Session) -> None:
    acc = _make_account(session, "P5", opening=0)
    _make_rule(session, to_id=acc.id, amount=10_000, kind="installment", installments=3)
    result = project(session, months=5)
    totals = [p.grand_total for p in result]
    # Months 1–3: +10 000 each; month 4–5: no change
    assert totals[0] == 10_000
    assert totals[1] == 20_000
    assert totals[2] == 30_000
    assert totals[3] == 30_000  # stopped
    assert totals[4] == 30_000


@pytest.mark.unit
def test_installment_remaining_accounts_for_already_posted(session: Session) -> None:
    acc = _make_account(session, "P6", opening=0)
    rule = _make_rule(session, to_id=acc.id, amount=10_000, kind="installment", installments=4)
    # Post 2 months already
    post_rule(rule.id, "2024-01", session)
    post_rule(rule.id, "2024-02", session)
    # Only 2 remaining → should apply for 2 more months
    result = project(session, months=4)
    totals = [p.grand_total for p in result]
    # Each month adds 10 000 to the actual balance; projection starts from current balance
    base = balance(acc.id, session)  # 20 000 from already-posted txns
    assert totals[0] == base + 10_000
    assert totals[1] == base + 20_000
    assert totals[2] == base + 20_000  # installment exhausted
    assert totals[3] == base + 20_000


@pytest.mark.unit
def test_yield_compounds_monthly(session: Session) -> None:
    acc = _make_account(session, "P7", opening=120_000)  # 1 200 €
    ey = ExpectedYield(account_id=acc.id, annual_rate=0.12)  # 12 % annual = 1 %/month
    session.add(ey)
    session.commit()
    result = project(session, months=1)
    # 120 000 * 1.01 = 121 200
    assert result[0].grand_total == 121_200


@pytest.mark.unit
def test_tier_totals_in_projection(session: Session) -> None:
    _make_account(session, "PI", opening=100_000, tier="Imediato")
    _make_account(session, "PD", opening=200_000, tier="Diferido")
    result = project(session, months=1)
    assert result[0].tier_totals["Imediato"] == 100_000
    assert result[0].tier_totals["Diferido"] == 200_000


@pytest.mark.unit
def test_to_chart_points_empty(session: Session) -> None:
    assert to_chart_points([]) == []


@pytest.mark.unit
def test_to_chart_points_single_value(session: Session) -> None:
    _make_account(session, "PC1", opening=50_000)
    result = project(session, months=1)
    points = to_chart_points(result)
    assert len(points) == 1
    assert points[0].x_pct == 50.0  # single point centred


@pytest.mark.unit
def test_to_chart_points_range(session: Session) -> None:
    acc = _make_account(session, "PC2", opening=0)
    _make_rule(session, to_id=acc.id, amount=10_000)
    result = project(session, months=3)
    points = to_chart_points(result)
    # x should go from 0 to 100
    assert points[0].x_pct == 0.0
    assert points[-1].x_pct == 100.0
    # y should go from 100 (min, top of svg) to 0 (max, bottom of svg)
    assert points[0].y_pct == 100.0
    assert points[-1].y_pct == 0.0
