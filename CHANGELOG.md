# Changelog

本文件记录各版本的重要变更。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [Unreleased]

## [0.3.0] - 2026-06-30

### Changed

- 品牌更名为 **AuthKit（AuthKit）**
- Python 包名 `ai_login_doctor` → `authkit`
- CLI 命令 `authkit` / `authkit-gui`
- 自定义应用图标（双径合一）与桌面快捷方式图标

## [0.2.0] - 2026-06-30

### Added

- 登录状态检查层（读取 `~/.codex/auth.json`，不发起网络请求）
- CLI 子命令 `login-status`
- GUI：**检查登录**、**设备码登录**（Codex）
- 回调端口占用进程名与冲突提示（如 wslrelay、Cursor）
- 开源文档：`CONTRIBUTING.md`、`docs/`、GitHub Issue 模板与 CI

### Changed

- 源码按职责拆分为 `core` / `checks` / `platform` / `repair` / `ui` 子包
- GUI 打开后不再自动诊断，需手动点击「开始诊断」
- 网络健康且已登录时，不再显示无关修复建议

### Fixed

- Windows 快捷方式双击闪退（`.cmd` CRLF、`pythonw` 启动）
- GUI 子进程隐藏控制台黑窗

## [0.1.0] - 2026-06-30

### Added

- 初始版本：代理/OAuth/回调端口五层诊断
- CLI：`check`、`fix`、`sync`、`gui`
- 图形界面与桌面快捷方式创建脚本
- Case A–F 故障分类与自动修复项

[Unreleased]: https://github.com/YOUR_USERNAME/authkit/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/YOUR_USERNAME/authkit/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/YOUR_USERNAME/authkit/releases/tag/v0.1.0
