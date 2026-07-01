import pytest
from app.i18n import DEFAULT_LOCALE, SUPPORTED_LOCALES, translate


@pytest.mark.unit
def test_translate_returns_pt_by_default() -> None:
    assert translate("pt", "nav.overview") == "Visão geral"


@pytest.mark.unit
def test_translate_returns_en() -> None:
    assert translate("en", "nav.overview") == "Overview"


@pytest.mark.unit
def test_translate_interpolates_placeholders() -> None:
    text = translate("en", "recorrentes.pending_banner", count=3, period="2026-07")
    assert text == "⏳ 3 pending rule(s) for 2026-07."


@pytest.mark.unit
def test_translate_falls_back_to_default_locale_for_unknown_locale() -> None:
    assert translate("xx", "nav.overview") == translate(DEFAULT_LOCALE, "nav.overview")


@pytest.mark.unit
def test_translate_falls_back_to_raw_key_when_missing() -> None:
    assert translate("en", "does.not.exist") == "does.not.exist"


@pytest.mark.unit
def test_supported_locales_include_default() -> None:
    assert DEFAULT_LOCALE in SUPPORTED_LOCALES
