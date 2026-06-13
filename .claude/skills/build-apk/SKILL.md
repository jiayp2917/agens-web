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

### Step 0: 网络环境配置（关键！）

WSL2 内访问 GitHub 和 Google Source 在国内网络环境下**极慢或不可达**，即使开 VPN。必须配置镜像加速：

1. **设置 git 全局镜像（gh-proxy.com）：**
   ```bash
   wsl bash -lc "git config --global url.https://gh-proxy.com/https://github.com/.insteadOf 'https://github.com/'"
   ```
   这样所有 `git clone https://github.com/...` 的操作会自动走 gh-proxy 镜像。

2. **验证 gh-proxy 可达：**
   ```bash
   wsl bash -lc "curl -sS -o /dev/null -w 'speed=%{speed_download}B/s\n' --max-time 10 https://gh-proxy.com/https://github.com/"
   ```
   速度应 > 100KB/s。如果超时，说明 VPN/网络有问题。

3. **确保 aria2 已安装（并发下载加速）：**
   ```bash
   wsl bash -lc "which aria2c || echo 'jia' | sudo -S apt-get install -y aria2"
   ```

4. **googlesource.com 问题：**
   SDL2_image 的 libjxl 子模块依赖 `skia.googlesource.com/skcms`，该域名在国内完全不通（VPN 也不管用）。
   如果构建卡在 `git clone ... skcms`，需要：
   - 杀掉卡住的 git 进程
   - 创建 stub skcms 目录（libjxl 的 JPEG XL 支持对游戏不需要）
   - 修改 `.gitmodules` 中的 skcms URL

   ```bash
   LIBJXL=~/agens-build/mobile/.buildozer/android/platform/build-arm64-v8a/build/bootstrap_builds/sdl2/jni/SDL2_image/external/libjxl
   # 杀掉卡住的 clone
   pkill -9 -f 'git.*skcms'
   # 创建 stub
   mkdir -p $LIBJXL/third_party/skcms
   echo '/* stub */' > $LIBJXL/third_party/skcms/skcms.h
   echo '/* stub */' > $LIBJXL/third_party/skcms/skcms.c
   # 修改 .gitmodules
   sed -i 's|url = https://skia.googlesource.com/skcms|url = https://github.com/nicowilliams/skcms|' $LIBJXL/.gitmodules
   ```

> **重要：** 构建成功后，`.buildozer` 缓存保留。下次构建跳过下载和 C 编译，只需 2-3 分钟。
> **不要轻易删除 `.buildozer`！** 只在 `--clean` 或缓存损坏时删除。

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

4. 检查 WSL 内构建环境（Java 21, Cython 0.29+, Buildozer 1.6+）：
   ```bash
   wsl bash -lc "java -version 2>&1 | head -1; cython --version 2>&1; buildozer --version 2>&1"
   ```

### Step 2: 同步代码到 WSL

使用 rsync 增量同步（排除不必要的文件）：

```bash
wsl bash -lc "rsync -a --delete \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='.git' \
  --exclude='.pytest_cache' \
  --exclude='.claude' \
  --exclude='.buildozer' \
  --exclude='bin' \
  --exclude='runtime' \
  --exclude='*.pyc' \
  --exclude='node_modules' \
  /mnt/d/chat/agens/ ~/agens-build/"
```

### Step 3: 创建符号链接

在 WSL 中创建 Buildozer 需要的软链（agens_novel → ../src/agens_novel，config → ../config）：

```bash
wsl bash -lc "cd ~/agens-build/mobile && \
  ln -sfn ../src/agens_novel agens_novel && \
  ln -sfn ../config config && \
  ls -la agens_novel config"
```

验证输出中两个链接都指向正确目标。

### Step 4: [可选] 清除缓存

仅当参数包含 `--clean` 时执行：

```bash
wsl bash -lc "rm -rf ~/agens-build/mobile/.buildozer"
```

> ⚠️ 删除 `.buildozer` 会导致下次构建需要重新下载+编译全部 C 库（10-20分钟）。
> 一般只需删除 `.buildozer/android/app` 或 `dists` 目录即可。

### Step 5: [可选] 预热 tarball（首次构建或 --clean 时）

如果 `.buildozer` 是全新的，用 aria2c 并发下载所有 tarball 比让 buildozer 自己下快 10-100 倍：

```bash
# 启动 buildozer，等它开始下载后 Ctrl+C 停止，此时 packages 目录已创建
# 然后用 aria2c 逐个预热（gh-proxy 镜像）
PKG_DIR=~/agens-build/mobile/.buildozer/android/platform/build-arm64-v8a/packages
aria2c -x 16 -s 16 -d $PKG_DIR/sdl2 -o SDL2-2.30.11.tar.gz \
  'https://gh-proxy.com/https://github.com/libsdl-org/SDL/releases/download/release-2.30.11/SDL2-2.30.11.tar.gz'
# 下载完成后 touch .mark 让 buildozer 跳过
touch $PKG_DIR/sdl2/.mark-SDL2-2.30.11.tar.gz
```

对每个 tarball 重复此操作。完整列表见 `buildozer.spec` 的 `requirements`。

### Step 6: 运行 Buildozer

根据 `--release` 参数选择构建类型。**必须用 `bash -lc`（login shell）确保 PATH 包含 `~/.local/bin`。**

**debug（默认）：**
```bash
wsl bash -lc "cd ~/agens-build/mobile && PIP_BREAK_SYSTEM_PACKAGES=1 buildozer android debug 2>&1"
```

**release：**
```bash
wsl bash -lc "cd ~/agens-build/mobile && PIP_BREAK_SYSTEM_PACKAGES=1 buildozer android release 2>&1"
```

> 构建时间参考：
> - 首次（无缓存）：10-20 分钟（下载 + C 交叉编译 + gradle）
> - 增量（有 .buildozer 缓存）：2-5 分钟（只重编译 Python 包 + gradle）
> - 仅改 Python 代码：2-3 分钟（跳过 C 编译）

**监控构建进度：**
```bash
# 查看活跃进程
wsl bash -lc "ps aux | grep -E 'buildozer|pythonforandroid|gcc|clang|pip|gradle' | grep -v grep"

# 查看已完成的编译产物
wsl bash -lc "du -sh ~/agens-build/mobile/.buildozer/android/platform/build-arm64-v8a/build/other_builds/*/"

# 检查 APK 是否产出
wsl bash -lc "ls -lh ~/agens-build/mobile/bin/*.apk 2>/dev/null"
```

### Step 7: 复制 APK 到桌面

```bash
wsl bash -lc "cp ~/agens-build/mobile/bin/agensnovel-*-debug.apk /mnt/c/Users/29176/Desktop/ 2>/dev/null; ls -lh ~/agens-build/mobile/bin/*.apk"
```

报告 APK 文件大小和路径。

### Step 8: 输出结果

向用户报告：
1. ✅ APK 路径和文件大小
2. 📱 安装方式：`adb install -r "%USERPROFILE%\Desktop\agensnovel-*.apk"` 或微信/QQ传输
3. 🐛 调试方式：`adb logcat -s python`
4. 如果有任何步骤失败，报告错误详情和建议修复方式

## 故障排查

| 问题 | 修复 |
|------|------|
| PEP 668 externally-managed-environment | 确保 Step 6 使用 `PIP_BREAK_SYSTEM_PACKAGES=1` |
| Python 语法错误（lambda赋值等） | 检查 `mobile/screens/*.py` 是否用了 3.14+ 语法 |
| stale cache 构建失败 | 使用 `--clean` 参数重试 |
| NDK/SDK 下载超时 | 确保 git mirror 已配置（Step 0），或用 aria2c 预热 |
| `git clone` GnuTLS error | VPN 未开或 gh-proxy 未配置；执行 Step 0 |
| `rmtree on symbolic link` 错误 | p4a 目录不能是符号链接，必须是真实目录（`cp -a` 而非 `ln -s`） |
| p4a remote URL 不匹配 | `git remote set-url origin https://github.com/kivy/python-for-android.git`（.git/config 里必须是干净 URL，git insteadOf 自动镜像） |
| 卡在 `skia.googlesource.com/skcms` | googlesource.com 在国内不通，需手动创建 stub（见 Step 0 第 4 点） |
| GitHub 下载极慢（< 50KB/s） | VPN 可能限速；用 aria2c 通过 gh-proxy 预热 tarball（见 Step 5） |
| pydantic-core 编译失败 | 在 buildozer.spec 的 requirements 中移除 pydantic，改用 `--no-deps` |

## 已知构建依赖顺序

buildozer 按以下顺序下载/编译（供监控进度参考）：

1. 下载 tarball：hostpython3 → libffi → openssl → sdl2_image → sdl2_mixer → sdl2_ttf → sqlite3 → python3 → sdl2
2. SDL2 bootstrap：解压 SDL2 + SDL2_image/mixer/ttf → `ndk-build` 编译 JNI
3. 交叉编译 C 库：hostpython3（桌面）→ python3（ARM64）→ openssl → libffi → sqlite3
4. 编译 Kivy：Kivy C 扩展（ARM64）
5. pip install：httpx, pyjnius, setuptools, langgraph, langchain-core, langchain-openai, pyyaml
6. Gradle 打包：生成 APK
