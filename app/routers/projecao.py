from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.db import get_session
from app.services import projection as proj_svc
from app.templates_env import templates

router = APIRouter(prefix="/projecao")


@router.get("", response_class=HTMLResponse)
def show_projecao(
    request: Request,
    months: int = 24,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    projections = proj_svc.project(session, months=months)
    chart_points = proj_svc.to_chart_points(projections)
    return templates.TemplateResponse(
        request,
        "pages/projecao.html",
        {
            "projections": projections,
            "chart_points": chart_points,
            "months": months,
        },
    )
