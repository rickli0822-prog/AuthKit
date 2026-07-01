"""修复与操作：同步代理、应用修复、设备码登录。"""

from authkit.repair.actions import find_codex_exe, launch_codex_device_auth
from authkit.repair.fixer import (
    apply_auto_fixes,
    apply_direct_repair,
    apply_fix,
    configure_client_ca_certificate,
    rollback_latest_repair,
    sync_proxy,
)

__all__ = [
    "apply_auto_fixes",
    "apply_direct_repair",
    "apply_fix",
    "configure_client_ca_certificate",
    "find_codex_exe",
    "launch_codex_device_auth",
    "rollback_latest_repair",
    "sync_proxy",
]
