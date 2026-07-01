"""Build AuthKit Windows release artifacts.

The script creates PyInstaller onedir builds for the GUI and CLI, writes a
portable zip, and builds an Inno Setup installer when ISCC.exe is available.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = REPO_ROOT / "build" / "windows-installer"
DIST_ROOT = REPO_ROOT / "dist" / "windows"
LAUNCHER_DIR = BUILD_ROOT / "launchers"
ISS_PATH = BUILD_ROOT / "AuthKit.iss"
BUILDER_VENV = BUILD_ROOT / "builder-venv"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build AuthKit Windows installer artifacts")
    parser.add_argument("--check-only", action="store_true", help="verify required builder tools without building artifacts")
    parser.add_argument("--skip-inno", action="store_true", help="skip Inno Setup even when ISCC.exe is available")
    parser.add_argument("--require-inno", action="store_true", help="fail if Inno Setup compiler is not available")
    parser.add_argument("--no-clean", action="store_true", help="reuse existing build/dist folders")
    args = parser.parse_args(argv)

    version = _project_version()
    pyinstaller = _require_pyinstaller()
    iscc = _find_iscc()

    if args.require_inno and not iscc:
        raise RuntimeError("Inno Setup compiler ISCC.exe was not found on PATH or in the default install folders")

    if args.check_only:
        print("AuthKit Windows installer tool check:")
        print(f"- pyinstaller: {pyinstaller}")
        print(f"- inno_setup: {iscc or 'not found; installer .iss will still be generated'}")
        print(f"- version: {version}")
        return 0

    if not args.no_clean:
        shutil.rmtree(BUILD_ROOT, ignore_errors=True)
        shutil.rmtree(DIST_ROOT, ignore_errors=True)
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    DIST_ROOT.mkdir(parents=True, exist_ok=True)
    LAUNCHER_DIR.mkdir(parents=True, exist_ok=True)

    builder_python = _create_builder_venv()
    gui_launcher, cli_launcher = _write_launchers()
    _run_pyinstaller(builder_python, gui_launcher, name="AuthKit", windowed=True)
    _run_pyinstaller(builder_python, cli_launcher, name="AuthKitCLI", windowed=False)
    _smoke_artifacts()

    zip_path = _write_portable_zip(version)
    iss_path = _write_inno_script(version)
    installer_path = None
    if not args.skip_inno and iscc:
        _run([iscc, str(iss_path)])
        expected = DIST_ROOT / f"AuthKit_Setup_{version}.exe"
        if not expected.is_file():
            raise RuntimeError(f"Inno Setup completed but installer was not found: {expected}")
        installer_path = expected

    print("AuthKit Windows artifacts:")
    print(f"- gui: {DIST_ROOT / 'AuthKit' / 'AuthKit.exe'}")
    print(f"- cli: {DIST_ROOT / 'AuthKitCLI' / 'AuthKitCLI.exe'}")
    print(f"- portable_zip: {zip_path}")
    print(f"- inno_script: {iss_path}")
    if installer_path:
        print(f"- installer: {installer_path}")
    else:
        print("- installer: not built; install Inno Setup or rerun without --skip-inno when ISCC.exe is available")
    return 0


def _project_version() -> str:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def _require_pyinstaller() -> str:
    command = [sys.executable, "-m", "PyInstaller", "--version"]
    completed = subprocess.run(command, cwd=REPO_ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if completed.returncode != 0:
        raise RuntimeError("PyInstaller is required. Install it with: python -m pip install pyinstaller")
    return completed.stdout.strip().splitlines()[-1]


def _find_iscc() -> str | None:
    found = shutil.which("ISCC.exe") or shutil.which("iscc.exe") or shutil.which("ISCC") or shutil.which("iscc")
    if found:
        return found
    for candidate in (
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
    ):
        if candidate.is_file():
            return str(candidate)
    return None


def _write_launchers() -> tuple[Path, Path]:
    gui = LAUNCHER_DIR / "authkit_gui.py"
    cli = LAUNCHER_DIR / "authkit_cli.py"
    gui.write_text(
        "from authkit.ui.app import main\n\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main())\n",
        encoding="utf-8",
    )
    cli.write_text(
        "from authkit.cli import main\n\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main())\n",
        encoding="utf-8",
    )
    return gui, cli


def _create_builder_venv() -> Path:
    _run([sys.executable, "-m", "venv", str(BUILDER_VENV)])
    python = _venv_python(BUILDER_VENV)
    _run([str(python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel", "pyinstaller"])
    _run([str(python), "-m", "pip", "install", "."])
    return python


def _venv_python(venv_dir: Path) -> Path:
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _run_pyinstaller(python: Path, launcher: Path, *, name: str, windowed: bool) -> None:
    args = [
        str(python),
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        name,
        "--icon",
        str(REPO_ROOT / "assets" / "authkit.ico"),
        "--distpath",
        str(DIST_ROOT),
        "--workpath",
        str(BUILD_ROOT / "pyinstaller-work" / name),
        "--specpath",
        str(BUILD_ROOT / "pyinstaller-spec" / name),
        "--collect-data",
        "authkit",
    ]
    if windowed:
        args.append("--windowed")
    args.append(str(launcher))
    _run(args)


def _write_portable_zip(version: str) -> Path:
    package_root = BUILD_ROOT / f"AuthKit-{version}-windows"
    shutil.rmtree(package_root, ignore_errors=True)
    package_root.mkdir(parents=True)
    shutil.copytree(DIST_ROOT / "AuthKit", package_root / "AuthKit")
    shutil.copytree(DIST_ROOT / "AuthKitCLI", package_root / "authkit-cli")
    (package_root / "README.txt").write_text(
        "AuthKit Windows portable build\n\n"
        "Run AuthKit\\AuthKit.exe to open the GUI.\n"
        "Run authkit-cli\\AuthKitCLI.exe from a terminal for CLI diagnostics.\n"
        "Repair commands must still be explicitly confirmed in the GUI or CLI.\n",
        encoding="utf-8",
    )
    archive_base = DIST_ROOT / f"AuthKit-{version}-windows-portable"
    zip_file = shutil.make_archive(str(archive_base), "zip", root_dir=package_root)
    return Path(zip_file)


def _smoke_artifacts() -> None:
    gui = DIST_ROOT / "AuthKit" / "AuthKit.exe"
    cli = DIST_ROOT / "AuthKitCLI" / "AuthKitCLI.exe"
    if not gui.is_file():
        raise RuntimeError(f"Missing GUI executable: {gui}")
    if not cli.is_file():
        raise RuntimeError(f"Missing CLI executable: {cli}")
    _run([str(gui), "--smoke"])
    _run([str(cli), "--help"])


def _write_inno_script(version: str) -> Path:
    app_source = (DIST_ROOT / "AuthKit").as_posix()
    cli_source = (DIST_ROOT / "AuthKitCLI").as_posix()
    output_dir = DIST_ROOT.as_posix()
    icon_path = (REPO_ROOT / "assets" / "authkit.ico").as_posix()
    ISS_PATH.write_text(
        f"""#define AppName "AuthKit"
#define AppVersion "{version}"
#define AppPublisher "AuthKit contributors"
#define AppSource "{app_source}"
#define CliSource "{cli_source}"
#define OutputDir "{output_dir}"
#define IconPath "{icon_path}"

[Setup]
AppId={{{{8F6D7F08-4FB0-4D20-9D4C-A17400100001}}}}
AppName={{#AppName}}
AppVersion={{#AppVersion}}
AppPublisher={{#AppPublisher}}
DefaultDirName={{autopf}}\\AuthKit
DefaultGroupName=AuthKit
OutputDir={{#OutputDir}}
OutputBaseFilename=AuthKit_Setup_{{#AppVersion}}
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile={{#IconPath}}
UninstallDisplayIcon={{app}}\\AuthKit.exe
PrivilegesRequired=lowest

[Files]
Source: "{{#AppSource}}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{{#CliSource}}\\*"; DestDir: "{{app}}\\cli"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{{group}}\\AuthKit"; Filename: "{{app}}\\AuthKit.exe"; WorkingDir: "{{app}}"
Name: "{{autodesktop}}\\AuthKit"; Filename: "{{app}}\\AuthKit.exe"; WorkingDir: "{{app}}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Run]
Filename: "{{app}}\\AuthKit.exe"; Description: "Launch AuthKit"; Flags: nowait postinstall skipifsilent
""",
        encoding="utf-8",
    )
    return ISS_PATH


def _run(command: list[str], *, isolated: bool = True) -> None:
    print(f"> {' '.join(command)}")
    env = os.environ.copy()
    if isolated:
        env.pop("PYTHONPATH", None)
    else:
        env["PYTHONPATH"] = str(REPO_ROOT / "src")
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=env,
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


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"windows installer build failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
