"""轻量操作：设备码登录等。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from authkit.platform.subprocess import CREATE_NO_WINDOW


def find_codex_exe() -> Path | None:
    bins = list((Path(os.environ.get("LOCALAPPDATA", "")) / "OpenAI" / "Codex" / "bin").glob("*/codex.exe"))
    if bins:
        return bins[0]
    found = shutil.which("codex")
    return Path(found) if found else None


def launch_codex_device_auth() -> str:
    codex_exe = find_codex_exe()
    if not codex_exe:
        raise FileNotFoundError("未找到 codex.exe，请确认已安装 Codex CLI 或 Desktop。")

    # 设备码登录需要用户看到终端输出，单独弹出一个 cmd 窗口
    command = f'start "Codex 设备码登录" cmd /k ""{codex_exe}"" login --device-auth"'
    if sys.platform == "win32":
        subprocess.Popen(command, shell=True, creationflags=CREATE_NO_WINDOW)
    else:
        subprocess.Popen(command, shell=True)
    return f"已打开终端窗口，请在窗口中完成设备码登录。\n命令：{codex_exe} login --device-auth"
