from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.db import get_session
from app.i18n import DEFAULT_LOCALE, translate
from app.models.tables import Person, Setting
from app.money import fmt_eur, fmt_pct
from app.services import division, people
from app.templates_env import templates

router = APIRouter(prefix="/config")

_FIELD_KINDS: dict[str, str] = {
    "name": "text",
    "gross_cents": "money",
    "net_before_taxes_cents": "money",
    "net_before_taxes_avg_cents": "money",
    "ir_rate": "percent",
}
_NO_OPTIONS: list[tuple[str, str]] = []


def _person_ir_cents(person: Person) -> int:
    return int(Decimal(person.net_before_taxes_cents) * Decimal(str(person.ir_rate)))


def _person_display(person: Person, field: str) -> str:
    if field == "name":
        return person.name
    if field == "gross_cents":
        return fmt_eur(person.gross_cents)
    if field == "net_before_taxes_cents":
        return fmt_eur(person.net_before_taxes_cents)
    if field == "net_before_taxes_avg_cents":
        return fmt_eur(person.net_before_taxes_avg_cents)
    return f"{fmt_pct(person.ir_rate)} ({fmt_eur(_person_ir_cents(person))})"


def _person_edit_value(person: Person, field: str, override: str | None = None) -> str:
    if override is not None:
        return override
    if field == "gross_cents":
        return f"{person.gross_cents / 100:.2f}".replace(".", ",")
    if field == "net_before_taxes_cents":
        return f"{person.net_before_taxes_cents / 100:.2f}".replace(".", ",")
    if field == "net_before_taxes_avg_cents":
        return f"{person.net_before_taxes_avg_cents / 100:.2f}".replace(".", ",")
    if field == "ir_rate":
        return f"{person.ir_rate * 100:.2f}".replace(".", ",")
    return person.name


@router.get("", response_class=HTMLResponse)
def show_config(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    people = division.person_net_incomes(session)
    pfu_setting = session.get(Setting, "pfu")
    pfu = pfu_setting.value if pfu_setting else "0.30"
    return templates.TemplateResponse(
        request,
        "pages/configuracoes.html",
        {
            "people": people,
            "pfu": pfu,
            "fixed_expense_tag": division.fixed_expense_tag(session) or "",
            "available_tags": division.list_rule_tags(session),
        },
    )


@router.post("/pfu", response_class=HTMLResponse)
def update_pfu(
    request: Request,
    pfu: Annotated[str, Form()],
    session: Session = Depends(get_session),
) -> HTMLResponse:
    setting = session.get(Setting, "pfu")
    if setting is None:
        setting = Setting(key="pfu", value=pfu)
    else:
        setting.value = pfu
    session.add(setting)
    session.commit()
    return HTMLResponse(f'<span id="pfu-val">{pfu}</span>')


@router.post("/fixed-expense-tag", response_class=HTMLResponse)
def update_fixed_expense_tag(
    request: Request,
    tag: Annotated[str, Form()] = "",
    session: Session = Depends(get_session),
) -> HTMLResponse:
    setting = session.get(Setting, "fixed_expense_tag")
    if setting is None:
        setting = Setting(key="fixed_expense_tag", value=tag)
    else:
        setting.value = tag
    session.add(setting)
    session.commit()
    locale = request.cookies.get("locale", DEFAULT_LOCALE)
    label = tag or translate(locale, "configuracoes.no_tag_selected")
    return HTMLResponse(f'<span id="fixed-expense-tag-val">{label}</span>')


@router.post("/pessoas/{person_id}", response_class=HTMLResponse)
def update_person(
    person_id: int,
    request: Request,
    gross_str: Annotated[str, Form()],
    net_before_taxes_str: Annotated[str, Form()],
    net_before_taxes_avg_str: Annotated[str, Form()],
    ir_str: Annotated[str, Form()],
    session: Session = Depends(get_session),
) -> HTMLResponse:
    person = session.get(Person, person_id)
    if person is None:
        return HTMLResponse("Pessoa não encontrada", status_code=404)
    person.gross_cents = int(float(gross_str.replace(",", ".")) * 100)
    person.net_before_taxes_cents = int(float(net_before_taxes_str.replace(",", ".")) * 100)
    person.net_before_taxes_avg_cents = int(float(net_before_taxes_avg_str.replace(",", ".")) * 100)
    person.ir_rate = float(ir_str.replace(",", ".")) / 100
    session.add(person)
    session.commit()
    people = division.person_net_incomes(session)
    return templates.TemplateResponse(
        request,
        "partials/_cfg_salaries.html",
        {"people": people},
    )


@router.post("/pessoas", response_class=HTMLResponse)
def create_person(
    request: Request,
    name: Annotated[str, Form()],
    gross_str: Annotated[str, Form()],
    net_before_taxes_str: Annotated[str, Form()],
    net_before_taxes_avg_str: Annotated[str, Form()],
    ir_str: Annotated[str, Form()],
    session: Session = Depends(get_session),
) -> HTMLResponse:
    person = Person(
        name=name,
        gross_cents=int(float(gross_str.replace(",", ".")) * 100),
        net_before_taxes_cents=int(float(net_before_taxes_str.replace(",", ".")) * 100),
        net_before_taxes_avg_cents=int(float(net_before_taxes_avg_str.replace(",", ".")) * 100),
        ir_rate=float(ir_str.replace(",", ".")) / 100,
    )
    session.add(person)
    session.commit()
    people = division.person_net_incomes(session)
    return templates.TemplateResponse(
        request,
        "partials/_cfg_salaries.html",
        {"people": people},
    )


@router.get("/pessoas/{person_id}/field/{field}/edit", response_class=HTMLResponse)
def edit_person_field(
    person_id: int,
    field: str,
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    person = session.get(Person, person_id)
    if person is None or field not in _FIELD_KINDS:
        return HTMLResponse("Not found", status_code=404)

    context = {
        "kind": _FIELD_KINDS[field],
        "value": _person_edit_value(person, field),
        "options": _NO_OPTIONS,
        "patch_url": f"/config/pessoas/{person_id}/field/{field}",
        "target": "#salaries",
        "original": _person_display(person, field),
        "error": None,
    }
    return templates.TemplateResponse(request, "partials/_editable_input.html", context)


@router.patch("/pessoas/{person_id}/field/{field}", response_class=HTMLResponse)
def patch_person_field(
    person_id: int,
    field: str,
    request: Request,
    value: Annotated[str, Form()] = "",
    session: Session = Depends(get_session),
) -> HTMLResponse:
    try:
        people.update_field(person_id, field, value, session)
    except ValueError:
        person = session.get(Person, person_id)
        locale = request.cookies.get("locale", DEFAULT_LOCALE)
        context = {
            "kind": _FIELD_KINDS.get(field, "text"),
            "value": _person_edit_value(person, field, override=value) if person else value,
            "options": _NO_OPTIONS,
            "patch_url": f"/config/pessoas/{person_id}/field/{field}",
            "target": "#salaries",
            "original": _person_display(person, field) if person else "",
            "error": translate(locale, "common.invalid_value"),
        }
        response = templates.TemplateResponse(request, "partials/_editable_input.html", context)
        response.headers["HX-Retarget"] = "closest td"
        response.headers["HX-Reswap"] = "innerHTML"
        return response

    people_list = division.person_net_incomes(session)
    return templates.TemplateResponse(
        request,
        "partials/_cfg_salaries.html",
        {"people": people_list},
    )
