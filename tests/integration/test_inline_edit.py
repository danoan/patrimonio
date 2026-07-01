import pytest
from app.models.tables import Account, Person, RecurringRule, UsdEvent
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


# ── Txn (ledger view) ──────────────────────────────────────────────


@pytest.mark.integration
def test_txn_field_edit_widget_get(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "IE-TXN1")
    txn = create_txn(
        TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=1000, comment="Orig"),
        session,
    )
    response = client.get(f"/movimentos/{txn.id}/field/comment/edit?view=ledger&page=1")
    assert response.status_code == 200
    assert "Orig" in response.text
    assert 'name="value"' in response.text


@pytest.mark.integration
def test_txn_field_patch_valid_updates_ledger(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "IE-TXN2")
    txn = create_txn(
        TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=1000, comment="Orig"),
        session,
    )
    response = client.patch(
        f"/movimentos/{txn.id}/field/comment?view=ledger&page=1",
        data={"value": "Updated"},
    )
    assert response.status_code == 200
    assert "Updated" in response.text
    assert 'id="ledger"' in response.text


@pytest.mark.integration
def test_txn_field_patch_invalid_amount_returns_error(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "IE-TXN3")
    txn = create_txn(
        TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=1000),
        session,
    )
    response = client.patch(
        f"/movimentos/{txn.id}/field/amount_cents?view=ledger&page=1",
        data={"value": "not-a-number"},
    )
    assert response.status_code == 200
    assert response.headers["HX-Retarget"] == "closest td"
    assert response.headers["HX-Reswap"] == "innerHTML"


@pytest.mark.integration
def test_txn_field_patch_tags(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "IE-TXN5")
    txn = create_txn(
        TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=1000),
        session,
    )
    response = client.patch(
        f"/movimentos/{txn.id}/field/tags?view=ledger&page=1",
        data={"value": "casa, mercado"},
    )
    assert response.status_code == 200
    assert "casa, mercado" in response.text
    assert 'id="ledger"' in response.text


@pytest.mark.integration
def test_txn_field_edit_via_statement_view(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "IE-TXN4")
    txn = create_txn(
        TxnCreate(date="2024-01-01", to_account=acc.id, amount_cents=1000),
        session,
    )
    response = client.patch(
        f"/movimentos/{txn.id}/field/amount_cents?view=statement&account_id={acc.id}",
        data={"value": "20,00"},
    )
    assert response.status_code == 200
    assert 'id="account-statement"' in response.text


# ── Account ─────────────────────────────────────────────────────────


@pytest.mark.integration
def test_account_field_edit_widget_get(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "IE-ACC1")
    response = client.get(f"/contas/{acc.id}/field/tier/edit")
    assert response.status_code == 200
    assert "<select" in response.text


@pytest.mark.integration
def test_account_field_patch_valid(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "IE-ACC2")
    response = client.patch(f"/contas/{acc.id}/field/tier", data={"value": "Diferido"})
    assert response.status_code == 200
    assert 'id="account-list"' in response.text


@pytest.mark.integration
def test_account_field_patch_account_type(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "IE-ACC4")
    response = client.patch(f"/contas/{acc.id}/field/account_type", data={"value": "savings"})
    assert response.status_code == 200
    assert 'id="account-list"' in response.text


@pytest.mark.integration
def test_account_field_patch_invalid_currency(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "IE-ACC3")
    response = client.patch(f"/contas/{acc.id}/field/currency", data={"value": "GBP"})
    assert response.status_code == 200
    assert response.headers["HX-Retarget"] == "closest td"


# ── RecurringRule ────────────────────────────────────────────────────


def _seed_rule(session: Session, account_id: int) -> RecurringRule:
    rule = RecurringRule(
        kind="fixed",
        description="Aluguel",
        to_account=account_id,
        amount_cents=50000,
        day_of_month=5,
    )
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule


@pytest.mark.integration
def test_rule_field_edit_widget_get(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "IE-RULE1")
    rule = _seed_rule(session, acc.id)  # type: ignore[arg-type]
    response = client.get(f"/recorrentes/{rule.id}/field/description/edit")
    assert response.status_code == 200
    assert "Aluguel" in response.text


@pytest.mark.integration
def test_rule_field_patch_valid(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "IE-RULE2")
    rule = _seed_rule(session, acc.id)  # type: ignore[arg-type]
    response = client.patch(
        f"/recorrentes/{rule.id}/field/description", data={"value": "Condomínio"}
    )
    assert response.status_code == 200
    assert "Condomínio" in response.text


@pytest.mark.integration
def test_rule_field_patch_invalid_day(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "IE-RULE3")
    rule = _seed_rule(session, acc.id)  # type: ignore[arg-type]
    response = client.patch(f"/recorrentes/{rule.id}/field/day_of_month", data={"value": "99"})
    assert response.status_code == 200
    assert response.headers["HX-Retarget"] == "closest td"


@pytest.mark.integration
def test_rule_field_edit_widget_get_to_account(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "IE-RULE4")
    rule = _seed_rule(session, acc.id)  # type: ignore[arg-type]
    response = client.get(f"/recorrentes/{rule.id}/field/to_account/edit")
    assert response.status_code == 200
    assert "<select" in response.text
    assert "IE-RULE4" in response.text


@pytest.mark.integration
def test_rule_field_patch_valid_to_account(client: TestClient, session: Session) -> None:
    acc1 = _seed_account(session, "IE-RULE5A")
    acc2 = _seed_account(session, "IE-RULE5B")
    rule = _seed_rule(session, acc1.id)  # type: ignore[arg-type]
    response = client.patch(
        f"/recorrentes/{rule.id}/field/to_account", data={"value": str(acc2.id)}
    )
    assert response.status_code == 200
    assert "IE-RULE5B" in response.text


@pytest.mark.integration
def test_rule_field_patch_invalid_account(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "IE-RULE6")
    rule = _seed_rule(session, acc.id)  # type: ignore[arg-type]
    response = client.patch(f"/recorrentes/{rule.id}/field/from_account", data={"value": "9999"})
    assert response.status_code == 200
    assert response.headers["HX-Retarget"] == "closest td"


# ── Person ────────────────────────────────────────────────────────────


def _seed_person(session: Session) -> Person:
    p = Person(
        name="Daniel",
        gross_cents=400000,
        net_before_taxes_cents=320000,
        net_before_taxes_avg_cents=320000,
        ir_rate=0.2,
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


@pytest.mark.integration
def test_person_field_edit_widget_get(client: TestClient, session: Session) -> None:
    p = _seed_person(session)
    response = client.get(f"/config/pessoas/{p.id}/field/gross_cents/edit")
    assert response.status_code == 200
    assert 'name="value"' in response.text


@pytest.mark.integration
def test_person_field_patch_valid(client: TestClient, session: Session) -> None:
    p = _seed_person(session)
    response = client.patch(f"/config/pessoas/{p.id}/field/name", data={"value": "Sofia"})
    assert response.status_code == 200
    assert "Sofia" in response.text


@pytest.mark.integration
def test_person_field_patch_invalid_rate(client: TestClient, session: Session) -> None:
    p = _seed_person(session)
    response = client.patch(f"/config/pessoas/{p.id}/field/ir_rate", data={"value": "abc"})
    assert response.status_code == 200
    assert response.headers["HX-Retarget"] == "closest td"


# ── UsdEvent ──────────────────────────────────────────────────────────


def _seed_usd_event(session: Session) -> UsdEvent:
    event = UsdEvent(
        date="2024-01-01",
        kind="vesting",
        gross_usd_cents=100000,
        net_usd_cents=75000,
        fx_eur_per_usd=0.93,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


@pytest.mark.integration
def test_usd_event_field_edit_widget_get(client: TestClient, session: Session) -> None:
    event = _seed_usd_event(session)
    response = client.get(f"/acoes-us/events/{event.id}/field/kind/edit")
    assert response.status_code == 200
    assert "<select" in response.text


@pytest.mark.integration
def test_usd_event_field_patch_valid_updates_section(client: TestClient, session: Session) -> None:
    event = _seed_usd_event(session)
    response = client.patch(
        f"/acoes-us/events/{event.id}/field/gross_usd_cents", data={"value": "2000,00"}
    )
    assert response.status_code == 200
    assert 'id="usd-section"' in response.text


@pytest.mark.integration
def test_usd_event_field_patch_invalid_kind(client: TestClient, session: Session) -> None:
    event = _seed_usd_event(session)
    response = client.patch(f"/acoes-us/events/{event.id}/field/kind", data={"value": "other"})
    assert response.status_code == 200
    assert response.headers["HX-Retarget"] == "closest td"
