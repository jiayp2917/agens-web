#!/bin/bash
set -e

ROOT=/mnt/d/chat/agens
DEST=/home/jia/agens-build

echo "=== SYNC START ==="
mkdir -p "$DEST/mobile" "$DEST/src" "$DEST/config"
find "$DEST" -mindepth 1 -maxdepth 1 \
  ! -name "mobile" \
  ! -name "src" \
  ! -name "config" \
  -exec rm -rf {} +
rm -f "$DEST/mobile/bin"/*.apk 2>/dev/null || true

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

echo "=== SYNC DONE ==="
echo "=== Starting buildozer ==="
cd "$DEST/mobile"
export PATH=/home/jia/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
buildozer android debug 2>&1
