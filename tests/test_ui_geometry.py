from pathlib import Path

import pytest

from authkit.ui import app as ui_app
from authkit.ui.app import _initial_window_geometry


def test_initial_window_geometry_uses_two_thirds_and_centers():
    assert _initial_window_geometry(screen_width=1920, screen_height=1080) == (1280, 760, 320, 160)


def test_initial_window_geometry_scales_on_large_screen():
    assert _initial_window_geometry(screen_width=3840, screen_height=2160) == (2560, 1440, 640, 360)


def test_initial_window_geometry_respects_small_screen_bounds():
    assert _initial_window_geometry(screen_width=1000, screen_height=700) == (1000, 700, 0, 0)


def test_gui_smoke_creates_updates_and_destroys_app(monkeypatch, tmp_path, capsys):
    icon_png = tmp_path / "authkit-icon-48.png"
    icon_ico = tmp_path / "authkit.ico"
    icon_png.write_text("", encoding="utf-8")
    icon_ico.write_text("", encoding="utf-8")
    calls = []

    class FakeApp:
        def update_idletasks(self):
            calls.append("update")

        def title(self):
            return "AuthKit"

        def geometry(self):
            return "1280x760+320+160"

        def destroy(self):
            calls.append("destroy")

    monkeypatch.setattr(ui_app, "AuthKitApp", FakeApp)
    monkeypatch.setattr(ui_app, "_asset_path", lambda name: icon_png if name.endswith(".png") else icon_ico)

    result = ui_app._run_gui_smoke()
    output = capsys.readouterr().out

    assert result == 0
    assert calls == ["update", "destroy"]
    assert "AuthKit GUI smoke passed." in output
    assert "- title: AuthKit" in output


def test_gui_smoke_destroys_app_when_resource_check_fails(monkeypatch, tmp_path):
    calls = []

    class FakeApp:
        def update_idletasks(self):
            calls.append("update")

        def destroy(self):
            calls.append("destroy")

    monkeypatch.setattr(ui_app, "AuthKitApp", FakeApp)
    monkeypatch.setattr(ui_app, "_asset_path", lambda _name: tmp_path / "missing")

    with pytest.raises(RuntimeError):
        ui_app._run_gui_smoke()

    assert calls == ["update", "destroy"]
