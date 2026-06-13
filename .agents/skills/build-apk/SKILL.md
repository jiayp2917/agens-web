---
name: build-apk
description: 将文字修仙项目打包为 Android APK（通过 WSL + Buildozer）
argument-hint: [--clean] [--release]
disable-model-invocation: true
allowed-tools: Bash(wsl *), Bash(python *), Bash(cp *), Bash(rm *), Bash(ls *), Bash(diff *), Bash(mkdir *), Bash(cat *), Bash(head *), Bash(grep *), Read, Edit, Write
---

# /build-apk — 文字修仙 APK 构建流水线

通过 WSL2 + Buildozer 将项目打包为 Android APK，输出到 Windows 桌面。

## 参数

- `--clean`：清除 WSL 构建缓存后重新打包（首次或依赖变更时用）
- `--release`：构建 release 版本（需要签名配置，默认 debug）
- 无参数：增量同步 + 快速打包

## 执行步骤

按顺序执行以下步骤，每步出错立即停止并报告。

### Step 1: 前置检查

1. 检查 WSL 可用性：
   ```bash
   wsl bash -c "echo ok"
   ```
   失败则报告"WSL 未就绪"并停止。

2. 检查两处内置 Key 一致性（防止漏改）：
   ```bash
   CLIENT_KEY=$(grep "_DEFAULT_KEY_B64" src/agens_novel/llm/client.py | head -1 | sed 's/.*= *"//;s/".*//')
   MAIN_KEY=$(grep "_DEFAULT_KEY_B64" mobile/main.py | head -1 | sed 's/.*= *"//;s/".*//')
   if [ "$CLIENT_KEY" != "$MAIN_KEY" ]; then echo "MISMATCH"; fi
   ```
   不一致则报告差异并停止，提示用户手动同步。

3. 编译检查（确保无 Python 语法错误）：
   ```bash
   python -m compileall -q src tests
   ```

### Step 2: 同步代码到 WSL

使用 rsync 增量同步（排除不必要的文件）：

```bash
wsl bash -c "rsync -avz --delete \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='.git' \
  --exclude='.pytest_cache' \
  --exclude='.Codex' \
  --exclude='.buildozer' \
  --exclude='runtime' \
  --exclude='*.pyc' \
  /mnt/d/chat/agens/ ~/agens-build/"
```

### Step 3: 创建符号链接

在 WSL 中创建 Buildozer 需要的软链（agens_novel → ../src/agens_novel，config → ../config）：

```bash
wsl bash -c "cd ~/agens-build/mobile && \
  ln -sfn ../src/agens_novel agens_novel && \
  ln -sfn ../config config && \
  ls -la agens_novel config"
```

验证输出中两个链接都指向正确目标。

### Step 4: [可选] 清除缓存

仅当参数包含 `--clean` 时执行：

```bash
wsl bash -c "rm -rf ~/agens-build/mobile/.buildozer/android/app"
```

### Step 5: 运行 Buildozer

根据 `--release` 参数选择构建类型：

**debug（默认）：**
```bash
wsl bash -c "cd ~/agens-build/mobile && PIP_BREAK_SYSTEM_PACKAGES=1 buildozer android debug 2>&1 | tail -30"
```

**release：**
```bash
wsl bash -c "cd ~/agens-build/mobile && PIP_BREAK_SYSTEM_PACKAGES=1 buildozer android release 2>&1 | tail -30"
```

> 注意：buildozer 首次编译需要 10-20 分钟（下载 NDK/SDK/编译 Python）。后续增量构建约 2-5 分钟。

### Step 6: 复制 APK 到桌面

```bash
wsl bash -c "cp ~/agens-build/mobile/bin/agensnovel-*-debug.apk /mnt/c/Users/29176/Desktop/ 2>/dev/null; ls -lh ~/agens-build/mobile/bin/*.apk"
```

报告 APK 文件大小和路径。

### Step 7: 输出结果

向用户报告：
1. ✅ APK 路径和文件大小
2. 📱 安装方式：`adb install -r "%USERPROFILE%\Desktop\agensnovel-*.apk"` 或微信/QQ传输
3. 🐛 调试方式：`adb logcat -s python`
4. 如果有任何步骤失败，报告错误详情和建议修复方式

## 故障排查

| 问题 | 修复 |
|------|------|
| PEP 668 externally-managed-environment | 确保 Step 5 使用 `PIP_BREAK_SYSTEM_PACKAGES=1` |
| Python 语法错误（lambda赋值等） | 检查 `mobile/screens/*.py` 是否用了 3.14+ 语法 |
| stale cache 构建失败 | 使用 `--clean` 参数重试 |
| NDK/SDK 下载超时 | 重试即可，buildozer 支持断点续传 |
| pydantic-core 编译失败 | 在 buildozer.spec 的 requirements 中移除 pydantic，改用 `--no-deps` |
