from fastapi.templating import Jinja2Templates
from jinja2 import pass_context
from jinja2.runtime import Context

from app.i18n import DEFAULT_LOCALE, translate
from app.money import fmt_eur, fmt_pct, fmt_usd
from app.services.ledger import is_resolved

templates = Jinja2Templates(directory="app/templates")
templates.env.filters["eur"] = fmt_eur
templates.env.filters["usd"] = fmt_usd
templates.env.filters["pct"] = fmt_pct


@pass_context
def t(context: Context, key: str, **kwargs: object) -> str:
    request = context["request"]
    locale = request.cookies.get("locale", DEFAULT_LOCALE)
    return translate(locale, key, **kwargs)


@pass_context
def current_locale(context: Context) -> str:
    request = context["request"]
    locale: str = request.cookies.get("locale", DEFAULT_LOCALE)
    return locale


templates.env.globals["t"] = t  # type: ignore[arg-type]
templates.env.globals["current_locale"] = current_locale  # type: ignore[arg-type]
templates.env.globals["is_resolved"] = is_resolved  # type: ignore[arg-type]
