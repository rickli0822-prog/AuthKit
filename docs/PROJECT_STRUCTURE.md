# 项目结构

```
authkit/
├── .github/                    # GitHub 配置
│   ├── ISSUE_TEMPLATE/         # Issue 模板
│   └── workflows/              # CI（测试）
├── docs/                       # 文档（架构、故障案例）
├── scripts/                    # Windows 启动与快捷方式脚本
├── src/
│   └── authkit/        # 主包
│       ├── __init__.py         # 版本号
│       ├── __main__.py         # python -m authkit
│       ├── cli.py              # 命令行入口
│       ├── models.py           # 数据模型（报告、Case、代理端点）
│       ├── report.py           # 人类可读 / JSON 报告渲染
│       ├── core/               # 诊断编排
│       │   └── diagnose.py     # run_diagnosis() 主流程
│       ├── checks/             # 各检查层实现
│       │   ├── client.py       # Codex doctor、Cursor/VS Code 设置
│       │   ├── login.py        # 本地登录凭据（轻量）
│       │   └── network.py      # OAuth 探测、回调端口
│       ├── platform/           # Windows 平台能力
│       │   ├── proxy.py        # WinINET 代理、环境变量读写
│       │   └── subprocess.py   # 隐藏控制台子进程
│       ├── repair/             # 修复与操作
│       │   ├── fixer.py        # sync / apply_fix
│       │   └── actions.py      # 设备码登录等
│       └── ui/                 # 图形界面
│           ├── app.py          # Tkinter 主窗口
│           └── theme.py        # 主题与字体
├── tests/                      # 单元测试
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
├── pyproject.toml
└── README.md
```

## 模块职责

| 模块 | 职责 |
|------|------|
| `core.diagnose` | 串联各检查层，分类 Case A–F，生成 `DiagnosisReport` |
| `checks.network` | TCP 探测、OAuth 端点、1455/1457 端口与进程 |
| `checks.login` | 读取 `~/.codex/auth.json`，不联网 |
| `checks.client` | 客户端安装与配置专项检查 |
| `platform.proxy` | 系统代理与环境变量同步（修复核心） |
| `repair.fixer` | 将建议修复写入用户环境变量 |
| `ui.app` | GUI：手动诊断、同步代理、设备码登录 |

## 数据流

```
cli.py / ui.app
    → core.diagnose.run_diagnosis()
        → platform.proxy（读代理）
        → checks.network（探测 OAuth / 端口）
        → checks.login（读凭据）
        → checks.client（客户端专项）
    → report.render_*()
    → repair.fixer（用户确认后修复）
```

## 入口点

| 方式 | 说明 |
|------|------|
| `authkit` | CLI（`pyproject.toml` scripts） |
| `authkit-gui` | GUI 独立入口 |
| `python -m authkit` | 模块方式 |
| `scripts/launch_gui.pyw` | 无控制台窗口启动（快捷方式推荐） |
