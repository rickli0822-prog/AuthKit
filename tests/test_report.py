from authkit.models import DiagnosisReport, FailureCase, FixAction, HealthStatus, LayerResult, OfficialGuidance
from authkit.report import render_human


def test_render_human_fix_safety_metadata():
    report = DiagnosisReport(
        tool_version="0.0.0",
        platform="Windows 11",
        client="codex",
        status=HealthStatus.UNHEALTHY,
        case=FailureCase.UNKNOWN,
        root_cause="Network blocked.",
        confidence="medium",
        browser_explanation="test",
        layers=[],
        fixes=[
            FixAction(
                fix_id="winsock-reset",
                description="Reset Winsock",
                command="authkit winsock --reset --apply",
                risk="medium",
                admin_required=True,
                restart_required=True,
                rollback_supported=False,
            )
        ],
    )

    rendered = render_human(report, locale="en")

    assert "Reset Winsock" in rendered
    assert "Safety: risk medium | admin yes | restart yes | rollback no" in rendered
    assert "authkit winsock --reset --apply" in rendered


def test_render_human_english_headings():
    report = DiagnosisReport(
        tool_version="0.0.0",
        platform="Windows 11",
        client="codex",
        status=HealthStatus.HEALTHY,
        case=FailureCase.NONE,
        root_cause="No obvious proxy/OAuth configuration issue was detected.",
        confidence="high",
        browser_explanation="Browsers use the Windows system proxy.",
        layers=[
            LayerResult(
                name="system_proxy",
                ok=True,
                summary="System proxy: http://127.0.0.1:7890, port reachable",
            )
        ],
        fixes=[],
        official_guidance=[
            OfficialGuidance(
                title="Official path: recover Codex sign-in",
                steps=["Run codex login --device-auth", "Run AuthKit again"],
                source="OpenAI Codex CLI Reference",
                url="https://developers.openai.com/codex/cli/reference/",
            )
        ],
    )

    rendered = render_human(report, locale="en")

    assert "Platform: Windows 11 | Client: codex" in rendered
    assert "Diagnosis: No obvious issue" in rendered
    assert "Root cause:" in rendered
    assert "Suggested fixes:" in rendered
    assert "No fix is currently needed." in rendered
    assert "Official quick guidance:" in rendered
    assert "Run codex login --device-auth" in rendered
    assert "平台:" not in rendered
