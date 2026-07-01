from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.db import get_session
from app.i18n import DEFAULT_LOCALE, translate
from app.models.tables import RecurringRule
from app.money import fmt_eur
from app.schemas.forms import RecurringRuleCreate
from app.services import accounts, balances, division, ledger, recurring
from app.templates_env import templates

router = APIRouter(prefix="/recorrentes")

_FIELD_KINDS: dict[str, str] = {
    "description": "text",
    "category": "text",
    "day_of_month": "text",
    "amount_cents": "money",
    "from_account": "select",
    "to_account": "select",
}
_NO_OPTIONS: list[tuple[str, str]] = []
_ACCOUNT_FIELDS = {"from_account", "to_account"}


def _rule_display(rule: RecurringRule, field: str, account_codes: dict[int | None, str]) -> str:
    if field == "description":
        return rule.description
    if field == "category":
        return rule.category or "—"
    if field == "day_of_month":
        return str(rule.day_of_month)
    if field == "from_account":
        return account_codes.get(rule.from_account, "—")
    if field == "to_account":
        return account_codes.get(rule.to_account, "—")
    return fmt_eur(rule.amount_cents)


def _rule_edit_value(rule: RecurringRule, field: str, override: str | None = None) -> str:
    if override is not None:
        return override
    if field == "amount_cents":
        return f"{rule.amount_cents / 100:.2f}".replace(".", ",")
    if field == "category":
        return rule.category or ""
    if field == "day_of_month":
        return str(rule.day_of_month)
    if field == "from_account":
        return str(rule.from_account) if rule.from_account is not None else ""
    if field == "to_account":
        return str(rule.to_account) if rule.to_account is not None else ""
    return rule.description


def _account_field_options(session: Session, locale: str) -> list[tuple[str, str]]:
    options = [("", translate(locale, "common.placeholder.external"))]
    options += [(str(a.id), a.code) for a in accounts.list_accounts(session, active_only=False)]
    return options


def _field_options(field: str, session: Session, locale: str) -> list[tuple[str, str]]:
    if field in _ACCOUNT_FIELDS:
        return _account_field_options(session, locale)
    return _NO_OPTIONS


def _recurring_list_context(session: Session, period: str) -> dict[str, object]:
    active_rules, finished_rules = recurring.rules_by_status(session)
    pending = recurring.pending_for_period(period, session)
    pending_ids = {r.id for r in pending}
    progress = {
        rule.id: recurring.installment_progress(rule.id, session)  # type: ignore[misc]
        for rule in active_rules + finished_rules
        if rule.id is not None
    }
    account_codes = {a.id: a.code for a in accounts.list_accounts(session, active_only=False)}
    account_groups = recurring.group_active_rules_by_account(session)
    return {
        "active_rules": active_rules,
        "finished_rules": finished_rules,
        "pending": pending,
        "pending_ids": pending_ids,
        "period": period,
        "progress": progress,
        "account_codes": account_codes,
        "account_groups": account_groups,
        "fixed_expense_tag": division.fixed_expense_tag(session),
    }


@router.get("", response_class=HTMLResponse)
def list_recorrentes(
    request: Request,
    to_account: Annotated[int | None, Query()] = None,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    period = recurring.current_period()
    context = _recurring_list_context(session, period)
    account_list = accounts.list_accounts(session)
    active_rules, finished_rules = recurring.rules_by_status(session)
    categories = sorted({r.category for r in active_rules + finished_rules if r.category})
    return templates.TemplateResponse(
        request,
        "pages/recorrentes.html",
        {
            **context,
            "account_list": account_list,
            "preselect_to_account": to_account,
            "categories": categories,
        },
    )


@router.post("", response_class=HTMLResponse)
def create_recorrente(
    request: Request,
    kind: Annotated[str, Form()],
    description: Annotated[str, Form()],
    amount_str: Annotated[str, Form()],
    day_of_month: Annotated[int, Form()] = 1,
    from_account: Annotated[str | None, Form()] = None,
    to_account: Annotated[str | None, Form()] = None,
    category: Annotated[str | None, Form()] = None,
    start_period: Annotated[str | None, Form()] = None,
    end_period: Annotated[str | None, Form()] = None,
    installments: Annotated[str | None, Form()] = None,
    notes: Annotated[str | None, Form()] = None,
    tags: Annotated[str | None, Form()] = None,
    view: Annotated[str, Query()] = "list",
    account_id: Annotated[int | None, Query()] = None,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    amount_cents = int(float(amount_str.replace(",", ".")) * 100)
    data = RecurringRuleCreate(
        kind=kind,
        description=description,
        from_account=int(from_account) if from_account else None,
        to_account=int(to_account) if to_account else None,
        amount_cents=amount_cents,
        category=category or None,
        day_of_month=day_of_month,
        start_period=start_period or None,
        end_period=end_period or None,
        installments=int(installments) if installments else None,
        notes=notes or None,
        tags=tags or None,
    )
    rule = recurring.create_rule(data, session)
    recurring.backfill_past_periods(rule.id, session)  # type: ignore[arg-type]

    if view == "statement" and account_id is not None:
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

    context = _recurring_list_context(session, recurring.current_period())
    return templates.TemplateResponse(request, "partials/_recurring_list.html", context)


@router.delete("/{rule_id}", response_class=HTMLResponse)
def delete_recorrente(
    rule_id: int,
    request: Request,
    delete_txns: Annotated[bool, Query()] = False,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    recurring.delete_rule(rule_id, session, delete_txns=delete_txns)
    context = _recurring_list_context(session, recurring.current_period())
    return templates.TemplateResponse(request, "partials/_recurring_list.html", context)


@router.post("/{rule_id}/post", response_class=HTMLResponse)
def post_recorrente(
    rule_id: int,
    request: Request,
    period: Annotated[str, Form()],
    session: Session = Depends(get_session),
) -> HTMLResponse:
    recurring.post_rule(rule_id, period, session)
    context = _recurring_list_context(session, period)
    return templates.TemplateResponse(request, "partials/_recurring_list.html", context)


@router.post("/post-all", response_class=HTMLResponse)
def post_all_recorrentes(
    request: Request,
    period: Annotated[str, Form()],
    session: Session = Depends(get_session),
) -> HTMLResponse:
    recurring.post_all_pending(period, session)
    context = _recurring_list_context(session, period)
    return templates.TemplateResponse(request, "partials/_recurring_list.html", context)


@router.post("/{rule_id}/skip", response_class=HTMLResponse)
def skip_recorrente(
    rule_id: int,
    request: Request,
    period: Annotated[str, Form()],
    session: Session = Depends(get_session),
) -> HTMLResponse:
    recurring.skip_rule(rule_id, period, session)
    context = _recurring_list_context(session, period)
    return templates.TemplateResponse(request, "partials/_recurring_list.html", context)


@router.get("/{rule_id}/field/{field}/edit", response_class=HTMLResponse)
def edit_recorrente_field(
    rule_id: int,
    field: str,
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    rule = session.get(RecurringRule, rule_id)
    if rule is None or field not in _FIELD_KINDS:
        return HTMLResponse("Not found", status_code=404)

    locale = request.cookies.get("locale", DEFAULT_LOCALE)
    account_codes = {a.id: a.code for a in accounts.list_accounts(session, active_only=False)}
    context = {
        "kind": _FIELD_KINDS[field],
        "value": _rule_edit_value(rule, field),
        "options": _field_options(field, session, locale),
        "patch_url": f"/recorrentes/{rule_id}/field/{field}",
        "target": "#recurring-list",
        "original": _rule_display(rule, field, account_codes),
        "error": None,
    }
    return templates.TemplateResponse(request, "partials/_editable_input.html", context)


@router.patch("/{rule_id}/field/{field}", response_class=HTMLResponse)
def patch_recorrente_field(
    rule_id: int,
    field: str,
    request: Request,
    value: Annotated[str, Form()] = "",
    session: Session = Depends(get_session),
) -> HTMLResponse:
    try:
        recurring.update_field(rule_id, field, value, session)
    except ValueError:
        rule = session.get(RecurringRule, rule_id)
        locale = request.cookies.get("locale", DEFAULT_LOCALE)
        account_codes = {a.id: a.code for a in accounts.list_accounts(session, active_only=False)}
        context = {
            "kind": _FIELD_KINDS.get(field, "text"),
            "value": _rule_edit_value(rule, field, override=value) if rule else value,
            "options": _field_options(field, session, locale),
            "patch_url": f"/recorrentes/{rule_id}/field/{field}",
            "target": "#recurring-list",
            "original": _rule_display(rule, field, account_codes) if rule else "",
            "error": translate(locale, "common.invalid_value"),
        }
        response = templates.TemplateResponse(request, "partials/_editable_input.html", context)
        response.headers["HX-Retarget"] = "closest td"
        response.headers["HX-Reswap"] = "innerHTML"
        return response

    context = _recurring_list_context(session, recurring.current_period())
    return templates.TemplateResponse(request, "partials/_recurring_list.html", context)


@router.get("/{rule_id}/config/edit", response_class=HTMLResponse)
def edit_rule_config(
    rule_id: int,
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    rule = session.get(RecurringRule, rule_id)
    if rule is None:
        return HTMLResponse("Not found", status_code=404)

    return templates.TemplateResponse(
        request,
        "partials/_rule_config_modal.html",
        {"rule": rule, "config_url": f"/recorrentes/{rule_id}/config"},
    )


@router.post("/{rule_id}/config", response_class=HTMLResponse)
def post_rule_config(
    rule_id: int,
    request: Request,
    notes: Annotated[str, Form()] = "",
    tags: Annotated[str, Form()] = "",
    session: Session = Depends(get_session),
) -> HTMLResponse:
    recurring.update_notes(rule_id, notes, session)
    recurring.update_tags(rule_id, tags, session)
    context = _recurring_list_context(session, recurring.current_period())
    return templates.TemplateResponse(request, "partials/_recurring_list.html", context)
