from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.db import get_session
from app.services import ir as ir_svc
from app.templates_env import templates

router = APIRouter(prefix="/ir")


@router.get("", response_class=HTMLResponse)
def show_ir(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    ir_svc.seed_default_brackets(session)
    results = ir_svc.compute_ir(session)
    brackets = ir_svc.list_brackets(session)
    return templates.TemplateResponse(
        request,
        "pages/ir.html",
        {"results": results, "brackets": brackets},
    )


@router.post("/brackets/reset", response_class=HTMLResponse)
def reset_brackets(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    """Reload the default French 2024 brackets."""
    ir_svc.replace_brackets(ir_svc.DEFAULT_BRACKETS, session)
    brackets = ir_svc.list_brackets(session)
    results = ir_svc.compute_ir(session)
    return templates.TemplateResponse(
        request,
        "partials/_ir_results.html",
        {"results": results, "brackets": brackets},
    )


@router.post("/brackets", response_class=HTMLResponse)
def update_brackets(
    request: Request,
    brackets_json: Annotated[str, Form()],
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """
    Accept a JSON array of [lower_eur, upper_eur, rate] tuples from a form field.
    Converts EUR amounts to cents internally.
    """
    import json

    raw: list[list[float]] = json.loads(brackets_json)
    parsed = [(int(r[0] * 100), int(r[1] * 100), float(r[2])) for r in raw]
    ir_svc.replace_brackets(parsed, session)
    brackets = ir_svc.list_brackets(session)
    results = ir_svc.compute_ir(session)
    return templates.TemplateResponse(
        request,
        "partials/_ir_results.html",
        {"results": results, "brackets": brackets},
    )
