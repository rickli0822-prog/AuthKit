from __future__ import annotations

import json

from authkit.brand import APP_NAME
from authkit.models import DiagnosisReport


CASE_TITLES = {
    "zh": {
        "none": "未发现明显问题",
        "A": "Case A — 代理端口不一致",
        "B": "Case B — 代理端口失效",
        "C": "Case C — localhost 未绕过代理",
        "D": "Case D — OAuth 回调端口冲突",
        "E": "Case E — TLS/证书问题",
        "F": "Case F — 需要无头/设备码登录",
        "unknown": "未知网络问题",
    },
    "en": {
        "none": "No obvious issue",
        "A": "Case A — proxy port mismatch",
        "B": "Case B — dead proxy port",
        "C": "Case C — localhost not bypassed",
        "D": "Case D — OAuth callback port conflict",
        "E": "Case E — TLS / certificate issue",
        "F": "Case F — headless / device code login required",
        "unknown": "Unknown network issue",
    },
}


def render_human(report: DiagnosisReport, *, locale: str = "zh") -> str:
    case_titles = CASE_TITLES.get(locale, CASE_TITLES["zh"])
    lines = [
        f"{APP_NAME} v{report.tool_version}",
        _text(locale, "platform_client", platform=report.platform, client=report.client),
        "",
        _text(locale, "status", status=report.status.value.upper()),
        _text(locale, "diagnosis", diagnosis=case_titles.get(report.case.value, report.case.value)),
        _text(locale, "confidence", confidence=report.confidence),
        "",
        _text(locale, "root_cause"),
        f"  {report.root_cause}",
        "",
        _text(locale, "explanation"),
        f"  {report.browser_explanation}",
        "",
        _text(locale, "layers"),
    ]

    for layer in report.layers:
        mark = "OK" if layer.ok else "FAIL"
        lines.append(f"  [{mark}] {layer.name}: {layer.summary}")

    if report.notes:
        lines.extend(["", _text(locale, "notes")])
        for note in report.notes:
            lines.append(f"  - {note}")

    if report.fixes:
        lines.extend(["", _text(locale, "fixes")])
        for index, fix in enumerate(report.fixes, start=1):
            lines.append(f"  [{index}] {fix.description}")
            lines.append(f"      {_fix_safety_text(fix, locale=locale)}")
            lines.append(f"      {fix.command}")
    else:
        lines.extend(["", _text(locale, "fixes"), f"  {_text(locale, 'no_fix')}"])

    if report.official_guidance:
        lines.extend(["", _text(locale, "official_guidance")])
        for index, guidance in enumerate(report.official_guidance, start=1):
            lines.append(f"  [{index}] {guidance.title}")
            for step in guidance.steps:
                lines.append(f"      - {step}")
            lines.append(f"      {guidance.source}: {guidance.url}")

    lines.extend(["", _text(locale, "next_steps"), *[f"  {line}" for line in _next_steps(locale)]])
    return "\n".join(lines)


def render_json(report: DiagnosisReport) -> str:
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)


def _fix_safety_text(fix, *, locale: str) -> str:
    if locale != "en":
        return (
            f"安全: 风险 {fix.risk} | 管理员 {_yes_no(fix.admin_required, locale=locale)} | "
            f"重启 {_yes_no(fix.restart_required, locale=locale)} | 可回滚 {_yes_no(fix.rollback_supported, locale=locale)}"
        )
    return _text(
        locale,
        "fix_safety",
        risk=fix.risk,
        admin=_yes_no(fix.admin_required, locale=locale),
        restart=_yes_no(fix.restart_required, locale=locale),
        rollback=_yes_no(fix.rollback_supported, locale=locale),
    )


def _yes_no(value: bool, *, locale: str) -> str:
    if locale == "en":
        return "yes" if value else "no"
    return "是" if value else "否"


def _text(locale: str, key: str, **kwargs: object) -> str:
    catalog = {
        "zh": {
            "platform_client": "平台: {platform} | 客户端: {client}",
            "status": "状态: {status}",
            "diagnosis": "诊断: {diagnosis}",
            "confidence": "置信度: {confidence}",
            "root_cause": "根因:",
            "explanation": "说明:",
            "layers": "检查层:",
            "notes": "备注:",
            "fixes": "建议修复:",
            "official_guidance": "官方快速指导:",
            "no_fix": "当前无需修复。",
            "next_steps": "下一步:",
        },
        "en": {
            "platform_client": "Platform: {platform} | Client: {client}",
            "status": "Status: {status}",
            "diagnosis": "Diagnosis: {diagnosis}",
            "confidence": "Confidence: {confidence}",
            "root_cause": "Root cause:",
            "explanation": "Explanation:",
            "layers": "Checks:",
            "notes": "Notes:",
            "fixes": "Suggested fixes:",
            "fix_safety": "Safety: risk {risk} | admin {admin} | restart {restart} | rollback {rollback}",
            "official_guidance": "Official quick guidance:",
            "no_fix": "No fix is currently needed.",
            "next_steps": "Next steps:",
        },
    }
    text = catalog.get(locale, catalog["zh"]).get(key, catalog["zh"].get(key, key))
    return text.format(**kwargs) if kwargs else text


def _next_steps(locale: str) -> list[str]:
    if locale == "en":
        return [
            "1. Run authkit fix --apply to apply automatic fixes one by one",
            "2. Fully quit and restart the target AI client",
            "3. Try signing in again; if it still fails, run codex login --device-auth",
        ]
    return [
        "1. 运行 authkit fix --apply 逐项应用自动修复",
        "2. 完全退出并重启目标 AI 客户端",
        "3. 重新尝试登录；仍失败可执行 codex login --device-auth",
    ]
