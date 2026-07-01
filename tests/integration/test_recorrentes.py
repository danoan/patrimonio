import pytest
from app.models.tables import Account
from fastapi.testclient import TestClient
from sqlmodel import Session


def _seed_account(session: Session, code: str) -> Account:
    a = Account(code=code, name=code, tier="Imediato", opening_cents=0, opening_date="2024-01-01")
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


@pytest.mark.integration
def test_get_recorrentes_page(client: TestClient) -> None:
    response = client.get("/recorrentes")
    assert response.status_code == 200
    assert "Recorrentes" in response.text


@pytest.mark.integration
def test_create_recurring_rule(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "R1")
    response = client.post(
        "/recorrentes",
        data={
            "kind": "fixed",
            "description": "Renda",
            "to_account": str(acc.id),
            "amount_str": "800.00",
            "day_of_month": "1",
        },
    )
    assert response.status_code == 200
    assert "Renda" in response.text


@pytest.mark.integration
def test_post_pending_rule(client: TestClient, session: Session) -> None:
    from app.schemas.forms import RecurringRuleCreate
    from app.services.recurring import create_rule, pending_for_period

    acc = _seed_account(session, "R2")
    rule = create_rule(
        RecurringRuleCreate(
            kind="fixed",
            description="Seguro",
            to_account=acc.id,  # type: ignore[arg-type]
            amount_cents=5000,
        ),
        session,
    )

    period = "2024-06"
    assert any(r.id == rule.id for r in pending_for_period(period, session))

    response = client.post(
        f"/recorrentes/{rule.id}/post",
        data={"period": period},
    )
    assert response.status_code == 200
    # Should no longer be pending
    assert not any(r.id == rule.id for r in pending_for_period(period, session))


@pytest.mark.integration
def test_post_all_pending_rules(client: TestClient, session: Session) -> None:
    from app.schemas.forms import RecurringRuleCreate
    from app.services.recurring import create_rule, pending_for_period

    acc = _seed_account(session, "R3")
    rule1 = create_rule(
        RecurringRuleCreate(
            kind="fixed", description="Aluguel", to_account=acc.id, amount_cents=50000
        ),
        session,
    )
    rule2 = create_rule(
        RecurringRuleCreate(
            kind="fixed", description="Internet", to_account=acc.id, amount_cents=3000
        ),
        session,
    )

    period = "2024-06"
    response = client.post("/recorrentes/post-all", data={"period": period})
    assert response.status_code == 200
    assert "Aluguel" in response.text
    assert not any(r.id in {rule1.id, rule2.id} for r in pending_for_period(period, session))


@pytest.mark.integration
def test_get_recorrentes_preselects_account(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "R4")
    response = client.get("/recorrentes", params={"to_account": acc.id})
    assert response.status_code == 200
    assert f'value="{acc.id}" selected' in response.text


@pytest.mark.integration
def test_get_recorrentes_preselect_opens_modal(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "R4B")
    response = client.get("/recorrentes", params={"to_account": acc.id})
    assert response.status_code == 200
    assert '<dialog id="new-rule-modal" class="modal" open>' in response.text


@pytest.mark.integration
def test_get_recorrentes_without_preselect_modal_closed(client: TestClient) -> None:
    response = client.get("/recorrentes")
    assert response.status_code == 200
    assert '<dialog id="new-rule-modal" class="modal" >' in response.text


@pytest.mark.integration
def test_recorrentes_page_has_new_rule_button(client: TestClient) -> None:
    response = client.get("/recorrentes")
    assert response.status_code == 200
    assert 'data-modal-open="new-rule-modal"' in response.text


@pytest.mark.integration
def test_recorrentes_page_renders_category_chips(client: TestClient, session: Session) -> None:
    from app.schemas.forms import RecurringRuleCreate
    from app.services.recurring import create_rule

    acc = _seed_account(session, "R9")
    create_rule(
        RecurringRuleCreate(
            kind="fixed",
            description="Aluguel",
            to_account=acc.id,  # type: ignore[arg-type]
            amount_cents=1000,
            category="Despesa fixa",
        ),
        session,
    )
    response = client.get("/recorrentes")
    assert response.status_code == 200
    assert "data-category-filter-bar" in response.text
    assert 'data-category-chip="Despesa fixa"' in response.text


@pytest.mark.integration
def test_recorrentes_page_no_chips_without_categories(client: TestClient) -> None:
    response = client.get("/recorrentes")
    assert response.status_code == 200
    assert "data-category-filter-bar" not in response.text


@pytest.mark.integration
def test_recurring_rows_carry_data_category(client: TestClient, session: Session) -> None:
    from app.schemas.forms import RecurringRuleCreate
    from app.services.recurring import create_rule

    acc = _seed_account(session, "R10")
    create_rule(
        RecurringRuleCreate(
            kind="fixed",
            description="Internet",
            to_account=acc.id,  # type: ignore[arg-type]
            amount_cents=1000,
            category="Despesa fixa",
        ),
        session,
    )
    response = client.get("/recorrentes")
    assert response.status_code == 200
    assert 'data-category="Despesa fixa"' in response.text


@pytest.mark.integration
def test_create_rule_with_past_start_backfills_txns(client: TestClient, session: Session) -> None:
    from datetime import date

    from app.services.balances import balance

    acc = _seed_account(session, "R5")
    today = date.today()
    total = today.year * 12 + (today.month - 1) - 2
    start_period = f"{total // 12}-{total % 12 + 1:02d}"

    response = client.post(
        "/recorrentes",
        data={
            "kind": "fixed",
            "description": "Depósito retroativo",
            "to_account": str(acc.id),
            "amount_str": "100,00",
            "day_of_month": "5",
            "start_period": start_period,
        },
    )
    assert response.status_code == 200
    # Two past months should have been auto-posted as real txns.
    assert balance(acc.id, session) == 20000  # type: ignore[arg-type]


@pytest.mark.integration
def test_recorrentes_page_shows_ativos_and_terminados_sections(client: TestClient) -> None:
    response = client.get("/recorrentes")
    assert response.status_code == 200
    assert "Ativos" in response.text
    assert "Terminados" in response.text


@pytest.mark.integration
def test_finished_rule_appears_under_terminados(client: TestClient, session: Session) -> None:
    from app.schemas.forms import RecurringRuleCreate
    from app.services.recurring import _shift_period, create_rule, current_period

    acc = _seed_account(session, "R6")
    this_period = current_period()
    rule = create_rule(
        RecurringRuleCreate(
            kind="fixed",
            description="Regra Encerrada",
            to_account=acc.id,  # type: ignore[arg-type]
            amount_cents=1000,
            start_period=_shift_period(this_period, -3),
            end_period=_shift_period(this_period, -1),
        ),
        session,
    )
    response = client.get("/recorrentes")
    assert response.status_code == 200
    terminados_idx = response.text.index("Terminados")
    ativos_idx = response.text.index("Ativos")
    rule_idx = response.text.index("Regra Encerrada")
    assert ativos_idx < terminados_idx < rule_idx
    assert rule.id is not None


@pytest.mark.integration
def test_delete_rule_keeps_txns(client: TestClient, session: Session) -> None:
    from app.schemas.forms import RecurringRuleCreate
    from app.services.balances import balance
    from app.services.recurring import create_rule, post_rule

    acc = _seed_account(session, "R7")
    rule = create_rule(
        RecurringRuleCreate(
            kind="fixed",
            description="Para remover",
            to_account=acc.id,  # type: ignore[arg-type]
            amount_cents=2000,
        ),
        session,
    )
    post_rule(rule.id, "2024-01", session)  # type: ignore[union-attr]

    response = client.request("DELETE", f"/recorrentes/{rule.id}")
    assert response.status_code == 200
    assert "Para remover" not in response.text
    assert balance(acc.id, session) == 2000  # type: ignore[arg-type]


@pytest.mark.integration
def test_delete_rule_with_delete_txns_removes_txns(client: TestClient, session: Session) -> None:
    from app.schemas.forms import RecurringRuleCreate
    from app.services.balances import balance
    from app.services.recurring import create_rule, post_rule

    acc = _seed_account(session, "R8")
    rule = create_rule(
        RecurringRuleCreate(
            kind="fixed",
            description="Para remover com lançamentos",
            to_account=acc.id,  # type: ignore[arg-type]
            amount_cents=2000,
        ),
        session,
    )
    post_rule(rule.id, "2024-01", session)  # type: ignore[union-attr]

    response = client.request("DELETE", f"/recorrentes/{rule.id}", params={"delete_txns": "true"})
    assert response.status_code == 200
    assert balance(acc.id, session) == 0  # type: ignore[arg-type]


@pytest.mark.integration
def test_skip_rule(client: TestClient, session: Session) -> None:
    from app.schemas.forms import RecurringRuleCreate
    from app.services.recurring import create_rule, pending_for_period

    acc = _seed_account(session, "R3")
    rule = create_rule(
        RecurringRuleCreate(
            kind="fixed",
            description="Ginásio",
            to_account=acc.id,  # type: ignore[arg-type]
            amount_cents=3000,
        ),
        session,
    )

    period = "2024-07"
    response = client.post(
        f"/recorrentes/{rule.id}/skip",
        data={"period": period},
    )
    assert response.status_code == 200
    assert not any(r.id == rule.id for r in pending_for_period(period, session))
    # Still pending next month
    assert any(r.id == rule.id for r in pending_for_period("2024-08", session))


@pytest.mark.integration
def test_recorrentes_page_has_tab_bar(client: TestClient) -> None:
    response = client.get("/recorrentes")
    assert response.status_code == 200
    assert "data-tab-group" in response.text
    assert 'data-tab="list"' in response.text
    assert 'data-tab="by-account"' in response.text


@pytest.mark.integration
def test_recorrentes_page_shows_grouped_by_account(client: TestClient, session: Session) -> None:
    from app.schemas.forms import RecurringRuleCreate
    from app.services.recurring import create_rule

    acc = _seed_account(session, "R11")
    create_rule(
        RecurringRuleCreate(
            kind="fixed",
            description="Poupança",
            to_account=acc.id,  # type: ignore[arg-type]
            amount_cents=15000,
        ),
        session,
    )
    create_rule(
        RecurringRuleCreate(
            kind="fixed",
            description="Poupança extra",
            to_account=acc.id,  # type: ignore[arg-type]
            amount_cents=5000,
        ),
        session,
    )

    response = client.get("/recorrentes")
    assert response.status_code == 200
    assert 'data-panel="by-account"' in response.text
    assert "R11" in response.text
    assert "200,00" in response.text  # 15000 + 5000 cents summed
    assert "2 regra(s)" in response.text


@pytest.mark.integration
def test_create_recurring_rule_with_notes(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "R12")
    response = client.post(
        "/recorrentes",
        data={
            "kind": "fixed",
            "description": "Seguro carro",
            "to_account": str(acc.id),
            "amount_str": "50.00",
            "day_of_month": "1",
            "notes": "Renovar em janeiro",
        },
    )
    assert response.status_code == 200
    from app.models.tables import RecurringRule
    from sqlmodel import select

    rule = session.exec(
        select(RecurringRule).where(RecurringRule.description == "Seguro carro")
    ).first()
    assert rule is not None
    assert rule.notes == "Renovar em janeiro"


@pytest.mark.integration
def test_create_recurring_rule_with_tags(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "R12B")
    response = client.post(
        "/recorrentes",
        data={
            "kind": "fixed",
            "description": "Seguro casa",
            "to_account": str(acc.id),
            "amount_str": "50.00",
            "day_of_month": "1",
            "tags": "casa, seguro",
        },
    )
    assert response.status_code == 200
    from app.models.tables import RecurringRule
    from sqlmodel import select

    rule = session.exec(
        select(RecurringRule).where(RecurringRule.description == "Seguro casa")
    ).first()
    assert rule is not None
    assert rule.tags == "casa, seguro"


@pytest.mark.integration
def test_config_modal_edit_and_save(client: TestClient, session: Session) -> None:
    from app.schemas.forms import RecurringRuleCreate
    from app.services.recurring import create_rule

    acc = _seed_account(session, "R13")
    rule = create_rule(
        RecurringRuleCreate(
            kind="fixed",
            description="Internet",
            to_account=acc.id,  # type: ignore[arg-type]
            amount_cents=3000,
        ),
        session,
    )

    edit_response = client.get(f"/recorrentes/{rule.id}/config/edit")  # type: ignore[arg-type]
    assert edit_response.status_code == 200
    assert 'id="config-modal"' in edit_response.text
    assert "Internet" in edit_response.text

    save_response = client.post(
        f"/recorrentes/{rule.id}/config",  # type: ignore[arg-type]
        data={"notes": "Plano de 500Mb", "tags": "casa, internet"},
    )
    assert save_response.status_code == 200
    assert "⚙️" in save_response.text

    session.refresh(rule)  # type: ignore[arg-type]
    assert rule.notes == "Plano de 500Mb"  # type: ignore[union-attr]
    assert rule.tags == "casa, internet"  # type: ignore[union-attr]


@pytest.mark.integration
def test_config_modal_edit_missing_rule_404(client: TestClient) -> None:
    response = client.get("/recorrentes/9999/config/edit")
    assert response.status_code == 404
