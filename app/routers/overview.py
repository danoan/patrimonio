from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.db import get_session
from app.services import balances, ledger, networth
from app.templates_env import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def overview(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    tier_totals = balances.tier_totals(session)
    total = balances.grand_total(session)
    recent = ledger.recent_txns(session, limit=10)
    chart_points = networth.to_chart_points(networth.monthly_history(session))
    return templates.TemplateResponse(
        request,
        "pages/overview.html",
        {
            "tier_totals": tier_totals,
            "grand_total": total,
            "recent_txns": recent,
            "chart_points": chart_points,
        },
    )


@router.get("/partials/kpis", response_class=HTMLResponse)
def kpis_partial(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    tier_totals = balances.tier_totals(session)
    total = balances.grand_total(session)
    return templates.TemplateResponse(
        request,
        "partials/_kpis.html",
        {"tier_totals": tier_totals, "grand_total": total},
    )
