import pytest
from app.models.tables import UsdEvent
from app.schemas.forms import UsdEventCreate
from app.services.usd import (
    euro_net_cents,
    record_event,
    update_field,
    usd_totals,
    withholding_cents,
)
from sqlmodel import Session


@pytest.mark.unit
def test_withholding_equals_gross_minus_net(session: Session) -> None:
    data = UsdEventCreate(
        date="2024-03-15",
        kind="vesting",
        gross_usd_cents=100000,  # $1000.00
        net_usd_cents=75000,  # $750.00 (25% withheld)
        fx_eur_per_usd=0.93,
    )
    event = record_event(data, session)
    assert withholding_cents(event) == 25000  # 100000 - 75000


@pytest.mark.unit
def test_euro_net_calculation(session: Session) -> None:
    data = UsdEventCreate(
        date="2024-03-15",
        kind="vesting",
        gross_usd_cents=100000,
        net_usd_cents=75000,
        fx_eur_per_usd=1.0,  # 1:1 for easy math
    )
    event = record_event(data, session)
    # euro_net = 75000 * 1.0 = 75000
    assert euro_net_cents(event) == 75000


@pytest.mark.unit
def test_euro_net_with_fx_rate(session: Session) -> None:
    data = UsdEventCreate(
        date="2024-03-15",
        kind="sale",
        gross_usd_cents=200000,  # $2000
        net_usd_cents=160000,  # $1600
        fx_eur_per_usd=0.92,
    )
    event = record_event(data, session)
    # euro_net = 160000 * 0.92 = 147200
    assert euro_net_cents(event) == 147200


@pytest.mark.unit
def test_usd_totals_aggregate_correctly(session: Session) -> None:
    # Event 1: gross 100000, net 70000, fx 1.0
    record_event(
        UsdEventCreate(
            date="2024-01-01",
            kind="vesting",
            gross_usd_cents=100000,
            net_usd_cents=70000,
            fx_eur_per_usd=1.0,
        ),
        session,
    )
    # Event 2: gross 50000, net 40000, fx 1.0
    record_event(
        UsdEventCreate(
            date="2024-02-01",
            kind="sale",
            gross_usd_cents=50000,
            net_usd_cents=40000,
            fx_eur_per_usd=1.0,
        ),
        session,
    )

    totals = usd_totals(session)
    assert totals.total_gross_usd_cents == 150000
    assert totals.total_net_usd_cents == 110000
    assert totals.total_withholding_usd_cents == 40000  # (30000 + 10000)
    assert totals.total_euro_net_cents == 110000  # 1:1 rate


@pytest.mark.unit
def test_withholding_is_always_non_negative(session: Session) -> None:
    """Withholding = gross - net; both defined, so this is always >= 0."""
    event = UsdEvent(
        date="2024-01-01",
        kind="vesting",
        gross_usd_cents=50000,
        net_usd_cents=50000,  # no withholding
        fx_eur_per_usd=1.0,
        created_at="2024-01-01T00:00:00",
    )
    assert withholding_cents(event) == 0


def _make_event(session: Session) -> UsdEvent:
    return record_event(
        UsdEventCreate(
            date="2024-01-01",
            kind="vesting",
            gross_usd_cents=100000,
            net_usd_cents=75000,
            fx_eur_per_usd=0.93,
        ),
        session,
    )


@pytest.mark.unit
def test_update_field_date_and_kind(session: Session) -> None:
    event = _make_event(session)
    updated = update_field(event.id, "date", "2024-05-01", session)  # type: ignore[arg-type]
    assert updated.date == "2024-05-01"
    updated = update_field(event.id, "kind", "sale", session)  # type: ignore[arg-type]
    assert updated.kind == "sale"


@pytest.mark.unit
def test_update_field_amounts_and_fx(session: Session) -> None:
    event = _make_event(session)
    updated = update_field(event.id, "gross_usd_cents", "500,00", session)  # type: ignore[arg-type]
    assert updated.gross_usd_cents == 50000
    updated = update_field(event.id, "net_usd_cents", "400,00", session)  # type: ignore[arg-type]
    assert updated.net_usd_cents == 40000
    updated = update_field(event.id, "fx_eur_per_usd", "0.95", session)  # type: ignore[arg-type]
    assert updated.fx_eur_per_usd == pytest.approx(0.95)


@pytest.mark.unit
def test_update_field_invalid_kind_raises(session: Session) -> None:
    event = _make_event(session)
    with pytest.raises(ValueError, match="vesting"):
        update_field(event.id, "kind", "other", session)  # type: ignore[arg-type]


@pytest.mark.unit
def test_update_field_invalid_amount_raises(session: Session) -> None:
    event = _make_event(session)
    with pytest.raises(ValueError, match="invalid amount"):
        update_field(event.id, "gross_usd_cents", "abc", session)  # type: ignore[arg-type]


@pytest.mark.unit
def test_update_field_invalid_fx_raises(session: Session) -> None:
    event = _make_event(session)
    with pytest.raises(ValueError, match="invalid fx rate"):
        update_field(event.id, "fx_eur_per_usd", "abc", session)  # type: ignore[arg-type]


@pytest.mark.unit
def test_update_field_unknown_field_raises(session: Session) -> None:
    event = _make_event(session)
    with pytest.raises(ValueError, match="not editable"):
        update_field(event.id, "instrument_id", "1", session)  # type: ignore[arg-type]


@pytest.mark.unit
def test_update_field_missing_event_raises(session: Session) -> None:
    with pytest.raises(ValueError, match="not found"):
        update_field(9999, "date", "2024-01-01", session)
