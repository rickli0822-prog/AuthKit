# AuthKit

AuthKit 是面向 Windows 的 AI 客户端登录诊断与修复工具，当前重点服务 FDE 在部署 Codex、Claude Code、Gemini、Cursor、VS Code 等 AI 工具时的现场排障。

<p align="center">
  <img src="assets/authkit-icon.svg" alt="AuthKit" width="96" height="96" />
</p>

## 快速开始

```powershell
python -m pip install -e .
authkit gui
authkit check
authkit-shortcut
```

## 功能

- 检查 AI 客户端安装、登录凭据、OAuth 端点、回调端口、代理配置和网络画像。
- 提供可审计的基础修复动作，包括代理同步、DNS 缓存刷新、Winsock 重置、客户端 CA 配置和防火墙放行。
- GUI 支持中英文切换，配置保存在 `%USERPROFILE%\.authkit\settings.json`。
- CLI 支持机器可读 JSON、修复审计查询和 FDE 支持包导出。

## FDE Support Bundle

现场诊断或修复后，推荐导出支持包作为交接证据：

```powershell
authkit bundle --client codex --out .\authkit-support-bundle.json --fast
```

支持包包含脱敏后的诊断快照、最近修复审计记录和低隐私元数据。字段契约与隐私边界见 `docs/SUPPORT_BUNDLE.md`。

## Repair Rollback

回滚前先查看最近一次可回滚修复：

```powershell
authkit rollback --preview
```

确认目标、变更项和安全信息后再执行：

```powershell
authkit rollback --apply
```

## 图标

```powershell
python scripts\build_icon.py
```

生成 `assets/authkit.ico`、`assets/authkit-icon-512.png` 和 `assets/authkit-icon-48.png`。

## 开发

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
python scripts\release_smoke.py
```

## Windows Release

```powershell
python scripts\build_windows_installer.py
```

The build writes a portable Windows zip under `dist\windows\` and creates
`AuthKit_Setup_<version>.exe` when Inno Setup is installed.
