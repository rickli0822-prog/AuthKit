"""Windows 平台能力：系统代理、隐藏子进程。"""

from authkit.platform.proxy import (
    clear_user_env_proxy,
    format_env_snapshot,
    parse_proxy_url,
    primary_env_proxy,
    read_env_proxy,
    read_system_proxy,
    read_user_env_values,
    restore_user_env_values,
    set_user_env_values,
    set_user_env_proxy,
    set_user_no_proxy,
)
from authkit.platform.subprocess import CREATE_NO_WINDOW, run_hidden

__all__ = [
    "CREATE_NO_WINDOW",
    "clear_user_env_proxy",
    "format_env_snapshot",
    "parse_proxy_url",
    "primary_env_proxy",
    "read_env_proxy",
    "read_system_proxy",
    "read_user_env_values",
    "restore_user_env_values",
    "run_hidden",
    "set_user_env_values",
    "set_user_env_proxy",
    "set_user_no_proxy",
]
