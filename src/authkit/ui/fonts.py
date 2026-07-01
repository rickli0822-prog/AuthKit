"""字体解析：对齐 Cursor（VS Code）在 Windows 上的默认字体栈。"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

import tkinter as tk
from tkinter import font as tkfont

# Cursor workbench.css — Windows
# .windows { Segoe WPC, Segoe UI }
# .windows:lang(zh-Hans) { Segoe WPC, Segoe UI, Microsoft YaHei }
FONT_UI_EN = ("Segoe UI", "Segoe UI Variable Text", "Segoe UI Variable", "Tahoma")
FONT_UI_ZH = ("Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI")

# Cursor / VS Code 编辑器默认等宽字体优先顺序
FONT_MONO = ("Cascadia Code", "Cascadia Mono", "Consolas", "Courier New")


@dataclass(frozen=True)
class FontSet:
    ui: str
    mono: str
    size_body: int = 21
    size_title: int = 40
    size_section: int = 20
    size_small: int = 18
    size_caption: int = 17
    size_mono_body: int = 20

    def ui_font(self, size: int | None = None, *, bold: bool = False) -> tuple[str, int, str] | tuple[str, int]:
        px = size if size is not None else self.size_body
        # Negative sizes are pixel heights in Tkinter. This avoids Windows DPI
        # point-size expansion from clipping text inside table rows and buttons.
        px = -abs(px)
        return (self.ui, px, "bold") if bold else (self.ui, px)

    def mono_font(self, size: int | None = None) -> tuple[str, int]:
        px = size if size is not None else self.size_mono
        return (self.mono, -abs(px))

    @property
    def size_mono(self) -> int:
        return self.size_mono_body


def _first_available(families: set[str], candidates: tuple[str, ...]) -> str:
    for name in candidates:
        if name in families:
            return name
    return candidates[-1]


def _parse_cursor_editor_font(families: set[str]) -> str | None:
    """若用户在 Cursor 中自定义了 editor.fontFamily，则优先沿用。"""
    settings_path = Path(os.environ.get("APPDATA", "")) / "Cursor" / "User" / "settings.json"
    if not settings_path.is_file():
        return None
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        raw = str(data.get("editor.fontFamily") or "").strip()
        if not raw:
            return None
        for part in re.split(r",\s*", raw):
            name = part.strip().strip("'\"")
            if name and name in families:
                return name
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    return None


def resolve_fonts(root: tk.Misc, locale: str) -> FontSet:
    families = set(tkfont.families(root))
    ui_candidates = FONT_UI_ZH if locale == "zh" else FONT_UI_EN
    ui = _first_available(families, ui_candidates)
    mono = _parse_cursor_editor_font(families) or _first_available(families, FONT_MONO)
    return FontSet(ui=ui, mono=mono)
