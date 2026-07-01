# 贡献指南

感谢你愿意改进 **authkit**。本项目面向 Windows 下 AI 客户端登录与代理问题，欢迎提交 Issue 与 Pull Request。

## 开发环境

要求：**Windows 10/11**、**Python 3.10+**。

```powershell
git clone https://github.com/YOUR_USERNAME/authkit.git
cd authkit
python -m pip install -e ".[dev]"
python -m pytest -q
python -m authkit check
```

## 项目结构

详见 [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md)。

## 提交 Issue

请尽量附带：

1. 目标客户端（Codex / Cursor / VS Code）
2. 完整错误信息（如 `Token exchange failed`）
3. `authkit check --json` 输出（可脱敏代理地址）
4. 是否使用系统代理 / Clash 等

## 提交 Pull Request

1. 从 `main` 拉取最新代码并创建分支
2. 保持改动聚焦，匹配现有代码风格
3. 为新逻辑补充或更新测试（`tests/`）
4. 在 `CHANGELOG.md` 的 `[Unreleased]` 下简要记录变更
5. 确保 `python -m pytest -q` 通过

## 代码约定

- 仅使用 Python 标准库（零运行时第三方依赖）
- 中文用户可见文案与注释；标识符保持英文
- Windows 子进程默认通过 `platform.subprocess.run_hidden` 隐藏控制台
- `check` 默认只读；会改系统的操作必须经用户确认（`fix --apply` / GUI 确认）

## 许可

贡献代码将按 [MIT License](LICENSE) 发布。
