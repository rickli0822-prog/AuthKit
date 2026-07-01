"""Run AuthKit release smoke checks.

This script verifies the field-delivery surface without creating shortcuts or
mutating Windows repair settings.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run AuthKit release smoke checks")
    parser.add_argument("--skip-tests", action="store_true", help="skip pytest when a prior full test run is already available")
    args = parser.parse_args(argv)

    _run([sys.executable, "-m", "compileall", "-q", "src", "scripts"])
    if not args.skip_tests:
        _run([sys.executable, "-m", "pytest", "-q"])
    _run([sys.executable, "scripts/foundation_audit.py"])
    _run([sys.executable, "scripts/build_windows_installer.py", "--check-only"])
    _run([sys.executable, "scripts/field_repair_drill.py"])
    _run([sys.executable, "scripts/field_sample_regression.py"])
    _wheel_install_smoke()
    print("AuthKit release smoke passed.")
    return 0


def _wheel_install_smoke() -> None:
    with tempfile.TemporaryDirectory(prefix="authkit-release-smoke-") as tmp_name:
        tmp = Path(tmp_name)
        wheel_dir = tmp / "wheel"
        venv_dir = tmp / "venv"
        wheel_dir.mkdir()

        _run([sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "-w", str(wheel_dir)])
        wheels = sorted(wheel_dir.glob("authkit-*.whl"))
        if not wheels:
            raise RuntimeError("AuthKit wheel was not produced")

        _run([sys.executable, "-m", "venv", str(venv_dir)])
        python = _venv_python(venv_dir)
        scripts = _venv_scripts_dir(venv_dir)
        _run([str(python), "-m", "pip", "install", "--no-index", "--find-links", str(wheel_dir), "authkit"])

        _run([str(python), "-c", _INSTALLED_PACKAGE_CHECK])
        for name in ("authkit", "authkit-gui", "authkit-shortcut"):
            exe = scripts / _script_name(name)
            if not exe.is_file():
                raise RuntimeError(f"Missing installed entry point: {exe}")
        authkit = scripts / _script_name("authkit")
        _run([str(authkit), "--help"])
        sample_bundle = tmp / "authkit-support-bundle.sample.json"
        _run([str(authkit), "bundle", "--sample", "--client", "codex", "--out", str(sample_bundle)])
        _run([str(authkit), "bundle", "--validate", str(sample_bundle)])
        _run([str(scripts / _script_name("authkit-shortcut")), "--dry-run"])
        if os.environ.get("AUTHKIT_SKIP_GUI_SMOKE") == "1":
            print("Skipping installed GUI smoke because AUTHKIT_SKIP_GUI_SMOKE=1.")
        else:
            _run([str(scripts / _script_name("authkit-gui")), "--smoke"])


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    print(f"> {' '.join(command)}")
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.stdout:
        print(completed.stdout.rstrip())
    if completed.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {completed.returncode}: {' '.join(command)}")
    return completed


def _venv_python(venv_dir: Path) -> Path:
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _venv_scripts_dir(venv_dir: Path) -> Path:
    if sys.platform == "win32":
        return venv_dir / "Scripts"
    return venv_dir / "bin"


def _script_name(name: str) -> str:
    if sys.platform == "win32":
        return f"{name}.exe"
    return name


_INSTALLED_PACKAGE_CHECK = r"""
import importlib.metadata as md
from importlib import resources

from authkit.brand import APP_NAME, ICON_ICO
from authkit.i18n import t
from authkit.ui.app import _asset_path
import authkit.shortcut

entry_points = {
    ep.name: ep.value
    for ep in md.entry_points(group="console_scripts")
    if ep.name.startswith("authkit")
}
assert entry_points["authkit"] == "authkit.cli:main", entry_points
assert entry_points["authkit-gui"] == "authkit.ui.app:main", entry_points
assert entry_points["authkit-shortcut"] == "authkit.shortcut:main", entry_points

assert resources.files("authkit.i18n").joinpath("zh.json").is_file()
assert resources.files("authkit.i18n").joinpath("en.json").is_file()
assert APP_NAME == "AuthKit"
assert t("app.tagline") != "app.tagline"
assert _asset_path(ICON_ICO).is_file()
assert hasattr(authkit.shortcut, "main")
print("installed-package-ok")
"""


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"release smoke failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
