import json
import uuid

from authkit import __version__
from authkit.models import DiagnosisReport, FailureCase, HealthStatus, ProxyEndpoint
from authkit.cli import (
    _audit_records_for_json,
    _format_audit_records,
    _format_rollback_preview,
    _recent_audit_records,
    _redact_support_bundle_value,
    _validate_support_bundle,
    _write_json_atomic,
    _write_sample_support_bundle,
    _write_support_bundle,
)
from authkit.repair.audit import (
    RepairAuditRecord,
    append_audit_record,
    json_safe,
    latest_rollbackable_record,
    load_audit_records,
)


def test_append_audit_record_writes_jsonl(tmp_path):
    path = tmp_path / "repair-log.jsonl"
    record = RepairAuditRecord(
        repair_id="abc",
        timestamp="2026-07-01T00:00:00+00:00",
        fix_id="sync-system-proxy",
        client="codex",
        before={"system_proxy": {"enabled": False}},
        after={"system_proxy": {"enabled": True}},
        changed_keys=["ProxyEnable"],
        rollback_supported=True,
        status="success",
        message="ok",
    )

    written = append_audit_record(record, path=path)

    assert written == path
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["repair_id"] == "abc"
    assert rows[0]["fix_id"] == "sync-system-proxy"
    assert rows[0]["risk"] == "low"
    assert rows[0]["admin_required"] is False
    assert rows[0]["restart_required"] is False
    assert rows[0]["schema_version"] == 1
    assert rows[0]["authkit_version"] == __version__
    assert rows[0]["platform"]
    assert rows[0]["before"]["system_proxy"]["enabled"] is False


def test_load_audit_record_defaults_new_metadata_fields(tmp_path):
    path = tmp_path / "repair-log.jsonl"
    path.write_text(
        json.dumps(
            {
                "repair_id": "legacy",
                "timestamp": "2026-07-01T00:00:00+00:00",
                "fix_id": "sync-env-proxy",
                "client": "codex",
                "before": {},
                "after": {},
                "changed_keys": [],
                "rollback_supported": True,
                "status": "success",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    record = load_audit_records(path=path)[0]

    assert record.risk == "low"
    assert record.admin_required is False
    assert record.restart_required is False
    assert record.schema_version == 1
    assert record.authkit_version == __version__
    assert record.platform


def test_json_safe_serializes_proxy_endpoint():
    data = json_safe({"endpoint": ProxyEndpoint("http", "127.0.0.1", 7890)})

    assert data["endpoint"]["host"] == "127.0.0.1"
    assert data["endpoint"]["port"] == 7890


def test_append_audit_record_serializes_non_json_snapshot_values(tmp_path):
    path = tmp_path / "repair-log.jsonl"
    record = RepairAuditRecord(
        repair_id="json-safe",
        timestamp="2026-07-01T00:00:00+00:00",
        fix_id="sync-env-proxy",
        client="codex",
        before={"endpoint": ProxyEndpoint("http", "127.0.0.1", 7890)},
        after={"path": tmp_path / "authkit-support-bundle.json"},
        changed_keys=["HTTP_PROXY"],
        rollback_supported=True,
        status="success",
    )

    append_audit_record(record, path=path)

    row = json.loads(path.read_text(encoding="utf-8").strip())
    assert row["before"]["endpoint"]["host"] == "127.0.0.1"
    assert row["before"]["endpoint"]["port"] == 7890
    assert row["after"]["path"].endswith("authkit-support-bundle.json")


def test_load_audit_records_skips_invalid_lines_and_finds_latest_rollbackable(tmp_path):
    path = tmp_path / "repair-log.jsonl"
    append_audit_record(
        RepairAuditRecord(
            repair_id="old",
            timestamp="2026-07-01T00:00:00+00:00",
            fix_id="sync-env-proxy",
            client="codex",
            before={"user_env": {"HTTP_PROXY": None}},
            after={},
            changed_keys=["HTTP_PROXY"],
            rollback_supported=True,
            status="success",
        ),
        path=path,
    )
    path.write_text(path.read_text(encoding="utf-8") + "{bad json}\n", encoding="utf-8")
    append_audit_record(
        RepairAuditRecord(
            repair_id="new",
            timestamp="2026-07-01T00:01:00+00:00",
            fix_id="sync-system-proxy",
            client="codex",
            before={"system_proxy": {"enabled": False}},
            after={},
            changed_keys=["ProxyEnable"],
            rollback_supported=True,
            status="success",
        ),
        path=path,
    )

    records = load_audit_records(path=path)
    latest = latest_rollbackable_record(path=path)

    assert [record.repair_id for record in records] == ["old", "new"]
    assert latest is not None
    assert latest.repair_id == "new"


def test_load_audit_records_tolerates_malformed_legacy_field_types(tmp_path):
    path = tmp_path / "repair-log.jsonl"
    path.write_text(
        "\n".join(
            [
                "[]",
                json.dumps(
                    {
                        "repair_id": "legacy",
                        "timestamp": "2026-07-01T00:00:00+00:00",
                        "fix_id": "sync-env-proxy",
                        "client": "codex",
                        "before": "not-a-dict",
                        "after": ["also", "not", "a", "dict"],
                        "changed_keys": "HTTP_PROXY",
                        "rollback_supported": True,
                        "status": "success",
                        "warnings": "restart terminal",
                        "schema_version": "bad",
                    }
                ),
                '{"repair_id": ',
            ]
        ),
        encoding="utf-8",
    )

    records = load_audit_records(path=path)

    assert len(records) == 1
    assert records[0].repair_id == "legacy"
    assert records[0].before == {}
    assert records[0].after == {}
    assert records[0].changed_keys == ["HTTP_PROXY"]
    assert records[0].warnings == ["restart terminal"]
    assert records[0].schema_version == 1


def test_cli_recent_audit_records_returns_latest_first(tmp_path, monkeypatch):
    path = tmp_path / "repair-log.jsonl"
    for index in range(3):
        append_audit_record(
            RepairAuditRecord(
                repair_id=f"r{index}",
                timestamp=f"2026-07-01T00:0{index}:00+00:00",
                fix_id="sync-env-proxy",
                client="codex",
                before={},
                after={},
                changed_keys=[f"KEY{index}"],
                rollback_supported=True,
                status="success",
            ),
            path=path,
        )
    monkeypatch.setattr("authkit.cli.load_audit_records", lambda: load_audit_records(path=path))

    records = _recent_audit_records(limit=2)

    assert [record.repair_id for record in records] == ["r2", "r1"]


def test_cli_format_audit_records_includes_safety_metadata():
    record = RepairAuditRecord(
        repair_id="r1",
        timestamp="2026-07-01T00:00:00+00:00",
        fix_id="winsock-reset",
        client="manual",
        before={},
        after={},
        changed_keys=["WinsockCatalog"],
        rollback_supported=False,
        status="failed",
        risk="medium",
        admin_required=True,
        restart_required=True,
        error="requires Administrator terminal",
    )

    rendered = _format_audit_records([record])

    assert "winsock-reset" in rendered
    assert "risk=medium; admin=yes; restart=yes; rollback=no" in rendered
    assert "changed=WinsockCatalog" in rendered
    assert "requires Administrator terminal" in rendered


def test_cli_format_audit_records_redacts_text_output_by_default(monkeypatch):
    monkeypatch.setenv("USERPROFILE", r"C:\Users\Rick")
    record = RepairAuditRecord(
        repair_id="r1",
        timestamp="2026-07-01T00:00:00+00:00",
        fix_id="sync-env-proxy",
        client="manual",
        before={},
        after={},
        changed_keys=["HTTP_PROXY"],
        rollback_supported=True,
        status="failed",
        error=r"failed for http://user:pass@127.0.0.1:7890 at C:\Users\Rick\.codex\auth.json",
    )

    redacted = _format_audit_records([record])
    raw = _format_audit_records([record], raw=True)

    assert "http://<redacted>@127.0.0.1:7890" in redacted
    assert r"%USERPROFILE%\.codex\auth.json" in redacted
    assert "user:pass" not in redacted
    assert "http://user:pass@127.0.0.1:7890" in raw
    assert r"C:\Users\Rick\.codex\auth.json" in raw


def test_cli_audit_json_redacts_by_default_and_allows_raw(monkeypatch):
    monkeypatch.setenv("USERPROFILE", r"C:\Users\Rick")
    record = RepairAuditRecord(
        repair_id="r1",
        timestamp="2026-07-01T00:00:00+00:00",
        fix_id="sync-env-proxy",
        client="codex",
        before={"user_env": {"HTTP_PROXY": "http://user:pass@127.0.0.1:7890"}},
        after={"auth_path": r"C:\Users\Rick\.codex\auth.json", "access_token": "secret-token"},
        changed_keys=["HTTP_PROXY"],
        rollback_supported=True,
        status="success",
    )

    redacted = _audit_records_for_json([record])
    raw = _audit_records_for_json([record], raw=True)

    assert redacted[0]["before"]["user_env"]["HTTP_PROXY"] == "http://<redacted>@127.0.0.1:7890"
    assert redacted[0]["after"]["auth_path"] == r"%USERPROFILE%\.codex\auth.json"
    assert redacted[0]["after"]["access_token"] == "<redacted>"
    assert raw[0]["before"]["user_env"]["HTTP_PROXY"] == "http://user:pass@127.0.0.1:7890"
    assert raw[0]["after"]["access_token"] == "secret-token"


def test_cli_format_rollback_preview_shows_target_and_safety_metadata():
    record = RepairAuditRecord(
        repair_id="r1",
        timestamp="2026-07-01T00:00:00+00:00",
        fix_id="sync-system-proxy",
        client="codex",
        before={"system_proxy": {"enabled": False}},
        after={},
        changed_keys=["ProxyEnable", "ProxyServer"],
        rollback_supported=True,
        status="success",
        risk="medium",
        admin_required=False,
        restart_required=False,
        message="Updated Windows system proxy",
    )

    rendered = _format_rollback_preview(record)

    assert "Latest rollbackable AuthKit repair:" in rendered
    assert "- repair_id: r1" in rendered
    assert "- action: sync-system-proxy" in rendered
    assert "- changed: ProxyEnable, ProxyServer" in rendered
    assert "- safety: risk=medium; admin=no; restart=no" in rendered
    assert "- message: Updated Windows system proxy" in rendered


def test_cli_write_support_bundle_includes_diagnosis_and_audit(tmp_path, monkeypatch):
    report = DiagnosisReport(
        tool_version="test",
        platform="Windows",
        client="codex",
        status=HealthStatus.HEALTHY,
        case=FailureCase.NONE,
        root_cause="ok",
        confidence="high",
        browser_explanation="test",
    )
    audit = RepairAuditRecord(
        repair_id="r1",
        timestamp="2026-07-01T00:00:00+00:00",
        fix_id="sync-env-proxy",
        client="codex",
        before={},
        after={},
        changed_keys=["HTTP_PROXY"],
        rollback_supported=True,
        status="success",
    )
    calls = []

    def fake_run_diagnosis(*, client, locale, fast=False):
        calls.append({"client": client, "locale": locale, "fast": fast})
        return report

    monkeypatch.setattr("authkit.cli.run_diagnosis", fake_run_diagnosis)
    monkeypatch.setattr("authkit.cli._recent_audit_records", lambda *, limit: [audit])

    target = _write_support_bundle(
        client="codex",
        out_path=tmp_path / "nested" / "bundle.json",
        audit_limit=5,
        locale="en",
    )

    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["kind"] == "authkit_support_bundle"
    assert uuid.UUID(data["metadata"]["bundle_id"])
    assert data["metadata"]["authkit_version"]
    assert data["metadata"]["generated_at_utc"].endswith("+00:00")
    assert data["metadata"]["client"] == "codex"
    assert data["metadata"]["locale"] == "en"
    assert data["metadata"]["audit_limit"] == 5
    assert data["metadata"]["audit_records_included"] == 1
    assert data["metadata"]["fast"] is False
    assert data["metadata"]["diagnosis_status"] == "healthy"
    assert data["metadata"]["diagnosis_case"] == "none"
    assert "hostname" not in data["metadata"]
    assert "username" not in data["metadata"]
    assert data["privacy"]["redaction_applied"] is True
    assert data["client"] == "codex"
    assert data["diagnosis"]["status"] == "healthy"
    assert data["repair_audit"][0]["fix_id"] == "sync-env-proxy"
    assert calls == [{"client": "codex", "locale": "en", "fast": False}]


def test_cli_write_support_bundle_can_use_fast_diagnosis(tmp_path, monkeypatch):
    report = DiagnosisReport(
        tool_version="test",
        platform="Windows",
        client="codex",
        status=HealthStatus.HEALTHY,
        case=FailureCase.NONE,
        root_cause="ok",
        confidence="high",
        browser_explanation="test",
    )
    calls = []

    def fake_run_diagnosis(*, client, locale, fast=False):
        calls.append({"client": client, "locale": locale, "fast": fast})
        return report

    monkeypatch.setattr("authkit.cli.run_diagnosis", fake_run_diagnosis)
    monkeypatch.setattr("authkit.cli._recent_audit_records", lambda *, limit: [])

    target = _write_support_bundle(
        client="codex",
        out_path=tmp_path / "bundle-fast.json",
        audit_limit=0,
        locale="zh",
        fast=True,
    )

    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["metadata"]["fast"] is True
    assert calls == [{"client": "codex", "locale": "zh", "fast": True}]


def test_cli_write_sample_support_bundle_is_valid_and_redacted(tmp_path):
    target = _write_sample_support_bundle(out_path=tmp_path / "sample-bundle.json", client="codex", locale="en")

    data = json.loads(target.read_text(encoding="utf-8"))
    problems = _validate_support_bundle(target)

    assert problems == []
    assert data["kind"] == "authkit_support_bundle"
    assert data["metadata"]["sample"] is True
    assert data["metadata"]["fast"] is True
    assert data["repair_audit"][0]["repair_id"] == "sample-repair"
    assert data["diagnosis"]["layers"][1]["details"]["api_key"] == "<redacted>"


def test_validate_support_bundle_reports_missing_required_fields(tmp_path):
    target = tmp_path / "bad-bundle.json"
    target.write_text(json.dumps({"kind": "wrong"}), encoding="utf-8")

    problems = _validate_support_bundle(target)

    assert "schema_version must be 1" in problems
    assert "kind must be authkit_support_bundle" in problems
    assert "metadata must be an object" in problems
    assert "diagnosis must be an object" in problems
    assert "repair_audit must be a list" in problems


def test_validate_support_bundle_reports_privacy_leaks(tmp_path):
    target = tmp_path / "leaky-bundle.json"
    data = {
        "schema_version": 1,
        "kind": "authkit_support_bundle",
        "client": "codex",
        "metadata": {
            "bundle_id": "id",
            "generated_at_utc": "2026-07-01T00:00:00+00:00",
            "authkit_version": "0.4.0",
            "client": "codex",
            "locale": "en",
            "audit_limit": 1,
            "audit_records_included": 0,
            "fast": True,
            "diagnosis_status": "healthy",
            "diagnosis_case": "none",
            "hostname": "field-pc",
        },
        "privacy": {"redaction_applied": True},
        "diagnosis": {
            "tool_version": "0.4.0",
            "platform": "Windows",
            "client": "codex",
            "status": "healthy",
            "diagnosis": {"case": "none"},
            "layers": [{"details": {"proxy": "http://user:pass@127.0.0.1:7890"}}],
            "fixes": [],
            "notes": [],
        },
        "repair_audit": [],
    }
    target.write_text(json.dumps(data), encoding="utf-8")

    problems = _validate_support_bundle(target)

    assert "metadata must not include hostname or username" in problems
    assert "bundle contains URL credentials" in problems
    assert "bundle contains forbidden key: hostname" in problems


def test_support_bundle_redacts_paths_url_credentials_and_secret_values(monkeypatch):
    monkeypatch.setenv("USERPROFILE", r"C:\Users\Rick")
    monkeypatch.setenv("APPDATA", r"C:\Users\Rick\AppData\Roaming")
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\Rick\AppData\Local")

    redacted = _redact_support_bundle_value(
        {
            "auth_path": r"C:\Users\Rick\.codex\auth.json",
            "proxy": "http://user:pass@127.0.0.1:7890",
            "access_token": "secret-token",
            "env_api_key_present": True,
            "items": [
                r"C:/Users/Rick/AppData/Roaming/Cursor/User/settings.json",
                r"c:\users\rick\.codex\auth.json",
                r"c:/users/rick/appdata/local/OpenAI/Codex/log.txt",
            ],
        }
    )

    assert redacted["auth_path"] == r"%USERPROFILE%\.codex\auth.json"
    assert redacted["proxy"] == "http://<redacted>@127.0.0.1:7890"
    assert redacted["access_token"] == "<redacted>"
    assert redacted["env_api_key_present"] is True
    assert redacted["items"][0] == "%APPDATA%/Cursor/User/settings.json"
    assert redacted["items"][1] == r"%USERPROFILE%\.codex\auth.json"
    assert redacted["items"][2] == "%LOCALAPPDATA%/OpenAI/Codex/log.txt"


def test_write_json_atomic_replaces_target_with_complete_json(tmp_path, monkeypatch):
    target = tmp_path / "bundle.json"
    fsync_calls = []

    monkeypatch.setattr("authkit.cli.os.fsync", lambda fileno: fsync_calls.append(fileno))

    _write_json_atomic(target, {"ok": True})

    assert json.loads(target.read_text(encoding="utf-8")) == {"ok": True}
    assert len(fsync_calls) == 1
    assert not list(tmp_path.glob(".*.tmp"))


def test_write_json_atomic_keeps_existing_target_when_temp_write_fails(tmp_path, monkeypatch):
    target = tmp_path / "bundle.json"
    target.write_text('{"existing": true}', encoding="utf-8")

    real_open = type(target).open

    def fail_open(self, *args, **kwargs):
        if self.name.endswith(".tmp"):
            raise OSError("disk full")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr("pathlib.Path.open", fail_open)

    try:
        _write_json_atomic(target, {"ok": True})
    except OSError as exc:
        assert "disk full" in str(exc)
    else:
        raise AssertionError("expected temp write failure")

    assert json.loads(target.read_text(encoding="utf-8")) == {"existing": True}
    assert not list(tmp_path.glob(".*.tmp"))
