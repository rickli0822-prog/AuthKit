from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from authkit import __version__
from authkit.brand import APP_NAME, APP_TAGLINE_KEY
from authkit.clients import CLIENT_CHOICES, CLIENT_LABELS
from authkit.i18n import get_locale, init_locale, t
from authkit.core.diagnose import run_diagnosis
from authkit.core.scan import scan_installed_clients
from authkit.models import DiagnosisReport, FailureCase, FixAction, HealthStatus, LayerResult, OfficialGuidance
from authkit.repair.fixer import apply_direct_repair, apply_fix, configure_client_ca_certificate, rollback_latest_repair, sync_proxy
from authkit.repair.audit import RepairAuditRecord, latest_rollbackable_record, load_audit_records
from authkit.checks.login import check_login_status
from authkit.report import render_human, render_json
from authkit.platform.proxy import read_system_proxy


SENSITIVE_KEY_PARTS = (
    "access_token",
    "refresh_token",
    "id_token",
    "oauth_token",
    "api_key",
    "authorization",
    "password",
    "secret",
    "cookie",
)
URL_WITH_CREDENTIALS_RE = re.compile(r"(?P<scheme>https?://)(?P<userinfo>[^/@\s]+:[^/@\s]+)@")


def build_parser() -> argparse.ArgumentParser:
    init_locale()
    parser = argparse.ArgumentParser(
        prog="authkit",
        description=t(APP_TAGLINE_KEY),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--lang", choices=["zh", "en"], help="输出语言 / UI language")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("gui", help="打开图形界面")

    check = subparsers.add_parser("check", help="运行完整诊断")
    check.add_argument("--json", action="store_true", help="输出 JSON 报告")
    check.add_argument(
        "--client",
        choices=CLIENT_CHOICES,
        default="codex",
        help="目标 AI 客户端",
    )

    scan = subparsers.add_parser("scan", help="扫描本机已安装客户端并逐一诊断")
    scan.add_argument("--json", action="store_true", help="输出 JSON 报告")

    fix = subparsers.add_parser("fix", help="查看或应用建议修复")
    fix.add_argument("--apply", action="store_true", help="逐项确认后应用可自动执行的修复")
    fix.add_argument("--client", choices=CLIENT_CHOICES, default="codex")

    sync = subparsers.add_parser("sync", help="将环境变量代理同步为系统代理")
    sync.add_argument("--proxy", help="手动指定代理地址，例如 http://127.0.0.1:7890")
    sync.add_argument("--no-proxy", default="127.0.0.1,localhost,::1", help="设置 NO_PROXY")
    sync.add_argument("--clear", action="store_true", help="清理用户级代理环境变量")
    sync.add_argument("--apply", action="store_true", help="直接执行，不交互确认")

    login_status = subparsers.add_parser("login-status", help="仅检查本地登录凭据（不探测网络）")
    rollback = subparsers.add_parser("rollback", help="rollback latest AuthKit repair")
    rollback.add_argument("--apply", action="store_true", help="run rollback without confirmation")
    rollback.add_argument("--preview", action="store_true", help="show the latest rollbackable repair without changing the machine")
    audit = subparsers.add_parser("audit", help="show AuthKit repair audit records")
    audit.add_argument("--json", action="store_true", help="output audit records as JSON")
    audit.add_argument("--raw", action="store_true", help="include unredacted local audit details")
    audit.add_argument("--limit", type=int, default=20, help="number of recent records to show")
    bundle = subparsers.add_parser("bundle", help="write a support bundle with diagnosis and repair audit evidence")
    bundle.add_argument("--client", choices=CLIENT_CHOICES, default="codex")
    bundle.add_argument("--out", help="target JSON file path")
    bundle.add_argument("--audit-limit", type=int, default=20, help="number of recent repair audit records to include")
    bundle.add_argument("--fast", action="store_true", help="use the bounded fast diagnosis path for field support collection")
    bundle.add_argument("--sample", action="store_true", help="write a redacted sample support bundle without running diagnosis")
    bundle.add_argument("--validate", help="validate an existing support bundle JSON file")
    ca = subparsers.add_parser("ca", help="configure client-level CA certificate")
    ca.add_argument("--client", choices=CLIENT_CHOICES, default="codex")
    ca.add_argument("--cert", required=True, help="path to enterprise CA certificate PEM/CRT/CER")
    ca.add_argument("--apply", action="store_true", help="write user-level CA environment variables")
    dns = subparsers.add_parser("dns", help="repair DNS resolver cache")
    dns.add_argument("--flush", action="store_true", help="flush Windows DNS resolver cache")
    dns.add_argument("--apply", action="store_true", help="run without confirmation")
    winsock = subparsers.add_parser("winsock", help="repair Windows Winsock catalog")
    winsock.add_argument("--reset", action="store_true", help="run netsh winsock reset")
    winsock.add_argument("--apply", action="store_true", help="run without confirmation")
    firewall = subparsers.add_parser("firewall", help="repair Windows Firewall rules")
    firewall.add_argument("--allow-outbound", action="store_true", help="add outbound allow rule for one client program")
    firewall.add_argument("--client", choices=CLIENT_CHOICES, default="codex")
    firewall.add_argument("--program", help="target client executable path")
    firewall.add_argument("--apply", action="store_true", help="run without confirmation")

    login_status.add_argument("--json", action="store_true", help="输出 JSON")
    login_status.add_argument(
        "--client",
        choices=CLIENT_CHOICES,
        default="codex",
        help="目标 AI 客户端",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    if sys.platform != "win32":
        print("authkit（AuthKit）当前仅支持 Windows。", file=sys.stderr)
        return 2

    # 尽量让 Windows 控制台正确显示中文
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = build_parser()
    args = parser.parse_args(argv)
    init_locale()
    if getattr(args, "lang", None):
        from authkit.i18n import set_locale

        set_locale(args.lang)

    try:
        if args.command == "gui":
            from authkit.ui.app import main as gui_main

            return gui_main()

        if args.command == "check":
            report = run_diagnosis(client=args.client, locale=get_locale())
            print(render_json(report) if args.json else render_human(report, locale=get_locale()))
            return 0 if report.status.value == "healthy" else 1

        if args.command == "scan":
            reports = scan_installed_clients(locale=get_locale(), fast=True)
            if not reports:
                print("未发现已安装的受支持客户端。")
                return 1
            if args.json:
                import json

                print(json.dumps([report.to_dict() for report in reports], ensure_ascii=False, indent=2))
            else:
                print(f"已扫描 {len(reports)} 个客户端: " + ", ".join(CLIENT_LABELS.get(report.client, report.client) for report in reports))
                for index, report in enumerate(reports):
                    if index:
                        print("\n" + "=" * 72 + "\n")
                    print(render_human(report, locale=get_locale()))
            return 0 if all(report.status.value == "healthy" for report in reports) else 1

        if args.command == "fix":
            report = run_diagnosis(client=args.client, locale=get_locale())
            if not args.apply:
                print(render_human(report, locale=get_locale()))
                return 0 if report.status.value == "healthy" else 1
            return _apply_report_fixes(report, locale=get_locale())

        if args.command == "sync":
            if args.clear:
                message = sync_proxy(None, clear=True)
            else:
                proxy = args.proxy
                if not proxy:
                    system = read_system_proxy()
                    endpoint = system["endpoint"]
                    proxy = endpoint.url if endpoint.is_set else ""
                if not args.apply:
                    print(f"将执行: authkit sync --apply --proxy \"{proxy}\"")
                    answer = input("确认执行? [y/N] ").strip().lower()
                    if answer not in {"y", "yes"}:
                        print("已取消。")
                        return 0
                message = sync_proxy(proxy, clear=False, no_proxy=args.no_proxy)
            print(message)
            print("请重新打开终端，并完全退出后重启目标 AI 客户端。")
            return 0

        if args.command == "rollback":
            if args.preview:
                record = latest_rollbackable_record()
                if record is None:
                    print("No rollbackable AuthKit repair record was found.")
                    return 1
                print(_format_rollback_preview(record))
                return 0
            if not args.apply:
                answer = input("Rollback latest AuthKit repair? [y/N] ").strip().lower()
                if answer not in {"y", "yes"}:
                    print("Cancelled.")
                    return 0
            print(rollback_latest_repair())
            print("Reopen the terminal and restart the target AI client.")
            return 0

        if args.command == "audit":
            records = _recent_audit_records(limit=args.limit)
            if args.json:
                print(json.dumps(_audit_records_for_json(records, raw=args.raw), ensure_ascii=False, indent=2))
            else:
                print(_format_audit_records(records, raw=args.raw))
            return 0

        if args.command == "bundle":
            if args.validate:
                problems = _validate_support_bundle(Path(args.validate))
                if problems:
                    print("Invalid AuthKit support bundle:")
                    for problem in problems:
                        print(f"- {problem}")
                    return 1
                print(f"Valid AuthKit support bundle: {Path(args.validate).expanduser()}")
                return 0
            if not args.out:
                print("Specify --out to write a support bundle, or use --validate <file>.")
                return 1
            if args.sample:
                target = _write_sample_support_bundle(out_path=Path(args.out), client=args.client, locale=get_locale())
                print(f"Wrote sample AuthKit support bundle: {target}")
                return 0
            target = _write_support_bundle(
                client=args.client,
                out_path=Path(args.out),
                audit_limit=args.audit_limit,
                locale=get_locale(),
                fast=args.fast,
            )
            print(f"Wrote AuthKit support bundle: {target}")
            return 0

        if args.command == "ca":
            if not args.apply:
                print(f'Will configure client-level CA for {args.client}: "{args.cert}"')
                answer = input("Continue? [y/N] ").strip().lower()
                if answer not in {"y", "yes"}:
                    print("Cancelled.")
                    return 0
            print(configure_client_ca_certificate(client=args.client, ca_path=args.cert))
            print("Reopen the terminal and restart the target AI client.")
            return 0

        if args.command == "dns":
            if not args.flush:
                print("Specify --flush.")
                return 1
            if not args.apply and not _confirm("Flush Windows DNS resolver cache?"):
                return 0
            print(apply_direct_repair("flush-dns-cache", client="manual"))
            return 0

        if args.command == "winsock":
            if not args.reset:
                print("Specify --reset.")
                return 1
            if not args.apply and not _confirm("Reset Windows Winsock catalog? Windows restart is required."):
                return 0
            print(apply_direct_repair("winsock-reset", client="manual"))
            print("Restart Windows before retesting the target AI client.")
            return 0

        if args.command == "firewall":
            if not args.allow_outbound:
                print("Specify --allow-outbound.")
                return 1
            if not args.program:
                print("Specify --program with the target client executable path.")
                return 1
            if not args.apply and not _confirm(f'Add outbound firewall allow rule for "{args.program}"?'):
                return 0
            print(apply_direct_repair("allow-firewall-outbound", client=args.client, program_path=args.program))
            return 0

        if args.command == "login-status":
            login = check_login_status(args.client, locale=get_locale())
            if args.json:
                import json

                print(json.dumps(login.to_dict(), ensure_ascii=False, indent=2))
            else:
                print(f"客户端: {login.client}")
                print(f"状态: {'已登录' if login.logged_in else '未登录'}")
                print(f"说明: {login.summary}")
                if login.auth_path:
                    print(f"凭据: {login.auth_path}")
            return 0 if login.logged_in else 1
    except Exception as exc:  # noqa: BLE001
        print(f"错误: {exc}", file=sys.stderr)
        return 2

    return 0


def _apply_report_fixes(report, *, locale: str = "zh") -> int:
    applicable = [fix for fix in report.fixes if fix.auto_applicable]
    if not applicable:
        print(render_human(report, locale=locale))
        print("\n没有可自动应用的修复项，请参考上方命令手动处理。")
        return 1

    print(render_human(report, locale=locale))
    print("\n可自动应用的修复:")
    for fix in applicable:
        print(f"\n[{fix.fix_id}] {fix.description}")
        print(f"命令: {fix.command}")
        answer = input("执行此项? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("跳过。")
            continue
        try:
            message = apply_fix(report, fix)
            print(message)
        except ValueError as exc:
            print(f"跳过: {exc}")

    print("\n修复完成。请重新打开终端，并完全退出后重启目标 AI 客户端。")
    return 0


def _recent_audit_records(*, limit: int) -> list:
    records = load_audit_records()
    if limit <= 0:
        return []
    return list(reversed(records[-limit:]))


def _write_support_bundle(*, client: str, out_path: Path, audit_limit: int, locale: str, fast: bool = False) -> Path:
    report = run_diagnosis(client=client, locale=locale, fast=fast)
    records = _recent_audit_records(limit=audit_limit)
    bundle = _support_bundle_payload(
        client=client,
        report=report,
        records=records,
        audit_limit=audit_limit,
        locale=locale,
        fast=fast,
    )
    target = out_path.expanduser()
    _write_json_atomic(target, bundle)
    return target


def _write_sample_support_bundle(*, out_path: Path, client: str = "codex", locale: str = "zh") -> Path:
    report = DiagnosisReport(
        tool_version=__version__,
        platform="Windows",
        client=client,
        status=HealthStatus.WARNING,
        case=FailureCase.PROXY_PORT_MISMATCH,
        root_cause="Sample: AI client proxy configuration differs from the reachable local proxy.",
        confidence="sample",
        browser_explanation="Sample bundle for field handoff validation; not collected from a real machine.",
        layers=[
            LayerResult(
                name="proxy",
                ok=False,
                summary="Sample proxy mismatch",
                details={
                    "system_proxy": "http://127.0.0.1:7890",
                    "client_proxy": "http://127.0.0.1:9999",
                    "auth_path": r"%USERPROFILE%\.codex\auth.json",
                    "access_token_present": True,
                },
            ),
            LayerResult(
                name="online_session",
                ok=True,
                summary="Sample endpoint reachable",
                details={"score": 65, "path": "env_proxy", "api_key": "<redacted>"},
            ),
        ],
        fixes=[
            FixAction(
                fix_id="sync-system-proxy",
                description="Sample: sync Windows system proxy to the reachable local proxy.",
                command="authkit fix --apply --client codex",
                risk="medium",
                auto_applicable=True,
                admin_required=False,
                restart_required=False,
                rollback_supported=True,
            )
        ],
        notes=["sample_bundle=true", "Do not treat sample data as customer evidence."],
        official_guidance=[
            OfficialGuidance(
                title="Sample official guidance",
                steps=["Reopen the terminal.", "Restart the AI client.", "Retry login."],
                source="AuthKit sample",
                url="https://example.invalid/authkit/sample",
            )
        ],
    )
    audit = RepairAuditRecord(
        repair_id="sample-repair",
        timestamp="2026-07-01T00:00:00+00:00",
        fix_id="sync-system-proxy",
        client=client,
        before={"system_proxy": {"ProxyServer": "http://127.0.0.1:9999"}},
        after={"system_proxy": {"ProxyServer": "http://127.0.0.1:7890"}},
        changed_keys=["ProxyServer"],
        rollback_supported=True,
        status="success",
        risk="medium",
        admin_required=False,
        restart_required=False,
        message="Sample repair audit record.",
    )
    bundle = _support_bundle_payload(
        client=client,
        report=report,
        records=[audit],
        audit_limit=1,
        locale=locale,
        fast=True,
    )
    bundle["metadata"]["sample"] = True
    target = out_path.expanduser()
    _write_json_atomic(target, bundle)
    return target


def _support_bundle_payload(
    *,
    client: str,
    report: DiagnosisReport,
    records: list[RepairAuditRecord],
    audit_limit: int,
    locale: str,
    fast: bool,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "authkit_support_bundle",
        "client": client,
        "metadata": _support_bundle_metadata(
            client=client,
            audit_limit=audit_limit,
            locale=locale,
            fast=fast,
            diagnosis_status=report.status.value,
            diagnosis_case=report.case.value,
            audit_records_included=len(records),
        ),
        "privacy": {
            "redaction_applied": True,
            "rules": [
                "secret-like values are redacted",
                "URL credentials are redacted",
                "current user profile paths are normalized",
            ],
        },
        "diagnosis": _redact_support_bundle_value(report.to_dict()),
        "repair_audit": _redact_support_bundle_value([record.to_dict() for record in records]),
    }


def _validate_support_bundle(path: Path) -> list[str]:
    target = path.expanduser()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return [f"cannot read JSON: {exc}"]

    problems: list[str] = []
    if not isinstance(data, dict):
        return ["bundle root must be a JSON object"]
    if data.get("schema_version") != 1:
        problems.append("schema_version must be 1")
    if data.get("kind") != "authkit_support_bundle":
        problems.append("kind must be authkit_support_bundle")
    if data.get("client") not in CLIENT_CHOICES:
        problems.append("client must be a supported AuthKit client")

    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        problems.append("metadata must be an object")
        metadata = {}
    for key in ("bundle_id", "generated_at_utc", "authkit_version", "client", "locale", "audit_limit", "audit_records_included", "fast", "diagnosis_status", "diagnosis_case"):
        if key not in metadata:
            problems.append(f"metadata.{key} is required")
    if "hostname" in metadata or "username" in metadata:
        problems.append("metadata must not include hostname or username")
    if metadata.get("client") != data.get("client"):
        problems.append("metadata.client must match top-level client")

    privacy = data.get("privacy")
    if not isinstance(privacy, dict) or privacy.get("redaction_applied") is not True:
        problems.append("privacy.redaction_applied must be true")

    diagnosis = data.get("diagnosis")
    if not isinstance(diagnosis, dict):
        problems.append("diagnosis must be an object")
    else:
        for key in ("tool_version", "platform", "client", "status", "diagnosis", "layers", "fixes", "notes"):
            if key not in diagnosis:
                problems.append(f"diagnosis.{key} is required")

    repair_audit = data.get("repair_audit")
    if not isinstance(repair_audit, list):
        problems.append("repair_audit must be a list")
    else:
        for index, record in enumerate(repair_audit):
            if not isinstance(record, dict):
                problems.append(f"repair_audit[{index}] must be an object")
                continue
            for key in ("repair_id", "timestamp", "fix_id", "status", "rollback_supported", "risk", "admin_required", "restart_required"):
                if key not in record:
                    problems.append(f"repair_audit[{index}].{key} is required")

    serialized = json.dumps(data, ensure_ascii=False)
    lowered = serialized.lower()
    if "access_token" in lowered and "<redacted>" not in serialized:
        problems.append("bundle appears to contain unredacted token fields")
    if re.search(r"https?://[^/@\s]+:[^/@\s]+@", serialized):
        problems.append("bundle contains URL credentials")
    for forbidden in ("hostname", "username"):
        if f'"{forbidden}"' in lowered:
            problems.append(f"bundle contains forbidden key: {forbidden}")
    return problems


def _write_json_atomic(target: Path, data: object) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        with temp.open("w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(target)
    finally:
        try:
            if temp.exists():
                temp.unlink()
        except OSError:
            pass


def _support_bundle_metadata(
    *,
    client: str,
    audit_limit: int,
    locale: str,
    fast: bool,
    diagnosis_status: str,
    diagnosis_case: str,
    audit_records_included: int,
) -> dict[str, object]:
    return {
        "bundle_id": str(uuid.uuid4()),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "authkit_version": __version__,
        "client": client,
        "locale": locale,
        "audit_limit": audit_limit,
        "audit_records_included": audit_records_included,
        "fast": fast,
        "diagnosis_status": diagnosis_status,
        "diagnosis_case": diagnosis_case,
        "platform": sys.platform,
        "python_version": ".".join(str(part) for part in sys.version_info[:3]),
    }


def _redact_support_bundle_value(value, *, key: str = ""):
    if isinstance(value, dict):
        return {str(item_key): _redact_support_bundle_value(item_value, key=str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_redact_support_bundle_value(item, key=key) for item in value]
    if isinstance(value, tuple):
        return [_redact_support_bundle_value(item, key=key) for item in value]
    if isinstance(value, str):
        if _is_sensitive_bundle_key(key):
            return "<redacted>"
        return _redact_support_bundle_string(value)
    return value


def _is_sensitive_bundle_key(key: str) -> bool:
    lowered = key.lower()
    if lowered.endswith("_present") or lowered.endswith("_exists"):
        return False
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def _redact_support_bundle_string(value: str) -> str:
    redacted = URL_WITH_CREDENTIALS_RE.sub(r"\g<scheme><redacted>@", value)
    for label, root in _privacy_roots():
        if not root:
            continue
        redacted = _replace_path_root(redacted, root, f"%{label}%")
        redacted = _replace_path_root(redacted, root.replace("\\", "/"), f"%{label}%")
    return redacted


def _replace_path_root(value: str, root: str, replacement: str) -> str:
    return re.sub(re.escape(root), lambda _match: replacement, value, flags=re.IGNORECASE)


def _privacy_roots() -> list[tuple[str, str]]:
    roots: list[tuple[str, str]] = []
    for name in ("USERPROFILE", "APPDATA", "LOCALAPPDATA"):
        value = os.environ.get(name)
        if value:
            roots.append((name, str(Path(value))))
    home = str(Path.home())
    if home and all(root != home for _label, root in roots):
        roots.append(("USERPROFILE", home))
    roots.sort(key=lambda item: len(item[1]), reverse=True)
    return roots


def _format_audit_records(records: list, *, raw: bool = False) -> str:
    if not records:
        return "No AuthKit repair audit records were found."
    lines = ["AuthKit repair audit records:"]
    for record in records:
        changed = ", ".join(record.changed_keys) if record.changed_keys else "-"
        safety = (
            f"risk={record.risk}; admin={'yes' if record.admin_required else 'no'}; "
            f"restart={'yes' if record.restart_required else 'no'}; rollback={'yes' if record.rollback_supported else 'no'}"
        )
        lines.append(
            f"- {record.timestamp} | {record.client or '-'} | {record.fix_id} | "
            f"{record.status} | {safety} | changed={changed}"
        )
        if record.error:
            lines.append(f"  error: {_redact_audit_text(record.error, raw=raw)}")
        elif record.message:
            lines.append(f"  message: {_redact_audit_text(record.message, raw=raw)}")
    return "\n".join(lines)


def _audit_records_for_json(records: list[RepairAuditRecord], *, raw: bool = False) -> list[dict[str, object]]:
    data = [record.to_dict() for record in records]
    if raw:
        return data
    return _redact_support_bundle_value(data)


def _redact_audit_text(value: str, *, raw: bool = False) -> str:
    return value if raw else _redact_support_bundle_string(value)


def _format_rollback_preview(record: RepairAuditRecord) -> str:
    changed = ", ".join(record.changed_keys) if record.changed_keys else "-"
    safety = (
        f"risk={record.risk}; admin={'yes' if record.admin_required else 'no'}; "
        f"restart={'yes' if record.restart_required else 'no'}"
    )
    lines = [
        "Latest rollbackable AuthKit repair:",
        f"- repair_id: {record.repair_id}",
        f"- timestamp: {record.timestamp}",
        f"- client: {record.client or '-'}",
        f"- action: {record.fix_id}",
        f"- changed: {changed}",
        f"- safety: {safety}",
    ]
    if record.message:
        lines.append(f"- message: {record.message}")
    return "\n".join(lines)


def _confirm(prompt: str) -> bool:
    answer = input(f"{prompt} [y/N] ").strip().lower()
    if answer in {"y", "yes"}:
        return True
    print("Cancelled.")
    return False


if __name__ == "__main__":
    raise SystemExit(main())
