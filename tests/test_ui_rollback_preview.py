from authkit.i18n import set_locale
from authkit.repair.audit import RepairAuditRecord
from authkit.ui.app import _format_gui_rollback_preview


def test_gui_rollback_preview_includes_target_changes_and_safety_metadata():
    set_locale("en", persist=False)
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

    rendered = _format_gui_rollback_preview(record)

    assert "ID: r1" in rendered
    assert "Action: sync-system-proxy" in rendered
    assert "Changed keys: ProxyEnable, ProxyServer" in rendered
    assert "Risk: medium" in rendered
    assert "Admin: No" in rendered
    assert "Restart: No" in rendered
    assert "Rollback: Yes" in rendered
    assert "Updated Windows system proxy" in rendered
