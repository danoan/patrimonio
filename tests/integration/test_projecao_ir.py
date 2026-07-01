import pytest
from app.models.tables import Account, Person
from app.schemas.forms import AccountCreate
from app.services.accounts import create_account
from app.services.ir import seed_default_brackets
from fastapi.testclient import TestClient
from sqlmodel import Session


def _seed_account(session: Session, code: str, opening: int = 100_000) -> Account:
    return create_account(
        AccountCreate(
            code=code,
            name=code,
            tier="Imediato",
            opening_cents=opening,
            opening_date="2024-01-01",
        ),
        session,
    )


@pytest.mark.integration
def test_projecao_page_empty(client: TestClient) -> None:
    response = client.get("/projecao")
    assert response.status_code == 200


@pytest.mark.integration
def test_projecao_page_with_accounts(client: TestClient, session: Session) -> None:
    _seed_account(session, "PROJ1", opening=500_000)
    response = client.get("/projecao")
    assert response.status_code == 200
    assert "PROJ1" not in response.text  # account codes aren't on this page
    assert "Imediato" in response.text


@pytest.mark.integration
def test_projecao_months_param(client: TestClient, session: Session) -> None:
    _seed_account(session, "PROJ2")
    response = client.get("/projecao?months=12")
    assert response.status_code == 200


@pytest.mark.integration
def test_ir_page_no_brackets_seeds_defaults(client: TestClient) -> None:
    response = client.get("/ir")
    assert response.status_code == 200
    assert "11" in response.text  # 11 % bracket appears


@pytest.mark.integration
def test_ir_page_with_people(client: TestClient, session: Session) -> None:
    seed_default_brackets(session)
    p = Person(
        name="Daniel",
        gross_cents=400_000,
        net_before_taxes_cents=320_000,
        net_before_taxes_avg_cents=320_000,
        ir_rate=0.125,
    )
    session.add(p)
    session.commit()
    response = client.get("/ir")
    assert response.status_code == 200
    assert "Daniel" in response.text


@pytest.mark.integration
def test_ir_brackets_reset(client: TestClient, session: Session) -> None:
    p = Person(
        name="Test",
        gross_cents=300_000,
        net_before_taxes_cents=240_000,
        net_before_taxes_avg_cents=240_000,
        ir_rate=0.0,
    )
    session.add(p)
    session.commit()
    response = client.post("/ir/brackets/reset")
    assert response.status_code == 200
    assert "Test" in response.text  # person appears in results after reset
