import pytest
from app.schemas.forms import AccountCreate
from app.services.accounts import (
    create_account,
    deactivate_account,
    get_account,
    get_account_by_id,
    list_accounts,
    rename_account,
    retier_account,
    retype_account,
    update_field,
)
from sqlmodel import Session


@pytest.mark.unit
def test_create_account(session: Session) -> None:
    data = AccountCreate(
        code="CC-TEST",
        name="Test Account",
        tier="Imediato",
        opening_cents=50000,
        opening_date="2024-01-01",
    )
    account = create_account(data, session)
    assert account.id is not None
    assert account.code == "CC-TEST"
    assert account.tier == "Imediato"
    assert account.opening_cents == 50000
    assert account.account_type == "checking"


@pytest.mark.unit
def test_create_account_with_type(session: Session) -> None:
    data = AccountCreate(
        code="SV-TEST",
        name="Savings Account",
        tier="Alocado",
        account_type="savings",
        opening_date="2024-01-01",
    )
    account = create_account(data, session)
    assert account.account_type == "savings"


@pytest.mark.unit
def test_create_duplicate_code_raises(session: Session) -> None:
    data = AccountCreate(code="DUPL", name="A", tier="Imediato", opening_date="2024-01-01")
    create_account(data, session)
    with pytest.raises(ValueError, match="already exists"):
        create_account(data, session)


@pytest.mark.unit
def test_get_account_by_code(session: Session) -> None:
    data = AccountCreate(
        code="GET-TEST", name="Get Test", tier="Diferido", opening_date="2024-01-01"
    )
    created = create_account(data, session)
    found = get_account("GET-TEST", session)
    assert found is not None
    assert found.id == created.id


@pytest.mark.unit
def test_get_account_missing_returns_none(session: Session) -> None:
    assert get_account("NONEXISTENT", session) is None


@pytest.mark.unit
def test_get_account_by_id(session: Session) -> None:
    data = AccountCreate(code="ID-TEST", name="ID Test", tier="Alocado", opening_date="2024-01-01")
    created = create_account(data, session)
    found = get_account_by_id(created.id, session)  # type: ignore[arg-type]
    assert found is not None
    assert found.code == "ID-TEST"


@pytest.mark.unit
def test_list_accounts_active_only(session: Session) -> None:
    data1 = AccountCreate(code="ACTIVE", name="Active", tier="Imediato", opening_date="2024-01-01")
    a = create_account(data1, session)
    deactivate_account(a.id, session)  # type: ignore[arg-type]

    data2 = AccountCreate(
        code="STILL-ACTIVE", name="Still Active", tier="Imediato", opening_date="2024-01-01"
    )
    create_account(data2, session)

    active = list_accounts(session, active_only=True)
    codes = [acc.code for acc in active]
    assert "STILL-ACTIVE" in codes
    assert "ACTIVE" not in codes


@pytest.mark.unit
def test_list_accounts_all(session: Session) -> None:
    data1 = AccountCreate(code="ALL1", name="All1", tier="Imediato", opening_date="2024-01-01")
    a = create_account(data1, session)
    deactivate_account(a.id, session)  # type: ignore[arg-type]
    data2 = AccountCreate(code="ALL2", name="All2", tier="Imediato", opening_date="2024-01-01")
    create_account(data2, session)
    all_accounts = list_accounts(session, active_only=False)
    codes = [acc.code for acc in all_accounts]
    assert "ALL1" in codes
    assert "ALL2" in codes


@pytest.mark.unit
def test_rename_account(session: Session) -> None:
    data = AccountCreate(code="RENAME", name="Old Name", tier="Imediato", opening_date="2024-01-01")
    a = create_account(data, session)
    updated = rename_account(a.id, "New Name", session)  # type: ignore[arg-type]
    assert updated.name == "New Name"


@pytest.mark.unit
def test_rename_nonexistent_raises(session: Session) -> None:
    with pytest.raises(ValueError, match="not found"):
        rename_account(999, "X", session)


@pytest.mark.unit
def test_retier_account(session: Session) -> None:
    data = AccountCreate(code="RETIER", name="Retier", tier="Imediato", opening_date="2024-01-01")
    a = create_account(data, session)
    updated = retier_account(a.id, "Diferido", session)  # type: ignore[arg-type]
    assert updated.tier == "Diferido"


@pytest.mark.unit
def test_retier_invalid_tier_raises(session: Session) -> None:
    data = AccountCreate(code="RTINV", name="RT Inv", tier="Imediato", opening_date="2024-01-01")
    a = create_account(data, session)
    with pytest.raises(ValueError):
        retier_account(a.id, "Invalid", session)  # type: ignore[arg-type]


@pytest.mark.unit
def test_retype_account(session: Session) -> None:
    data = AccountCreate(code="RETYPE", name="Retype", tier="Imediato", opening_date="2024-01-01")
    a = create_account(data, session)
    updated = retype_account(a.id, "variable", session)  # type: ignore[arg-type]
    assert updated.account_type == "variable"


@pytest.mark.unit
def test_retype_invalid_account_type_raises(session: Session) -> None:
    data = AccountCreate(code="RTYINV", name="RTY Inv", tier="Imediato", opening_date="2024-01-01")
    a = create_account(data, session)
    with pytest.raises(ValueError):
        retype_account(a.id, "Invalid", session)  # type: ignore[arg-type]


@pytest.mark.unit
def test_deactivate_account(session: Session) -> None:
    data = AccountCreate(code="DEACT", name="Deact", tier="Imediato", opening_date="2024-01-01")
    a = create_account(data, session)
    deactivated = deactivate_account(a.id, session)  # type: ignore[arg-type]
    assert deactivated.active == 0


@pytest.mark.unit
def test_update_field_name(session: Session) -> None:
    data = AccountCreate(code="UF1", name="Old", tier="Imediato", opening_date="2024-01-01")
    a = create_account(data, session)
    updated = update_field(a.id, "name", "New", session)  # type: ignore[arg-type]
    assert updated.name == "New"


@pytest.mark.unit
def test_update_field_tier(session: Session) -> None:
    data = AccountCreate(code="UF2", name="UF2", tier="Imediato", opening_date="2024-01-01")
    a = create_account(data, session)
    updated = update_field(a.id, "tier", "Alocado", session)  # type: ignore[arg-type]
    assert updated.tier == "Alocado"


@pytest.mark.unit
def test_update_field_account_type(session: Session) -> None:
    data = AccountCreate(code="UF7", name="UF7", tier="Imediato", opening_date="2024-01-01")
    a = create_account(data, session)
    updated = update_field(a.id, "account_type", "savings", session)  # type: ignore[arg-type]
    assert updated.account_type == "savings"


@pytest.mark.unit
def test_update_field_currency(session: Session) -> None:
    data = AccountCreate(code="UF3", name="UF3", tier="Imediato", opening_date="2024-01-01")
    a = create_account(data, session)
    updated = update_field(a.id, "currency", "USD", session)  # type: ignore[arg-type]
    assert updated.currency == "USD"


@pytest.mark.unit
def test_update_field_invalid_currency_raises(session: Session) -> None:
    data = AccountCreate(code="UF4", name="UF4", tier="Imediato", opening_date="2024-01-01")
    a = create_account(data, session)
    with pytest.raises(ValueError):
        update_field(a.id, "currency", "GBP", session)  # type: ignore[arg-type]


@pytest.mark.unit
def test_update_field_opening_cents_and_date(session: Session) -> None:
    data = AccountCreate(code="UF5", name="UF5", tier="Imediato", opening_date="2024-01-01")
    a = create_account(data, session)
    updated = update_field(a.id, "opening_cents", "123,45", session)  # type: ignore[arg-type]
    assert updated.opening_cents == 12345
    updated = update_field(a.id, "opening_date", "2024-05-01", session)  # type: ignore[arg-type]
    assert updated.opening_date == "2024-05-01"


@pytest.mark.unit
def test_update_field_unknown_field_raises(session: Session) -> None:
    data = AccountCreate(code="UF6", name="UF6", tier="Imediato", opening_date="2024-01-01")
    a = create_account(data, session)
    with pytest.raises(ValueError, match="not editable"):
        update_field(a.id, "code", "NEW-CODE", session)  # type: ignore[arg-type]


@pytest.mark.unit
def test_update_field_missing_account_raises(session: Session) -> None:
    with pytest.raises(ValueError, match="not found"):
        update_field(9999, "name", "X", session)
