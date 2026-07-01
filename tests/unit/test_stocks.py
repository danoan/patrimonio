import pytest
from app.models.tables import Instrument, Setting
from app.schemas.forms import TradeCreate
from app.services.stocks import (
    current_price,
    delete_trade,
    get_instrument_by_ticker,
    position_for_instrument,
    positions,
    record_trade,
    update_price,
)
from sqlmodel import Session


def _make_instrument(session: Session, ticker: str = "FDJ", currency: str = "EUR") -> Instrument:
    inst = Instrument(ticker=ticker, name=ticker, currency=currency)
    session.add(inst)
    session.commit()
    session.refresh(inst)
    return inst


@pytest.mark.unit
def test_weighted_average_cost_single_buy(session: Session) -> None:
    inst = _make_instrument(session)
    data = TradeCreate(
        instrument_id=inst.id,  # type: ignore[arg-type]
        kind="buy",
        date="2024-01-10",
        qty=10,
        price_cents=2000,  # €20.00 per share
        order_cost_cents=500,  # €5.00 commission
    )
    record_trade(data, session)
    pos_list = positions(session)
    assert len(pos_list) == 1
    pos = pos_list[0]
    # avg = (10*2000 + 500) / 10 = 20500 / 10 = 2050
    assert pos.avg_cost_cents == 2050
    assert pos.qty == 10


@pytest.mark.unit
def test_weighted_average_cost_multiple_buys(session: Session) -> None:
    inst = _make_instrument(session, "FDJ2")
    # Buy 10 @ €20
    record_trade(
        TradeCreate(
            instrument_id=inst.id,
            kind="buy",
            date="2024-01-10",
            qty=10,
            price_cents=2000,
            order_cost_cents=0,
        ),
        session,
    )  # type: ignore[arg-type]
    # Buy 10 @ €30
    record_trade(
        TradeCreate(
            instrument_id=inst.id,
            kind="buy",
            date="2024-01-15",
            qty=10,
            price_cents=3000,
            order_cost_cents=0,
        ),
        session,
    )  # type: ignore[arg-type]

    pos_list = positions(session)
    pos = next(p for p in pos_list if p.instrument.ticker == "FDJ2")
    # avg = (10*2000 + 10*3000) / 20 = 50000 / 20 = 2500
    assert pos.avg_cost_cents == 2500
    assert pos.qty == 20


@pytest.mark.unit
def test_realized_gain_on_sell(session: Session) -> None:
    inst = _make_instrument(session, "FDJ3")
    # Buy 10 @ €20
    record_trade(
        TradeCreate(
            instrument_id=inst.id,
            kind="buy",
            date="2024-01-10",
            qty=10,
            price_cents=2000,
            order_cost_cents=0,
        ),
        session,
    )  # type: ignore[arg-type]

    # Sell 5 @ €30 (gain per share = 30 - 20 = €10)
    trade = record_trade(
        TradeCreate(
            instrument_id=inst.id,
            kind="sell",
            date="2024-01-20",
            qty=5,
            price_cents=3000,
            order_cost_cents=0,
        ),
        session,
    )  # type: ignore[arg-type]

    # realized = (3000 - 2000) * 5 = 5000 = €50.00
    assert trade.realized_cents == 5000


@pytest.mark.unit
def test_pfu_reserve_on_positive_gain(session: Session) -> None:
    """PFU (30%) is reserved on positive realized gains."""
    # Set PFU to 0.30
    setting = Setting(key="pfu", value="0.30")
    session.add(setting)
    session.commit()

    inst = _make_instrument(session, "FDJ4")
    record_trade(
        TradeCreate(
            instrument_id=inst.id,
            kind="buy",
            date="2024-01-10",
            qty=10,
            price_cents=1000,
            order_cost_cents=0,
        ),
        session,
    )  # type: ignore[arg-type]

    # Sell all 10 @ €20 — realized = (2000 - 1000) * 10 = 10000
    trade = record_trade(
        TradeCreate(
            instrument_id=inst.id,
            kind="sell",
            date="2024-01-20",
            qty=10,
            price_cents=2000,
            order_cost_cents=0,
        ),
        session,
    )  # type: ignore[arg-type]

    assert trade.realized_cents == 10000
    # tax = 10000 * 0.30 = 3000
    assert trade.tax_reserved_cents == 3000


@pytest.mark.unit
def test_no_pfu_on_loss(session: Session) -> None:
    """No PFU reserved when selling at a loss."""
    setting = Setting(key="pfu", value="0.30")
    session.add(setting)
    session.commit()

    inst = _make_instrument(session, "FDJ5")
    record_trade(
        TradeCreate(
            instrument_id=inst.id,
            kind="buy",
            date="2024-01-10",
            qty=10,
            price_cents=3000,
            order_cost_cents=0,
        ),
        session,
    )  # type: ignore[arg-type]

    trade = record_trade(
        TradeCreate(
            instrument_id=inst.id,
            kind="sell",
            date="2024-01-20",
            qty=10,
            price_cents=2000,
            order_cost_cents=0,
        ),
        session,
    )  # type: ignore[arg-type]

    assert trade.realized_cents is not None and trade.realized_cents < 0
    assert trade.tax_reserved_cents == 0


@pytest.mark.unit
def test_partial_sell_leaves_remaining_position(session: Session) -> None:
    inst = _make_instrument(session, "FDJ6")
    record_trade(
        TradeCreate(
            instrument_id=inst.id,
            kind="buy",
            date="2024-01-10",
            qty=20,
            price_cents=1000,
            order_cost_cents=0,
        ),
        session,
    )  # type: ignore[arg-type]
    record_trade(
        TradeCreate(
            instrument_id=inst.id,
            kind="sell",
            date="2024-01-20",
            qty=8,
            price_cents=1500,
            order_cost_cents=0,
        ),
        session,
    )  # type: ignore[arg-type]

    pos_list = positions(session)
    pos = next((p for p in pos_list if p.instrument.ticker == "FDJ6"), None)
    assert pos is not None
    assert pos.qty == 12


@pytest.mark.unit
def test_update_price_creates_price_row(session: Session) -> None:
    inst = _make_instrument(session, "FDJ7")
    price = update_price(inst.id, 5000, session)  # type: ignore[arg-type]
    assert price.price_cents == 5000
    assert current_price(inst.id, session) == 5000  # type: ignore[arg-type]


@pytest.mark.unit
def test_update_price_twice_same_day_updates_existing_row(session: Session) -> None:
    inst = _make_instrument(session, "FDJ8")
    update_price(inst.id, 5000, session)  # type: ignore[arg-type]
    update_price(inst.id, 6000, session)  # type: ignore[arg-type]
    assert current_price(inst.id, session) == 6000  # type: ignore[arg-type]


@pytest.mark.unit
def test_update_price_unknown_instrument_raises(session: Session) -> None:
    with pytest.raises(ValueError, match="not found"):
        update_price(9999, 1000, session)


@pytest.mark.unit
def test_get_instrument_by_ticker(session: Session) -> None:
    inst = _make_instrument(session, "FDJ9")
    found = get_instrument_by_ticker("FDJ9", session)
    assert found is not None
    assert found.id == inst.id
    assert get_instrument_by_ticker("MISSING", session) is None


@pytest.mark.unit
def test_position_for_instrument(session: Session) -> None:
    inst = _make_instrument(session, "FDJ10")
    record_trade(
        TradeCreate(
            instrument_id=inst.id,
            kind="buy",
            date="2024-01-10",
            qty=10,
            price_cents=2000,
            order_cost_cents=0,
        ),
        session,
    )  # type: ignore[arg-type]
    pos = position_for_instrument(inst.id, session)  # type: ignore[arg-type]
    assert pos is not None
    assert pos.qty == 10


@pytest.mark.unit
def test_position_for_instrument_none_without_trades(session: Session) -> None:
    inst = _make_instrument(session, "FDJ11")
    assert position_for_instrument(inst.id, session) is None  # type: ignore[arg-type]


@pytest.mark.unit
def test_delete_trade_removes_position(session: Session) -> None:
    inst = _make_instrument(session, "FDJ12")
    trade = record_trade(
        TradeCreate(
            instrument_id=inst.id,
            kind="buy",
            date="2024-01-10",
            qty=10,
            price_cents=2000,
            order_cost_cents=0,
        ),
        session,
    )  # type: ignore[arg-type]
    delete_trade(trade.id, session)  # type: ignore[arg-type]
    assert position_for_instrument(inst.id, session) is None  # type: ignore[arg-type]


@pytest.mark.unit
def test_delete_trade_unknown_raises(session: Session) -> None:
    with pytest.raises(ValueError, match="not found"):
        delete_trade(9999, session)
