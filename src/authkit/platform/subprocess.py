"""Windows 子进程工具：隐藏控制台窗口。"""

from __future__ import annotations

import subprocess
import sys
from typing import Any


CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def run_hidden(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
    if sys.platform == "win32" and "creationflags" not in kwargs:
        kwargs["creationflags"] = CREATE_NO_WINDOW
    return subprocess.run(*args, **kwargs)
