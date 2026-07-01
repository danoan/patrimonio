from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app.i18n import DEFAULT_LOCALE, SUPPORTED_LOCALES

router = APIRouter(prefix="/locale")


@router.get("/{lang}")
def set_locale(lang: str, request: Request) -> RedirectResponse:
    locale = lang if lang in SUPPORTED_LOCALES else DEFAULT_LOCALE
    redirect_to = request.headers.get("referer", "/")
    response = RedirectResponse(url=redirect_to, status_code=303)
    response.set_cookie(
        "locale",
        locale,
        max_age=60 * 60 * 24 * 365,
        samesite="lax",
    )
    return response
