from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlmodel import Session, select

from app.models.tables import UsdEvent
from app.schemas.forms import UsdEventCreate


@dataclass
class UsdTotals:
    total_gross_usd_cents: int
    total_net_usd_cents: int
    total_withholding_usd_cents: int
    total_euro_net_cents: int


def record_event(data: UsdEventCreate, session: Session) -> UsdEvent:
    event = UsdEvent(
        instrument_id=data.instrument_id,
        date=data.date,
        kind=data.kind,
        gross_usd_cents=data.gross_usd_cents,
        net_usd_cents=data.net_usd_cents,
        fx_eur_per_usd=data.fx_eur_per_usd,
        created_at=datetime.now(UTC).isoformat(),
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def withholding_cents(event: UsdEvent) -> int:
    return event.gross_usd_cents - event.net_usd_cents


def euro_net_cents(event: UsdEvent) -> int:
    return int(Decimal(event.net_usd_cents) * Decimal(str(event.fx_eur_per_usd)))


def usd_totals(session: Session) -> UsdTotals:
    events = session.exec(select(UsdEvent)).all()
    total_gross = sum(e.gross_usd_cents for e in events)
    total_net = sum(e.net_usd_cents for e in events)
    total_withholding = sum(withholding_cents(e) for e in events)
    total_euro_net = sum(euro_net_cents(e) for e in events)
    return UsdTotals(
        total_gross_usd_cents=total_gross,
        total_net_usd_cents=total_net,
        total_withholding_usd_cents=total_withholding,
        total_euro_net_cents=total_euro_net,
    )


def list_events(session: Session) -> list[UsdEvent]:
    return list(session.exec(select(UsdEvent).order_by(UsdEvent.date)).all())  # type: ignore[arg-type]


_EDITABLE_FIELDS = {"date", "kind", "gross_usd_cents", "net_usd_cents", "fx_eur_per_usd"}


def update_field(event_id: int, field: str, raw_value: str, session: Session) -> UsdEvent:
    if field not in _EDITABLE_FIELDS:
        raise ValueError(f"field '{field}' is not editable")
    event = session.get(UsdEvent, event_id)
    if event is None:
        raise ValueError(f"UsdEvent {event_id} not found")

    if field == "date":
        if not raw_value:
            raise ValueError("date is required")
        event.date = raw_value
    elif field == "kind":
        if raw_value not in {"vesting", "sale"}:
            raise ValueError("kind must be 'vesting' or 'sale'")
        event.kind = raw_value
    elif field == "gross_usd_cents":
        try:
            event.gross_usd_cents = int(float(raw_value.replace(",", ".")) * 100)
        except ValueError as exc:
            raise ValueError("invalid amount") from exc
    elif field == "net_usd_cents":
        try:
            event.net_usd_cents = int(float(raw_value.replace(",", ".")) * 100)
        except ValueError as exc:
            raise ValueError("invalid amount") from exc
    elif field == "fx_eur_per_usd":
        try:
            event.fx_eur_per_usd = float(raw_value.replace(",", "."))
        except ValueError as exc:
            raise ValueError("invalid fx rate") from exc

    session.add(event)
    session.commit()
    session.refresh(event)
    return event
