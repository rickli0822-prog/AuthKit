"""登录状态快速检查（不发起网络探测）。"""

from __future__ import annotations

import json
import os
import subprocess
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from authkit.platform.subprocess import run_hidden


TOKEN_KEYS = (
    "access_token",
    "refresh_token",
    "id_token",
    "token",
    "api_key",
)


@dataclass
class LoginStatus:
    client: str
    logged_in: bool
    summary: str
    auth_path: str
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "client": self.client,
            "logged_in": self.logged_in,
            "summary": self.summary,
            "auth_path": self.auth_path,
            "details": self.details,
        }


def check_login_status(client: str, *, locale: str = "zh") -> LoginStatus:
    if client == "codex":
        return _check_codex_login(locale=locale)
    if client == "claude":
        return _check_claude_login(locale=locale)
    if client == "gemini":
        return _check_gemini_login(locale=locale)
    if client == "cursor":
        return _check_cursor_login(locale=locale)
    if client == "vscode":
        return LoginStatus(
            client=client,
            logged_in=False,
            summary=_text(locale, "vscode_in_app"),
            auth_path="",
            details={"supported": False},
        )
    return LoginStatus(client=client, logged_in=False, summary=_text(locale, "unknown_client"), auth_path="", details={})


def _check_codex_login(*, locale: str = "zh") -> LoginStatus:
    auth_path = Path(os.environ.get("USERPROFILE", "")) / ".codex" / "auth.json"
    details = _inspect_auth_file(auth_path)
    logged_in = details.get("looks_valid", False)

    if logged_in:
        summary = _text(locale, "codex_logged_in", modified_at=details.get("modified_at", _text(locale, "unknown")))
    elif auth_path.is_file():
        summary = _text(locale, "codex_invalid")
    else:
        summary = _text(locale, "codex_missing")

    return LoginStatus(
        client="codex",
        logged_in=logged_in,
        summary=summary,
        auth_path=str(auth_path),
        details=details,
    )


def _check_claude_login(*, locale: str = "zh") -> LoginStatus:
    home = Path(os.environ.get("USERPROFILE", ""))
    candidates = [
        home / ".claude" / ".credentials.json",
        home / ".claude" / "credentials.json",
        home / ".claude.json",
    ]
    existing = next((path for path in candidates if path.is_file()), None)
    env_present = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"))
    details = {
        "env_api_key_present": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "env_oauth_token_present": bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")),
        "candidate_paths": [str(path) for path in candidates],
    }
    if existing:
        details.update(_inspect_auth_file(existing))
        details["credential_path"] = str(existing)

    logged_in = env_present or bool(existing)
    if logged_in:
        summary = _text(locale, "claude_credentials_detected")
    else:
        summary = _text(locale, "claude_credentials_missing")
    return LoginStatus(
        client="claude",
        logged_in=logged_in,
        summary=summary,
        auth_path=str(existing) if existing else "",
        details=details,
    )


def _check_gemini_login(*, locale: str = "zh") -> LoginStatus:
    home = Path(os.environ.get("USERPROFILE", ""))
    candidates = [
        home / ".gemini" / "oauth_creds.json",
        home / ".gemini" / "credentials.json",
        home / ".config" / "gemini" / "oauth_creds.json",
    ]
    existing = next((path for path in candidates if path.is_file()), None)
    google_credentials = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    env_present = bool(
        os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or (google_credentials and Path(google_credentials).is_file())
    )
    details = {
        "env_gemini_api_key_present": bool(os.environ.get("GEMINI_API_KEY")),
        "env_google_api_key_present": bool(os.environ.get("GOOGLE_API_KEY")),
        "google_application_credentials_present": bool(google_credentials),
        "google_application_credentials_file_exists": bool(google_credentials and Path(google_credentials).is_file()),
        "candidate_paths": [str(path) for path in candidates],
    }
    if existing:
        details.update(_inspect_auth_file(existing))
        details["credential_path"] = str(existing)

    logged_in = env_present or bool(existing)
    if logged_in:
        summary = _text(locale, "gemini_credentials_detected")
    else:
        summary = _text(locale, "gemini_credentials_missing")
    return LoginStatus(
        client="gemini",
        logged_in=logged_in,
        summary=summary,
        auth_path=str(existing) if existing else google_credentials,
        details=details,
    )


def _check_cursor_login(*, locale: str = "zh") -> LoginStatus:
    appdata = _cursor_appdata_dir()
    user_dir = appdata / "User" if appdata else None
    settings_path = user_dir / "settings.json" if user_dir else None
    state_db_path = user_dir / "globalStorage" / "state.vscdb" if user_dir else None
    storage_paths = [
        appdata / "Local Storage" if appdata else None,
        appdata / "Session Storage" if appdata else None,
        appdata / "Network" if appdata else None,
        user_dir,
    ]
    processes = _list_processes_by_name(("Cursor",))
    process_paths = sorted({str(item.get("path", "")) for item in processes if item.get("path")})
    state_details = _inspect_cursor_state_db(state_db_path) if state_db_path else {"exists": False, "logged_in": False}

    logged_in = bool(state_details.get("logged_in"))
    if logged_in:
        summary_key = "cursor_credentials_detected"
    else:
        summary_key = "cursor_running_in_app" if processes else "cursor_in_app"
    auth_path = str(state_db_path) if state_db_path and state_db_path.is_file() else str(settings_path) if settings_path and settings_path.is_file() else ""
    return LoginStatus(
        client="cursor",
        logged_in=logged_in,
        summary=_text(locale, summary_key),
        auth_path=auth_path,
        details={
            "supported": logged_in,
            "verification": "cursor_state_db" if logged_in else "in_app_required",
            "app_running": bool(processes),
            "process_count": len(processes),
            "process_paths": process_paths[:5],
            "appdata_present": bool(appdata and appdata.exists()),
            "settings_present": bool(settings_path and settings_path.is_file()),
            "state_db": state_details,
            "storage_present": any(path is not None and path.exists() for path in storage_paths),
        },
    )


def _cursor_appdata_dir() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "Cursor"


def _list_processes_by_name(names: tuple[str, ...]) -> list[dict[str, Any]]:
    names_literal = "@(" + ",".join(f"'{name}'" for name in names) + ")"
    command = (
        f"$names={names_literal}; "
        "Get-Process | Where-Object { $names -contains $_.ProcessName } | "
        "Select-Object ProcessName,Id,Path | ConvertTo-Json -Compress"
    )
    try:
        completed = run_hidden(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    raw = completed.stdout.strip()
    if completed.returncode != 0 or not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []

    processes: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        processes.append(
            {
                "name": item.get("ProcessName") or "",
                "pid": item.get("Id"),
                "path": item.get("Path") or "",
            }
        )
    return processes


def _inspect_cursor_state_db(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {"exists": False, "logged_in": False}

    auth_keys = (
        "cursorAuth/accessToken",
        "cursorAuth/refreshToken",
        "cursorAuth/cachedEmail",
        "cursorAuth/cachedScopedProfile",
    )
    optional_keys = (
        "cursorAuth/stripeMembershipType",
        "cursorAuth/stripeSubscriptionStatus",
        "cursorAuth/cachedSignUpType",
    )
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1)
        try:
            placeholders = ",".join("?" for _ in (*auth_keys, *optional_keys))
            rows = conn.execute(
                f"select key, length(value) from ItemTable where key in ({placeholders})",
                (*auth_keys, *optional_keys),
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return {"exists": True, "logged_in": False, "read_error": str(exc)}

    lengths = {str(key): int(length or 0) for key, length in rows}
    present_auth_keys = [key for key in auth_keys if lengths.get(key, 0) > 0]
    return {
        "exists": True,
        "logged_in": bool(present_auth_keys),
        "credential_markers": present_auth_keys,
        "access_token_present": lengths.get("cursorAuth/accessToken", 0) > 0,
        "refresh_token_present": lengths.get("cursorAuth/refreshToken", 0) > 0,
        "cached_email_present": lengths.get("cursorAuth/cachedEmail", 0) > 0,
        "cached_profile_present": lengths.get("cursorAuth/cachedScopedProfile", 0) > 0,
        "membership_marker_present": lengths.get("cursorAuth/stripeMembershipType", 0) > 0,
        "subscription_marker_present": lengths.get("cursorAuth/stripeSubscriptionStatus", 0) > 0,
    }


def _text(locale: str, key: str, **kwargs: object) -> str:
    catalog = {
        "zh": {
            "unknown": "未知",
            "cursor_in_app": "Cursor 登录状态需在应用内查看",
            "cursor_running_in_app": "Cursor 正在运行；登录状态需在应用内账号入口确认",
            "cursor_credentials_detected": "已检测到 Cursor 本地登录凭据",
            "vscode_in_app": "VS Code 登录状态需在扩展内查看",
            "unknown_client": "未知客户端",
            "codex_logged_in": "已检测到登录凭据（更新于 {modified_at}）",
            "codex_invalid": "auth.json 存在但内容无效或已损坏，建议重新登录",
            "codex_missing": "未登录（未找到 ~/.codex/auth.json）",
            "claude_credentials_detected": "已检测到 Claude Code 凭据或 API Key 环境变量",
            "claude_credentials_missing": "未检测到 Claude Code 凭据或 ANTHROPIC_API_KEY",
            "gemini_credentials_detected": "已检测到 Gemini 凭据或 API Key 环境变量",
            "gemini_credentials_missing": "未检测到 Gemini OAuth 凭据或 GEMINI_API_KEY / GOOGLE_API_KEY",
        },
        "en": {
            "unknown": "unknown",
            "cursor_in_app": "Open Cursor and confirm sign-in from the account UI",
            "cursor_running_in_app": "Cursor is running; confirm sign-in from the account UI",
            "cursor_credentials_detected": "Cursor local sign-in credentials were detected",
            "vscode_in_app": "Check VS Code sign-in status inside the extension",
            "unknown_client": "Unknown client",
            "codex_logged_in": "Sign-in credentials detected (updated at {modified_at})",
            "codex_invalid": "auth.json exists but is invalid or damaged. Sign in again.",
            "codex_missing": "Not signed in (~/.codex/auth.json was not found)",
            "claude_credentials_detected": "Claude Code credentials or API key environment variables were detected",
            "claude_credentials_missing": "Claude Code credentials or ANTHROPIC_API_KEY were not detected",
            "gemini_credentials_detected": "Gemini credentials or API key environment variables were detected",
            "gemini_credentials_missing": "Gemini OAuth credentials or GEMINI_API_KEY / GOOGLE_API_KEY were not detected",
        },
    }
    text = catalog.get(locale, catalog["zh"]).get(key, catalog["zh"].get(key, key))
    return text.format(**kwargs) if kwargs else text


def _inspect_auth_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"exists": False, "looks_valid": False}

    try:
        stat = path.stat()
        modified_at = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return {"exists": True, "looks_valid": False, "empty": True, "modified_at": modified_at}

        data = json.loads(raw)
        token_keys = _find_token_keys(data)
        looks_valid = bool(token_keys) and isinstance(data, (dict, list))
        return {
            "exists": True,
            "looks_valid": looks_valid,
            "modified_at": modified_at,
            "size_bytes": stat.st_size,
            "token_keys": token_keys,
            "top_level_keys": list(data.keys())[:12] if isinstance(data, dict) else [],
        }
    except (OSError, json.JSONDecodeError) as exc:
        return {"exists": True, "looks_valid": False, "parse_error": str(exc)}


def _find_token_keys(data: object, prefix: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(data, dict):
        for key, value in data.items():
            full = f"{prefix}.{key}" if prefix else str(key)
            lowered = str(key).lower()
            if any(token_key in lowered for token_key in TOKEN_KEYS):
                if value not in (None, "", {}):
                    found.append(full)
            found.extend(_find_token_keys(value, full))
    elif isinstance(data, list):
        for index, item in enumerate(data[:5]):
            found.extend(_find_token_keys(item, f"{prefix}[{index}]"))
    return found
