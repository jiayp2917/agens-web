#!/bin/bash
set -e
S=/mnt/d/chat/agens/mobile
D=/home/jia/agens-build/mobile
echo "=== SYNC START ==="
cp -v "$S/screens/character_create_screen.py" "$D/screens/"
cp -v "$S/screens/death_screen.py" "$D/screens/"
cp -v "$S/screens/home_screen.py" "$D/screens/home_screen.py"
cp -v "$S/screens/game_screen.py" "$D/screens/game_screen.py"
cp -v "$S/widgets/status_bar.py" "$D/widgets/"
cp -v "$S/widgets/action_bar.py" "$D/widgets/"
cp -v "$S/widgets/narrative_view.py" "$D/widgets/"
cp -v "$S/widgets/combat_bar.py" "$D/widgets/" 2>/dev/null || true
cp -v "$S/widgets/loading_overlay.py" "$D/widgets/" 2>/dev/null || true
cp -v "$S/theme.py" "$D/theme.py"
cp -v "$S/main.py" "$D/main.py"
test -f "$S/audio_manager.py" && cp -v "$S/audio_manager.py" "$D/" || true
mkdir -p "$D/assets/images" "$D/assets/fonts"
test -f "$S/assets/images/ink_home_bg.png" && cp -v "$S/assets/images/ink_home_bg.png" "$D/assets/images/" || true
test -f "$S/assets/fonts/NotoSansSC-Regular.otf" && cp -v "$S/assets/fonts/NotoSansSC-Regular.otf" "$D/assets/fonts/" || true
cp -v "$S/service/engine_adapter.py" "$D/service/"
cp -v "$S/service/settings_store.py" "$D/service/"
cp -v "$S/service/save_manager_compat.py" "$D/service/"
if [ -L "$D/agens_novel" ]; then rm -f "$D/agens_novel"; fi
rsync -a --delete "$S/agens_novel/" "$D/agens_novel/" 2>/dev/null || true
if [ -L "$D/config" ]; then rm -f "$D/config"; fi
rsync -a --delete "$S/config/" "$D/config/" 2>/dev/null || true
cp -v "$S/buildozer.spec" "$D/buildozer.spec"
echo "=== SYNC DONE ==="
echo "=== Starting buildozer ==="
cd "$D"
export PATH=/home/jia/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
buildozer android debug 2>&1
