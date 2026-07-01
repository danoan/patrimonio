from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.db import get_session
from app.services import division
from app.templates_env import templates

router = APIRouter(prefix="/divisao")


@router.get("", response_class=HTMLResponse)
def show_divisao(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    split = division.compute_split(session)
    return templates.TemplateResponse(
        request,
        "pages/divisao.html",
        {"split": split},
    )
