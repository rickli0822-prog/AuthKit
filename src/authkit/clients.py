from __future__ import annotations

import os
import shutil
from pathlib import Path

CLIENT_LABELS = {
    "codex": "Codex",
    "claude": "Claude Code",
    "gemini": "Gemini CLI",
    "cursor": "Cursor",
    "vscode": "VS Code",
}

CLIENT_CHOICES = tuple(CLIENT_LABELS)

FULL_DIAGNOSTIC_CLIENTS = {"codex", "claude", "gemini"}


def is_client_installed(client: str) -> bool:
    local_appdata = Path(os.environ.get("LOCALAPPDATA", ""))
    appdata = Path(os.environ.get("APPDATA", ""))

    if client == "codex":
        codex_bins = list((local_appdata / "OpenAI" / "Codex" / "bin").glob("*/codex.exe"))
        return bool(codex_bins or shutil.which("codex"))
    if client == "claude":
        return bool(shutil.which("claude"))
    if client == "gemini":
        return bool(shutil.which("gemini"))
    if client == "cursor":
        return (appdata / "Cursor").exists()
    if client == "vscode":
        return bool((appdata / "Code").exists() or shutil.which("code"))
    return False


def installed_clients() -> list[str]:
    return [client for client in CLIENT_CHOICES if is_client_installed(client)]
