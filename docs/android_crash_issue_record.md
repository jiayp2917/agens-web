# Android 启动与打包记录

日期：2026-06-14
范围：Android-only Kivy 入口、Buildozer 打包资源和启动链路。

## 当前结论

产品入口固定为 `mobile/main.py`，APK 入口通过仓库根目录 `main.py` 导入 `mobile.main`。终端交互入口已经移除，不作为启动或验证路径。

`mobile/buildozer.spec` 使用仓库根目录作为 `source.dir`，显式打包：

- `main.py`
- `bgm.flac`
- `mobile/**/*`
- `src/agens_novel/**/*`
- `config/**/*`

这样可以避免依赖 `mobile/agens_novel`、`mobile/config` 这类本地 symlink。

## 已处理风险

- Android 下 `AGENS_NOVEL_ROOT` 指向仓库根目录，保证提示词、运行目录和根目录 BGM 可解析。
- BGM 打包扩展名包含 `flac`。
- 移动端入口不再额外注入内置 API key；用户设置中的 API key 仅写入应用私有 `secrets.json`，普通 `settings.json` 不保存 key，UI 只显示掩码摘要。
- 主页、读档、教程、设置、游戏页都走 Kivy 移动端 UI。

## 仍需真机验证

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests mobile\main.py mobile\audio_manager.py mobile\screens mobile\widgets mobile\service
.\.venv\Scripts\python.exe -m pytest -q
```

WSL/Buildozer：

```bash
cd /mnt/d/chat/agens/mobile
buildozer android debug
```

真机日志：

```powershell
adb logcat -c
adb logcat | findstr /i "python kivy agens traceback exception importerror modulenotfounderror filenotfounderror"
```

重点确认 APK 内存在 `main.py`、`mobile/`、`src/agens_novel/`、`config/prompts/system/` 和 `bgm.flac`。
