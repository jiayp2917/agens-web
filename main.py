"""Buildozer entry point for the Android/Kivy app.

The product path is Android-only. This file lets Buildozer use the repository
root as ``source.dir`` while packaging the mobile shell and shared engine.
"""

from __future__ import annotations

from mobile.main import XianxiaApp


if __name__ == "__main__":
    XianxiaApp().run()
