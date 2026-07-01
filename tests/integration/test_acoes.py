import pytest
from app.models.tables import Instrument
from app.schemas.forms import TradeCreate
from app.services.stocks import record_trade
from fastapi.testclient import TestClient
from sqlmodel import Session


def _seed_instrument(session: Session, ticker: str = "FDJ") -> Instrument:
    inst = Instrument(ticker=ticker, name=ticker, currency="EUR")
    session.add(inst)
    session.commit()
    session.refresh(inst)
    return inst


def _seed_trade(session: Session, instrument_id: int, qty: int = 10, price_cents: int = 2000):
    return record_trade(
        TradeCreate(
            instrument_id=instrument_id,
            kind="buy",
            date="2024-01-10",
            qty=qty,
            price_cents=price_cents,
            order_cost_cents=0,
        ),
        session,
    )


@pytest.mark.integration
def test_price_field_edit_widget_get(client: TestClient, session: Session) -> None:
    inst = _seed_instrument(session, "ACP1")
    response = client.get(f"/acoes/instruments/{inst.id}/price/edit")
    assert response.status_code == 200
    assert 'name="value"' in response.text


@pytest.mark.integration
def test_price_field_edit_widget_unknown_instrument(client: TestClient) -> None:
    response = client.get("/acoes/instruments/9999/price/edit")
    assert response.status_code == 404


@pytest.mark.integration
def test_price_field_patch_valid(client: TestClient, session: Session) -> None:
    inst = _seed_instrument(session, "ACP2")
    _seed_trade(session, inst.id)  # type: ignore[arg-type]
    response = client.patch(f"/acoes/instruments/{inst.id}/price", data={"value": "45,50"})
    assert response.status_code == 200
    assert 'id="positions"' in response.text
    assert "45,50" in response.text


@pytest.mark.integration
def test_price_field_patch_invalid(client: TestClient, session: Session) -> None:
    inst = _seed_instrument(session, "ACP3")
    response = client.patch(f"/acoes/instruments/{inst.id}/price", data={"value": "abc"})
    assert response.status_code == 200
    assert response.headers["HX-Retarget"] == "closest td"


@pytest.mark.integration
def test_acoes_detail_page(client: TestClient, session: Session) -> None:
    inst = _seed_instrument(session, "ACP4")
    _seed_trade(session, inst.id)  # type: ignore[arg-type]
    response = client.get(f"/acoes/{inst.ticker}")
    assert response.status_code == 200
    assert "ACP4" in response.text
    assert "2024-01-10" in response.text


@pytest.mark.integration
def test_acoes_detail_page_unknown_ticker(client: TestClient) -> None:
    response = client.get("/acoes/UNKNOWN")
    assert response.status_code == 404


@pytest.mark.integration
def test_delete_trade(client: TestClient, session: Session) -> None:
    inst = _seed_instrument(session, "ACP5")
    trade = _seed_trade(session, inst.id)  # type: ignore[arg-type]
    response = client.delete(f"/acoes/{inst.ticker}/trades/{trade.id}")
    assert response.status_code == 200
    assert 'id="instrument-detail"' in response.text
    assert "2024-01-10" not in response.text


@pytest.mark.integration
def test_delete_trade_unknown_ticker(client: TestClient) -> None:
    response = client.delete("/acoes/UNKNOWN/trades/1")
    assert response.status_code == 404
