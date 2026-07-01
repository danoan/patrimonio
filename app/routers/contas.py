from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.db import get_session
from app.i18n import DEFAULT_LOCALE, translate
from app.models.tables import Account
from app.money import fmt_eur
from app.schemas.forms import AccountCreate, AccountValuationCreate, TxnCreate
from app.services import accounts, balances, ledger, valuations
from app.services.recurring import current_period
from app.templates_env import templates

router = APIRouter(prefix="/contas")

_FIELD_KINDS: dict[str, str] = {
    "name": "text",
    "tier": "select",
    "account_type": "select",
    "currency": "select",
    "opening_cents": "money",
    "opening_date": "date",
}


def _tier_badge(tier: str, locale: str) -> str:
    label = translate(locale, f"tier.{tier.lower()}") if tier else ""
    return f'<span class="tier tier--{tier}">{label}</span>'


def _account_type_label(account_type: str, locale: str) -> str:
    return translate(locale, f"account_type.{account_type}") if account_type else ""


def _account_display(account: Account, field: str, locale: str) -> str:
    if field == "name":
        return account.name
    if field == "tier":
        return _tier_badge(account.tier, locale)
    if field == "account_type":
        return _account_type_label(account.account_type, locale)
    if field == "currency":
        return account.currency
    if field == "opening_cents":
        return fmt_eur(account.opening_cents)
    return account.opening_date


def _account_edit_value(account: Account, field: str, override: str | None = None) -> str:
    if override is not None:
        return override
    if field == "opening_cents":
        return f"{account.opening_cents / 100:.2f}".replace(".", ",")
    if field == "name":
        return account.name
    if field == "tier":
        return account.tier
    if field == "account_type":
        return account.account_type
    if field == "currency":
        return account.currency
    return account.opening_date


def _account_field_options(field: str, locale: str) -> list[tuple[str, str]]:
    if field == "tier":
        tiers = ("Imediato", "Diferido", "Alocado")
        return [(tier, translate(locale, f"tier.{tier.lower()}")) for tier in tiers]
    if field == "account_type":
        types = ("checking", "savings", "variable")
        return [(t, _account_type_label(t, locale)) for t in types]
    if field == "currency":
        return [("EUR", "EUR"), ("USD", "USD")]
    return []


@router.get("", response_class=HTMLResponse)
def list_contas(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    account_list = accounts.list_accounts(session)
    account_balances = {a.id: balances.balance(a.id, session) for a in account_list if a.id}
    return templates.TemplateResponse(
        request,
        "pages/contas.html",
        {"account_list": account_list, "balances": account_balances},
    )


def _valuation_section_context(account_id: int, session: Session) -> dict[str, object]:
    return {
        "account_id": account_id,
        "valuation_history": valuations.valuation_history(account_id, session),
        "performance": valuations.performance(account_id, session),
        "chart_points": valuations.to_chart_points(valuations.list_valuations(account_id, session)),
        "default_period": current_period(),
    }


@router.get("/{code}", response_class=HTMLResponse)
def conta_detail(
    code: str,
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    account = accounts.get_account(code, session)
    if account is None:
        return HTMLResponse("Conta não encontrada", status_code=404)
    statement = ledger.account_statement(account.id, session)  # type: ignore[arg-type]
    current_balance = balances.balance(account.id, session)  # type: ignore[arg-type]
    return templates.TemplateResponse(
        request,
        "pages/conta_detail.html",
        {
            "account": account,
            "account_id": account.id,
            "statement": statement,
            "current_balance": current_balance,
            "account_list": accounts.list_accounts(session),
            "note_counts": ledger.note_counts_for_txns([r.txn for r in statement], session),
            **_valuation_section_context(account.id, session),  # type: ignore[arg-type]
        },
    )


@router.post("/{account_id}/valuations", response_class=HTMLResponse)
def record_conta_valuation(
    account_id: int,
    request: Request,
    period: Annotated[str, Form()],
    balance_str: Annotated[str, Form()],
    session: Session = Depends(get_session),
) -> HTMLResponse:
    locale = request.cookies.get("locale", DEFAULT_LOCALE)
    error: str | None = None
    try:
        balance_cents = int(float(balance_str.replace(",", ".")) * 100)
        data = AccountValuationCreate(period=period, balance_cents=balance_cents)
        valuations.record_valuation(account_id, data, session)
    except ValueError:
        error = translate(locale, "common.invalid_value")

    context = _valuation_section_context(account_id, session)
    context["error"] = error
    context["current_balance"] = balances.balance(account_id, session)
    context["oob_balance"] = True
    return templates.TemplateResponse(request, "partials/_account_valuations.html", context)


@router.delete("/{account_id}/valuations/{period}", response_class=HTMLResponse)
def delete_conta_valuation(
    account_id: int,
    period: str,
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    valuations.delete_valuation(account_id, period, session)
    context = _valuation_section_context(account_id, session)
    context["current_balance"] = balances.balance(account_id, session)
    context["oob_balance"] = True
    return templates.TemplateResponse(request, "partials/_account_valuations.html", context)


@router.post("/{account_id}/lancamentos", response_class=HTMLResponse)
def post_lancamento_conta(
    account_id: int,
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


@router.delete("/{account_id}/lancamentos/{txn_id}", response_class=HTMLResponse)
def delete_lancamento_conta(
    account_id: int,
    txn_id: int,
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    ledger.delete_txn(txn_id, session)
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


@router.post("", response_class=HTMLResponse)
def create_conta(
    request: Request,
    code: Annotated[str, Form()],
    name: Annotated[str, Form()],
    tier: Annotated[str, Form()],
    opening_date: Annotated[str, Form()],
    account_type: Annotated[str, Form()] = "checking",
    currency: Annotated[str, Form()] = "EUR",
    opening_str: Annotated[str, Form()] = "0",
    session: Session = Depends(get_session),
) -> HTMLResponse:
    opening_cents = int(float(opening_str.replace(",", ".")) * 100)
    data = AccountCreate(
        code=code,
        name=name,
        tier=tier,
        account_type=account_type,
        currency=currency,
        opening_cents=opening_cents,
        opening_date=opening_date,
    )
    accounts.create_account(data, session)
    account_list = accounts.list_accounts(session)
    account_balances = {a.id: balances.balance(a.id, session) for a in account_list if a.id}
    return templates.TemplateResponse(
        request,
        "partials/_account_list.html",
        {"account_list": account_list, "balances": account_balances},
    )


@router.get("/{account_id}/field/{field}/edit", response_class=HTMLResponse)
def edit_conta_field(
    account_id: int,
    field: str,
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    account = session.get(Account, account_id)
    if account is None or field not in _FIELD_KINDS:
        return HTMLResponse("Not found", status_code=404)

    locale = request.cookies.get("locale", DEFAULT_LOCALE)
    context = {
        "kind": _FIELD_KINDS[field],
        "value": _account_edit_value(account, field),
        "options": _account_field_options(field, locale),
        "patch_url": f"/contas/{account_id}/field/{field}",
        "target": "#account-list",
        "original": _account_display(account, field, locale),
        "error": None,
    }
    return templates.TemplateResponse(request, "partials/_editable_input.html", context)


@router.patch("/{account_id}/field/{field}", response_class=HTMLResponse)
def patch_conta_field(
    account_id: int,
    field: str,
    request: Request,
    value: Annotated[str, Form()] = "",
    session: Session = Depends(get_session),
) -> HTMLResponse:
    locale = request.cookies.get("locale", DEFAULT_LOCALE)
    try:
        accounts.update_field(account_id, field, value, session)
    except ValueError:
        account = session.get(Account, account_id)
        context = {
            "kind": _FIELD_KINDS.get(field, "text"),
            "value": _account_edit_value(account, field, override=value) if account else value,
            "options": _account_field_options(field, locale),
            "patch_url": f"/contas/{account_id}/field/{field}",
            "target": "#account-list",
            "original": _account_display(account, field, locale) if account else "",
            "error": translate(locale, "common.invalid_value"),
        }
        response = templates.TemplateResponse(request, "partials/_editable_input.html", context)
        response.headers["HX-Retarget"] = "closest td"
        response.headers["HX-Reswap"] = "innerHTML"
        return response

    account_list = accounts.list_accounts(session)
    account_balances = {a.id: balances.balance(a.id, session) for a in account_list if a.id}
    return templates.TemplateResponse(
        request,
        "partials/_account_list.html",
        {"account_list": account_list, "balances": account_balances},
    )
