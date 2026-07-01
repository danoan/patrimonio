from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select

from app.db import get_session
from app.i18n import DEFAULT_LOCALE, translate
from app.models.tables import Instrument
from app.money import fmt_eur
from app.schemas.forms import TradeCreate
from app.services import stocks
from app.templates_env import templates

router = APIRouter(prefix="/acoes")


@router.get("", response_class=HTMLResponse)
def list_acoes(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    pos = stocks.positions(session)
    instruments = session.exec(select(Instrument).where(Instrument.currency == "EUR")).all()
    return templates.TemplateResponse(
        request,
        "pages/acoes.html",
        {"positions": pos, "instruments": instruments},
    )


@router.post("/trades", response_class=HTMLResponse)
def record_trade(
    request: Request,
    instrument_id: Annotated[int, Form()],
    kind: Annotated[str, Form()],
    date: Annotated[str, Form()],
    qty: Annotated[int, Form()],
    price_str: Annotated[str, Form()],
    order_cost_str: Annotated[str, Form()] = "0",
    session: Session = Depends(get_session),
) -> HTMLResponse:
    price_cents = int(float(price_str.replace(",", ".")) * 100)
    order_cost_cents = int(float(order_cost_str.replace(",", ".")) * 100)
    data = TradeCreate(
        instrument_id=instrument_id,
        kind=kind,
        date=date,
        qty=qty,
        price_cents=price_cents,
        order_cost_cents=order_cost_cents,
    )
    stocks.record_trade(data, session)
    pos = stocks.positions(session)
    return templates.TemplateResponse(
        request,
        "partials/_positions.html",
        {"positions": pos},
    )


@router.get("/instruments/{instrument_id}/price/edit", response_class=HTMLResponse)
def edit_instrument_price(
    instrument_id: int,
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    inst = session.get(Instrument, instrument_id)
    if inst is None:
        return HTMLResponse("Not found", status_code=404)

    price_cents = stocks.current_price(instrument_id, session)
    options: list[tuple[str, str]] = []
    context = {
        "kind": "money",
        "value": f"{price_cents / 100:.2f}".replace(".", ","),
        "options": options,
        "patch_url": f"/acoes/instruments/{instrument_id}/price",
        "target": "#positions",
        "original": fmt_eur(price_cents),
        "error": None,
    }
    return templates.TemplateResponse(request, "partials/_editable_input.html", context)


@router.patch("/instruments/{instrument_id}/price", response_class=HTMLResponse)
def patch_instrument_price(
    instrument_id: int,
    request: Request,
    value: Annotated[str, Form()] = "",
    session: Session = Depends(get_session),
) -> HTMLResponse:
    locale = request.cookies.get("locale", DEFAULT_LOCALE)
    try:
        price_cents = int(float(value.replace(",", ".")) * 100)
        stocks.update_price(instrument_id, price_cents, session)
    except ValueError:
        current_cents = stocks.current_price(instrument_id, session)
        options: list[tuple[str, str]] = []
        context = {
            "kind": "money",
            "value": value,
            "options": options,
            "patch_url": f"/acoes/instruments/{instrument_id}/price",
            "target": "#positions",
            "original": fmt_eur(current_cents),
            "error": translate(locale, "common.invalid_value"),
        }
        response = templates.TemplateResponse(request, "partials/_editable_input.html", context)
        response.headers["HX-Retarget"] = "closest td"
        response.headers["HX-Reswap"] = "innerHTML"
        return response

    pos = stocks.positions(session)
    return templates.TemplateResponse(request, "partials/_positions.html", {"positions": pos})


@router.get("/{ticker}", response_class=HTMLResponse)
def acoes_detail(
    ticker: str,
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    inst = stocks.get_instrument_by_ticker(ticker, session)
    if inst is None:
        return HTMLResponse("Instrumento não encontrado", status_code=404)
    position = stocks.position_for_instrument(inst.id, session)  # type: ignore[arg-type]
    trades = stocks.list_trades(inst.id, session)  # type: ignore[arg-type]
    return templates.TemplateResponse(
        request,
        "pages/acoes_detail.html",
        {"instrument": inst, "position": position, "trades": trades},
    )


@router.delete("/{ticker}/trades/{trade_id}", response_class=HTMLResponse)
def delete_trade_route(
    ticker: str,
    trade_id: int,
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    inst = stocks.get_instrument_by_ticker(ticker, session)
    if inst is None:
        return HTMLResponse("Not found", status_code=404)
    stocks.delete_trade(trade_id, session)
    position = stocks.position_for_instrument(inst.id, session)  # type: ignore[arg-type]
    trades = stocks.list_trades(inst.id, session)  # type: ignore[arg-type]
    return templates.TemplateResponse(
        request,
        "partials/_instrument_detail.html",
        {"instrument": inst, "position": position, "trades": trades},
    )
