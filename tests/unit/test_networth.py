import pytest
from app.models.tables import Account, NetworthSnapshot, Txn
from app.services.networth import monthly_history, to_chart_points
from sqlmodel import Session, select


def _make_account(session: Session, code: str, tier: str, opening: int = 0) -> Account:
    a = Account(code=code, name=code, tier=tier, opening_cents=opening, opening_date="2024-01-01")
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


def _txn(session: Session, date: str, to_account: int, amount: int) -> None:
    session.add(
        Txn(date=date, to_account=to_account, amount_cents=amount, created_at=f"{date}T00:00:00")
    )
    session.commit()


@pytest.mark.unit
def test_monthly_history_empty_when_no_txns(session: Session) -> None:
    assert monthly_history(session) == []


@pytest.mark.unit
def test_monthly_history_spans_from_first_txn_to_current_month(session: Session) -> None:
    from datetime import date

    a = _make_account(session, "MH1", "Imediato", opening=1_000)
    _txn(session, "2024-01-15", a.id, 500)  # type: ignore[arg-type]

    history = monthly_history(session)
    periods = [h.period for h in history]
    current_period = f"{date.today().year}-{date.today().month:02d}"
    assert periods[0] == "2024-01"
    assert periods[-1] == current_period
    assert "2024-02" in periods  # months with no activity are still included


@pytest.mark.unit
def test_monthly_history_totals_grow_only_after_txn_month(session: Session) -> None:
    a = _make_account(session, "MH2", "Imediato", opening=1_000)
    _txn(session, "2024-03-10", a.id, 2_000)  # type: ignore[arg-type]

    history = {h.period: h for h in monthly_history(session)}
    assert history["2024-01"].tier_totals["Imediato"] == 1_000
    assert history["2024-02"].tier_totals["Imediato"] == 1_000
    assert history["2024-03"].tier_totals["Imediato"] == 3_000
    assert history["2024-03"].grand_total == 3_000


@pytest.mark.unit
def test_monthly_history_caches_closed_months(session: Session) -> None:
    a = _make_account(session, "MH3", "Imediato", opening=1_000)
    _txn(session, "2024-01-10", a.id, 2_000)  # type: ignore[arg-type]

    history = monthly_history(session)
    closed_periods = [h.period for h in history[:-1]]
    assert closed_periods  # at least one closed month exists
    snapshots = session.exec(
        select(NetworthSnapshot).where(NetworthSnapshot.period.in_(closed_periods))  # type: ignore[attr-defined]
    ).all()
    # 3 tiers cached per closed period
    assert len(snapshots) == 3 * len(closed_periods)


@pytest.mark.unit
def test_monthly_history_current_month_not_cached(session: Session) -> None:
    from datetime import date

    a = _make_account(session, "MH4", "Imediato", opening=1_000)
    _txn(session, "2024-01-10", a.id, 2_000)  # type: ignore[arg-type]

    monthly_history(session)
    current_period = f"{date.today().year}-{date.today().month:02d}"
    cached = session.exec(
        select(NetworthSnapshot).where(NetworthSnapshot.period == current_period)
    ).all()
    assert cached == []


@pytest.mark.unit
def test_monthly_history_uses_cache_over_recompute(session: Session) -> None:
    a = _make_account(session, "MH5", "Imediato", opening=1_000)
    _txn(session, "2024-01-10", a.id, 2_000)  # type: ignore[arg-type]

    monthly_history(session)  # populates cache for 2024-01
    # Tamper with the cached snapshot directly; a correct cache-hit returns this
    # tampered value instead of recomputing from the ledger.
    for row in session.exec(
        select(NetworthSnapshot).where(NetworthSnapshot.period == "2024-01")
    ).all():
        if row.tier == "Imediato":
            row.total_cents = 999_999
            session.add(row)
    session.commit()

    history = {h.period: h for h in monthly_history(session)}
    assert history["2024-01"].tier_totals["Imediato"] == 999_999


@pytest.mark.unit
def test_to_chart_points_empty() -> None:
    assert to_chart_points([]) == []


@pytest.mark.unit
def test_to_chart_points_normalizes_range(session: Session) -> None:
    a = _make_account(session, "MH6", "Imediato", opening=1_000)
    _txn(session, "2024-02-10", a.id, 4_000)  # type: ignore[arg-type]

    history = monthly_history(session)
    points = to_chart_points(history)
    assert len(points) == len(history)
    assert points[0].x_pct == 0.0
    assert points[-1].x_pct == 100.0
    y_values = [p.y_pct for p in points]
    assert min(y_values) == 0.0
    assert max(y_values) == 100.0


@pytest.mark.unit
def test_to_chart_points_single_point_centers_x() -> None:
    from app.services.networth import MonthlyNetworth

    points = to_chart_points(
        [MonthlyNetworth(period="2024-01", tier_totals={"Imediato": 100}, grand_total=100)]
    )
    assert points[0].x_pct == 50.0
    assert points[0].y_pct == 100.0  # single value: min==max, no variation to normalize
