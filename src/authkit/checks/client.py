from __future__ import annotations

import json
import os
import shutil
from authkit.platform.subprocess import run_hidden
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _run_version(command: list[str], *, timeout: int = 10) -> str:
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
        output = ((completed.stdout or "") + (completed.stderr or "")).strip()
        return output.splitlines()[0][:160] if output else ""
    except Exception:
        return ""


def _run_diagnostic(command: list[str], *, keywords: tuple[str, ...], timeout: int = 45) -> dict[str, Any]:
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
        output = (completed.stdout or "") + (completed.stderr or "")
        return {
            "exit_code": completed.returncode,
            "summary": _extract_lines(output, keywords),
            "ran": True,
        }
    except Exception as exc:  # noqa: BLE001
        return {"exit_code": None, "summary": str(exc), "ran": False}


def _skipped_fast_scan() -> dict[str, Any]:
    return {"ran": False, "summary": "skipped in fast scan", "exit_code": None, "skipped_reason": "fast_scan"}


def _skipped_manual_doctor() -> dict[str, Any]:
    return {
        "ran": False,
        "summary": "skipped by AuthKit; run claude doctor manually only when the built-in checks are inconclusive",
        "exit_code": None,
        "skipped_reason": "manual_only",
    }


def _npm_claude_target_present(claude_exe: str | None) -> bool | None:
    if not claude_exe:
        return None
    path = Path(claude_exe)
    npm_root = path.parent
    if npm_root.name.lower() != "npm":
        return None
    return (npm_root / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe").is_file()


def check_codex(*, fast: bool = False) -> dict[str, Any]:
    home = Path(os.environ.get("USERPROFILE", "")) / ".codex"
    auth_file = home / "auth.json"
    config_file = home / "config.toml"
    codex_bins = list((Path(os.environ.get("LOCALAPPDATA", "")) / "OpenAI" / "Codex" / "bin").glob("*/codex.exe"))
    codex_exe = codex_bins[0] if codex_bins else shutil.which("codex")

    doctor_summary = ""
    doctor_ok = None
    if codex_exe:
        if fast:
            doctor_summary = "skipped in fast scan"
        else:
            try:
                completed = run_hidden(
                    [str(codex_exe), "doctor"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=45,
                    check=False,
                )
                output = (completed.stdout or "") + (completed.stderr or "")
                doctor_summary = _extract_doctor_lines(output)
                doctor_ok = "reachability" in output and "active provider endpoints are reachable" in output
            except Exception as exc:  # noqa: BLE001
                doctor_summary = f"运行 codex doctor 失败: {exc}"

    return {
        "installed": bool(codex_exe),
        "codex_exe": str(codex_exe) if codex_exe else "",
        "auth_present": auth_file.is_file(),
        "config_present": config_file.is_file(),
        "doctor_ok": doctor_ok,
        "doctor_summary": doctor_summary,
        "fast_scan": fast,
        "login_hint": "若浏览器能登录但 Desktop 失败，通常是 Codex 后端未走正确代理。修复后请完全退出并重启 Codex。",
    }


def check_cursor(*, fast: bool = False) -> dict[str, Any]:
    appdata = Path(os.environ.get("APPDATA", ""))
    settings = _read_json(appdata / "Cursor" / "User" / "settings.json")
    return {
        "installed": (appdata / "Cursor").exists(),
        "http_proxy": settings.get("http.proxy"),
        "http_no_proxy": settings.get("http.noProxy"),
        "proxy_support": settings.get("http.proxySupport"),
        "run_in_wsl": settings.get("chatgpt.runCodexInWindowsSubsystemForLinux"),
        "fast_scan": fast,
        "login_hint": "若启用 WSL 运行 Codex 且 1455 被 wslrelay 占用，请关闭该设置后重试登录。",
    }


def check_vscode(*, fast: bool = False) -> dict[str, Any]:
    appdata = Path(os.environ.get("APPDATA", ""))
    settings = _read_json(appdata / "Code" / "User" / "settings.json")
    return {
        "installed": (appdata / "Code").exists(),
        "http_proxy": settings.get("http.proxy"),
        "http_no_proxy": settings.get("http.noProxy"),
        "proxy_support": settings.get("http.proxySupport"),
        "fast_scan": fast,
    }


def check_claude(*, fast: bool = False) -> dict[str, Any]:
    home = Path(os.environ.get("USERPROFILE", ""))
    claude_exe = shutil.which("claude")
    settings_file = home / ".claude" / "settings.json"
    settings = _read_json(settings_file)
    doctor = _skipped_fast_scan() if fast and claude_exe else _skipped_manual_doctor()
    return {
        "support_level": "full",
        "installed": bool(claude_exe),
        "executable": claude_exe or "",
        "install_source": "npm_global" if claude_exe and Path(claude_exe).parent.name.lower() == "npm" else "path",
        "npm_target_present": _npm_claude_target_present(claude_exe),
        "version": "" if fast else (_run_version([claude_exe, "--version"], timeout=3) if claude_exe else ""),
        "settings_present": settings_file.is_file(),
        "settings_path": str(settings_file),
        "settings_keys": sorted(settings.keys())[:20],
        "env_http_proxy_present": bool(os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")),
        "env_https_proxy_present": bool(os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")),
        "env_no_proxy_present": bool(os.environ.get("NO_PROXY") or os.environ.get("no_proxy")),
        "env_anthropic_api_key_present": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "env_claude_oauth_present": bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")),
        "doctor": doctor,
        "fast_scan": fast,
        "login_hint": "Claude Code 支持代理、企业 CA 与 doctor 检查；如代理或证书改变，请重启终端后再运行 claude doctor。",
    }


def check_gemini(*, fast: bool = False) -> dict[str, Any]:
    home = Path(os.environ.get("USERPROFILE", ""))
    gemini_exe = shutil.which("gemini")
    settings_candidates = [
        home / ".gemini" / "settings.json",
        home / ".config" / "gemini" / "settings.json",
    ]
    settings_file = next((path for path in settings_candidates if path.is_file()), settings_candidates[0])
    settings = _read_json(settings_file)
    return {
        "support_level": "beta_full",
        "installed": bool(gemini_exe),
        "executable": gemini_exe or "",
        "version": "" if fast else (_run_version([gemini_exe, "--version"]) if gemini_exe else ""),
        "settings_present": settings_file.is_file(),
        "settings_path": str(settings_file),
        "settings_keys": sorted(settings.keys())[:20],
        "env_http_proxy_present": bool(os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")),
        "env_https_proxy_present": bool(os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")),
        "env_no_proxy_present": bool(os.environ.get("NO_PROXY") or os.environ.get("no_proxy")),
        "env_gemini_api_key_present": bool(os.environ.get("GEMINI_API_KEY")),
        "env_google_api_key_present": bool(os.environ.get("GOOGLE_API_KEY")),
        "env_google_application_credentials_present": bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")),
        "fast_scan": fast,
        "login_hint": "Gemini CLI 支持 OAuth 与 API Key 两类凭据；如使用企业代理，请确认 HTTPS_PROXY/NO_PROXY 在启动终端前已生效。",
    }


def _extract_doctor_lines(output: str) -> str:
    return _extract_lines(output, ("auth", "reachability", "websocket", "proxy", "fail", "ok"))


def _extract_lines(output: str, keywords: tuple[str, ...]) -> str:
    interesting = []
    for line in output.splitlines():
        stripped = line.strip()
        if any(key in stripped.lower() for key in keywords):
            interesting.append(stripped)
    return "\n".join(interesting[:12])


def check_client(client: str, *, fast: bool = False) -> dict[str, Any]:
    if client == "codex":
        return check_codex(fast=fast)
    if client == "claude":
        return check_claude(fast=fast)
    if client == "gemini":
        return check_gemini(fast=fast)
    if client == "cursor":
        return check_cursor(fast=fast)
    if client == "vscode":
        return check_vscode(fast=fast)
    return {
        "codex": check_codex(fast=fast),
        "claude": check_claude(fast=fast),
        "gemini": check_gemini(fast=fast),
        "cursor": check_cursor(fast=fast),
        "vscode": check_vscode(fast=fast),
    }
