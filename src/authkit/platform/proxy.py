from __future__ import annotations

import os
import re
import sys
import ctypes

from authkit.models import ProxyEndpoint

if sys.platform != "win32":
    raise RuntimeError("authkit（AuthKit）当前仅支持 Windows")

import winreg  # noqa: E402


PROXY_ENV_NAMES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "http_proxy",
    "https_proxy",
    "ALL_PROXY",
    "all_proxy",
    "NO_PROXY",
    "no_proxy",
)

DEFAULT_PROXY_OVERRIDE = "localhost;127.0.0.1;<local>"
INTERNET_SETTINGS_KEY = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"


def parse_proxy_url(value: str | None) -> ProxyEndpoint:
    if not value:
        return ProxyEndpoint()
    raw = value.strip()
    match = re.match(r"^(https?|socks5h?)://([^:/]+):(\d+)/?$", raw, re.IGNORECASE)
    if not match:
        return ProxyEndpoint(raw=raw)
    scheme, host, port = match.groups()
    return ProxyEndpoint(scheme=scheme.lower(), host=host, port=int(port), raw=raw)


def read_system_proxy() -> dict[str, object]:
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        INTERNET_SETTINGS_KEY,
    ) as key:
        enabled = bool(winreg.QueryValueEx(key, "ProxyEnable")[0])
        server = str(winreg.QueryValueEx(key, "ProxyServer")[0] or "")
        override = str(winreg.QueryValueEx(key, "ProxyOverride")[0] or "")
    endpoint = _parse_wininet_server(server) if enabled and server else ProxyEndpoint()
    return {
        "enabled": enabled,
        "server": server,
        "endpoint": endpoint,
        "override": override,
        "bypass_localhost": _bypasses_localhost(override),
    }


def set_system_proxy(endpoint: ProxyEndpoint, *, override: str | None = DEFAULT_PROXY_OVERRIDE) -> list[str]:
    if not endpoint.is_set:
        raise ValueError("Cannot write an empty system proxy endpoint")
    changed = ["ProxyEnable", "ProxyServer"]
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        INTERNET_SETTINGS_KEY,
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, f"{endpoint.host}:{endpoint.port}")
        if override is not None:
            winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ, override)
            changed.append("ProxyOverride")
    if notify_system_proxy_changed():
        changed.append("WinINETRefresh")
    else:
        changed.append("WinINETRefreshFailed")
    return changed


def restore_system_proxy(snapshot: dict[str, object]) -> list[str]:
    enabled = 1 if bool(snapshot.get("enabled")) else 0
    server = str(snapshot.get("server") or "")
    override = str(snapshot.get("override") or "")
    changed = ["ProxyEnable", "ProxyServer", "ProxyOverride"]
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        INTERNET_SETTINGS_KEY,
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, enabled)
        winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, server)
        winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ, override)
    if notify_system_proxy_changed():
        changed.append("WinINETRefresh")
    else:
        changed.append("WinINETRefreshFailed")
    return changed


def notify_system_proxy_changed() -> bool:
    try:
        internet_set_option = ctypes.windll.wininet.InternetSetOptionW
        settings_changed = internet_set_option(0, 39, 0, 0)
        refresh = internet_set_option(0, 37, 0, 0)
        return bool(settings_changed and refresh)
    except (AttributeError, OSError):
        return False


def _parse_wininet_server(server: str) -> ProxyEndpoint:
    # 常见格式: 127.0.0.1:7890 或 http=127.0.0.1:7890;https=127.0.0.1:7890
    if "=" in server:
        for part in server.split(";"):
            if part.lower().startswith("http=") or part.lower().startswith("https="):
                host_port = part.split("=", 1)[1]
                host, _, port = host_port.partition(":")
                if host and port.isdigit():
                    return ProxyEndpoint("http", host, int(port), server)
    host, _, port = server.partition(":")
    if host and port.isdigit():
        return ProxyEndpoint("http", host, int(port), server)
    return ProxyEndpoint(raw=server)


def _bypasses_localhost(override: str) -> bool:
    tokens = {item.strip().lower() for item in override.split(";") if item.strip()}
    required = {"localhost", "127.0.0.1", "<local>"}
    return bool(required & tokens) or any(token.startswith("127.") for token in tokens)


def read_env_proxy(scope: str = "process") -> dict[str, str | None]:
    values: dict[str, str | None] = {}
    if scope == "user":
        for name in PROXY_ENV_NAMES:
            values[name] = os.environ.get(name) or _read_user_env(name)
    else:
        for name in PROXY_ENV_NAMES:
            values[name] = os.environ.get(name)
    return values


def _read_user_env(name: str) -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value) if value else None
    except OSError:
        return None


def primary_env_proxy(env: dict[str, str | None]) -> ProxyEndpoint:
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        endpoint = parse_proxy_url(env.get(name))
        if endpoint.is_set:
            return endpoint
    return ProxyEndpoint()


def set_user_no_proxy(value: str) -> list[str]:
    changed: list[str] = []
    for name in ("NO_PROXY", "no_proxy"):
        _write_user_env(name, value)
        changed.append(name)
    return changed


def set_user_env_proxy(endpoint: ProxyEndpoint, no_proxy: str | None = None) -> list[str]:
    if not endpoint.is_set:
        raise ValueError("无法同步空的代理地址")
    url = endpoint.url
    changed: list[str] = []
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        _write_user_env(name, url)
        changed.append(name)
    if no_proxy is not None:
        changed.extend(set_user_no_proxy(no_proxy))
    return changed


def clear_user_env_proxy() -> list[str]:
    cleared: list[str] = []
    for name in PROXY_ENV_NAMES:
        if _delete_user_env(name):
            cleared.append(name)
    return cleared


def restore_user_env_proxy(snapshot: dict[str, str | None]) -> list[str]:
    changed: list[str] = []
    for name in PROXY_ENV_NAMES:
        value = snapshot.get(name)
        if value:
            _write_user_env(name, str(value))
            changed.append(name)
        elif _delete_user_env(name):
            changed.append(name)
    return changed


def set_user_env_values(values: dict[str, str]) -> list[str]:
    changed: list[str] = []
    for name, value in values.items():
        _write_user_env(name, value)
        changed.append(name)
    return changed


def read_user_env_values(names: tuple[str, ...]) -> dict[str, str | None]:
    return {name: os.environ.get(name) or _read_user_env(name) for name in names}


def restore_user_env_values(snapshot: dict[str, str | None]) -> list[str]:
    changed: list[str] = []
    for name, value in snapshot.items():
        if value:
            _write_user_env(name, str(value))
            changed.append(name)
        elif _delete_user_env(name):
            changed.append(name)
    return changed


def _write_user_env(name: str, value: str) -> None:
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        "Environment",
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_EXPAND_SZ, value)


def _delete_user_env(name: str) -> bool:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            "Environment",
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.DeleteValue(key, name)
        return True
    except OSError:
        return False


def format_env_snapshot(env: dict[str, str | None]) -> dict[str, str]:
    return {name: value for name, value in env.items() if value}
