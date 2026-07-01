# 故障分类（Case A–F）

authkit 将常见问题归纳为以下类型，便于搜索、写 Issue 与写复盘文章。

## Case A — 代理端口不一致（最常见）

**现象**：浏览器能打开 ChatGPT 登录页，Codex 报 `Token exchange failed`。

**原因**：Windows 系统代理（如 `127.0.0.1:7890`）与环境变量 `HTTP_PROXY`（如 `127.0.0.1:7897`）端口不一致；浏览器走系统代理，Codex CLI/后端读环境变量。

**修复**：`authkit sync --apply`，然后重启终端与 Codex。

## Case B — 代理端口失效

**现象**：环境变量或系统代理指向的端口无进程监听（Clash 未启动等）。

**修复**：启动代理软件，或 `authkit sync --clear --apply` 清理失效配置。

## Case C — localhost 未绕过代理

**现象**：OAuth 本地回调 `localhost:1455` 被错误转发到代理。

**修复**：确保 `NO_PROXY` 包含 `127.0.0.1,localhost,::1`；检查系统代理绕过列表。

## Case D — OAuth 回调端口冲突

**现象**：`1455` 被 `wslrelay`、Cursor 等非 Codex 进程占用。

**修复**：关闭占用进程或调整 Cursor「在 WSL 中运行 Codex」等设置。

## Case E — TLS / 企业证书

**现象**：访问 `auth.openai.com` 出现证书错误。

**修复**：配置企业 CA（如 `CODEX_CA_CERTIFICATE`），联系 IT。

## Case F / 设备码登录

**现象**：网络正常但浏览器 OAuth 仍失败。

**修复**：`codex login --device-auth`，或在 GUI 点击「设备码登录」。

## 报告中的检查层

| 层 | 说明 |
|----|------|
| `system_proxy` | WinINET 系统代理 |
| `env_proxy` | 用户/进程环境变量 |
| `oauth_endpoints` | OAuth 与 ChatGPT API 可达性 |
| `callback_ports` | 1455 / 1457 监听与进程 |
| `login_status` | Codex 本地凭据（不联网） |
| `client_specific` | 客户端 doctor / settings |

提交 Issue 时请附上 `authkit check --json` 输出。
