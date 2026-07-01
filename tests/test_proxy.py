from authkit.models import ProxyEndpoint
from authkit.platform import proxy
from authkit.platform.proxy import parse_proxy_url


def test_parse_proxy_url_http():
    endpoint = parse_proxy_url("http://127.0.0.1:7890")
    assert endpoint.host == "127.0.0.1"
    assert endpoint.port == 7890
    assert endpoint.url == "http://127.0.0.1:7890"


def test_parse_proxy_url_with_trailing_slash():
    endpoint = parse_proxy_url("http://127.0.0.1:7890/")
    assert endpoint.port == 7890


def test_parse_empty_proxy():
    endpoint = parse_proxy_url("")
    assert not endpoint.is_set


def test_set_system_proxy_writes_wininet_values(monkeypatch):
    writes = []

    class FakeKey:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(proxy.winreg, "OpenKey", lambda *args: FakeKey())
    monkeypatch.setattr(proxy.winreg, "SetValueEx", lambda _key, name, _reserved, kind, value: writes.append((name, kind, value)))
    monkeypatch.setattr(proxy, "notify_system_proxy_changed", lambda: True)

    changed = proxy.set_system_proxy(ProxyEndpoint("http", "127.0.0.1", 7890), override="localhost;<local>")

    assert changed == ["ProxyEnable", "ProxyServer", "ProxyOverride", "WinINETRefresh"]
    assert ("ProxyEnable", proxy.winreg.REG_DWORD, 1) in writes
    assert ("ProxyServer", proxy.winreg.REG_SZ, "127.0.0.1:7890") in writes
    assert ("ProxyOverride", proxy.winreg.REG_SZ, "localhost;<local>") in writes


def test_set_system_proxy_reports_refresh_failure(monkeypatch):
    class FakeKey:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(proxy.winreg, "OpenKey", lambda *args: FakeKey())
    monkeypatch.setattr(proxy.winreg, "SetValueEx", lambda *_args: None)
    monkeypatch.setattr(proxy, "notify_system_proxy_changed", lambda: False)

    changed = proxy.set_system_proxy(ProxyEndpoint("http", "127.0.0.1", 7890), override=None)

    assert changed == ["ProxyEnable", "ProxyServer", "WinINETRefreshFailed"]


def test_restore_system_proxy_writes_snapshot(monkeypatch):
    writes = []

    class FakeKey:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(proxy.winreg, "OpenKey", lambda *args: FakeKey())
    monkeypatch.setattr(proxy.winreg, "SetValueEx", lambda _key, name, _reserved, kind, value: writes.append((name, kind, value)))
    monkeypatch.setattr(proxy, "notify_system_proxy_changed", lambda: True)

    changed = proxy.restore_system_proxy(
        {
            "enabled": False,
            "server": "127.0.0.1:7890",
            "override": "localhost;<local>",
        }
    )

    assert changed == ["ProxyEnable", "ProxyServer", "ProxyOverride", "WinINETRefresh"]
    assert ("ProxyEnable", proxy.winreg.REG_DWORD, 0) in writes
    assert ("ProxyServer", proxy.winreg.REG_SZ, "127.0.0.1:7890") in writes
    assert ("ProxyOverride", proxy.winreg.REG_SZ, "localhost;<local>") in writes


def test_restore_user_env_proxy_writes_and_deletes(monkeypatch):
    writes = []
    deletes = []

    monkeypatch.setattr(proxy, "_write_user_env", lambda name, value: writes.append((name, value)))
    monkeypatch.setattr(proxy, "_delete_user_env", lambda name: deletes.append(name) or name == "HTTPS_PROXY")

    changed = proxy.restore_user_env_proxy({"HTTP_PROXY": "http://127.0.0.1:7890", "HTTPS_PROXY": None})

    assert ("HTTP_PROXY", "http://127.0.0.1:7890") in writes
    assert "HTTPS_PROXY" in deletes
    assert changed == ["HTTP_PROXY", "HTTPS_PROXY"]
