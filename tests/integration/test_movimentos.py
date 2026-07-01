import pytest
from app.models.tables import Account, Txn, TxnNote
from fastapi.testclient import TestClient
from sqlmodel import Session, select


def _seed_account(session: Session, code: str, tier: str = "Imediato", opening: int = 0) -> Account:
    a = Account(code=code, name=code, tier=tier, opening_cents=opening, opening_date="2024-01-01")
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


@pytest.mark.integration
def test_post_movement_returns_ledger_fragment(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "CC1", opening=0)
    response = client.post(
        "/movimentos",
        data={
            "date": "2024-06-01",
            "to_account": str(acc.id),
            "amount_str": "100.00",
            "comment": "Teste",
        },
    )
    assert response.status_code == 200
    assert "Teste" in response.text


@pytest.mark.integration
def test_post_movement_updates_balance(client: TestClient, session: Session) -> None:
    from app.services.balances import balance

    acc = _seed_account(session, "CC2", opening=50000)
    client.post(
        "/movimentos",
        data={
            "date": "2024-06-01",
            "to_account": str(acc.id),
            "amount_str": "200.00",
        },
    )
    assert balance(acc.id, session) == 50000 + 20000  # type: ignore[arg-type]


@pytest.mark.integration
def test_get_movimentos_page(client: TestClient, session: Session) -> None:
    response = client.get("/movimentos")
    assert response.status_code == 200
    assert "Lançar" in response.text


@pytest.mark.integration
def test_movimentos_lists_recent_transactions(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "CC3", opening=0)
    client.post(
        "/movimentos",
        data={
            "date": "2024-06-01",
            "to_account": str(acc.id),
            "amount_str": "50.00",
            "comment": "Salário junho",
        },
    )
    response = client.get("/movimentos")
    assert "Salário junho" in response.text


@pytest.mark.integration
def test_movimentos_filters_by_date_range(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "CC4", opening=0)
    client.post(
        "/movimentos",
        data={
            "date": "2024-01-01",
            "to_account": str(acc.id),
            "amount_str": "10.00",
            "comment": "Janeiro",
        },
    )
    client.post(
        "/movimentos",
        data={
            "date": "2024-12-01",
            "to_account": str(acc.id),
            "amount_str": "20.00",
            "comment": "Dezembro",
        },
    )
    response = client.get("/movimentos", params={"date_from": "2024-06-01"})
    assert "Dezembro" in response.text
    assert "Janeiro" not in response.text


@pytest.mark.integration
def test_movimentos_pagination(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "CC5", opening=0)
    for i in range(1, 4):
        client.post(
            "/movimentos",
            data={
                "date": f"2024-01-0{i}",
                "to_account": str(acc.id),
                "amount_str": "10.00",
                "comment": f"Txn{i}",
            },
        )
    response = client.get(
        "/movimentos",
        params={"page": 1, "date_from": "2024-01-01", "date_to": "2024-01-03"},
    )
    assert response.status_code == 200
    assert "página 1 de 1" in response.text


@pytest.mark.integration
def test_movimentos_htmx_request_returns_fragment_only(
    client: TestClient, session: Session
) -> None:
    response = client.get("/movimentos", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "sidebar__logo" not in response.text
    assert 'id="ledger"' in response.text


@pytest.mark.integration
def test_movimentos_plain_get_returns_full_page(client: TestClient, session: Session) -> None:
    response = client.get("/movimentos")
    assert response.status_code == 200
    assert "sidebar__logo" in response.text


@pytest.mark.integration
def test_delete_movimento_removes_it(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "CC6", opening=0)
    post_response = client.post(
        "/movimentos",
        data={
            "date": "2024-06-01",
            "to_account": str(acc.id),
            "amount_str": "75.00",
            "comment": "Para remover",
        },
    )
    assert "Para remover" in post_response.text
    txn_id = session.exec(select(Txn).where(Txn.comment == "Para remover")).first().id  # type: ignore[union-attr]

    delete_response = client.request("DELETE", f"/movimentos/{txn_id}")
    assert delete_response.status_code == 200
    assert "Para remover" not in delete_response.text

    list_response = client.get("/movimentos")
    assert "Para remover" not in list_response.text


@pytest.mark.integration
def test_post_movement_with_needs_resolution_checkbox(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "CC7", opening=0)
    response = client.post(
        "/movimentos",
        data={
            "date": "2024-06-01",
            "to_account": str(acc.id),
            "amount_str": "50.00",
            "comment": "Emprestei",
            "needs_resolution": "on",
        },
    )
    assert response.status_code == 200
    txn = session.exec(select(Txn).where(Txn.comment == "Emprestei")).first()
    assert txn is not None
    assert txn.needs_resolution == 1


@pytest.mark.integration
def test_toggle_needs_resolution_route(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "CC8", opening=0)
    client.post(
        "/movimentos",
        data={"date": "2024-06-01", "to_account": str(acc.id), "amount_str": "10.00"},
    )
    txn = session.exec(select(Txn)).first()
    assert txn is not None

    response = client.patch(f"/movimentos/{txn.id}/needs-resolution?needs_resolution=true")
    assert response.status_code == 200
    session.refresh(txn)
    assert txn.needs_resolution == 1

    response = client.patch(f"/movimentos/{txn.id}/needs-resolution?needs_resolution=false")
    assert response.status_code == 200
    session.refresh(txn)
    assert txn.needs_resolution == 0


@pytest.mark.integration
def test_resolve_edit_route_renders_modal(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "CC9", opening=0)
    client.post(
        "/movimentos",
        data={"date": "2024-06-01", "to_account": str(acc.id), "amount_str": "10.00"},
    )
    txn = session.exec(select(Txn)).first()
    assert txn is not None

    response = client.get(f"/movimentos/{txn.id}/resolve/edit")
    assert response.status_code == 200
    assert 'id="resolve-modal"' in response.text


@pytest.mark.integration
def test_resolve_candidates_excludes_self_and_filters(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "CC10", opening=0)
    client.post(
        "/movimentos",
        data={
            "date": "2024-06-01",
            "to_account": str(acc.id),
            "amount_str": "10.00",
            "comment": "Aluguel",
        },
    )
    client.post(
        "/movimentos",
        data={
            "date": "2024-06-02",
            "to_account": str(acc.id),
            "amount_str": "20.00",
            "comment": "Mercado",
        },
    )
    aluguel = session.exec(select(Txn).where(Txn.comment == "Aluguel")).first()
    assert aluguel is not None

    response = client.get(f"/movimentos/{aluguel.id}/resolve/candidates", params={"q": "Aluguel"})
    assert response.status_code == 200
    assert "Aluguel" not in response.text
    assert "Mercado" not in response.text

    response = client.get(f"/movimentos/{aluguel.id}/resolve/candidates", params={"q": "Mercado"})
    assert "Mercado" in response.text


@pytest.mark.integration
def test_post_resolve_with_pair_succeeds(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "CC11", opening=0)
    client.post(
        "/movimentos",
        data={"date": "2024-06-01", "to_account": str(acc.id), "amount_str": "10.00"},
    )
    client.post(
        "/movimentos",
        data={"date": "2024-06-02", "to_account": str(acc.id), "amount_str": "10.00"},
    )
    txns = session.exec(select(Txn)).all()
    a, b = txns[0], txns[1]

    response = client.post(f"/movimentos/{a.id}/resolve", data={"resolved_txn_id": str(b.id)})
    assert response.status_code == 200
    session.refresh(a)
    assert a.resolved_txn_id == b.id


@pytest.mark.integration
def test_post_resolve_with_note_succeeds(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "CC12", opening=0)
    client.post(
        "/movimentos",
        data={"date": "2024-06-01", "to_account": str(acc.id), "amount_str": "10.00"},
    )
    txn = session.exec(select(Txn)).first()
    assert txn is not None

    response = client.post(f"/movimentos/{txn.id}/resolve", data={"resolution_note": "Perdoado"})
    assert response.status_code == 200
    session.refresh(txn)
    assert txn.resolution_note == "Perdoado"


@pytest.mark.integration
def test_post_resolve_requires_one_field_returns_error(
    client: TestClient, session: Session
) -> None:
    acc = _seed_account(session, "CC13", opening=0)
    client.post(
        "/movimentos",
        data={"date": "2024-06-01", "to_account": str(acc.id), "amount_str": "10.00"},
    )
    txn = session.exec(select(Txn)).first()
    assert txn is not None

    response = client.post(f"/movimentos/{txn.id}/resolve", data={})
    assert response.status_code == 200
    assert response.headers["HX-Retarget"] == "#resolve-modal-container"
    assert response.headers["HX-Reswap"] == "innerHTML"


@pytest.mark.integration
def test_delete_resolve_clears_link(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "CC14", opening=0)
    client.post(
        "/movimentos",
        data={"date": "2024-06-01", "to_account": str(acc.id), "amount_str": "10.00"},
    )
    client.post(
        "/movimentos",
        data={"date": "2024-06-02", "to_account": str(acc.id), "amount_str": "10.00"},
    )
    txns = session.exec(select(Txn)).all()
    a, b = txns[0], txns[1]
    client.post(f"/movimentos/{a.id}/resolve", data={"resolved_txn_id": str(b.id)})

    response = client.request("DELETE", f"/movimentos/{a.id}/resolve")
    assert response.status_code == 200
    session.refresh(a)
    assert a.resolved_txn_id is None


@pytest.mark.integration
def test_delete_movimento_that_is_a_resolved_pair_clears_dependent(
    client: TestClient, session: Session
) -> None:
    acc = _seed_account(session, "CC15", opening=0)
    client.post(
        "/movimentos",
        data={"date": "2024-06-01", "to_account": str(acc.id), "amount_str": "10.00"},
    )
    client.post(
        "/movimentos",
        data={"date": "2024-06-02", "to_account": str(acc.id), "amount_str": "10.00"},
    )
    txns = session.exec(select(Txn)).all()
    a, b = txns[0], txns[1]
    client.post(f"/movimentos/{a.id}/resolve", data={"resolved_txn_id": str(b.id)})

    response = client.request("DELETE", f"/movimentos/{b.id}")
    assert response.status_code == 200
    session.refresh(a)
    assert a.resolved_txn_id is None


@pytest.mark.integration
def test_ledger_splits_pending_and_regular_tables(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "CC17", opening=0)
    client.post(
        "/movimentos",
        data={
            "date": "2024-06-01",
            "to_account": str(acc.id),
            "amount_str": "10.00",
            "comment": "Emprestimo",
            "needs_resolution": "on",
        },
    )
    client.post(
        "/movimentos",
        data={
            "date": "2024-06-02",
            "to_account": str(acc.id),
            "amount_str": "20.00",
            "comment": "Compra normal",
        },
    )

    response = client.get("/movimentos")
    assert response.status_code == 200
    pending_pos = response.text.index("Emprestimo")
    regular_pos = response.text.index("Compra normal")
    assert pending_pos < regular_pos


@pytest.mark.integration
def test_resolved_txn_moves_from_pending_to_regular_table(
    client: TestClient, session: Session
) -> None:
    acc = _seed_account(session, "CC18", opening=0)
    client.post(
        "/movimentos",
        data={
            "date": "2024-06-01",
            "to_account": str(acc.id),
            "amount_str": "10.00",
            "comment": "Emprestei",
            "needs_resolution": "on",
        },
    )
    txn = session.exec(select(Txn).where(Txn.comment == "Emprestei")).first()
    assert txn is not None

    before = client.get("/movimentos")
    assert before.text.index("Emprestei") < before.text.index("Movimentos")

    response = client.post(f"/movimentos/{txn.id}/resolve", data={"resolution_note": "Pago"})
    assert response.status_code == 200
    assert response.text.index("Movimentos") < response.text.index("Emprestei")


@pytest.mark.integration
def test_resolve_via_account_statement_view(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "CC16", opening=0)
    client.post(
        "/movimentos",
        data={"date": "2024-06-01", "to_account": str(acc.id), "amount_str": "10.00"},
    )
    txn = session.exec(select(Txn)).first()
    assert txn is not None

    response = client.post(
        f"/movimentos/{txn.id}/resolve",
        params={"view": "statement", "account_id": acc.id},
        data={"resolution_note": "Perdoado"},
    )
    assert response.status_code == 200
    assert 'id="account-statement"' in response.text
    session.refresh(txn)
    assert txn.resolution_note == "Perdoado"


@pytest.mark.integration
def test_notes_modal_shows_empty_state(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "CC19", opening=0)
    client.post(
        "/movimentos",
        data={"date": "2024-06-01", "to_account": str(acc.id), "amount_str": "10.00"},
    )
    txn = session.exec(select(Txn)).first()
    assert txn is not None

    response = client.get(f"/movimentos/{txn.id}/notes")
    assert response.status_code == 200
    assert 'id="notes-modal"' in response.text


@pytest.mark.integration
def test_post_txn_note_adds_it_and_updates_badge(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "CC20", opening=0)
    client.post(
        "/movimentos",
        data={"date": "2024-06-01", "to_account": str(acc.id), "amount_str": "10.00"},
    )
    txn = session.exec(select(Txn)).first()
    assert txn is not None

    response = client.post(f"/movimentos/{txn.id}/notes", data={"text": "Primeira nota"})
    assert response.status_code == 200
    assert "Primeira nota" in response.text
    assert f'id="txn-notes-badge-{txn.id}"' in response.text
    assert 'hx-swap-oob="true"' in response.text


@pytest.mark.integration
def test_post_txn_note_blank_returns_error(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "CC21", opening=0)
    client.post(
        "/movimentos",
        data={"date": "2024-06-01", "to_account": str(acc.id), "amount_str": "10.00"},
    )
    txn = session.exec(select(Txn)).first()
    assert txn is not None

    response = client.post(f"/movimentos/{txn.id}/notes", data={"text": "  "})
    assert response.status_code == 200
    assert "editable-error" in response.text


@pytest.mark.integration
def test_delete_txn_note_removes_it(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "CC22", opening=0)
    client.post(
        "/movimentos",
        data={"date": "2024-06-01", "to_account": str(acc.id), "amount_str": "10.00"},
    )
    txn = session.exec(select(Txn)).first()
    assert txn is not None
    client.post(f"/movimentos/{txn.id}/notes", data={"text": "Para remover"})
    note = session.exec(select(TxnNote).where(TxnNote.txn_id == txn.id)).first()
    assert note is not None

    response = client.request("DELETE", f"/movimentos/{txn.id}/notes/{note.id}")
    assert response.status_code == 200
    assert "Para remover" not in response.text


@pytest.mark.integration
def test_notes_badge_appears_in_ledger_and_statement(client: TestClient, session: Session) -> None:
    acc = _seed_account(session, "CC23", opening=0)
    client.post(
        "/movimentos",
        data={"date": "2024-06-01", "to_account": str(acc.id), "amount_str": "10.00"},
    )
    txn = session.exec(select(Txn)).first()
    assert txn is not None
    client.post(f"/movimentos/{txn.id}/notes", data={"text": "Uma nota"})

    ledger_response = client.get("/movimentos")
    assert f'id="txn-notes-badge-{txn.id}"' in ledger_response.text

    statement_response = client.get("/contas/CC23")
    assert f'id="txn-notes-badge-{txn.id}"' in statement_response.text
