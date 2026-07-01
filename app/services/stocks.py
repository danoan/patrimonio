from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlmodel import Session, col, select

from app.models.tables import Instrument, Price, Setting, Trade
from app.schemas.forms import TradeCreate


@dataclass
class Position:
    instrument: Instrument
    qty: int
    avg_cost_cents: int
    current_price_cents: int
    unrealized_cents: int


def _get_pfu(session: Session) -> Decimal:
    setting = session.get(Setting, "pfu")
    if setting is None:
        return Decimal("0.30")
    return Decimal(setting.value)


def current_price(instrument_id: int, session: Session) -> int:
    price = session.exec(
        select(Price).where(Price.instrument_id == instrument_id).order_by(col(Price.as_of).desc())  # type: ignore[arg-type]
    ).first()
    return price.price_cents if price else 0


def update_price(instrument_id: int, price_cents: int, session: Session) -> Price:
    inst = session.get(Instrument, instrument_id)
    if inst is None:
        raise ValueError(f"Instrument {instrument_id} not found")

    today = datetime.now(UTC).date().isoformat()
    existing = session.get(Price, (instrument_id, today))
    if existing is not None:
        existing.price_cents = price_cents
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    price = Price(instrument_id=instrument_id, price_cents=price_cents, as_of=today)
    session.add(price)
    session.commit()
    session.refresh(price)
    return price


def get_instrument_by_ticker(ticker: str, session: Session) -> Instrument | None:
    return session.exec(select(Instrument).where(Instrument.ticker == ticker)).first()


def position_for_instrument(instrument_id: int, session: Session) -> Position | None:
    for pos in positions(session):
        if pos.instrument.id == instrument_id:
            return pos
    return None


def positions(session: Session) -> list[Position]:
    """Compute current positions by replaying all trades (weighted average cost)."""
    instruments = session.exec(select(Instrument)).all()
    result: list[Position] = []

    for inst in instruments:
        if inst.id is None:
            continue
        trades = session.exec(
            select(Trade)
            .where(Trade.instrument_id == inst.id)
            .order_by(col(Trade.date), col(Trade.id))  # type: ignore[arg-type]
        ).all()

        qty = 0
        avg_cost_cents = 0  # integer cents

        for trade in trades:
            if trade.kind == "buy":
                total_cost = (
                    qty * avg_cost_cents + trade.qty * trade.price_cents + trade.order_cost_cents
                )
                qty += trade.qty
                avg_cost_cents = total_cost // qty if qty > 0 else 0
            elif trade.kind == "sell":
                qty -= trade.qty
                # avg_cost_cents unchanged on sell
                if qty < 0:
                    qty = 0

        if qty <= 0:
            continue

        price_cents = current_price(inst.id, session)
        unrealized = (price_cents - avg_cost_cents) * qty

        result.append(
            Position(
                instrument=inst,
                qty=qty,
                avg_cost_cents=avg_cost_cents,
                current_price_cents=price_cents,
                unrealized_cents=unrealized,
            )
        )
    return result


def record_trade(data: TradeCreate, session: Session) -> Trade:
    inst = session.get(Instrument, data.instrument_id)
    if inst is None:
        raise ValueError(f"Instrument {data.instrument_id} not found")

    realized_cents: int | None = None
    tax_reserved_cents: int | None = None

    if data.kind == "sell":
        # Compute current avg cost
        past_trades = session.exec(
            select(Trade)
            .where(Trade.instrument_id == data.instrument_id)
            .order_by(col(Trade.date), col(Trade.id))  # type: ignore[arg-type]
        ).all()

        qty = 0
        avg_cost = 0

        for t in past_trades:
            if t.kind == "buy":
                total = qty * avg_cost + t.qty * t.price_cents + t.order_cost_cents
                qty += t.qty
                avg_cost = total // qty if qty > 0 else 0
            elif t.kind == "sell":
                qty -= t.qty

        if data.qty > qty:
            raise ValueError(f"Cannot sell {data.qty} shares; only {qty} available")

        pfu = _get_pfu(session)
        realized = (data.price_cents - avg_cost) * data.qty - data.order_cost_cents
        tax = max(0, int(Decimal(realized) * pfu))
        realized_cents = realized
        tax_reserved_cents = tax

    trade = Trade(
        instrument_id=data.instrument_id,
        kind=data.kind,
        date=data.date,
        qty=data.qty,
        price_cents=data.price_cents,
        order_cost_cents=data.order_cost_cents,
        realized_cents=realized_cents,
        tax_reserved_cents=tax_reserved_cents,
        created_at=datetime.now(UTC).isoformat(),
    )
    session.add(trade)
    session.commit()
    session.refresh(trade)
    return trade


def list_trades(instrument_id: int, session: Session) -> list[Trade]:
    return list(
        session.exec(
            select(Trade)
            .where(Trade.instrument_id == instrument_id)
            .order_by(col(Trade.date).desc(), col(Trade.id).desc())  # type: ignore[arg-type]
        ).all()
    )


def delete_trade(trade_id: int, session: Session) -> None:
    trade = session.get(Trade, trade_id)
    if trade is None:
        raise ValueError(f"Trade {trade_id} not found")
    session.delete(trade)
    session.commit()
