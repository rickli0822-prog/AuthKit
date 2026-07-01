import types

from authkit.platform import privileges


def test_is_running_as_admin_returns_false_outside_windows(monkeypatch):
    monkeypatch.setattr(privileges.sys, "platform", "linux")

    assert privileges.is_running_as_admin() is False


def test_is_running_as_admin_returns_false_when_windows_api_fails(monkeypatch):
    monkeypatch.setattr(privileges.sys, "platform", "win32")
    monkeypatch.setattr(privileges.ctypes, "windll", types.SimpleNamespace(shell32=object()), raising=False)

    assert privileges.is_running_as_admin() is False


def test_is_running_as_admin_uses_windows_shell_api(monkeypatch):
    class Shell32:
        @staticmethod
        def IsUserAnAdmin():
            return 1

    monkeypatch.setattr(privileges.sys, "platform", "win32")
    monkeypatch.setattr(privileges.ctypes, "windll", types.SimpleNamespace(shell32=Shell32()), raising=False)

    assert privileges.is_running_as_admin() is True
