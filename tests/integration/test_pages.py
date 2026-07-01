"""Smoke tests for pages and partials that lack coverage."""

import pytest
from app.models.tables import Account, Person
from app.schemas.forms import AccountCreate, TxnCreate
from app.services.accounts import create_account
from app.services.ledger import create_txn
from fastapi.testclient import TestClient
from sqlmodel import Session


def _seed_account(session: Session, code: str, tier: str = "Imediato") -> Account:
    return create_account(
        AccountCreate(code=code, name=code, tier=tier, opening_date="2024-01-01"),
        session,
    )


@pytest.mark.integration
def test_overview_page(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "patrimônio" in response.text.lower()


@pytest.mark.integration
def test_overview_chart_placeholder_when_no_txns(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "<svg" not in response.text
    assert "Histórico disponível após lançamentos" in response.text


@pytest.mark.integration
def test_overview_chart_renders_with_multi_month_history(
    client: TestClient, session: Session
) -> None:
    acc = _seed_account(session, "OV-CHART")
    create_txn(
        TxnCreate(date="2024-01-15", to_account=acc.id, amount_cents=10_000),  # type: ignore[arg-type]
        session,
    )
    response = client.get("/")
    assert response.status_code == 200
    assert "<svg" in response.text
    assert "2024-01" in response.text


@pytest.mark.integration
def test_overview_kpis_partial(client: TestClient) -> None:
    response = client.get("/partials/kpis")
    assert response.status_code == 200
    assert "Imediato" in response.text


@pytest.mark.integration
def test_contas_page(client: TestClient, session: Session) -> None:
    _seed_account(session, "CONTAS-TEST")
    response = client.get("/contas")
    assert response.status_code == 200
    assert "CONTAS-TEST" in response.text


@pytest.mark.integration
def test_conta_detail_page(client: TestClient, session: Session) -> None:
    _seed_account(session, "DETAIL-ACC")
    response = client.get("/contas/DETAIL-ACC")
    assert response.status_code == 200
    assert "DETAIL-ACC" in response.text


@pytest.mark.integration
def test_conta_detail_not_found(client: TestClient) -> None:
    response = client.get("/contas/DOESNOTEXIST")
    assert response.status_code == 404


@pytest.mark.integration
def test_divisao_page(client: TestClient, session: Session) -> None:
    response = client.get("/divisao")
    assert response.status_code == 200


@pytest.mark.integration
def test_divisao_with_people(client: TestClient, session: Session) -> None:
    p = Person(
        name="Daniel",
        gross_cents=400000,
        net_before_taxes_cents=320000,
        net_before_taxes_avg_cents=320000,
        ir_rate=0.2,
    )
    session.add(p)
    session.commit()
    response = client.get("/divisao")
    assert response.status_code == 200
    assert "Daniel" in response.text


@pytest.mark.integration
def test_acoes_page(client: TestClient) -> None:
    response = client.get("/acoes")
    assert response.status_code == 200


@pytest.mark.integration
def test_acoes_us_page(client: TestClient) -> None:
    response = client.get("/acoes-us")
    assert response.status_code == 200


@pytest.mark.integration
def test_config_page(client: TestClient) -> None:
    response = client.get("/config")
    assert response.status_code == 200
    assert "PFU" in response.text


@pytest.mark.integration
def test_create_person_via_config(client: TestClient) -> None:
    response = client.post(
        "/config/pessoas",
        data={
            "name": "Sofia",
            "gross_str": "3000.00",
            "net_before_taxes_str": "2400.00",
            "net_before_taxes_avg_str": "2400.00",
            "ir_str": "16,67",
        },
    )
    assert response.status_code == 200
    assert "Sofia" in response.text


@pytest.mark.integration
def test_rename_account_via_contas(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "RENAME-ACC")
    response = client.patch(
        f"/contas/{acc.id}/field/name",
        data={"value": "Renamed Account"},
    )
    assert response.status_code == 200
    assert "Renamed Account" in response.text


@pytest.mark.integration
def test_delete_lancamento_from_extrato(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "DEL-EXT")
    txn = create_txn(
        TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=1000, comment="Remover-me"),
        session,
    )
    response = client.request("DELETE", f"/contas/{acc.id}/lancamentos/{txn.id}")
    assert response.status_code == 200
    assert "Remover-me" not in response.text
    assert 'hx-swap-oob="true"' in response.text

    detail = client.get(f"/contas/{acc.code}")
    assert "Remover-me" not in detail.text


@pytest.mark.integration
def test_update_pfu(client: TestClient) -> None:
    response = client.post("/config/pfu", data={"pfu": "0.28"})
    assert response.status_code == 200
    assert "0.28" in response.text


@pytest.mark.integration
def test_update_fixed_expense_tag(client: TestClient) -> None:
    response = client.post("/config/fixed-expense-tag", data={"tag": "casa"})
    assert response.status_code == 200
    assert "casa" in response.text
    assert 'id="fixed-expense-tag-val"' in response.text


@pytest.mark.integration
def test_config_page_lists_rule_tags(client: TestClient, session: Session) -> None:
    from app.models.tables import RecurringRule

    session.add(RecurringRule(kind="fixed", description="Aluguel", amount_cents=1000, tags="casa"))
    session.commit()
    response = client.get("/config")
    assert response.status_code == 200
    assert "casa" in response.text
