"""Create Windows desktop and Start Menu shortcuts for AuthKit."""

from __future__ import annotations

import os
import shutil
import sys
import argparse
from pathlib import Path

from authkit.brand import APP_NAME, APP_TAGLINE_KEY, APP_WINDOW_TITLE_KEY, ICON_ICO
from authkit.i18n import init_locale, t
from authkit.platform.subprocess import run_hidden


SHORTCUT_FILE_NAME = f"{APP_NAME}.lnk"


def _find_pythonw() -> str | None:
    for name in ("pythonw.exe", "python.exe"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _source_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _app_icon(root: Path | None = None) -> str:
    source_root = root or _source_root()
    ico = source_root / "assets" / ICON_ICO
    if ico.is_file():
        return str(ico)
    try:
        from authkit.ui.app import _asset_path

        packaged = _asset_path(ICON_ICO)
        if packaged.is_file():
            return str(packaged)
    except Exception:
        pass
    return os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "imageres.dll,109")


def _launcher_target(root: Path | None, pythonw: str | None) -> tuple[str, str, str] | None:
    source_root = root or _source_root()
    launcher_cmd = source_root / "scripts" / "authkit-gui.cmd"
    launcher_pyw = source_root / "scripts" / "launch_gui.pyw"
    if launcher_pyw.is_file() and pythonw:
        return pythonw, f'"{launcher_pyw}"', str(source_root)
    if launcher_cmd.is_file():
        return str(launcher_cmd), "", str(source_root)

    installed_gui = _installed_gui_entrypoint()
    if installed_gui:
        return installed_gui, "", str(Path.home())
    return None


def _installed_gui_entrypoint() -> str | None:
    found = shutil.which("authkit-gui") or shutil.which("authkit-gui.exe")
    if found:
        return found
    executable = Path(sys.executable)
    candidates = [executable.with_name("authkit-gui.exe"), executable.with_name("authkit-gui")]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create AuthKit Windows shortcuts")
    parser.add_argument("--dry-run", action="store_true", help="show shortcut targets without creating .lnk files")
    args = parser.parse_args(argv)

    if sys.platform != "win32":
        print("Only Windows is supported.", file=sys.stderr)
        return 2

    init_locale()
    root = _source_root()
    pythonw = _find_pythonw()
    if pythonw and pythonw.lower().endswith("python.exe"):
        candidate = str(Path(pythonw).with_name("pythonw.exe"))
        if Path(candidate).is_file():
            pythonw = candidate

    launcher = _launcher_target(root, pythonw)
    if launcher is None:
        print("Could not find the AuthKit GUI launcher. Install AuthKit or keep the scripts launcher files.", file=sys.stderr)
        return 1
    target_path, arguments, working_dir = launcher

    user_profile = os.environ.get("USERPROFILE")
    appdata = os.environ.get("APPDATA")
    if not user_profile or not appdata:
        print("USERPROFILE and APPDATA are required to create Windows shortcuts.", file=sys.stderr)
        return 1

    plan = _shortcut_plan(
        user_profile=Path(user_profile),
        appdata=Path(appdata),
        target_path=target_path,
        arguments=arguments,
        working_dir=working_dir,
        icon=_app_icon(root),
    )

    if args.dry_run:
        print("AuthKit shortcut dry run:")
        print(f"- target: {plan['target_path']}")
        print(f"- arguments: {plan['arguments'] or '-'}")
        print(f"- working_dir: {plan['working_dir']}")
        print(f"- icon: {plan['icon']}")
        for link in plan["links"]:
            print(f"- link: {link}")
        return 0

    for link in plan["links"]:
        _create_shortcut(
            link_path=str(link),
            target_path=str(plan["target_path"]),
            arguments=str(plan["arguments"]),
            working_dir=str(plan["working_dir"]),
            description=str(plan["description"]),
            icon=str(plan["icon"]),
        )
        print(f"Created: {link}")

    print(f"\nDouble-click {t(APP_WINDOW_TITLE_KEY)} on the desktop to open AuthKit.")
    return 0


def _shortcut_plan(
    *,
    user_profile: Path,
    appdata: Path,
    target_path: str,
    arguments: str,
    working_dir: str,
    icon: str,
) -> dict[str, object]:
    desktop = user_profile / "Desktop"
    start_menu = appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    return {
        "target_path": target_path,
        "arguments": arguments,
        "working_dir": working_dir,
        "description": f"{APP_NAME} - {t(APP_TAGLINE_KEY)}",
        "icon": icon,
        "links": [
            desktop / SHORTCUT_FILE_NAME,
            start_menu / SHORTCUT_FILE_NAME,
        ],
    }


def _create_shortcut(
    *,
    link_path: str,
    target_path: str,
    arguments: str,
    working_dir: str,
    description: str,
    icon: str,
) -> None:
    link = Path(link_path)
    link.parent.mkdir(parents=True, exist_ok=True)

    ps = f"""
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut('{_escape_ps(link_path)}')
$shortcut.TargetPath = '{_escape_ps(target_path)}'
$shortcut.Arguments = '{_escape_ps(arguments)}'
$shortcut.WorkingDirectory = '{_escape_ps(working_dir)}'
$shortcut.WindowStyle = 1
$shortcut.Description = '{_escape_ps(description)}'
$shortcut.IconLocation = '{_escape_ps(icon)}'
$shortcut.Save()
"""
    completed = run_hidden(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "Failed to create shortcut").strip())


def _escape_ps(value: str) -> str:
    return value.replace("'", "''")
