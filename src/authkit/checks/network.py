from __future__ import annotations

import json
import socket
import time
from authkit import __version__
from authkit.platform.subprocess import run_hidden
import urllib.error
import urllib.request
from typing import Any

from authkit.models import ProxyEndpoint


PROCESS_HINTS: dict[str, dict[str, str]] = {
    "zh": {
        "wslrelay": "WSL 中继，可能抢占 OAuth 回调",
        "Cursor": "Cursor 占用回调端口",
        "Code": "VS Code 占用回调端口",
        "codex": "Codex 监听中",
        "Codex": "Codex 监听中",
        "python": "本地 Python 服务",
        "pythonw": "本地 Python 服务",
    },
    "en": {
        "wslrelay": "WSL relay may capture the OAuth callback",
        "Cursor": "Cursor is using the callback port",
        "Code": "VS Code is using the callback port",
        "codex": "Codex is listening",
        "Codex": "Codex is listening",
        "python": "Local Python service",
        "pythonw": "Local Python service",
    },
}

CODEX_LISTENER_NAMES = {"codex", "Codex", "codex.exe"}
OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
CHATGPT_API_URL = "https://chatgpt.com/backend-api/"
CALLBACK_PORTS = (1455, 1457)


def tcp_probe(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def http_probe(
    url: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    proxy: ProxyEndpoint | None = None,
    timeout: float = 12.0,
) -> dict[str, Any]:
    started = time.monotonic()

    def with_latency(payload: dict[str, Any]) -> dict[str, Any]:
        return {**payload, "latency_ms": int((time.monotonic() - started) * 1000)}

    request_headers = {"User-Agent": f"authkit/{__version__}"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    handlers: list[urllib.request.BaseHandler] = []
    if proxy and proxy.is_set:
        handlers.append(
            urllib.request.ProxyHandler(
                {
                    "http": proxy.url,
                    "https": proxy.url,
                }
            )
        )
    opener = urllib.request.build_opener(*handlers)
    try:
        with opener.open(request, timeout=timeout) as response:
            return with_latency({
                "ok": True,
                "status": response.status,
                "reason": getattr(response, "reason", ""),
                "error": "",
            })
    except urllib.error.HTTPError as exc:
        # OAuth token 端点对无效请求返回 400/401/403 仍表示网络可达
        return with_latency({
            "ok": exc.code in (400, 401, 403, 405, 415),
            "status": exc.code,
            "reason": exc.reason,
            "error": str(exc),
        })
    except Exception as exc:  # noqa: BLE001 - 需要汇总网络错误
        return with_latency({
            "ok": False,
            "status": None,
            "reason": "",
            "error": str(exc),
        })


def probe_oauth_token(proxy: ProxyEndpoint | None, *, timeout: float = 12.0) -> dict[str, Any]:
    body = b"grant_type=client_credentials"
    return http_probe(
        OAUTH_TOKEN_URL,
        method="POST",
        body=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        proxy=proxy,
        timeout=timeout,
    )


def probe_chatgpt_api(proxy: ProxyEndpoint | None, *, timeout: float = 12.0) -> dict[str, Any]:
    return http_probe(CHATGPT_API_URL, method="HEAD", proxy=proxy, timeout=timeout)


def list_port_listeners(port: int, *, timeout: int = 8) -> list[dict[str, Any]]:
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        (
            f"$conns = Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue; "
            "if (-not $conns) { '[]' } else { "
            "$conns | ForEach-Object { "
            "[PSCustomObject]@{ LocalAddress=$_.LocalAddress; OwningProcess=$_.OwningProcess; "
            "ProcessName=(Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue).ProcessName } "
            "} | ConvertTo-Json -Compress }"
        ),
    ]
    try:
        completed = run_hidden(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        raw = (completed.stdout or "").strip()
        if not raw:
            return []
        data = json.loads(raw)
        if isinstance(data, dict):
            return [data]
        return list(data)
    except Exception:
        return []


def summarize_port(port: int, *, locale: str = "zh", timeout: int = 8) -> dict[str, Any]:
    listeners = list_port_listeners(port, timeout=timeout)
    enriched = [annotate_listener(item, locale=locale) for item in listeners]
    return {
        "port": port,
        "listening": bool(enriched),
        "listeners": enriched,
        "summary": format_port_line(port, enriched, locale=locale),
    }


def annotate_listener(listener: dict[str, Any], *, locale: str = "zh") -> dict[str, Any]:
    name = str(listener.get("ProcessName") or "")
    hint = PROCESS_HINTS.get(locale, PROCESS_HINTS["zh"]).get(name, "")
    role = "codex" if name in CODEX_LISTENER_NAMES else ("conflict" if hint else "other")
    return {**listener, "hint": hint, "role": role}


def format_port_line(port: int, listeners: list[dict[str, Any]], *, locale: str = "zh") -> str:
    if not listeners:
        return f":{port} " + ("idle" if locale == "en" else "空闲")
    parts: list[str] = []
    for item in listeners:
        name = item.get("ProcessName") or ("unknown" if locale == "en" else "未知")
        pid = item.get("OwningProcess") or "?"
        hint = item.get("hint") or ""
        text = f"{name}(PID {pid})"
        if hint:
            text += f" — {hint}"
        parts.append(text)
    return f":{port} " + "；".join(parts)


def analyze_callback_ports(port_infos: list[dict[str, Any]], *, locale: str = "zh") -> tuple[bool, str]:
    conflict = False
    lines: list[str] = []
    for info in port_infos:
        fallback = "unknown" if locale == "en" else "未知"
        lines.append(info.get("summary") or f":{info.get('port')} {fallback}")
        if info.get("port") == 1455 and info.get("listening"):
            names = {item.get("ProcessName", "") for item in info.get("listeners", [])}
            if names and not names.intersection(CODEX_LISTENER_NAMES):
                conflict = True
    summary = " | ".join(lines)
    if conflict:
        summary += " | " + (
            "1455 is used by a non-Codex process" if locale == "en" else "1455 被非 Codex 进程占用"
        )
    return conflict, summary
