from pathlib import Path
import re

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 compatibility.
    tomllib = None

from authkit.brand import ICON_ICO, ICON_PNG_48
from authkit.ui.app import _asset_path


def _load_pyproject() -> dict[str, dict[str, dict[str, object]]]:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    if tomllib is not None:
        return tomllib.loads(text)

    def array_value(key: str) -> list[str]:
        match = re.search(rf'(?m)^"{re.escape(key)}"\s*=\s*\[([^\]]*)\]', text)
        if not match:
            raise AssertionError(f"missing package-data entry: {key}")
        return re.findall(r'"([^"]+)"', match.group(1))

    def script_value(key: str) -> str:
        match = re.search(rf'(?m)^{re.escape(key)}\s*=\s*"([^"]+)"', text)
        if not match:
            raise AssertionError(f"missing script entry: {key}")
        return match.group(1)

    return {
        "tool": {
            "setuptools": {
                "package-data": {
                    "authkit.i18n": array_value("authkit.i18n"),
                    "authkit": array_value("authkit"),
                }
            }
        },
        "project": {
            "scripts": {
                "authkit": script_value("authkit"),
                "authkit-gui": script_value("authkit-gui"),
                "authkit-shortcut": script_value("authkit-shortcut"),
            }
        },
    }


def test_i18n_json_declared_as_package_data():
    data = _load_pyproject()

    package_data = data["tool"]["setuptools"]["package-data"]

    assert "*.json" in package_data["authkit.i18n"]


def test_gui_assets_declared_as_package_data():
    data = _load_pyproject()

    package_data = data["tool"]["setuptools"]["package-data"]

    assert "assets/*.png" in package_data["authkit"]
    assert "assets/*.ico" in package_data["authkit"]


def test_installed_shortcut_entrypoint_declared():
    data = _load_pyproject()

    scripts = data["project"]["scripts"]

    assert scripts["authkit"] == "authkit.cli:main"
    assert scripts["authkit-gui"] == "authkit.ui.app:main"
    assert scripts["authkit-shortcut"] == "authkit.shortcut:main"


def test_release_smoke_script_documents_installed_package_gate():
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "release_smoke.py"
    foundation = root / "scripts" / "foundation_audit.py"
    drill = root / "scripts" / "field_repair_drill.py"
    samples = root / "scripts" / "field_sample_regression.py"
    checklist = root / "docs" / "RELEASE_CHECKLIST.md"
    readiness = root / "docs" / "FOUNDATION_READINESS.md"

    script_text = script.read_text(encoding="utf-8")
    foundation_text = foundation.read_text(encoding="utf-8")
    drill_text = drill.read_text(encoding="utf-8")
    samples_text = samples.read_text(encoding="utf-8")
    checklist_text = checklist.read_text(encoding="utf-8")
    readiness_text = readiness.read_text(encoding="utf-8")

    assert "pip\", \"wheel" in script_text
    assert "authkit-shortcut" in script_text
    assert "_INSTALLED_PACKAGE_CHECK" in script_text
    assert "scripts/foundation_audit.py" in script_text
    assert "scripts/field_repair_drill.py" in script_text
    assert "scripts/field_sample_regression.py" in script_text
    assert "FOUNDATION_READINESS.md" in foundation_text
    assert "release_smoke.py" in foundation_text
    assert "flush-dns-cache" in drill_text
    assert "LOCALAPPDATA" in drill_text
    assert "metadata.expected" in samples_text
    assert "python scripts\\release_smoke.py" in checklist_text
    assert "foundation_audit.py" in checklist_text
    assert "field_repair_drill.py" in checklist_text
    assert "field_sample_regression.py" in checklist_text
    assert "authkit-gui --smoke" in readiness_text


def test_field_sample_regression_fixture_is_valid():
    from authkit.cli import _validate_support_bundle

    root = Path(__file__).resolve().parents[1]
    sample = root / "docs" / "field_samples" / "codex-proxy-mismatch.sample.json"

    assert sample.is_file()
    assert _validate_support_bundle(sample) == []


def test_gui_asset_path_prefers_packaged_assets():
    icon_png = _asset_path(ICON_PNG_48)
    icon_ico = _asset_path(ICON_ICO)

    assert icon_png.is_file()
    assert icon_ico.is_file()
    assert icon_png.parent.name == "assets"
    assert icon_png.parent.parent.name == "authkit"
