"""界面文案国际化。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from authkit.settings import DEFAULT_LOCALE, SUPPORTED_LOCALES, load_locale, save_locale

_LOCALE = DEFAULT_LOCALE


def get_locale() -> str:
    return _LOCALE


def set_locale(locale: str, *, persist: bool = True) -> None:
    global _LOCALE
    if locale not in SUPPORTED_LOCALES:
        locale = DEFAULT_LOCALE
    _LOCALE = locale
    if persist:
        save_locale(locale)


def init_locale() -> str:
    global _LOCALE
    _LOCALE = load_locale()
    return _LOCALE


@lru_cache(maxsize=8)
def _load_catalog(locale: str) -> dict[str, str]:
    path = Path(__file__).with_name(f"{locale}.json")
    if not path.is_file():
        path = Path(__file__).with_name(f"{DEFAULT_LOCALE}.json")
    return json.loads(path.read_text(encoding="utf-8"))


def t(key: str, **kwargs: Any) -> str:
    catalog = _load_catalog(_LOCALE)
    text = catalog.get(key) or _load_catalog(DEFAULT_LOCALE).get(key) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text


def case_title(case_value: str) -> str:
    mapping = {
        "none": "case.none",
        "A": "case.A",
        "B": "case.B",
        "C": "case.C",
        "D": "case.D",
        "E": "case.E",
        "F": "case.F",
        "unknown": "case.unknown",
    }
    return t(mapping.get(case_value, "case.unknown"))


def layer_name(layer_key: str) -> str:
    return t(f"layer.{layer_key}")


def locale_label(locale: str) -> str:
    return "中文" if locale == "zh" else "English"
