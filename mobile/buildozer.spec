[app]

# (str) Title of your application
title = 文字修仙

# (str) Package name
package.name = agensnovel

# (str) Package domain (reverse domain notation)
package.domain = org.agens

# (str) Source directory where the main application lives.
# Use mobile/ itself as source root. Symlinks agens_novel/ and config/
# are created by the build skill (ln -sfn ../src/agens_novel agens_novel).
source.dir = .

# (list) Source files to include
source.include_exts = py,png,jpg,kv,atlas,json,yaml,md,txt,otf,ttf

# (list) Extra directories to include — with source.dir=. everything under
# mobile/ is included by default.  Symlinks (agens_novel, config) are followed.
source.include_patterns = *

# (list) List of directory to exclude from source
source.exclude_dirs = __pycache__, .pytest_cache, .buildozer, bin

# (list) List of exclusions using pattern matching
source.exclude_patterns = .buildozer/*,bin/*

# (str) Application version
version = 0.4.0

# (list) Application requirements
# NOTE: pydantic is NOT listed — the project no longer depends on it directly.
# langgraph pulls it transitively; if that fails, use requirements.txt with --no-deps.
requirements = python3==3.11.9,hostpython3==3.11.9,kivy==2.3.0,httpx,langgraph,langchain-core,langchain-openai,pyyaml

# (str) Presplash image
#presplash.filename = %(source.dir)s/assets/presplash.png

# (str) Application orientation (landscape, portrait, all)
orientation = portrait

# (bool) Fullscreen mode
fullscreen = 0

# (str) Android log filter
android.logcat_filters = *:S python:D

# (list) Android permissions
android.permissions = INTERNET

# (int) Target Android API level
android.api = 34

# (int) Minimum Android API level
android.minapi = 26

# (str) Android NDK version
android.ndk = 25b

# (bool) Accept Android SDK license
android.accept_sdk_license = True

# (list) Android architectures
android.archs = arm64-v8a

# (str) python-for-android branch
p4a.branch = master

# (bool) Use --private data storage
android.private_storage = True

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug)
log_level = 2

# (bool) Warn if building as root
warn_on_root = 1

# (str) Path to build output
build_dir = ./.buildozer

# (str) Path to bin output
bin_dir = ./bin
