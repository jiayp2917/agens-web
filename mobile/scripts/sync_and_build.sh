#!/bin/bash
set -e

ROOT=/mnt/d/chat/agens
DEST=/home/jia/agens-build

echo "=== SYNC START ==="
mkdir -p "$DEST/mobile" "$DEST/src" "$DEST/config"

rsync -a --delete \
  --exclude ".buildozer/" \
  --exclude "bin/" \
  --exclude "__pycache__/" \
  --exclude "agens_novel" \
  --exclude "config" \
  "$ROOT/mobile/" "$DEST/mobile/"
rsync -a --delete "$ROOT/src/agens_novel/" "$DEST/src/agens_novel/"
rsync -a --delete "$ROOT/config/" "$DEST/config/"
cp -v "$ROOT/main.py" "$DEST/main.py"
cp -v "$ROOT/bgm.flac" "$DEST/bgm.flac"

echo "=== SYNC DONE ==="
echo "=== Starting buildozer ==="
cd "$DEST/mobile"
export PATH=/home/jia/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
buildozer android debug 2>&1
