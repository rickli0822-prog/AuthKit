# Codex 登录失败？我做了一个 Windows 本地诊断工具 AuthKit

> 建议发布平台：掘金  
> 建议标签：AI 工具、Windows、开源、效率工具、Codex  
> 建议摘要：AuthKit 是一个 Windows 本地工具，用来诊断 Codex、Claude Code、Gemini 等 AI 客户端登录失败、代理错乱、OAuth 回调端口冲突和网络不可达问题，并生成脱敏支持包。

## 这不是一个“又一个网络检测工具”

我做 AuthKit 的原因很直接：现在很多 AI 编程工具的问题，不是模型能力问题，而是“客户端根本没连上”。

典型现场是这样的：

- 浏览器里已经登录了，但 Codex CLI 还是说未登录。
- Claude Code 安装了，命令也能执行，但请求一直失败。
- 公司网络下 AI 客户端连不上，换个网络又正常。
- 本机开了代理，浏览器能用，CLI 工具却走了另一条网络路径。
- 用户把截图、报错、代理配置发来发去，最后还是靠猜。

这些问题的共同点是：它们不适合靠聊天排查。需要一个本地工具，把登录证据、代理路径、OAuth 回调、端点可达性、修复记录一次性查清楚。

AuthKit 就是为这个场景做的。

GitHub：<https://github.com/rickli0822-prog/AuthKit>

## AuthKit 解决什么问题

一句话：

> AuthKit 是一个 Windows 本地 AI 客户端登录诊断与修复工具。

它当前主要面向这些客户端：

- Codex
- Claude Code
- Gemini
- Cursor
- VS Code AI 相关能力

其中 Codex、Claude Code、Gemini 是完整诊断目标；Cursor 和 VS Code 因为本地登录状态契约有限，目前按部分诊断处理。

AuthKit 关注的不是“网速快不快”，而是这些问题：

- AI 客户端是否安装。
- 本地是否存在登录凭据标记，但不读取 token 值。
- 环境变量代理和 Windows 系统代理是否冲突。
- `NO_PROXY` 是否可能挡住 localhost / OAuth callback。
- OAuth 回调端口是否被占用。
- AI endpoint 是否可达。
- 当前网络出口、IP 版本、基础风险信号是否异常。
- 修复动作是否有审计记录，能不能回滚。

## 为什么不直接让用户手工改代理

因为现场排障最怕“修好了但不知道改过什么”。

AuthKit 的设计原则是：

1. 诊断先行，不默认修改系统。
2. 修复必须显式触发。
3. 修复必须写本地审计记录。
4. 能回滚的修复要支持回滚预览。
5. 支持包默认脱敏，不能把 token、cookie、密码带出去。

例如，AuthKit 可以做系统代理同步、DNS 缓存刷新、Winsock reset、客户端 CA 配置、Firewall outbound allow 这类动作，但这些都不是安装时偷偷执行的。

安装器只安装文件和快捷方式。修复动作要用户明确触发。

## 快速使用

Windows 用户可以直接下载安装包：

<https://github.com/rickli0822-prog/AuthKit/releases/latest>

开发者可以从源码运行：

```powershell
python -m pip install -e ".[dev]"
authkit gui
```

CLI 诊断：

```powershell
authkit check --client codex
```

扫描本机已安装支持的 AI 客户端：

```powershell
authkit scan
```

生成脱敏支持包：

```powershell
authkit bundle --client codex --out .\authkit-support-bundle.json --fast
```

验证支持包能否安全交付：

```powershell
authkit bundle --validate .\authkit-support-bundle.json
```

## 支持包比截图更适合现场交接

很多登录失败问题，单靠截图没有上下文。

AuthKit 的 support bundle 会把这些内容放到一个 JSON 里：

- 诊断快照
- 最近修复审计记录
- 低隐私元数据
- 诊断状态和问题类型
- 是否使用 fast 诊断路径

默认会脱敏：

- access token
- refresh token
- API key
- password
- cookie
- URL 里的账号密码
- 本机用户目录路径

这样现场工程师可以把证据交给下一个人，而不是只交一句“用户说连不上”。

## 当前边界

AuthKit 不是万能修复器。

它能比较可靠地处理这些方向：

- 代理配置不一致
- 系统代理和环境变量代理错位
- OAuth callback / localhost 相关问题
- AI endpoint 网络不可达
- 本地登录凭据缺失或客户端状态异常
- 可审计的低风险修复和回滚

它不能直接解决：

- 账号被封、订阅过期、组织权限不足
- MFA、风控、服务端故障
- 企业网关策略不允许访问
- 第三方客户端没有稳定本地登录状态契约

这些情况 AuthKit 会尽量给出证据和下一步建议，而不是假装一键修好。

## 为什么开源

登录失败问题有很强的现场差异。

不同公司网络、代理软件、AI 客户端版本、证书策略、终端权限都会影响结果。闭门造一个工具，很容易只适配自己的机器。

所以 AuthKit 更需要真实样本：

- 哪个客户端失败。
- 什么网络环境。
- 诊断报告是什么。
- 修复动作是否有效。
- 哪些字段不该暴露。

如果你遇到 Codex / Claude Code / Gemini 在 Windows 上登录失败，可以用 AuthKit 生成脱敏支持包，然后提 GitHub Issue。

## 后续计划

短期我会优先做这些事：

- 收集真实失败样本，加入回归测试。
- 强化 Codex、Claude Code、Gemini 的登录诊断准确性。
- 让 GUI 更适合现场工程师快速交付证据。
- 扩展更多安全、可审计、可回滚的修复动作。

不会优先做这些事：

- 泛网络测速。
- 静默自动修系统。
- 读取或上传用户 token。
- 为了功能数量牺牲现场可信度。

## 最后

如果你经常帮别人处理 AI 工具登录失败，AuthKit 可能正好适合你。

项目地址：

<https://github.com/rickli0822-prog/AuthKit>

下载地址：

<https://github.com/rickli0822-prog/AuthKit/releases/latest>

欢迎提交真实、脱敏的失败样本。对 AuthKit 来说，这比泛泛的 feature request 更有价值。
