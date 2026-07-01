from sqlmodel import Session

from app.models.tables import Person

_EDITABLE_FIELDS = {
    "name",
    "gross_cents",
    "net_before_taxes_cents",
    "net_before_taxes_avg_cents",
    "ir_rate",
}


def update_field(person_id: int, field: str, raw_value: str, session: Session) -> Person:
    if field not in _EDITABLE_FIELDS:
        raise ValueError(f"field '{field}' is not editable")
    person = session.get(Person, person_id)
    if person is None:
        raise ValueError(f"Person {person_id} not found")

    if field == "name":
        if not raw_value:
            raise ValueError("name is required")
        person.name = raw_value
    elif field == "gross_cents":
        try:
            person.gross_cents = int(float(raw_value.replace(",", ".")) * 100)
        except ValueError as exc:
            raise ValueError("invalid amount") from exc
    elif field == "net_before_taxes_cents":
        try:
            person.net_before_taxes_cents = int(float(raw_value.replace(",", ".")) * 100)
        except ValueError as exc:
            raise ValueError("invalid amount") from exc
    elif field == "net_before_taxes_avg_cents":
        try:
            person.net_before_taxes_avg_cents = int(float(raw_value.replace(",", ".")) * 100)
        except ValueError as exc:
            raise ValueError("invalid amount") from exc
    elif field == "ir_rate":
        try:
            person.ir_rate = float(raw_value.replace(",", ".")) / 100
        except ValueError as exc:
            raise ValueError("invalid rate") from exc

    session.add(person)
    session.commit()
    session.refresh(person)
    return person
