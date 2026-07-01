import pytest
from app.models.tables import Account
from app.money import fmt_eur
from app.schemas.forms import AccountCreate
from app.services.accounts import create_account
from fastapi.testclient import TestClient
from sqlmodel import Session


def _seed_account(session: Session, code: str = "AV-TEST") -> Account:
    return create_account(
        AccountCreate(code=code, name=code, tier="Diferido", opening_date="2024-01-01"),
        session,
    )


@pytest.mark.integration
def test_conta_detail_shows_valuation_section(client: TestClient, session: Session) -> None:
    _seed_account(session)
    response = client.get("/contas/AV-TEST")
    assert response.status_code == 200
    assert "account-valuations" in response.text


@pytest.mark.integration
def test_record_valuation(client: TestClient, session: Session) -> None:
    acc = _seed_account(session)
    response = client.post(
        f"/contas/{acc.id}/valuations",
        data={"period": "2024-01", "balance_str": "1234,56"},
    )
    assert response.status_code == 200
    assert fmt_eur(123_456) in response.text


@pytest.mark.integration
def test_record_valuation_updates_current_balance(client: TestClient, session: Session) -> None:
    from app.services.balances import balance

    acc = _seed_account(session)
    client.post(
        f"/contas/{acc.id}/valuations",
        data={"period": "2024-01", "balance_str": "500,00"},
    )
    assert balance(acc.id, session) == 50_000  # type: ignore[arg-type]


@pytest.mark.integration
def test_record_valuation_upsert_same_period(client: TestClient, session: Session) -> None:
    from app.services.valuations import list_valuations

    acc = _seed_account(session)
    client.post(f"/contas/{acc.id}/valuations", data={"period": "2024-01", "balance_str": "100,00"})
    client.post(f"/contas/{acc.id}/valuations", data={"period": "2024-01", "balance_str": "200,00"})
    rows = list_valuations(acc.id, session)  # type: ignore[arg-type]
    assert len(rows) == 1
    assert rows[0].balance_cents == 20_000


@pytest.mark.integration
def test_record_valuation_invalid_amount_shows_error(client: TestClient, session: Session) -> None:
    acc = _seed_account(session)
    response = client.post(
        f"/contas/{acc.id}/valuations",
        data={"period": "2024-01", "balance_str": "not-a-number"},
    )
    assert response.status_code == 200
    assert "Valor inválido" in response.text or "Invalid value" in response.text


@pytest.mark.integration
def test_delete_valuation(client: TestClient, session: Session) -> None:
    from app.services.valuations import list_valuations

    acc = _seed_account(session)
    client.post(f"/contas/{acc.id}/valuations", data={"period": "2024-01", "balance_str": "100,00"})
    response = client.request("DELETE", f"/contas/{acc.id}/valuations/2024-01")
    assert response.status_code == 200
    assert list_valuations(acc.id, session) == []  # type: ignore[arg-type]
