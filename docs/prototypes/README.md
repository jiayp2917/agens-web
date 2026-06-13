# Android 高保真原型图

本目录是“文字修仙模拟器”Android 竖屏静态高保真原型，水墨极简风格。

## 文件

- `index.html`：一页多画板原型，可直接在浏览器打开。
- `prototype.css`：原型样式。
- `assets/ink-home-bg.png`：本地生成的水墨主页背景图。
- `exports/*.png`：导出的 390x844 Android 竖屏原型图。

## 原型范围

- 主页
- 主页读档弹窗
- 主页设置弹窗
- 主页教程弹窗
- 游戏界面：高自由度、中自由度、低自由度
- 角色创建界面
- `2917` 隐藏结果态
- 死亡/重新开始态

## 关键约束

- 境界展示只包含：练气、筑基、金丹、元婴、化神、合体、大乘、渡劫。
- `2917` 不在界面明确告知，只通过特殊开局结果体现。
- 原型不修改 Kivy 代码，不包含可点击 Demo。

## 重新生成

```powershell
$py = "C:\Users\29176\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
& $py docs\prototypes\scripts\generate_ink_assets.py

powershell -ExecutionPolicy Bypass -File docs\prototypes\scripts\export_screenshots.ps1
```
