import json
import sqlite3
from pathlib import Path

from authkit.checks.login import check_login_status, _find_token_keys, _inspect_auth_file
from authkit.checks.network import analyze_callback_ports, format_port_line


def test_find_token_keys_nested():
    data = {"tokens": {"access_token": "abc", "meta": {"refresh_token": ""}}}
    keys = _find_token_keys(data)
    assert "tokens.access_token" in keys
    assert "tokens.meta.refresh_token" not in keys


def test_inspect_auth_file_valid(tmp_path: Path):
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({"access_token": "secret", "user": "u"}), encoding="utf-8")
    info = _inspect_auth_file(auth)
    assert info["exists"] is True
    assert info["looks_valid"] is True
    assert "access_token" in info["token_keys"]


def test_inspect_auth_file_missing(tmp_path: Path):
    info = _inspect_auth_file(tmp_path / "missing.json")
    assert info["exists"] is False
    assert info["looks_valid"] is False


def test_check_login_status_codex_missing(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    status = check_login_status("codex")
    assert status.logged_in is False
    assert "未登录" in status.summary


def test_check_login_status_codex_missing_english(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    status = check_login_status("codex", locale="en")
    assert status.logged_in is False
    assert "Not signed in" in status.summary


def test_check_login_status_claude_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    status = check_login_status("claude", locale="en")
    assert status.logged_in is True
    assert status.details["env_api_key_present"] is True
    assert "secret" not in str(status.to_dict())


def test_check_login_status_gemini_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "secret")
    status = check_login_status("gemini", locale="en")
    assert status.logged_in is True
    assert status.details["env_gemini_api_key_present"] is True
    assert "secret" not in str(status.to_dict())


def test_check_login_status_cursor_running_is_in_app_check(monkeypatch, tmp_path: Path):
    appdata = tmp_path / "AppData" / "Roaming"
    settings = appdata / "Cursor" / "User" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setattr(
        "authkit.checks.login._list_processes_by_name",
        lambda names: [{"name": "Cursor", "pid": 123, "path": r"C:\Users\Rick\AppData\Local\Programs\cursor\Cursor.exe"}],
    )

    status = check_login_status("cursor", locale="en")

    assert status.logged_in is False
    assert status.summary == "Cursor is running; confirm sign-in from the account UI"
    assert status.auth_path == str(settings)
    assert status.details["supported"] is False
    assert status.details["app_running"] is True
    assert status.details["settings_present"] is True


def test_check_login_status_cursor_state_db_credentials(monkeypatch, tmp_path: Path):
    appdata = tmp_path / "AppData" / "Roaming"
    state_db = appdata / "Cursor" / "User" / "globalStorage" / "state.vscdb"
    state_db.parent.mkdir(parents=True)
    conn = sqlite3.connect(state_db)
    try:
        conn.execute("create table ItemTable (key text primary key, value blob)")
        conn.execute("insert into ItemTable(key, value) values (?, ?)", ("cursorAuth/accessToken", "secret-access"))
        conn.execute("insert into ItemTable(key, value) values (?, ?)", ("cursorAuth/cachedEmail", "rick@example.com"))
        conn.commit()
    finally:
        conn.close()
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setattr("authkit.checks.login._list_processes_by_name", lambda names: [])

    status = check_login_status("cursor", locale="en")

    assert status.logged_in is True
    assert status.summary == "Cursor local sign-in credentials were detected"
    assert status.auth_path == str(state_db)
    assert status.details["supported"] is True
    assert status.details["state_db"]["access_token_present"] is True
    assert status.details["state_db"]["cached_email_present"] is True
    assert "secret-access" not in str(status.to_dict())
    assert "rick@example.com" not in str(status.to_dict())


def test_analyze_callback_ports_conflict():
    port_infos = [
        {
            "port": 1455,
            "listening": True,
            "summary": ":1455 wslrelay(PID 1)",
            "listeners": [{"ProcessName": "wslrelay", "OwningProcess": 1, "hint": "WSL", "role": "conflict"}],
        },
        {"port": 1457, "listening": False, "summary": ":1457 空闲", "listeners": []},
    ]
    conflict, summary = analyze_callback_ports(port_infos)
    assert conflict is True
    assert "1455 被非 Codex 进程占用" in summary


def test_analyze_callback_ports_conflict_english():
    port_infos = [
        {
            "port": 1455,
            "listening": True,
            "summary": ":1455 wslrelay(PID 1)",
            "listeners": [{"ProcessName": "wslrelay", "OwningProcess": 1, "hint": "WSL", "role": "conflict"}],
        }
    ]
    conflict, summary = analyze_callback_ports(port_infos, locale="en")
    assert conflict is True
    assert "non-Codex process" in summary


def test_analyze_callback_ports_codex_ok():
    port_infos = [
        {
            "port": 1455,
            "listening": True,
            "summary": ":1455 codex(PID 9)",
            "listeners": [{"ProcessName": "codex", "OwningProcess": 9, "hint": "", "role": "codex"}],
        },
    ]
    conflict, _ = analyze_callback_ports(port_infos)
    assert conflict is False


def test_format_port_line_with_hint():
    line = format_port_line(
        1455,
        [{"ProcessName": "wslrelay", "OwningProcess": 42, "hint": "WSL 转发"}],
    )
    assert "wslrelay" in line
    assert "WSL 转发" in line
