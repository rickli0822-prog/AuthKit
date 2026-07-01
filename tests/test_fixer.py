from authkit.models import DiagnosisReport, FailureCase, FixAction, HealthStatus, LayerResult
from authkit.repair.audit import RepairAuditRecord, append_audit_record, load_audit_records
from authkit.repair import fixer


def _report_with_env_proxy() -> DiagnosisReport:
    return DiagnosisReport(
        tool_version="test",
        platform="Windows",
        client="codex",
        status=HealthStatus.WARNING,
        case=FailureCase.UNKNOWN,
        root_cause="test",
        confidence="low",
        browser_explanation="test",
        layers=[
            LayerResult(
                name="env_proxy",
                ok=True,
                summary="env proxy",
                details={"primary_endpoint": {"scheme": "http", "host": "127.0.0.1", "port": 7890, "raw": ""}},
            )
        ],
    )


def _report_with_client_executable() -> DiagnosisReport:
    report = _report_with_env_proxy()
    report.layers.append(
        LayerResult(
            name="client_specific",
            ok=True,
            summary="client",
            details={"executable": r"C:\Tools\claude.exe"},
        )
    )
    return report


def test_apply_fix_sync_system_proxy(monkeypatch):
    calls = []
    audits = []
    monkeypatch.setattr(fixer, "set_system_proxy", lambda endpoint, *, override: calls.append((endpoint, override)) or ["ProxyEnable"])
    monkeypatch.setattr(fixer, "read_system_proxy", lambda: {"enabled": False, "server": "", "endpoint": {}, "override": ""})
    monkeypatch.setattr(fixer, "append_audit_record", lambda record: audits.append(record))

    message = fixer.apply_fix(
        _report_with_env_proxy(),
        FixAction(
            fix_id="sync-system-proxy",
            description="sync",
            command="authkit system-proxy --apply",
            auto_applicable=True,
        ),
    )

    assert message == "Updated Windows system proxy: ProxyEnable"
    assert calls[0][0].url == "http://127.0.0.1:7890"
    assert calls[0][1] == "127.0.0.1;localhost;::1;<local>"
    assert audits[0].fix_id == "sync-system-proxy"
    assert audits[0].client == "codex"
    assert audits[0].changed_keys == ["ProxyEnable"]
    assert audits[0].status == "success"
    assert audits[0].risk == "medium"
    assert audits[0].admin_required is False
    assert audits[0].restart_required is False
    assert audits[0].rollback_supported is True


def test_rollback_latest_repair_restores_system_proxy_and_audits(tmp_path, monkeypatch):
    path = tmp_path / "repair-log.jsonl"
    append_audit_record(
        RepairAuditRecord(
            repair_id="original",
            timestamp="2026-07-01T00:00:00+00:00",
            fix_id="sync-system-proxy",
            client="codex",
            before={"system_proxy": {"enabled": False, "server": "", "override": ""}},
            after={"system_proxy": {"enabled": True, "server": "127.0.0.1:7890", "override": "localhost;<local>"}},
            changed_keys=["ProxyEnable", "ProxyServer"],
            rollback_supported=True,
            status="success",
            message="ok",
        ),
        path=path,
    )
    restores = []
    monkeypatch.setattr(fixer, "read_system_proxy", lambda: {"enabled": True, "server": "127.0.0.1:7890", "override": ""})
    monkeypatch.setattr(fixer, "restore_system_proxy", lambda snapshot: restores.append(snapshot) or ["ProxyEnable", "ProxyServer"])

    message = fixer.rollback_latest_repair(path=path)
    records = load_audit_records(path=path)

    assert restores == [{"enabled": False, "server": "", "override": ""}]
    assert "Rolled back repair original (sync-system-proxy)" in message
    assert records[-1].fix_id == "rollback:sync-system-proxy"
    assert records[-1].rollback_supported is False
    assert records[-1].status == "success"


def test_sync_proxy_writes_repair_audit(monkeypatch):
    audits = []
    monkeypatch.setattr(fixer, "read_env_proxy", lambda _scope: {"HTTP_PROXY": None})
    monkeypatch.setattr(fixer, "set_user_env_proxy", lambda _endpoint, _no_proxy: ["HTTP_PROXY", "HTTPS_PROXY"])
    monkeypatch.setattr(fixer, "append_audit_record", lambda record, **_kwargs: audits.append(record))

    message = fixer.sync_proxy("http://127.0.0.1:7890")

    assert message == "Synced user environment variables: HTTP_PROXY, HTTPS_PROXY"
    assert audits[0].fix_id == "sync-env-proxy"
    assert audits[0].client == "manual"
    assert audits[0].changed_keys == ["HTTP_PROXY", "HTTPS_PROXY"]
    assert audits[0].rollback_supported is True
    assert audits[0].risk == "low"


def test_apply_fix_flush_dns_cache_audits_non_rollbackable(monkeypatch):
    audits = []
    calls = []
    monkeypatch.setattr(fixer, "append_audit_record", lambda record, **_kwargs: audits.append(record))
    monkeypatch.setattr(
        fixer,
        "flush_dns_cache",
        lambda: calls.append("flush") or {"returncode": 0, "stdout": "flushed", "stderr": ""},
    )

    message = fixer.apply_fix(
        _report_with_env_proxy(),
        FixAction(
            fix_id="flush-dns-cache",
            description="flush dns",
            command="ipconfig /flushdns",
            auto_applicable=True,
        ),
    )

    assert message == "Flushed Windows DNS resolver cache."
    assert calls == ["flush"]
    assert audits[0].fix_id == "flush-dns-cache"
    assert audits[0].changed_keys == ["DnsClientCache"]
    assert audits[0].rollback_supported is False
    assert audits[0].risk == "low"
    assert audits[0].admin_required is False
    assert audits[0].restart_required is False
    assert audits[0].before == {"dns_cache": {"persistent_config_changed": False}}


def test_flush_dns_cache_runs_ipconfig(monkeypatch):
    calls = []

    class Completed:
        returncode = 0
        stdout = "Successfully flushed"
        stderr = ""

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return Completed()

    monkeypatch.setattr(fixer.subprocess, "run", fake_run)

    result = fixer.flush_dns_cache()

    assert result["returncode"] == 0
    assert calls[0][0] == ["ipconfig", "/flushdns"]
    assert calls[0][1]["timeout"] == fixer.DNS_FLUSH_TIMEOUT_SECONDS


def test_apply_direct_repair_flush_dns_audits(monkeypatch):
    audits = []
    monkeypatch.setattr(fixer, "append_audit_record", lambda record, **_kwargs: audits.append(record))
    monkeypatch.setattr(fixer, "flush_dns_cache", lambda: {"returncode": 0, "stdout": "flushed", "stderr": ""})

    message = fixer.apply_direct_repair("flush-dns-cache")

    assert message == "Flushed Windows DNS resolver cache."
    assert audits[0].fix_id == "flush-dns-cache"
    assert audits[0].client == "manual"
    assert audits[0].changed_keys == ["DnsClientCache"]
    assert audits[0].risk == "low"
    assert audits[0].admin_required is False


def test_apply_fix_winsock_reset_audits_non_rollbackable(monkeypatch):
    audits = []
    calls = []
    monkeypatch.setattr(fixer, "is_running_as_admin", lambda: True)
    monkeypatch.setattr(fixer, "append_audit_record", lambda record, **_kwargs: audits.append(record))
    monkeypatch.setattr(
        fixer,
        "reset_winsock_catalog",
        lambda: calls.append("reset") or {"returncode": 0, "stdout": "restart required", "stderr": ""},
    )

    message = fixer.apply_fix(
        _report_with_env_proxy(),
        FixAction(
            fix_id="winsock-reset",
            description="reset winsock",
            command="netsh winsock reset",
            auto_applicable=False,
        ),
    )

    assert message == "Reset Windows Winsock catalog. Restart Windows before retesting."
    assert calls == ["reset"]
    assert audits[0].fix_id == "winsock-reset"
    assert audits[0].changed_keys == ["WinsockCatalog"]
    assert audits[0].rollback_supported is False
    assert audits[0].risk == "medium"
    assert audits[0].admin_required is True
    assert audits[0].restart_required is True
    assert audits[0].before == {"winsock": {"restart_required": True, "rollback_supported": False}}
    assert "Restart Windows before retesting" in audits[0].warnings[-1]


def test_reset_winsock_catalog_runs_netsh(monkeypatch):
    calls = []

    class Completed:
        returncode = 0
        stdout = "Successfully reset the Winsock Catalog."
        stderr = ""

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return Completed()

    monkeypatch.setattr(fixer.subprocess, "run", fake_run)

    result = fixer.reset_winsock_catalog()

    assert result["returncode"] == 0
    assert result["restart_required"] is True
    assert calls[0][0] == ["netsh", "winsock", "reset"]
    assert calls[0][1]["timeout"] == fixer.WINSOCK_RESET_TIMEOUT_SECONDS


def test_apply_direct_repair_winsock_audits(monkeypatch):
    audits = []
    monkeypatch.setattr(fixer, "is_running_as_admin", lambda: True)
    monkeypatch.setattr(fixer, "append_audit_record", lambda record, **_kwargs: audits.append(record))
    monkeypatch.setattr(fixer, "reset_winsock_catalog", lambda: {"returncode": 0, "stdout": "reset", "stderr": ""})

    message = fixer.apply_direct_repair("winsock-reset")

    assert message == "Reset Windows Winsock catalog. Restart Windows before retesting."
    assert audits[0].fix_id == "winsock-reset"
    assert audits[0].changed_keys == ["WinsockCatalog"]
    assert audits[0].rollback_supported is False
    assert audits[0].admin_required is True
    assert audits[0].restart_required is True


def test_apply_fix_firewall_allow_audits_non_rollbackable(monkeypatch):
    audits = []
    calls = []
    monkeypatch.setattr(fixer, "is_running_as_admin", lambda: True)
    monkeypatch.setattr(fixer, "append_audit_record", lambda record, **_kwargs: audits.append(record))
    monkeypatch.setattr(
        fixer,
        "allow_firewall_outbound",
        lambda *, program_path, client: calls.append((program_path, client))
        or {"returncode": 0, "stdout": "Ok.", "stderr": "", "rule_name": "AuthKit Allow codex Outbound"},
    )

    message = fixer.apply_fix(
        _report_with_client_executable(),
        FixAction(
            fix_id="allow-firewall-outbound",
            description="firewall",
            command="netsh advfirewall firewall add rule",
            auto_applicable=False,
        ),
    )

    assert message == r"Added Windows Firewall outbound allow rule for C:\Tools\claude.exe."
    assert calls == [(r"C:\Tools\claude.exe", "codex")]
    assert audits[0].fix_id == "allow-firewall-outbound"
    assert audits[0].changed_keys == ["FirewallRule"]
    assert audits[0].rollback_supported is False
    assert audits[0].risk == "medium"
    assert audits[0].admin_required is True
    assert audits[0].restart_required is False
    assert audits[0].before == {"firewall": {"rollback_supported": False, "rule_prefix": "AuthKit Allow"}}


def test_allow_firewall_outbound_uses_netsh_argument_list(tmp_path, monkeypatch):
    program = tmp_path / "codex.exe"
    program.write_text("stub", encoding="utf-8")
    calls = []

    class Completed:
        returncode = 0
        stdout = "Ok."
        stderr = ""

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return Completed()

    monkeypatch.setattr(fixer.subprocess, "run", fake_run)

    result = fixer.allow_firewall_outbound(program_path=str(program), client="codex")

    assert result["rule_name"] == "AuthKit Allow codex Outbound"
    assert result["program_path"] == str(program)
    assert calls[0][0][:5] == ["netsh", "advfirewall", "firewall", "add", "rule"]
    assert "dir=out" in calls[0][0]
    assert "action=allow" in calls[0][0]
    assert f"program={program}" in calls[0][0]
    assert "profile=any" in calls[0][0]
    assert calls[0][1]["timeout"] == fixer.FIREWALL_RULE_TIMEOUT_SECONDS


def test_allow_firewall_outbound_rejects_missing_program_before_netsh(monkeypatch):
    calls = []
    monkeypatch.setattr(fixer.subprocess, "run", lambda *args, **kwargs: calls.append((args, kwargs)))

    try:
        fixer.allow_firewall_outbound(program_path=r"C:\Missing\codex.exe", client="codex")
    except ValueError as exc:
        error = str(exc)
    else:
        raise AssertionError("expected ValueError")

    assert "Target client executable was not found" in error
    assert calls == []


def test_apply_direct_repair_firewall_audits(monkeypatch):
    audits = []
    calls = []
    monkeypatch.setattr(fixer, "is_running_as_admin", lambda: True)
    monkeypatch.setattr(fixer, "append_audit_record", lambda record, **_kwargs: audits.append(record))
    monkeypatch.setattr(
        fixer,
        "allow_firewall_outbound",
        lambda *, program_path, client: calls.append((program_path, client)) or {"returncode": 0, "stdout": "ok", "stderr": ""},
    )

    message = fixer.apply_direct_repair("allow-firewall-outbound", client="codex", program_path=r"C:\Tools\codex.exe")

    assert message == r"Added Windows Firewall outbound allow rule for C:\Tools\codex.exe."
    assert calls == [(r"C:\Tools\codex.exe", "codex")]
    assert audits[0].fix_id == "allow-firewall-outbound"
    assert audits[0].changed_keys == ["FirewallRule"]
    assert audits[0].admin_required is True


def test_apply_direct_repair_firewall_missing_program_audits_failure(monkeypatch):
    audits = []
    monkeypatch.setattr(fixer, "is_running_as_admin", lambda: True)
    monkeypatch.setattr(fixer, "append_audit_record", lambda record, **_kwargs: audits.append(record))

    try:
        fixer.apply_direct_repair("allow-firewall-outbound", client="codex", program_path=r"C:\Missing\codex.exe")
    except ValueError as exc:
        error = str(exc)
    else:
        raise AssertionError("expected ValueError")

    assert "Target client executable was not found" in error
    assert audits[0].fix_id == "allow-firewall-outbound"
    assert audits[0].status == "failed"
    assert audits[0].admin_required is True
    assert "Target client executable was not found" in audits[0].error


def test_apply_direct_repair_winsock_requires_admin_and_audits_failure(monkeypatch):
    audits = []
    calls = []
    monkeypatch.setattr(fixer, "is_running_as_admin", lambda: False)
    monkeypatch.setattr(fixer, "append_audit_record", lambda record, **_kwargs: audits.append(record))
    monkeypatch.setattr(fixer, "reset_winsock_catalog", lambda: calls.append("reset") or {})

    try:
        fixer.apply_direct_repair("winsock-reset")
    except PermissionError as exc:
        error = str(exc)
    else:
        raise AssertionError("expected PermissionError")

    assert "Administrator terminal" in error
    assert calls == []
    assert audits[0].fix_id == "winsock-reset"
    assert audits[0].status == "failed"
    assert audits[0].admin_required is True
    assert audits[0].restart_required is True
    assert "Administrator terminal" in audits[0].error


def test_apply_fix_firewall_requires_admin_before_netsh(monkeypatch):
    audits = []
    calls = []
    monkeypatch.setattr(fixer, "is_running_as_admin", lambda: False)
    monkeypatch.setattr(fixer, "append_audit_record", lambda record, **_kwargs: audits.append(record))
    monkeypatch.setattr(fixer, "allow_firewall_outbound", lambda **_kwargs: calls.append(_kwargs) or {})

    try:
        fixer.apply_fix(
            _report_with_client_executable(),
            FixAction(
                fix_id="allow-firewall-outbound",
                description="firewall",
                command="authkit firewall --allow-outbound",
                auto_applicable=False,
                admin_required=True,
            ),
        )
    except PermissionError as exc:
        error = str(exc)
    else:
        raise AssertionError("expected PermissionError")

    assert "Administrator terminal" in error
    assert calls == []
    assert audits[0].fix_id == "allow-firewall-outbound"
    assert audits[0].status == "failed"
    assert audits[0].admin_required is True


def test_configure_client_ca_certificate_writes_env_and_audits(tmp_path, monkeypatch):
    cert = tmp_path / "corp-ca.pem"
    cert.write_text("-----BEGIN CERTIFICATE-----\n-----END CERTIFICATE-----\n", encoding="utf-8")
    audits = []
    writes = []
    monkeypatch.setattr(fixer, "read_user_env_values", lambda names: {name: None for name in names})
    monkeypatch.setattr(fixer, "set_user_env_values", lambda values: writes.append(values) or list(values))
    monkeypatch.setattr(fixer, "append_audit_record", lambda record, **_kwargs: audits.append(record))

    message = fixer.configure_client_ca_certificate(client="codex", ca_path=str(cert))

    assert message == "Configured client-level CA certificate for codex: CODEX_CA_CERTIFICATE"
    assert writes == [{"CODEX_CA_CERTIFICATE": str(cert)}]
    assert audits[0].fix_id == "configure-client-ca"
    assert audits[0].rollback_supported is True
    assert audits[0].risk == "medium"
    assert audits[0].admin_required is False
    assert audits[0].restart_required is False
    assert audits[0].before["client_ca"]["system_trust_store_changed"] is False
    assert audits[0].changed_keys == ["CODEX_CA_CERTIFICATE"]


def test_configure_client_ca_certificate_uses_node_extra_ca_for_claude(tmp_path, monkeypatch):
    cert = tmp_path / "corp-ca.pem"
    cert.write_text("cert", encoding="utf-8")
    writes = []
    monkeypatch.setattr(fixer, "read_user_env_values", lambda names: {name: None for name in names})
    monkeypatch.setattr(fixer, "set_user_env_values", lambda values: writes.append(values) or list(values))
    monkeypatch.setattr(fixer, "append_audit_record", lambda *_args, **_kwargs: None)

    fixer.configure_client_ca_certificate(client="claude", ca_path=str(cert))

    assert writes == [{"NODE_EXTRA_CA_CERTS": str(cert)}]


def test_rollback_client_ca_restores_previous_env(tmp_path, monkeypatch):
    path = tmp_path / "repair-log.jsonl"
    append_audit_record(
        RepairAuditRecord(
            repair_id="ca",
            timestamp="2026-07-01T00:00:00+00:00",
            fix_id="configure-client-ca",
            client="codex",
            before={"client_ca": {"env": {"CODEX_CA_CERTIFICATE": None}}},
            after={"client_ca": {"env": {"CODEX_CA_CERTIFICATE": str(tmp_path / "corp-ca.pem")}}},
            changed_keys=["CODEX_CA_CERTIFICATE"],
            rollback_supported=True,
            status="success",
            message="ok",
        ),
        path=path,
    )
    restored = []
    monkeypatch.setattr(fixer, "restore_user_env_values", lambda snapshot: restored.append(snapshot) or ["CODEX_CA_CERTIFICATE"])
    monkeypatch.setattr(fixer, "read_user_env_values", lambda names: {name: "current" for name in names})

    message = fixer.rollback_latest_repair(path=path)

    assert restored == [{"CODEX_CA_CERTIFICATE": None}]
    assert "configure-client-ca" in message
