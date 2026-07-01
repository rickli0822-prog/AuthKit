from __future__ import annotations

from pathlib import Path
import subprocess

from authkit.models import DiagnosisReport, FixAction, ProxyEndpoint
from authkit.platform.proxy import (
    clear_user_env_proxy,
    parse_proxy_url,
    read_env_proxy,
    read_system_proxy,
    read_user_env_values,
    restore_system_proxy,
    restore_user_env_proxy,
    restore_user_env_values,
    set_system_proxy,
    set_user_env_proxy,
    set_user_env_values,
    set_user_no_proxy,
)
from authkit.platform.privileges import is_running_as_admin
from authkit.repair.audit import (
    RepairAuditRecord,
    append_audit_record,
    json_safe,
    latest_rollbackable_record,
    new_repair_id,
    utc_timestamp,
)


DEFAULT_NO_PROXY = "127.0.0.1,localhost,::1"
DEFAULT_PROXY_OVERRIDE = "127.0.0.1;localhost;::1;<local>"
DNS_FLUSH_TIMEOUT_SECONDS = 15
WINSOCK_RESET_TIMEOUT_SECONDS = 30
FIREWALL_RULE_TIMEOUT_SECONDS = 30
FIREWALL_RULE_PREFIX = "AuthKit Allow"
CA_ENV_BY_CLIENT = {
    "codex": ("CODEX_CA_CERTIFICATE",),
    "claude": ("NODE_EXTRA_CA_CERTS",),
    "gemini": ("NODE_EXTRA_CA_CERTS",),
    "cursor": ("NODE_EXTRA_CA_CERTS",),
    "vscode": ("NODE_EXTRA_CA_CERTS",),
}

REPAIR_METADATA: dict[str, dict[str, object]] = {
    "sync-env-proxy": {
        "risk": "low",
        "admin_required": False,
        "restart_required": False,
        "rollback_supported": True,
    },
    "clear-env-proxy": {
        "risk": "low",
        "admin_required": False,
        "restart_required": False,
        "rollback_supported": True,
    },
    "set-no-proxy": {
        "risk": "low",
        "admin_required": False,
        "restart_required": False,
        "rollback_supported": True,
    },
    "sync-system-proxy": {
        "risk": "medium",
        "admin_required": False,
        "restart_required": False,
        "rollback_supported": True,
    },
    "flush-dns-cache": {
        "risk": "low",
        "admin_required": False,
        "restart_required": False,
        "rollback_supported": False,
    },
    "winsock-reset": {
        "risk": "medium",
        "admin_required": True,
        "restart_required": True,
        "rollback_supported": False,
    },
    "allow-firewall-outbound": {
        "risk": "medium",
        "admin_required": True,
        "restart_required": False,
        "rollback_supported": False,
    },
    "configure-client-ca": {
        "risk": "medium",
        "admin_required": False,
        "restart_required": False,
        "rollback_supported": True,
    },
}


def apply_fix(report: DiagnosisReport, fix: FixAction) -> str:
    return _apply_fix_with_audit(report, fix)


def repair_metadata(fix_id: str) -> dict[str, object]:
    return {
        "risk": "low",
        "admin_required": False,
        "restart_required": False,
        "rollback_supported": False,
        **REPAIR_METADATA.get(fix_id, {}),
    }


def _require_admin_privileges(fix_id: str, metadata: dict[str, object]) -> None:
    if not metadata.get("admin_required"):
        return
    if is_running_as_admin():
        return
    raise PermissionError(f"Repair {fix_id} requires an elevated Administrator terminal.")


def apply_direct_repair(fix_id: str, *, client: str = "manual", program_path: str | None = None) -> str:
    repair_id = new_repair_id()
    before = _snapshot_for_fix(fix_id)
    metadata = repair_metadata(fix_id)
    warnings: list[str] = []
    try:
        _require_admin_privileges(fix_id, metadata)
        message, changed = _apply_direct_repair_inner(
            fix_id,
            client=client,
            program_path=program_path,
            warnings=warnings,
        )
        append_audit_record(
            RepairAuditRecord(
                repair_id=repair_id,
                timestamp=utc_timestamp(),
                fix_id=fix_id,
                client=client,
                before=before,
                after=_snapshot_for_fix(fix_id),
                changed_keys=changed,
                rollback_supported=bool(metadata["rollback_supported"]),
                status="success",
                risk=str(metadata["risk"]),
                admin_required=bool(metadata["admin_required"]),
                restart_required=bool(metadata["restart_required"]),
                message=message,
                warnings=warnings,
            )
        )
        return message
    except Exception as exc:
        append_audit_record(
            RepairAuditRecord(
                repair_id=repair_id,
                timestamp=utc_timestamp(),
                fix_id=fix_id,
                client=client,
                before=before,
                after=_snapshot_for_fix(fix_id),
                changed_keys=[],
                rollback_supported=False,
                status="failed",
                risk=str(metadata["risk"]),
                admin_required=bool(metadata["admin_required"]),
                restart_required=bool(metadata["restart_required"]),
                error=str(exc),
                warnings=warnings,
            )
        )
        raise


def _apply_fix_with_audit(report: DiagnosisReport, fix: FixAction) -> str:
    repair_id = new_repair_id()
    before = _snapshot_for_fix(fix.fix_id)
    metadata = repair_metadata(fix.fix_id)
    warnings: list[str] = []
    try:
        _require_admin_privileges(fix.fix_id, metadata)
        message, changed = _apply_fix_inner(report, fix, warnings=warnings)
        after = _snapshot_for_fix(fix.fix_id)
        append_audit_record(
            RepairAuditRecord(
                repair_id=repair_id,
                timestamp=utc_timestamp(),
                fix_id=fix.fix_id,
                client=report.client,
                before=before,
                after=after,
                changed_keys=changed,
                rollback_supported=fix.rollback_supported or bool(metadata["rollback_supported"]),
                status="success",
                risk=str(metadata["risk"]),
                admin_required=fix.admin_required or bool(metadata["admin_required"]),
                restart_required=fix.restart_required or bool(metadata["restart_required"]),
                message=message,
                warnings=warnings,
            )
        )
        return message
    except Exception as exc:
        append_audit_record(
            RepairAuditRecord(
                repair_id=repair_id,
                timestamp=utc_timestamp(),
                fix_id=fix.fix_id,
                client=report.client,
                before=before,
                after=_snapshot_for_fix(fix.fix_id),
                changed_keys=[],
                rollback_supported=False,
                status="failed",
                risk=str(metadata["risk"]),
                admin_required=fix.admin_required or bool(metadata["admin_required"]),
                restart_required=fix.restart_required or bool(metadata["restart_required"]),
                error=str(exc),
                warnings=warnings,
            )
        )
        raise


def _apply_fix_inner(report: DiagnosisReport, fix: FixAction, *, warnings: list[str]) -> tuple[str, list[str]]:
    if fix.fix_id == "sync-env-proxy":
        proxy = _proxy_from_report(report, layer_name="system_proxy")
        if not proxy.is_set:
            raise ValueError("No usable system proxy was found in the report; cannot sync user environment.")
        changed = set_user_env_proxy(proxy, DEFAULT_NO_PROXY)
        return f"Updated user environment variables: {', '.join(changed)}", changed

    if fix.fix_id == "clear-env-proxy":
        cleared = clear_user_env_proxy()
        return f"Cleared user environment variables: {', '.join(cleared) if cleared else 'none'}", cleared

    if fix.fix_id == "set-no-proxy":
        changed = set_user_no_proxy(DEFAULT_NO_PROXY)
        return f"Updated NO_PROXY: {', '.join(changed)}", changed

    if fix.fix_id == "sync-system-proxy":
        proxy = _proxy_from_report(report, layer_name="env_proxy")
        if not proxy.is_set:
            raise ValueError("No usable environment proxy was found in the report; cannot sync Windows system proxy.")
        changed = set_system_proxy(proxy, override=DEFAULT_PROXY_OVERRIDE)
        return f"Updated Windows system proxy: {', '.join(changed)}", changed

    if fix.fix_id == "flush-dns-cache":
        result = flush_dns_cache()
        stdout = str(result.get("stdout") or "").strip()
        stderr = str(result.get("stderr") or "").strip()
        if stderr:
            warnings.append(stderr)
        if stdout:
            warnings.append(stdout)
        return "Flushed Windows DNS resolver cache.", ["DnsClientCache"]

    if fix.fix_id == "winsock-reset":
        result = reset_winsock_catalog()
        stdout = str(result.get("stdout") or "").strip()
        stderr = str(result.get("stderr") or "").strip()
        if stderr:
            warnings.append(stderr)
        if stdout:
            warnings.append(stdout)
        warnings.append("Restart Windows before retesting the target AI client.")
        return "Reset Windows Winsock catalog. Restart Windows before retesting.", ["WinsockCatalog"]

    if fix.fix_id == "allow-firewall-outbound":
        program_path = _program_path_from_report(report)
        if not program_path:
            raise ValueError("No target client executable path was found in the report; cannot create a firewall rule.")
        result = allow_firewall_outbound(program_path=program_path, client=report.client)
        stdout = str(result.get("stdout") or "").strip()
        stderr = str(result.get("stderr") or "").strip()
        if stderr:
            warnings.append(stderr)
        if stdout:
            warnings.append(stdout)
        return f"Added Windows Firewall outbound allow rule for {program_path}.", ["FirewallRule"]

    raise ValueError(f"Fix {fix.fix_id} requires manual execution: {fix.command}")


def _apply_direct_repair_inner(
    fix_id: str,
    *,
    client: str,
    program_path: str | None,
    warnings: list[str],
) -> tuple[str, list[str]]:
    if fix_id == "flush-dns-cache":
        result = flush_dns_cache()
        _append_command_output_warnings(result, warnings)
        return "Flushed Windows DNS resolver cache.", ["DnsClientCache"]
    if fix_id == "winsock-reset":
        result = reset_winsock_catalog()
        _append_command_output_warnings(result, warnings)
        warnings.append("Restart Windows before retesting the target AI client.")
        return "Reset Windows Winsock catalog. Restart Windows before retesting.", ["WinsockCatalog"]
    if fix_id == "allow-firewall-outbound":
        if not program_path:
            raise ValueError("program_path is required for firewall repair.")
        result = allow_firewall_outbound(program_path=program_path, client=client)
        _append_command_output_warnings(result, warnings)
        return f"Added Windows Firewall outbound allow rule for {program_path}.", ["FirewallRule"]
    raise ValueError(f"Unsupported direct repair: {fix_id}")


def _append_command_output_warnings(result: dict[str, object], warnings: list[str]) -> None:
    stdout = str(result.get("stdout") or "").strip()
    stderr = str(result.get("stderr") or "").strip()
    if stderr:
        warnings.append(stderr)
    if stdout:
        warnings.append(stdout)


def apply_auto_fixes(report: DiagnosisReport) -> list[str]:
    messages: list[str] = []
    for fix in report.fixes:
        if not fix.auto_applicable:
            continue
        try:
            messages.append(apply_fix(report, fix))
        except ValueError as exc:
            messages.append(str(exc))
    return messages


def sync_proxy(proxy_url: str | None, *, clear: bool = False, no_proxy: str | None = DEFAULT_NO_PROXY) -> str:
    fix_id = "clear-env-proxy" if clear else "sync-env-proxy"
    repair_id = new_repair_id()
    before = _snapshot_for_fix(fix_id)
    metadata = repair_metadata(fix_id)
    try:
        if clear:
            changed = clear_user_env_proxy()
            message = f"Cleared user environment variables: {', '.join(changed) if changed else 'none'}"
        else:
            endpoint = parse_proxy_url(proxy_url)
            if not endpoint.is_set:
                raise ValueError("Provide a valid proxy URL, for example http://127.0.0.1:7890")
            changed = set_user_env_proxy(endpoint, no_proxy)
            message = f"Synced user environment variables: {', '.join(changed)}"
        append_audit_record(
            RepairAuditRecord(
                repair_id=repair_id,
                timestamp=utc_timestamp(),
                fix_id=fix_id,
                client="manual",
                before=before,
                after=_snapshot_for_fix(fix_id),
                changed_keys=changed,
                rollback_supported=bool(metadata["rollback_supported"]),
                status="success",
                risk=str(metadata["risk"]),
                admin_required=bool(metadata["admin_required"]),
                restart_required=bool(metadata["restart_required"]),
                message=message,
            )
        )
        return message
    except Exception as exc:
        append_audit_record(
            RepairAuditRecord(
                repair_id=repair_id,
                timestamp=utc_timestamp(),
                fix_id=fix_id,
                client="manual",
                before=before,
                after=_snapshot_for_fix(fix_id),
                changed_keys=[],
                rollback_supported=False,
                status="failed",
                risk=str(metadata["risk"]),
                admin_required=bool(metadata["admin_required"]),
                restart_required=bool(metadata["restart_required"]),
                error=str(exc),
            )
        )
        raise


def rollback_latest_repair(*, path: Path | None = None) -> str:
    record = latest_rollbackable_record(path=path)
    if record is None:
        raise ValueError("No rollbackable AuthKit repair record was found.")
    before = _snapshot_for_fix(record.fix_id)
    changed: list[str] = []
    try:
        changed = _rollback_record(record)
        after = _snapshot_for_fix(record.fix_id)
        message = f"Rolled back repair {record.repair_id} ({record.fix_id}): {', '.join(changed) if changed else 'no changes'}"
        append_audit_record(
            RepairAuditRecord(
                repair_id=new_repair_id(),
                timestamp=utc_timestamp(),
                fix_id=f"rollback:{record.fix_id}",
                client=record.client,
                before=before,
                after=after,
                changed_keys=changed,
                rollback_supported=False,
                status="success",
                message=message,
            ),
            path=path,
        )
        return message
    except Exception as exc:
        append_audit_record(
            RepairAuditRecord(
                repair_id=new_repair_id(),
                timestamp=utc_timestamp(),
                fix_id=f"rollback:{record.fix_id}",
                client=record.client,
                before=before,
                after=_snapshot_for_fix(record.fix_id),
                changed_keys=changed,
                rollback_supported=False,
                status="failed",
                error=str(exc),
            ),
            path=path,
        )
        raise


def configure_client_ca_certificate(*, client: str, ca_path: str) -> str:
    cert_path = Path(ca_path).expanduser()
    if not cert_path.is_file():
        raise ValueError(f"CA certificate file was not found: {ca_path}")
    env_names = ca_env_names_for_client(client)
    if not env_names:
        raise ValueError(f"Client {client} does not have a supported client-level CA environment variable.")

    repair_id = new_repair_id()
    before = _client_ca_snapshot(client, env_names, str(cert_path))
    metadata = repair_metadata("configure-client-ca")
    try:
        changed = set_user_env_values({name: str(cert_path) for name in env_names})
        after = _client_ca_snapshot(client, env_names, str(cert_path))
        message = f"Configured client-level CA certificate for {client}: {', '.join(changed)}"
        append_audit_record(
            RepairAuditRecord(
                repair_id=repair_id,
                timestamp=utc_timestamp(),
                fix_id="configure-client-ca",
                client=client,
                before=before,
                after=after,
                changed_keys=changed,
                rollback_supported=bool(metadata["rollback_supported"]),
                status="success",
                risk=str(metadata["risk"]),
                admin_required=bool(metadata["admin_required"]),
                restart_required=bool(metadata["restart_required"]),
                message=message,
                warnings=["Restart the terminal and target AI client so the CA environment variable is reloaded."],
            )
        )
        return message
    except Exception as exc:
        append_audit_record(
            RepairAuditRecord(
                repair_id=repair_id,
                timestamp=utc_timestamp(),
                fix_id="configure-client-ca",
                client=client,
                before=before,
                after=_client_ca_snapshot(client, env_names, str(cert_path)),
                changed_keys=[],
                rollback_supported=False,
                status="failed",
                risk=str(metadata["risk"]),
                admin_required=bool(metadata["admin_required"]),
                restart_required=bool(metadata["restart_required"]),
                error=str(exc),
            )
        )
        raise


def ca_env_names_for_client(client: str) -> tuple[str, ...]:
    return CA_ENV_BY_CLIENT.get(client, ("NODE_EXTRA_CA_CERTS",))


def flush_dns_cache() -> dict[str, object]:
    completed = subprocess.run(
        ["ipconfig", "/flushdns"],
        capture_output=True,
        text=True,
        timeout=DNS_FLUSH_TIMEOUT_SECONDS,
        check=False,
    )
    result = {
        "command": "ipconfig /flushdns",
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    if completed.returncode != 0:
        raise RuntimeError(
            f"ipconfig /flushdns failed with exit code {completed.returncode}: "
            f"{(completed.stderr or completed.stdout).strip()}"
        )
    return result


def reset_winsock_catalog() -> dict[str, object]:
    completed = subprocess.run(
        ["netsh", "winsock", "reset"],
        capture_output=True,
        text=True,
        timeout=WINSOCK_RESET_TIMEOUT_SECONDS,
        check=False,
    )
    result = {
        "command": "netsh winsock reset",
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "restart_required": True,
    }
    if completed.returncode != 0:
        raise RuntimeError(
            f"netsh winsock reset failed with exit code {completed.returncode}: "
            f"{(completed.stderr or completed.stdout).strip()}"
        )
    return result


def allow_firewall_outbound(*, program_path: str, client: str) -> dict[str, object]:
    if not program_path:
        raise ValueError("program_path is required")
    target = Path(program_path).expanduser()
    if not target.is_file():
        raise ValueError(f"Target client executable was not found: {program_path}")
    rule_name = firewall_rule_name(client)
    completed = subprocess.run(
        [
            "netsh",
            "advfirewall",
            "firewall",
            "add",
            "rule",
            f"name={rule_name}",
            "dir=out",
            "action=allow",
            f"program={target}",
            "enable=yes",
            "profile=any",
        ],
        capture_output=True,
        text=True,
        timeout=FIREWALL_RULE_TIMEOUT_SECONDS,
        check=False,
    )
    result = {
        "command": "netsh advfirewall firewall add rule",
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "rule_name": rule_name,
        "program_path": str(target),
    }
    if completed.returncode != 0:
        raise RuntimeError(
            f"firewall rule creation failed with exit code {completed.returncode}: "
            f"{(completed.stderr or completed.stdout).strip()}"
        )
    return result


def firewall_rule_name(client: str) -> str:
    safe_client = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in client).strip("_")
    return f"{FIREWALL_RULE_PREFIX} {safe_client or 'AI Client'} Outbound"


def _client_ca_snapshot(client: str, env_names: tuple[str, ...], ca_path: str) -> dict[str, object]:
    return json_safe(
        {
            "client_ca": {
                "client": client,
                "ca_path": ca_path,
                "env": read_user_env_values(env_names),
                "system_trust_store_changed": False,
            }
        }
    )


def _proxy_from_report(report: DiagnosisReport, *, layer_name: str) -> ProxyEndpoint:
    for layer in report.layers:
        if layer.name != layer_name:
            continue
        endpoint = layer.details.get("endpoint", {}) or layer.details.get("primary_endpoint", {})
        if endpoint.get("host") and endpoint.get("port"):
            return ProxyEndpoint(
                scheme=endpoint.get("scheme", "http"),
                host=endpoint["host"],
                port=int(endpoint["port"]),
                raw=endpoint.get("raw", ""),
            )
    return parse_proxy_url("")


def _program_path_from_report(report: DiagnosisReport) -> str:
    for layer in report.layers:
        if layer.name != "client_specific":
            continue
        details = layer.details
        for key in ("codex_exe", "executable"):
            value = str(details.get(key) or "")
            if value:
                return value
    return ""


def _rollback_record(record: RepairAuditRecord) -> list[str]:
    if record.fix_id in {"sync-env-proxy", "clear-env-proxy", "set-no-proxy"}:
        snapshot = record.before.get("user_env")
        if not isinstance(snapshot, dict):
            raise ValueError("The repair record does not contain a user environment snapshot.")
        return restore_user_env_proxy(snapshot)
    if record.fix_id == "sync-system-proxy":
        snapshot = record.before.get("system_proxy")
        if not isinstance(snapshot, dict):
            raise ValueError("The repair record does not contain a Windows system proxy snapshot.")
        return restore_system_proxy(snapshot)
    if record.fix_id == "configure-client-ca":
        container = record.before.get("client_ca")
        if not isinstance(container, dict) or not isinstance(container.get("env"), dict):
            raise ValueError("The repair record does not contain a client CA environment snapshot.")
        return restore_user_env_values(container["env"])
    raise ValueError(f"Repair {record.fix_id} does not support rollback.")


def _snapshot_for_fix(fix_id: str) -> dict[str, object]:
    snapshot: dict[str, object] = {}
    if fix_id in {"sync-env-proxy", "clear-env-proxy", "set-no-proxy"}:
        snapshot["user_env"] = read_env_proxy("user")
    if fix_id == "sync-system-proxy":
        snapshot["system_proxy"] = read_system_proxy()
    if fix_id == "flush-dns-cache":
        snapshot["dns_cache"] = {"persistent_config_changed": False}
    if fix_id == "winsock-reset":
        snapshot["winsock"] = {"restart_required": True, "rollback_supported": False}
    if fix_id == "allow-firewall-outbound":
        snapshot["firewall"] = {"rollback_supported": False, "rule_prefix": FIREWALL_RULE_PREFIX}
    if fix_id == "configure-client-ca":
        snapshot["client_ca"] = {"system_trust_store_changed": False}
    return json_safe(snapshot)
