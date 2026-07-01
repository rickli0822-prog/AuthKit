"""用户设置读写。"""

from __future__ import annotations

import json
import os
from pathlib import Path

from authkit.brand import CONFIG_DIR_NAME

DEFAULT_LOCALE = "zh"
SUPPORTED_LOCALES = ("zh", "en")


def config_dir() -> Path:
    userprofile = os.environ.get("USERPROFILE")
    base = Path(userprofile) if userprofile else Path.home()
    return base / CONFIG_DIR_NAME


def config_path() -> Path:
    return config_dir() / "settings.json"


def load_settings() -> dict:
    path = config_path()
    if not path.is_file():
        return {"locale": DEFAULT_LOCALE}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"locale": DEFAULT_LOCALE}
        if data.get("locale") not in SUPPORTED_LOCALES:
            data["locale"] = DEFAULT_LOCALE
        return data
    except (OSError, json.JSONDecodeError):
        return {"locale": DEFAULT_LOCALE}


def save_settings(settings: dict) -> None:
    directory = config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    target = config_path()
    temp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        payload = json.dumps(settings, ensure_ascii=False, indent=2)
        with temp.open("w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(target)
    finally:
        try:
            if temp.exists():
                temp.unlink()
        except OSError:
            pass


def load_locale() -> str:
    return str(load_settings().get("locale", DEFAULT_LOCALE))


def save_locale(locale: str) -> None:
    if locale not in SUPPORTED_LOCALES:
        locale = DEFAULT_LOCALE
    settings = load_settings()
    settings["locale"] = locale
    save_settings(settings)
