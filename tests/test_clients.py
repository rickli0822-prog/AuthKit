from authkit.checks.client import _read_json, check_claude, check_cursor
from authkit import cli
from authkit.cli import build_parser
from authkit.clients import CLIENT_CHOICES, CLIENT_LABELS, FULL_DIAGNOSTIC_CLIENTS, installed_clients


def test_client_registry_includes_new_full_clients():
    assert "claude" in CLIENT_CHOICES
    assert "gemini" in CLIENT_CHOICES
    assert CLIENT_LABELS["claude"] == "Claude Code"
    assert {"codex", "claude", "gemini"}.issubset(FULL_DIAGNOSTIC_CLIENTS)


def test_cli_accepts_new_clients():
    parser = build_parser()
    args = parser.parse_args(["check", "--client", "claude"])
    assert args.client == "claude"
    args = parser.parse_args(["login-status", "--client", "gemini"])
    assert args.client == "gemini"
    args = parser.parse_args(["scan", "--json"])
    assert args.command == "scan"
    assert args.json is True
    args = parser.parse_args(["ca", "--client", "codex", "--cert", r"C:\corp-ca.pem", "--apply"])
    assert args.command == "ca"
    assert args.client == "codex"
    assert args.cert == r"C:\corp-ca.pem"
    assert args.apply is True
    args = parser.parse_args(["dns", "--flush", "--apply"])
    assert args.command == "dns"
    assert args.flush is True
    args = parser.parse_args(["winsock", "--reset", "--apply"])
    assert args.command == "winsock"
    assert args.reset is True
    args = parser.parse_args(["firewall", "--allow-outbound", "--client", "codex", "--program", r"C:\Tools\codex.exe", "--apply"])
    assert args.command == "firewall"
    assert args.allow_outbound is True
    assert args.program == r"C:\Tools\codex.exe"
    args = parser.parse_args(["firewall"])
    assert args.command == "firewall"
    assert args.program is None
    args = parser.parse_args(["firewall", "--allow-outbound"])
    assert args.command == "firewall"
    assert args.allow_outbound is True
    assert args.program is None
    args = parser.parse_args(["audit", "--json", "--limit", "5", "--raw"])
    assert args.command == "audit"
    assert args.json is True
    assert args.limit == 5
    assert args.raw is True
    args = parser.parse_args(["rollback", "--preview"])
    assert args.command == "rollback"
    assert args.preview is True
    assert args.apply is False
    args = parser.parse_args(
        ["bundle", "--client", "claude", "--out", r"C:\Temp\authkit-bundle.json", "--audit-limit", "7", "--fast"]
    )
    assert args.command == "bundle"
    assert args.client == "claude"
    assert args.out == r"C:\Temp\authkit-bundle.json"
    assert args.audit_limit == 7
    assert args.fast is True

    validate_args = parser.parse_args(["bundle", "--validate", r"C:\Temp\authkit-bundle.json"])
    assert validate_args.command == "bundle"
    assert validate_args.validate == r"C:\Temp\authkit-bundle.json"
    assert validate_args.out is None

    sample_args = parser.parse_args(["bundle", "--sample", "--out", r"C:\Temp\sample-bundle.json"])
    assert sample_args.command == "bundle"
    assert sample_args.sample is True
    assert sample_args.out == r"C:\Temp\sample-bundle.json"


def test_cli_firewall_missing_program_returns_clear_error(monkeypatch, capsys):
    monkeypatch.setattr(cli.sys, "platform", "win32")
    monkeypatch.setattr(cli, "apply_direct_repair", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected repair")))

    code = cli.main(["firewall", "--allow-outbound", "--apply"])

    assert code == 1
    assert "Specify --program" in capsys.readouterr().out


def test_installed_clients_detects_known_app_dirs(monkeypatch, tmp_path):
    appdata = tmp_path / "AppData" / "Roaming"
    local_appdata = tmp_path / "AppData" / "Local"
    (appdata / "Cursor").mkdir(parents=True)
    (local_appdata / "OpenAI" / "Codex" / "bin" / "1.0.0").mkdir(parents=True)
    (local_appdata / "OpenAI" / "Codex" / "bin" / "1.0.0" / "codex.exe").write_text("", encoding="utf-8")

    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))
    monkeypatch.setenv("PATH", "")

    clients = installed_clients()

    assert "codex" in clients
    assert "cursor" in clients


def test_read_json_and_cursor_settings(monkeypatch, tmp_path):
    appdata = tmp_path / "AppData" / "Roaming"
    settings = appdata / "Cursor" / "User" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text('{"http.proxy": "http://127.0.0.1:7890"}', encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(appdata))

    assert _read_json(settings)["http.proxy"] == "http://127.0.0.1:7890"
    assert check_cursor(fast=True)["http_proxy"] == "http://127.0.0.1:7890"


def test_claude_check_skips_external_doctor_by_default(monkeypatch, tmp_path):
    claude = tmp_path / "claude.cmd"
    claude.write_text("@echo off\n", encoding="utf-8")
    monkeypatch.setattr("shutil.which", lambda command: str(claude) if command == "claude" else None)
    monkeypatch.setattr("authkit.checks.client._run_version", lambda *_args, **_kwargs: "claude 1.0.0")

    result = check_claude()

    assert result["installed"] is True
    assert result["version"] == "claude 1.0.0"
    assert result["doctor"]["ran"] is False
    assert result["doctor"]["skipped_reason"] == "manual_only"
