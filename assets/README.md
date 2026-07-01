# 品牌资源

| 文件 | 说明 |
|------|------|
| `authkit-logo-mark.png` | **官方盾形标志**（白线黑底，无文字） |
| `authkit-logo-source.png` | 旧版带字样原图（可删） |
| `authkit-icon-512.png` | **仅盾形**，无文字，用于 README |
| `authkit-icon-48.png` | 界面左上角 Logo |
| `authkit.ico` | 任务栏 / 窗口 / 快捷方式图标（无文字） |

从原图裁切在 16×16 会糊，请使用 **矢量绘制** 脚本：

```powershell
python scripts/build_icon.py
```

每个尺寸单独绘制盾形标志（深灰底 + 白线），不含任何文字。
