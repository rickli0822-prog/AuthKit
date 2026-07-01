# 脚本说明

本目录包含 Windows 下的启动与快捷方式辅助脚本，**无需单独安装**即可配合 `pip install -e .` 使用。

| 文件 | 用途 |
|------|------|
| `launch_gui.pyw` | **推荐**：`pythonw` 无黑窗启动 GUI（快捷方式目标参数） |
| `launch_gui.vbs` | 查找 `pythonw` 并调用 `launch_gui.pyw` |
| `authkit-gui.cmd` | 双击入口，内部调用 VBS |
| `create_desktop_shortcut.py` | 在桌面与开始菜单创建「AuthKit」快捷方式 |
| `create-desktop-shortcut.cmd` | 一键运行上述 Python 脚本 |
| `create-desktop-shortcut.ps1` | PowerShell 版快捷方式（指向 `.cmd`） |
| `launch-gui.ps1` | 开发用：`pip install -e .` 后启动 GUI |
| `check.ps1` | 开发用：安装并运行 `check` |

## 创建桌面快捷方式

```powershell
cd <项目根目录>
python scripts\create_desktop_shortcut.py
```

安装后推荐使用正式入口：

```powershell
authkit-shortcut
```

快捷方式目标为 `pythonw.exe`，参数为 `scripts\launch_gui.pyw`。
