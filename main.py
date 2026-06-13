"""Buildozer entry point for the Android app.

The desktop CLI remains ``python -m agens_novel``. This file exists so
Buildozer can use the repository root as ``source.dir`` and package both the
mobile Kivy shell and the shared ``src/agens_novel`` engine.
"""

from __future__ import annotations

from mobile.main import XianxiaApp


if __name__ == "__main__":
    XianxiaApp().run()
