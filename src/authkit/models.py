from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    WARNING = "warning"


class FailureCase(str, Enum):
    NONE = "none"
    PROXY_PORT_MISMATCH = "A"
    DEAD_PROXY_PORT = "B"
    LOCALHOST_PROXIED = "C"
    CALLBACK_PORT_CONFLICT = "D"
    TLS_OR_CA = "E"
    HEADLESS_FALLBACK = "F"
    UNKNOWN = "unknown"


@dataclass
class ProxyEndpoint:
    scheme: str = "http"
    host: str = ""
    port: int = 0
    raw: str = ""

    @property
    def is_set(self) -> bool:
        return bool(self.host and self.port)

    @property
    def url(self) -> str:
        if not self.is_set:
            return ""
        return f"{self.scheme}://{self.host}:{self.port}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LayerResult:
    name: str
    ok: bool
    summary: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ok": self.ok,
            "summary": self.summary,
            "details": self.details,
        }


@dataclass
class FixAction:
    fix_id: str
    description: str
    command: str
    risk: str = "low"
    auto_applicable: bool = False
    admin_required: bool = False
    restart_required: bool = False
    rollback_supported: bool = False
    audit_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OfficialGuidance:
    title: str
    steps: list[str]
    source: str
    url: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DiagnosisReport:
    tool_version: str
    platform: str
    client: str
    status: HealthStatus
    case: FailureCase
    root_cause: str
    confidence: str
    browser_explanation: str
    layers: list[LayerResult] = field(default_factory=list)
    fixes: list[FixAction] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    official_guidance: list[OfficialGuidance] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_version": self.tool_version,
            "platform": self.platform,
            "client": self.client,
            "status": self.status.value,
            "diagnosis": {
                "case": self.case.value,
                "root_cause": self.root_cause,
                "confidence": self.confidence,
                "browser_explanation": self.browser_explanation,
            },
            "layers": [layer.to_dict() for layer in self.layers],
            "fixes": [fix.to_dict() for fix in self.fixes],
            "notes": self.notes,
            "official_guidance": [guidance.to_dict() for guidance in self.official_guidance],
        }
