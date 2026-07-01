import json
from pathlib import Path
from typing import Any

DEFAULT_LOCALE = "pt"
SUPPORTED_LOCALES = ("pt", "en")

_DIR = Path(__file__).parent
_CATALOGS: dict[str, dict[str, Any]] = {
    locale: json.loads((_DIR / f"{locale}.json").read_text(encoding="utf-8"))
    for locale in SUPPORTED_LOCALES
}


def _lookup(catalog: dict[str, Any], key: str) -> str | None:
    node: dict[str, Any] | str = catalog
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, str) else None


def translate(locale: str, key: str, **kwargs: object) -> str:
    catalog = _CATALOGS.get(locale, _CATALOGS[DEFAULT_LOCALE])
    text = _lookup(catalog, key)
    if text is None:
        text = _lookup(_CATALOGS[DEFAULT_LOCALE], key)
    if text is None:
        return key
    return text.format(**kwargs) if kwargs else text
