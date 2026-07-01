from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.db import get_session
from app.i18n import DEFAULT_LOCALE, translate
from app.models.tables import Txn
from app.money import fmt_eur
from app.schemas.forms import TxnCreate
from app.services import accounts, balances, ledger
from app.templates_env import templates

router = APIRouter(prefix="/movimentos")

_FIELD_KINDS: dict[str, str] = {
    "date": "date",
    "category": "text",
    "comment": "text",
    "tags": "text",
    "amount_cents": "money",
}
_NO_OPTIONS: list[tuple[str, str]] = []


def _txn_display(txn: Txn, field: str) -> str:
    if field == "amount_cents":
        return fmt_eur(txn.amount_cents)
    if field == "category":
        return txn.category or "—"
    if field == "comment":
        return txn.comment or "—"
    if field == "tags":
        return txn.tags or "—"
    return txn.date


def _txn_edit_value(txn: Txn, field: str, override: str | None = None) -> str:
    if override is not None:
        return override
    if field == "amount_cents":
        return f"{txn.amount_cents / 100:.2f}".replace(".", ",")
    if field == "category":
        return txn.category or ""
    if field == "comment":
        return txn.comment or ""
    if field == "tags":
        return txn.tags or ""
    return txn.date


def _txn_field_qs(
    view: str,
    page: int,
    date_from: str | None,
    date_to: str | None,
    account_id: int | None,
) -> str:
    params = [f"view={view}"]
    if view == "statement":
        if account_id is not None:
            params.append(f"account_id={account_id}")
    else:
        params.append(f"page={page}")
        if date_from:
            params.append(f"date_from={date_from}")
        if date_to:
            params.append(f"date_to={date_to}")
    return "?" + "&".join(params)


def _pair_label(txn: Txn) -> str:
    return f"{txn.date} — {txn.comment or txn.category or '—'} — {fmt_eur(txn.amount_cents)}"


def _account_names(session: Session) -> dict[int | None, str]:
    return {a.id: a.name for a in accounts.list_accounts(session, active_only=False)}


def _render_txn_view(
    request: Request,
    session: Session,
    view: str,
    page: int,
    date_from: str | None,
    date_to: str | None,
    account_id: int | None,
) -> HTMLResponse:
    if view == "statement":
        if account_id is None:
            return HTMLResponse("account_id required", status_code=400)
        statement = ledger.account_statement(account_id, session)
        current_balance = balances.balance(account_id, session)
        return templates.TemplateResponse(
            request,
            "partials/_account_statement.html",
            {
                "account_id": account_id,
                "statement": statement,
                "current_balance": current_balance,
                "oob_balance": True,
                "note_counts": ledger.note_counts_for_txns([r.txn for r in statement], session),
            },
        )

    txn_page = ledger.list_txns(session, date_from=date_from, date_to=date_to, page=page)
    pending_txns = ledger.list_pending_txns(session)
    return templates.TemplateResponse(
        request,
        "partials/_ledger.html",
        {
            "txn_page": txn_page,
            "pending_txns": pending_txns,
            "date_from": date_from,
            "date_to": date_to,
            "account_names": _account_names(session),
            "note_counts": ledger.note_counts_for_txns(txn_page.txns + pending_txns, session),
        },
    )


@router.get("", response_class=HTMLResponse)
def list_movimentos(
    request: Request,
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    txn_page = ledger.list_txns(session, date_from=date_from, date_to=date_to, page=page)
    pending_txns = ledger.list_pending_txns(session)
    context = {
        "txn_page": txn_page,
        "pending_txns": pending_txns,
        "date_from": date_from,
        "date_to": date_to,
        "account_names": _account_names(session),
        "note_counts": ledger.note_counts_for_txns(txn_page.txns + pending_txns, session),
    }

    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(request, "partials/_ledger.html", context)

    account_list = accounts.list_accounts(session)
    return templates.TemplateResponse(
        request,
        "pages/movimentos.html",
        {**context, "account_list": account_list},
    )


@router.delete("/{txn_id}", response_class=HTMLResponse)
def delete_movimento(
    txn_id: int,
    request: Request,
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    ledger.delete_txn(txn_id, session)
    txn_page = ledger.list_txns(session, date_from=date_from, date_to=date_to, page=page)
    pending_txns = ledger.list_pending_txns(session)
    return templates.TemplateResponse(
        request,
        "partials/_ledger.html",
        {
            "txn_page": txn_page,
            "pending_txns": pending_txns,
            "date_from": date_from,
            "date_to": date_to,
            "account_names": _account_names(session),
            "note_counts": ledger.note_counts_for_txns(txn_page.txns + pending_txns, session),
        },
    )


@router.post("", response_class=HTMLResponse)
def post_movimento(
    request: Request,
    date: Annotated[str, Form()],
    amount_str: Annotated[str, Form()],
    from_account: Annotated[str | None, Form()] = None,
    to_account: Annotated[str | None, Form()] = None,
    category: Annotated[str | None, Form()] = None,
    comment: Annotated[str | None, Form()] = None,
    tags: Annotated[str | None, Form()] = None,
    needs_resolution: Annotated[bool, Form()] = False,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    # Convert amount from decimal string to cents
    amount_cents = int(float(amount_str.replace(",", ".")) * 100)

    data = TxnCreate(
        date=date,
        from_account=int(from_account) if from_account else None,
        to_account=int(to_account) if to_account else None,
        amount_cents=amount_cents,
        category=category or None,
        comment=comment or None,
        tags=tags or None,
        needs_resolution=needs_resolution,
    )
    ledger.create_txn(data, session)

    txn_page = ledger.list_txns(session, page=1)
    pending_txns = ledger.list_pending_txns(session)
    return templates.TemplateResponse(
        request,
        "partials/_ledger.html",
        {
            "txn_page": txn_page,
            "pending_txns": pending_txns,
            "date_from": None,
            "date_to": None,
            "account_names": _account_names(session),
            "note_counts": ledger.note_counts_for_txns(txn_page.txns + pending_txns, session),
        },
    )


@router.get("/{txn_id}/field/{field}/edit", response_class=HTMLResponse)
def edit_txn_field(
    txn_id: int,
    field: str,
    request: Request,
    view: Annotated[str, Query()] = "ledger",
    page: Annotated[int, Query(ge=1)] = 1,
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
    account_id: Annotated[int | None, Query()] = None,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    txn = session.get(Txn, txn_id)
    if txn is None or field not in _FIELD_KINDS:
        return HTMLResponse("Not found", status_code=404)

    qs = _txn_field_qs(view, page, date_from, date_to, account_id)
    context = {
        "kind": _FIELD_KINDS[field],
        "value": _txn_edit_value(txn, field),
        "options": _NO_OPTIONS,
        "patch_url": f"/movimentos/{txn_id}/field/{field}{qs}",
        "target": "#ledger" if view == "ledger" else "#account-statement",
        "original": _txn_display(txn, field),
        "error": None,
    }
    return templates.TemplateResponse(request, "partials/_editable_input.html", context)


@router.patch("/{txn_id}/field/{field}", response_class=HTMLResponse)
def patch_txn_field(
    txn_id: int,
    field: str,
    request: Request,
    value: Annotated[str, Form()] = "",
    view: Annotated[str, Query()] = "ledger",
    page: Annotated[int, Query(ge=1)] = 1,
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
    account_id: Annotated[int | None, Query()] = None,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    try:
        ledger.update_txn_field(txn_id, field, value, session)
    except ValueError:
        txn = session.get(Txn, txn_id)
        qs = _txn_field_qs(view, page, date_from, date_to, account_id)
        locale = request.cookies.get("locale", DEFAULT_LOCALE)
        context = {
            "kind": _FIELD_KINDS.get(field, "text"),
            "value": _txn_edit_value(txn, field, override=value) if txn else value,
            "options": _NO_OPTIONS,
            "patch_url": f"/movimentos/{txn_id}/field/{field}{qs}",
            "target": "#ledger" if view == "ledger" else "#account-statement",
            "original": _txn_display(txn, field) if txn else "",
            "error": translate(locale, "common.invalid_value"),
        }
        response = templates.TemplateResponse(request, "partials/_editable_input.html", context)
        response.headers["HX-Retarget"] = "closest td"
        response.headers["HX-Reswap"] = "innerHTML"
        return response

    return _render_txn_view(request, session, view, page, date_from, date_to, account_id)


@router.patch("/{txn_id}/needs-resolution", response_class=HTMLResponse)
def patch_needs_resolution(
    txn_id: int,
    request: Request,
    needs_resolution: Annotated[bool, Query()] = False,
    view: Annotated[str, Query()] = "ledger",
    page: Annotated[int, Query(ge=1)] = 1,
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
    account_id: Annotated[int | None, Query()] = None,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    ledger.set_needs_resolution(txn_id, needs_resolution, session)
    return _render_txn_view(request, session, view, page, date_from, date_to, account_id)


@router.get("/{txn_id}/resolve/edit", response_class=HTMLResponse)
def edit_resolve_txn(
    txn_id: int,
    request: Request,
    view: Annotated[str, Query()] = "ledger",
    page: Annotated[int, Query(ge=1)] = 1,
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
    account_id: Annotated[int | None, Query()] = None,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    txn = session.get(Txn, txn_id)
    if txn is None:
        return HTMLResponse("Not found", status_code=404)

    qs = _txn_field_qs(view, page, date_from, date_to, account_id)
    current_pair = session.get(Txn, txn.resolved_txn_id) if txn.resolved_txn_id else None
    context = {
        "txn": txn,
        "current_pair_label": _pair_label(current_pair) if current_pair else None,
        "resolve_url": f"/movimentos/{txn_id}/resolve{qs}",
        "target": "#ledger" if view == "ledger" else "#account-statement",
        "error": None,
    }
    return templates.TemplateResponse(request, "partials/_resolve_modal.html", context)


@router.get("/{txn_id}/resolve/candidates", response_class=HTMLResponse)
def resolve_candidates(
    txn_id: int,
    request: Request,
    q: Annotated[str, Query()] = "",
    session: Session = Depends(get_session),
) -> HTMLResponse:
    candidates = ledger.search_txns(q, txn_id, session)
    return templates.TemplateResponse(
        request,
        "partials/_pair_candidates.html",
        {"candidates": candidates},
    )


@router.post("/{txn_id}/resolve", response_class=HTMLResponse)
def post_resolve_txn(
    txn_id: int,
    request: Request,
    resolved_txn_id: Annotated[str | None, Form()] = None,
    resolution_note: Annotated[str | None, Form()] = None,
    view: Annotated[str, Query()] = "ledger",
    page: Annotated[int, Query(ge=1)] = 1,
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
    account_id: Annotated[int | None, Query()] = None,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    try:
        ledger.resolve_txn(
            txn_id,
            session,
            resolved_txn_id=int(resolved_txn_id) if resolved_txn_id else None,
            resolution_note=resolution_note or None,
        )
    except ValueError:
        txn = session.get(Txn, txn_id)
        locale = request.cookies.get("locale", DEFAULT_LOCALE)
        qs = _txn_field_qs(view, page, date_from, date_to, account_id)
        current_pair = session.get(Txn, int(resolved_txn_id)) if resolved_txn_id else None
        context = {
            "txn": txn,
            "current_pair_label": _pair_label(current_pair) if current_pair else None,
            "resolve_url": f"/movimentos/{txn_id}/resolve{qs}",
            "target": "#ledger" if view == "ledger" else "#account-statement",
            "error": translate(locale, "resolution.error_required"),
        }
        response = templates.TemplateResponse(request, "partials/_resolve_modal.html", context)
        response.headers["HX-Retarget"] = "#resolve-modal-container"
        response.headers["HX-Reswap"] = "innerHTML"
        return response

    return _render_txn_view(request, session, view, page, date_from, date_to, account_id)


@router.delete("/{txn_id}/resolve", response_class=HTMLResponse)
def delete_resolve_txn(
    txn_id: int,
    request: Request,
    view: Annotated[str, Query()] = "ledger",
    page: Annotated[int, Query(ge=1)] = 1,
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
    account_id: Annotated[int | None, Query()] = None,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    ledger.unresolve_txn(txn_id, session)
    return _render_txn_view(request, session, view, page, date_from, date_to, account_id)


def _notes_modal_response(
    request: Request,
    txn_id: int,
    qs: str,
    session: Session,
    error: str | None = None,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "partials/_notes_modal.html",
        {
            "txn_id": txn_id,
            "notes": ledger.list_txn_notes(txn_id, session),
            "qs": qs,
            "error": error,
        },
    )


@router.get("/{txn_id}/notes", response_class=HTMLResponse)
def edit_txn_notes(
    txn_id: int,
    request: Request,
    view: Annotated[str, Query()] = "ledger",
    page: Annotated[int, Query(ge=1)] = 1,
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
    account_id: Annotated[int | None, Query()] = None,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    txn = session.get(Txn, txn_id)
    if txn is None:
        return HTMLResponse("Not found", status_code=404)

    qs = _txn_field_qs(view, page, date_from, date_to, account_id)
    return _notes_modal_response(request, txn_id, qs, session)


@router.post("/{txn_id}/notes", response_class=HTMLResponse)
def post_txn_note(
    txn_id: int,
    request: Request,
    text: Annotated[str, Form()] = "",
    view: Annotated[str, Query()] = "ledger",
    page: Annotated[int, Query(ge=1)] = 1,
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
    account_id: Annotated[int | None, Query()] = None,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    qs = _txn_field_qs(view, page, date_from, date_to, account_id)
    locale = request.cookies.get("locale", DEFAULT_LOCALE)
    try:
        ledger.add_txn_note(txn_id, text, session)
    except ValueError:
        return _notes_modal_response(
            request, txn_id, qs, session, error=translate(locale, "common.invalid_value")
        )

    return _notes_modal_response(request, txn_id, qs, session)


@router.delete("/{txn_id}/notes/{note_id}", response_class=HTMLResponse)
def delete_txn_note(
    txn_id: int,
    note_id: int,
    request: Request,
    view: Annotated[str, Query()] = "ledger",
    page: Annotated[int, Query(ge=1)] = 1,
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
    account_id: Annotated[int | None, Query()] = None,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    ledger.delete_txn_note(note_id, session)
    qs = _txn_field_qs(view, page, date_from, date_to, account_id)
    return _notes_modal_response(request, txn_id, qs, session)
