from pathlib import Path

from authkit.brand import ICON_ICO
from authkit import shortcut


def test_app_icon_falls_back_to_packaged_icon_when_source_assets_missing(tmp_path):
    icon = Path(shortcut._app_icon(tmp_path))

    assert icon.name == ICON_ICO
    assert icon.is_file()
    assert icon.parent.name == "assets"
    assert icon.parent.parent.name == "authkit"


def test_launcher_target_prefers_source_pythonw_launcher(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    launcher = scripts / "launch_gui.pyw"
    launcher.write_text("", encoding="utf-8")

    target, arguments, working_dir = shortcut._launcher_target(tmp_path, r"C:\Python\pythonw.exe")

    assert target == r"C:\Python\pythonw.exe"
    assert arguments == f'"{launcher}"'
    assert working_dir == str(tmp_path)


def test_launcher_target_falls_back_to_source_cmd_without_pythonw(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    launcher = scripts / "authkit-gui.cmd"
    launcher.write_text("", encoding="utf-8")

    target, arguments, working_dir = shortcut._launcher_target(tmp_path, None)

    assert target == str(launcher)
    assert arguments == ""
    assert working_dir == str(tmp_path)


def test_launcher_target_falls_back_to_installed_entrypoint(monkeypatch, tmp_path):
    home = tmp_path / "home"

    monkeypatch.setattr(shortcut.shutil, "which", lambda name: r"C:\Tools\authkit-gui.exe" if name == "authkit-gui" else None)
    monkeypatch.setattr(shortcut.Path, "home", lambda: home)

    target, arguments, working_dir = shortcut._launcher_target(tmp_path, None)

    assert target == r"C:\Tools\authkit-gui.exe"
    assert arguments == ""
    assert working_dir == str(home)


def test_launcher_target_falls_back_to_sibling_installed_entrypoint(monkeypatch, tmp_path):
    home = tmp_path / "home"
    scripts = tmp_path / "venv" / "Scripts"
    scripts.mkdir(parents=True)
    python = scripts / "python.exe"
    gui = scripts / "authkit-gui.exe"
    python.write_text("", encoding="utf-8")
    gui.write_text("", encoding="utf-8")

    monkeypatch.setattr(shortcut.shutil, "which", lambda _name: None)
    monkeypatch.setattr(shortcut.sys, "executable", str(python))
    monkeypatch.setattr(shortcut.Path, "home", lambda: home)

    target, arguments, working_dir = shortcut._launcher_target(tmp_path, None)

    assert target == str(gui)
    assert arguments == ""
    assert working_dir == str(home)


def test_shortcut_plan_uses_desktop_and_start_menu_paths(tmp_path):
    plan = shortcut._shortcut_plan(
        user_profile=tmp_path / "User",
        appdata=tmp_path / "AppData" / "Roaming",
        target_path=r"C:\Tools\authkit-gui.exe",
        arguments="",
        working_dir=str(tmp_path),
        icon=r"C:\Tools\authkit.ico",
    )

    links = plan["links"]

    assert plan["target_path"] == r"C:\Tools\authkit-gui.exe"
    assert plan["description"].startswith("AuthKit - ")
    assert links[0] == tmp_path / "User" / "Desktop" / "AuthKit.lnk"
    assert links[1] == tmp_path / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "AuthKit.lnk"


def test_shortcut_dry_run_does_not_create_shortcuts(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "User"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
    monkeypatch.setattr(shortcut, "_source_root", lambda: tmp_path)
    monkeypatch.setattr(shortcut, "_find_pythonw", lambda: None)
    monkeypatch.setattr(shortcut, "_app_icon", lambda _root=None: r"C:\Tools\authkit.ico")
    monkeypatch.setattr(shortcut.shutil, "which", lambda name: r"C:\Tools\authkit-gui.exe" if name == "authkit-gui" else None)
    monkeypatch.setattr(shortcut, "_create_shortcut", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("should not create shortcut")))

    result = shortcut.main(["--dry-run"])
    output = capsys.readouterr().out

    assert result == 0
    assert "AuthKit shortcut dry run:" in output
    assert r"C:\Tools\authkit-gui.exe" in output
    assert "AuthKit.lnk" in output


def test_legacy_shortcut_script_delegates_to_package_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "create_desktop_shortcut.py"

    content = script.read_text(encoding="utf-8")

    assert "from authkit.shortcut import main" in content
