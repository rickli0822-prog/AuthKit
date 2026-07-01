import json
from pathlib import Path

from authkit.i18n import init_locale, set_locale, t


def test_i18n_catalog_files_are_valid_json():
    i18n_dir = Path(__file__).resolve().parents[1] / "src" / "authkit" / "i18n"

    for path in sorted(i18n_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert "app.tagline" in data
        assert "network_strip.title" in data


def test_i18n_chinese_default():
    init_locale()
    set_locale("zh", persist=False)
    assert t("toolbar.diagnose") == "开始诊断"


def test_i18n_english():
    set_locale("en", persist=False)
    assert t("toolbar.diagnose") == "Run diagnosis"


def test_fix_none_needed_uses_selected_client_label():
    set_locale("en", persist=False)
    assert t("fix.none_needed", client="VS Code") == "No fix needed. Try signing in to VS Code."
    set_locale("zh", persist=False)
    assert t("fix.none_needed", client="VS Code") == "当前无需修复，可直接在 VS Code 中尝试登录。"


def test_i18n_repair_audit_keys():
    set_locale("en", persist=False)
    assert t("section.audit") == "Repair audit"
    assert t("audit.rollback_latest") == "Rollback latest"
    assert t("audit.risk") == "Risk"
    assert t("audit.admin") == "Admin"
    assert t("audit.restart") == "Restart"
    set_locale("zh", persist=False)
    assert t("section.audit") == "修复审计"
    assert t("audit.rollback_latest") == "回滚最近修复"
