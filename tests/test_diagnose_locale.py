import pytest

from authkit.checks.login import LoginStatus
from authkit.core import diagnose
from authkit.models import ProxyEndpoint
from authkit.report import render_human


@pytest.fixture(autouse=True)
def stub_network_profile(monkeypatch):
    monkeypatch.setattr(
        diagnose,
        "collect_network_profile",
        lambda **_kwargs: {
            "public_ip": "203.0.113.10",
            "score": 90,
            "quality": "good",
            "summary": "IP 203.0.113.10 | geo | ISP | score 90 good | AI endpoints reachable",
        },
    )


def test_run_diagnosis_english_text(monkeypatch):
    empty_endpoint = ProxyEndpoint()

    monkeypatch.setattr(
        diagnose,
        "read_system_proxy",
        lambda: {
            "enabled": False,
            "server": "",
            "endpoint": empty_endpoint,
            "override": "",
            "bypass_localhost": True,
        },
    )
    monkeypatch.setattr(diagnose, "read_env_proxy", lambda _scope: {})
    monkeypatch.setattr(diagnose, "primary_env_proxy", lambda _env: empty_endpoint)
    monkeypatch.setattr(diagnose, "tcp_probe", lambda _host, _port: False)
    monkeypatch.setattr(diagnose, "probe_oauth_token", lambda _proxy, **_kwargs: {"ok": True})
    monkeypatch.setattr(diagnose, "probe_chatgpt_api", lambda _proxy, **_kwargs: {"ok": True})
    monkeypatch.setattr(
        diagnose,
        "summarize_port",
        lambda port, *, locale="zh", **_kwargs: {"port": port, "listening": False, "summary": f":{port} idle"},
    )
    monkeypatch.setattr(diagnose, "check_client", lambda _client, **_kwargs: {"supported": True})
    monkeypatch.setattr(
        diagnose,
        "check_login_status",
        lambda client, *, locale="zh": LoginStatus(
            client=client,
            logged_in=True,
            summary="Sign-in credentials detected",
            auth_path="",
            details={},
        ),
    )

    report = diagnose.run_diagnosis("codex", locale="en")
    rendered = render_human(report, locale="en")

    assert report.root_cause == "No obvious proxy/OAuth configuration issue was detected."
    assert report.layers[0].summary.startswith("System proxy:")
    assert "OAuth / ChatGPT endpoint connectivity check" in report.layers[2].summary
    online_layer = next(layer for layer in report.layers if layer.name == "online_session")
    assert online_layer.ok is True
    assert online_layer.details["mode"] == "online"
    assert online_layer.details["service_reachable"] is True
    assert "Platform:" in rendered
    assert "系统代理" not in rendered


def test_run_diagnosis_uses_claude_endpoint(monkeypatch):
    empty_endpoint = ProxyEndpoint()
    urls = []

    monkeypatch.setattr(
        diagnose,
        "read_system_proxy",
        lambda: {
            "enabled": False,
            "server": "",
            "endpoint": empty_endpoint,
            "override": "",
            "bypass_localhost": True,
        },
    )
    monkeypatch.setattr(diagnose, "read_env_proxy", lambda _scope: {})
    monkeypatch.setattr(diagnose, "primary_env_proxy", lambda _env: empty_endpoint)
    monkeypatch.setattr(diagnose, "tcp_probe", lambda _host, _port: False)
    monkeypatch.setattr(
        diagnose,
        "http_probe",
        lambda url, **_kwargs: urls.append(url) or {"ok": True},
    )
    monkeypatch.setattr(
        diagnose,
        "summarize_port",
        lambda port, *, locale="zh", **_kwargs: {"port": port, "listening": False, "summary": f":{port} idle"},
    )
    monkeypatch.setattr(diagnose, "check_client", lambda _client, **_kwargs: {"supported": True})
    monkeypatch.setattr(
        diagnose,
        "check_login_status",
        lambda client, *, locale="zh": LoginStatus(client=client, logged_in=True, summary="ok", auth_path="", details={}),
    )

    report = diagnose.run_diagnosis("claude", locale="en")

    assert "https://api.anthropic.com/v1/messages" in urls
    assert "https://api.anthropic.com/v1/models" in urls
    assert report.layers[2].summary == "Claude / Anthropic API endpoint connectivity check"


def test_run_diagnosis_includes_official_guidance(monkeypatch):
    empty_endpoint = ProxyEndpoint()

    monkeypatch.setattr(
        diagnose,
        "read_system_proxy",
        lambda: {
            "enabled": False,
            "server": "",
            "endpoint": empty_endpoint,
            "override": "",
            "bypass_localhost": True,
        },
    )
    monkeypatch.setattr(diagnose, "read_env_proxy", lambda _scope: {})
    monkeypatch.setattr(diagnose, "primary_env_proxy", lambda _env: empty_endpoint)
    monkeypatch.setattr(diagnose, "tcp_probe", lambda _host, _port: False)
    monkeypatch.setattr(diagnose, "probe_oauth_token", lambda _proxy, **_kwargs: {"ok": True})
    monkeypatch.setattr(diagnose, "probe_chatgpt_api", lambda _proxy, **_kwargs: {"ok": True})
    monkeypatch.setattr(
        diagnose,
        "summarize_port",
        lambda port, *, locale="zh", **_kwargs: {"port": port, "listening": False, "summary": f":{port} idle"},
    )
    monkeypatch.setattr(diagnose, "check_client", lambda _client, **_kwargs: {"supported": True})
    monkeypatch.setattr(
        diagnose,
        "check_login_status",
        lambda client, *, locale="zh": LoginStatus(client=client, logged_in=False, summary="missing", auth_path="", details={}),
    )

    report = diagnose.run_diagnosis("codex", locale="en")

    titles = [guidance.title for guidance in report.official_guidance]
    assert "Official path: recover Codex sign-in" in titles
    assert "Success loop: verify Codex" in titles
    assert any("codex login --device-auth" in step for guidance in report.official_guidance for step in guidance.steps)


def test_run_diagnosis_emits_progress_events(monkeypatch):
    empty_endpoint = ProxyEndpoint()

    monkeypatch.setattr(
        diagnose,
        "read_system_proxy",
        lambda: {
            "enabled": False,
            "server": "",
            "endpoint": empty_endpoint,
            "override": "",
            "bypass_localhost": True,
        },
    )
    monkeypatch.setattr(diagnose, "read_env_proxy", lambda _scope: {})
    monkeypatch.setattr(diagnose, "primary_env_proxy", lambda _env: empty_endpoint)
    monkeypatch.setattr(diagnose, "tcp_probe", lambda _host, _port, **_kwargs: False)
    monkeypatch.setattr(diagnose, "probe_oauth_token", lambda _proxy, **_kwargs: {"ok": True})
    monkeypatch.setattr(diagnose, "probe_chatgpt_api", lambda _proxy, **_kwargs: {"ok": True})
    monkeypatch.setattr(
        diagnose,
        "summarize_port",
        lambda port, *, locale="zh", **_kwargs: {"port": port, "listening": False, "summary": f":{port} idle"},
    )
    monkeypatch.setattr(diagnose, "check_client", lambda _client, **_kwargs: {"supported": True})
    monkeypatch.setattr(
        diagnose,
        "check_login_status",
        lambda client, *, locale="zh": LoginStatus(client=client, logged_in=True, summary="ok", auth_path="", details={}),
    )

    events = []
    diagnose.run_diagnosis("claude", locale="en", progress=events.append)

    assert events[0]["name"] == "system_proxy"
    assert events[0]["state"] == "running"
    assert any(event["name"] == "online_session" and event["state"] == "running" for event in events)
    assert any(event["name"] == "client_specific" and event["state"] == "running" for event in events)
    assert events[-1]["name"] == "finalize"
    assert events[-1]["state"] == "done"


def test_online_session_layer_reports_blocked_service(monkeypatch):
    empty_endpoint = ProxyEndpoint()

    monkeypatch.setattr(
        diagnose,
        "read_system_proxy",
        lambda: {
            "enabled": False,
            "server": "",
            "endpoint": empty_endpoint,
            "override": "",
            "bypass_localhost": True,
        },
    )
    monkeypatch.setattr(diagnose, "read_env_proxy", lambda _scope: {})
    monkeypatch.setattr(diagnose, "primary_env_proxy", lambda _env: empty_endpoint)
    monkeypatch.setattr(diagnose, "tcp_probe", lambda _host, _port, **_kwargs: False)
    monkeypatch.setattr(diagnose, "probe_oauth_token", lambda _proxy, **_kwargs: {"ok": False, "error": "timeout"})
    monkeypatch.setattr(diagnose, "probe_chatgpt_api", lambda _proxy, **_kwargs: {"ok": False, "error": "timeout"})
    monkeypatch.setattr(
        diagnose,
        "summarize_port",
        lambda port, *, locale="zh", **_kwargs: {"port": port, "listening": False, "summary": f":{port} idle"},
    )
    monkeypatch.setattr(diagnose, "check_client", lambda _client, **_kwargs: {"supported": True})
    monkeypatch.setattr(
        diagnose,
        "check_login_status",
        lambda client, *, locale="zh": LoginStatus(client=client, logged_in=True, summary="ok", auth_path="", details={}),
    )

    report = diagnose.run_diagnosis("codex", locale="en")
    online_layer = next(layer for layer in report.layers if layer.name == "online_session")

    assert online_layer.ok is False
    assert online_layer.details["service_reachable"] is False
    assert online_layer.details["probe_errors"]["oauth_via_env"] == "timeout"


def test_build_fixes_suggests_system_proxy_sync_when_env_proxy_is_reachable():
    fixes = diagnose._build_fixes(
        case=diagnose.FailureCase.NONE,
        system_endpoint=ProxyEndpoint(),
        env_endpoint=ProxyEndpoint("http", "127.0.0.1", 7890),
        system_alive=False,
        env_alive=True,
        system={"bypass_localhost": True},
        client="codex",
        logged_in=True,
        locale="en",
    )

    sync_fix = next(fix for fix in fixes if fix.fix_id == "sync-system-proxy")
    assert sync_fix.auto_applicable is True
    assert sync_fix.risk == "medium"
    assert "127.0.0.1:7890" in sync_fix.description


def test_build_fixes_system_proxy_sync_uses_chinese_description():
    fixes = diagnose._build_fixes(
        case=diagnose.FailureCase.NONE,
        system_endpoint=ProxyEndpoint(),
        env_endpoint=ProxyEndpoint("http", "127.0.0.1", 7890),
        system_alive=False,
        env_alive=True,
        system={"bypass_localhost": True},
        client="codex",
        logged_in=True,
        locale="zh",
    )

    sync_fix = next(fix for fix in fixes if fix.fix_id == "sync-system-proxy")
    assert "Windows 系统代理" in sync_fix.description
    assert "Sync the Windows system proxy" not in sync_fix.description


def test_build_fixes_suggests_dns_flush_for_weak_network_profile():
    fixes = diagnose._build_fixes(
        case=diagnose.FailureCase.UNKNOWN,
        system_endpoint=ProxyEndpoint(),
        env_endpoint=ProxyEndpoint(),
        system_alive=False,
        env_alive=False,
        system={"bypass_localhost": True},
        client="codex",
        logged_in=True,
        network_profile={"score": 45, "endpoint_reachable": False},
        locale="en",
    )

    dns_fix = next(fix for fix in fixes if fix.fix_id == "flush-dns-cache")
    assert dns_fix.auto_applicable is True
    assert dns_fix.risk == "low"
    assert dns_fix.command == "authkit dns --flush --apply"


def test_build_fixes_suggests_manual_winsock_reset_for_blocked_unknown_network():
    fixes = diagnose._build_fixes(
        case=diagnose.FailureCase.UNKNOWN,
        system_endpoint=ProxyEndpoint(),
        env_endpoint=ProxyEndpoint(),
        system_alive=False,
        env_alive=False,
        system={"bypass_localhost": True},
        client="codex",
        logged_in=True,
        network_profile={"score": 35, "endpoint_reachable": False},
        locale="en",
    )

    winsock_fix = next(fix for fix in fixes if fix.fix_id == "winsock-reset")
    assert winsock_fix.auto_applicable is False
    assert winsock_fix.risk == "medium"
    assert winsock_fix.admin_required is True
    assert winsock_fix.restart_required is True
    assert winsock_fix.rollback_supported is False
    assert winsock_fix.command == "authkit winsock --reset --apply"
    assert "restart required" in winsock_fix.description.lower()


def test_build_fixes_suggests_manual_firewall_allow_when_client_path_exists():
    fixes = diagnose._build_fixes(
        case=diagnose.FailureCase.UNKNOWN,
        system_endpoint=ProxyEndpoint(),
        env_endpoint=ProxyEndpoint(),
        system_alive=False,
        env_alive=False,
        system={"bypass_localhost": True},
        client="claude",
        logged_in=True,
        network_profile={"score": 35, "endpoint_reachable": False},
        client_info={"executable": r"C:\Tools\claude.exe"},
        locale="en",
    )

    firewall_fix = next(fix for fix in fixes if fix.fix_id == "allow-firewall-outbound")
    assert firewall_fix.auto_applicable is False
    assert firewall_fix.risk == "medium"
    assert firewall_fix.admin_required is True
    assert firewall_fix.restart_required is False
    assert firewall_fix.rollback_supported is False
    assert r'C:\Tools\claude.exe' in firewall_fix.description
    assert firewall_fix.command == 'authkit firewall --allow-outbound --client "claude" --program "C:\\Tools\\claude.exe" --apply'


def test_build_fixes_skips_firewall_allow_without_client_path():
    fixes = diagnose._build_fixes(
        case=diagnose.FailureCase.UNKNOWN,
        system_endpoint=ProxyEndpoint(),
        env_endpoint=ProxyEndpoint(),
        system_alive=False,
        env_alive=False,
        system={"bypass_localhost": True},
        client="claude",
        logged_in=True,
        network_profile={"score": 35, "endpoint_reachable": False},
        client_info={},
        locale="en",
    )

    assert "allow-firewall-outbound" not in {fix.fix_id for fix in fixes}


def test_build_fixes_tls_uses_client_level_ca_command():
    fixes = diagnose._build_fixes(
        case=diagnose.FailureCase.TLS_OR_CA,
        system_endpoint=ProxyEndpoint(),
        env_endpoint=ProxyEndpoint(),
        system_alive=False,
        env_alive=False,
        system={"bypass_localhost": True},
        client="claude",
        logged_in=True,
        network_profile={"score": 70, "endpoint_reachable": True},
        client_info={"executable": r"C:\Tools\claude.exe"},
        locale="en",
    )

    ca_fix = next(fix for fix in fixes if fix.fix_id == "configure-client-ca")
    assert ca_fix.auto_applicable is False
    assert ca_fix.risk == "medium"
    assert ca_fix.command == 'authkit ca --apply --client "claude" --cert "C:\\path\\to\\corp-ca.pem"'
    assert "without importing it into the system trust store" in ca_fix.description


def test_build_fixes_does_not_suggest_dns_flush_for_healthy_case():
    fixes = diagnose._build_fixes(
        case=diagnose.FailureCase.NONE,
        system_endpoint=ProxyEndpoint(),
        env_endpoint=ProxyEndpoint(),
        system_alive=False,
        env_alive=False,
        system={"bypass_localhost": True},
        client="codex",
        logged_in=True,
        network_profile={"score": 90, "endpoint_reachable": True},
        locale="en",
    )

    assert "flush-dns-cache" not in {fix.fix_id for fix in fixes}
    assert "winsock-reset" not in {fix.fix_id for fix in fixes}
    assert "allow-firewall-outbound" not in {fix.fix_id for fix in fixes}
