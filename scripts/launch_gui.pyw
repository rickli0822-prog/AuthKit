"""AuthKit GUI 启动器（供快捷方式 / pythonw 调用）。"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def _dialog_title() -> str:
    try:
        from authkit.brand import APP_WINDOW_TITLE_KEY
        from authkit.i18n import init_locale, t

        init_locale()
        return t(APP_WINDOW_TITLE_KEY)
    except Exception:
        return "Login Diagnostics"


def _show_error(message: str) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, _dialog_title(), 0x10)
    except Exception:
        pass


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    try:
        from authkit.ui.app import main as gui_main

        return gui_main()
    except Exception as exc:
        log_path = Path(os.environ.get("TEMP", ".")) / "authkit-gui.log"
        log_path.write_text(traceback.format_exc(), encoding="utf-8")
        _show_error(
            f"启动失败：{exc}\n\n"
            f"详细日志已保存到：\n{log_path}\n\n"
            "请确认已安装 Python 3.10+。"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
