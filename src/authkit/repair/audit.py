from __future__ import annotations

import json
import os
import sys
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from authkit import __version__


AUDIT_DIR_NAME = "AuthKit"
AUDIT_FILE_NAME = "repair-log.jsonl"
AUDIT_SCHEMA_VERSION = 1


@dataclass
class RepairAuditRecord:
    repair_id: str
    timestamp: str
    fix_id: str
    client: str
    before: dict[str, Any]
    after: dict[str, Any]
    changed_keys: list[str]
    rollback_supported: bool
    status: str
    risk: str = "low"
    admin_required: bool = False
    restart_required: bool = False
    message: str = ""
    error: str = ""
    warnings: list[str] = field(default_factory=list)
    schema_version: int = AUDIT_SCHEMA_VERSION
    authkit_version: str = __version__
    platform: str = sys.platform

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RepairAuditRecord":
        return cls(
            repair_id=str(data.get("repair_id", "")),
            timestamp=str(data.get("timestamp", "")),
            fix_id=str(data.get("fix_id", "")),
            client=str(data.get("client", "")),
            before=_dict_or_empty(data.get("before")),
            after=_dict_or_empty(data.get("after")),
            changed_keys=_string_list(data.get("changed_keys")),
            rollback_supported=bool(data.get("rollback_supported", False)),
            status=str(data.get("status", "")),
            risk=str(data.get("risk", "low")),
            admin_required=bool(data.get("admin_required", False)),
            restart_required=bool(data.get("restart_required", False)),
            message=str(data.get("message", "")),
            error=str(data.get("error", "")),
            warnings=_string_list(data.get("warnings")),
            schema_version=_int_or_default(data.get("schema_version"), AUDIT_SCHEMA_VERSION),
            authkit_version=str(data.get("authkit_version") or __version__),
            platform=str(data.get("platform") or sys.platform),
        )


def default_audit_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / AUDIT_DIR_NAME / AUDIT_FILE_NAME


def new_repair_id() -> str:
    return uuid.uuid4().hex


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_audit_record(record: RepairAuditRecord, *, path: Path | None = None) -> Path:
    target = path or default_audit_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(json_safe(record.to_dict()), ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return target


def load_audit_records(*, path: Path | None = None) -> list[RepairAuditRecord]:
    target = path or default_audit_path()
    if not target.exists():
        return []
    records: list[RepairAuditRecord] = []
    for line in target.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            try:
                records.append(RepairAuditRecord.from_dict(data))
            except (TypeError, ValueError):
                continue
    return records


def latest_rollbackable_record(*, path: Path | None = None) -> RepairAuditRecord | None:
    for record in reversed(load_audit_records(path=path)):
        if record.status == "success" and record.rollback_supported and record.before:
            return record
    return None


def json_safe(value: Any) -> Any:
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return json_safe(value.to_dict())
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


def _int_or_default(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
