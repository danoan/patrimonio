import pytest
from app.models.tables import Account, RecurringRule, Txn
from app.schemas.forms import AccountCreate
from app.services.accounts import create_account
from fastapi.testclient import TestClient
from sqlmodel import Session, select


def _seed_account(session: Session, code: str = "CD-TEST") -> Account:
    return create_account(
        AccountCreate(code=code, name=code, tier="Imediato", opening_date="2024-01-01"),
        session,
    )


@pytest.mark.integration
def test_conta_detail_shows_add_txn_modal(client: TestClient, session: Session) -> None:
    _seed_account(session)
    response = client.get("/contas/CD-TEST")
    assert response.status_code == 200
    assert 'id="add-txn-modal"' in response.text
    assert 'data-tab="once"' in response.text
    assert 'data-tab="recurring"' in response.text


@pytest.mark.integration
def test_post_lancamento_conta_creates_txn(client: TestClient, session: Session) -> None:
    acc = _seed_account(session)
    response = client.post(
        f"/contas/{acc.id}/lancamentos",
        data={
            "date": "2024-06-01",
            "to_account": str(acc.id),
            "amount_str": "150,00",
            "comment": "Depósito único",
        },
    )
    assert response.status_code == 200
    assert "Depósito único" in response.text
    assert 'id="account-statement"' in response.text

    txn = session.exec(select(Txn).where(Txn.comment == "Depósito único")).first()
    assert txn is not None
    assert txn.amount_cents == 15_000
    assert txn.to_account == acc.id


@pytest.mark.integration
def test_post_lancamento_conta_updates_balance_oob(client: TestClient, session: Session) -> None:
    acc = _seed_account(session)
    response = client.post(
        f"/contas/{acc.id}/lancamentos",
        data={"date": "2024-06-01", "to_account": str(acc.id), "amount_str": "100,00"},
    )
    assert 'id="current-balance-value"' in response.text
    assert 'hx-swap-oob="true"' in response.text


@pytest.mark.integration
def test_create_recorrente_with_statement_view_returns_account_statement(
    client: TestClient, session: Session
) -> None:
    acc = _seed_account(session)
    response = client.post(
        f"/recorrentes?view=statement&account_id={acc.id}",
        data={
            "kind": "fixed",
            "description": "Aporte mensal",
            "to_account": str(acc.id),
            "amount_str": "80,00",
            "day_of_month": "5",
        },
    )
    assert response.status_code == 200
    assert 'id="account-statement"' in response.text

    rule = session.exec(
        select(RecurringRule).where(RecurringRule.description == "Aporte mensal")
    ).first()
    assert rule is not None
    assert rule.to_account == acc.id


@pytest.mark.integration
def test_create_recorrente_without_statement_view_returns_recurring_list(
    client: TestClient, session: Session
) -> None:
    acc = _seed_account(session)
    response = client.post(
        "/recorrentes",
        data={
            "kind": "fixed",
            "description": "Sem view",
            "to_account": str(acc.id),
            "amount_str": "10,00",
        },
    )
    assert response.status_code == 200
    assert 'id="recurring-list"' in response.text
