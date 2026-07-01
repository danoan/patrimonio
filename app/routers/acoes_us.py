from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select

from app.db import get_session
from app.i18n import DEFAULT_LOCALE, translate
from app.models.tables import Instrument, UsdEvent
from app.money import fmt_usd
from app.schemas.forms import UsdEventCreate
from app.services import usd
from app.templates_env import templates

router = APIRouter(prefix="/acoes-us")

_FIELD_KINDS: dict[str, str] = {
    "date": "date",
    "kind": "select",
    "gross_usd_cents": "money",
    "net_usd_cents": "money",
    "fx_eur_per_usd": "text",
}


def _event_display(event: UsdEvent, field: str, locale: str) -> str:
    if field == "date":
        return event.date
    if field == "kind":
        return translate(locale, f"usd_kind.{event.kind}")
    if field == "gross_usd_cents":
        return fmt_usd(event.gross_usd_cents)
    if field == "net_usd_cents":
        return fmt_usd(event.net_usd_cents)
    return str(event.fx_eur_per_usd)


def _event_edit_value(event: UsdEvent, field: str, override: str | None = None) -> str:
    if override is not None:
        return override
    if field == "gross_usd_cents":
        return f"{event.gross_usd_cents / 100:.2f}".replace(".", ",")
    if field == "net_usd_cents":
        return f"{event.net_usd_cents / 100:.2f}".replace(".", ",")
    if field == "kind":
        return event.kind
    if field == "fx_eur_per_usd":
        return str(event.fx_eur_per_usd)
    return event.date


def _event_field_options(field: str, locale: str) -> list[tuple[str, str]]:
    if field == "kind":
        return [
            ("vesting", translate(locale, "usd_kind.vesting")),
            ("sale", translate(locale, "usd_kind.sale")),
        ]
    return []


@router.get("", response_class=HTMLResponse)
def list_acoes_us(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    events = usd.list_events(session)
    totals = usd.usd_totals(session)
    instruments = session.exec(select(Instrument).where(Instrument.currency == "USD")).all()
    return templates.TemplateResponse(
        request,
        "pages/acoes_us.html",
        {"events": events, "totals": totals, "instruments": instruments},
    )


@router.post("/events", response_class=HTMLResponse)
def record_event(
    request: Request,
    date: Annotated[str, Form()],
    kind: Annotated[str, Form()],
    gross_str: Annotated[str, Form()],
    net_str: Annotated[str, Form()],
    fx_str: Annotated[str, Form()],
    instrument_id: Annotated[str | None, Form()] = None,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    gross_cents = int(float(gross_str.replace(",", ".")) * 100)
    net_cents = int(float(net_str.replace(",", ".")) * 100)
    fx = float(fx_str.replace(",", "."))
    data = UsdEventCreate(
        instrument_id=int(instrument_id) if instrument_id else None,
        date=date,
        kind=kind,
        gross_usd_cents=gross_cents,
        net_usd_cents=net_cents,
        fx_eur_per_usd=fx,
    )
    usd.record_event(data, session)
    events = usd.list_events(session)
    totals = usd.usd_totals(session)
    return templates.TemplateResponse(
        request,
        "partials/_usd_section.html",
        {"events": events, "totals": totals},
    )


@router.get("/events/{event_id}/field/{field}/edit", response_class=HTMLResponse)
def edit_event_field(
    event_id: int,
    field: str,
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    event = session.get(UsdEvent, event_id)
    if event is None or field not in _FIELD_KINDS:
        return HTMLResponse("Not found", status_code=404)

    locale = request.cookies.get("locale", DEFAULT_LOCALE)
    context = {
        "kind": _FIELD_KINDS[field],
        "value": _event_edit_value(event, field),
        "options": _event_field_options(field, locale),
        "patch_url": f"/acoes-us/events/{event_id}/field/{field}",
        "target": "#usd-section",
        "original": _event_display(event, field, locale),
        "error": None,
    }
    return templates.TemplateResponse(request, "partials/_editable_input.html", context)


@router.patch("/events/{event_id}/field/{field}", response_class=HTMLResponse)
def patch_event_field(
    event_id: int,
    field: str,
    request: Request,
    value: Annotated[str, Form()] = "",
    session: Session = Depends(get_session),
) -> HTMLResponse:
    locale = request.cookies.get("locale", DEFAULT_LOCALE)
    try:
        usd.update_field(event_id, field, value, session)
    except ValueError:
        event = session.get(UsdEvent, event_id)
        context = {
            "kind": _FIELD_KINDS.get(field, "text"),
            "value": _event_edit_value(event, field, override=value) if event else value,
            "options": _event_field_options(field, locale),
            "patch_url": f"/acoes-us/events/{event_id}/field/{field}",
            "target": "#usd-section",
            "original": _event_display(event, field, locale) if event else "",
            "error": translate(locale, "common.invalid_value"),
        }
        response = templates.TemplateResponse(request, "partials/_editable_input.html", context)
        response.headers["HX-Retarget"] = "closest td"
        response.headers["HX-Reswap"] = "innerHTML"
        return response

    events = usd.list_events(session)
    totals = usd.usd_totals(session)
    return templates.TemplateResponse(
        request,
        "partials/_usd_section.html",
        {"events": events, "totals": totals},
    )
