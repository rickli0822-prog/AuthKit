"""字体解析测试。"""

from authkit.ui.fonts import FONT_MONO, FONT_UI_EN, FONT_UI_ZH, FontSet, _first_available


def test_first_available_font():
    families = {"Segoe UI", "Consolas"}
    assert _first_available(families, FONT_UI_EN) == "Segoe UI"
    assert _first_available(families, FONT_MONO) == "Consolas"


def test_zh_ui_font_fallback():
    families = {"Microsoft YaHei UI", "Cascadia Code"}
    assert _first_available(families, FONT_UI_ZH) == "Microsoft YaHei UI"


def test_font_tokens_are_large_enough_for_desktop_gui():
    fonts = FontSet(ui="Segoe UI", mono="Consolas")

    assert fonts.size_body >= 20
    assert fonts.size_small >= 17
    assert fonts.size_caption >= 16
    assert fonts.size_mono >= 19
