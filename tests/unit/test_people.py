import pytest
from app.models.tables import Person
from app.services.people import update_field
from sqlmodel import Session


def _add_person(
    session: Session,
    name: str = "Daniel",
    gross: int = 400000,
    ir_rate: float = 0.2,
    net_before_taxes: int = 320000,
) -> Person:
    p = Person(
        name=name,
        gross_cents=gross,
        net_before_taxes_cents=net_before_taxes,
        net_before_taxes_avg_cents=net_before_taxes,
        ir_rate=ir_rate,
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


@pytest.mark.unit
def test_update_field_name(session: Session) -> None:
    p = _add_person(session)
    updated = update_field(p.id, "name", "Sofia", session)  # type: ignore[arg-type]
    assert updated.name == "Sofia"


@pytest.mark.unit
def test_update_field_gross_cents(session: Session) -> None:
    p = _add_person(session)
    updated = update_field(p.id, "gross_cents", "3500,00", session)  # type: ignore[arg-type]
    assert updated.gross_cents == 350000


@pytest.mark.unit
def test_update_field_net_before_taxes_cents(session: Session) -> None:
    p = _add_person(session)
    updated = update_field(p.id, "net_before_taxes_cents", "3200,00", session)  # type: ignore[arg-type]
    assert updated.net_before_taxes_cents == 320000


@pytest.mark.unit
def test_update_field_net_before_taxes_avg_cents(session: Session) -> None:
    p = _add_person(session)
    updated = update_field(p.id, "net_before_taxes_avg_cents", "3100,00", session)  # type: ignore[arg-type]
    assert updated.net_before_taxes_avg_cents == 310000


@pytest.mark.unit
def test_update_field_ir_rate(session: Session) -> None:
    p = _add_person(session)
    updated = update_field(p.id, "ir_rate", "22,4", session)  # type: ignore[arg-type]
    assert updated.ir_rate == pytest.approx(0.224)


@pytest.mark.unit
def test_update_field_empty_name_raises(session: Session) -> None:
    p = _add_person(session)
    with pytest.raises(ValueError, match="required"):
        update_field(p.id, "name", "", session)  # type: ignore[arg-type]


@pytest.mark.unit
def test_update_field_invalid_gross_raises(session: Session) -> None:
    p = _add_person(session)
    with pytest.raises(ValueError, match="invalid amount"):
        update_field(p.id, "gross_cents", "abc", session)  # type: ignore[arg-type]


@pytest.mark.unit
def test_update_field_invalid_rate_raises(session: Session) -> None:
    p = _add_person(session)
    with pytest.raises(ValueError, match="invalid rate"):
        update_field(p.id, "ir_rate", "abc", session)  # type: ignore[arg-type]


@pytest.mark.unit
def test_update_field_unknown_field_raises(session: Session) -> None:
    p = _add_person(session)
    with pytest.raises(ValueError, match="not editable"):
        update_field(p.id, "id", "1", session)  # type: ignore[arg-type]


@pytest.mark.unit
def test_update_field_missing_person_raises(session: Session) -> None:
    with pytest.raises(ValueError, match="not found"):
        update_field(9999, "name", "X", session)
