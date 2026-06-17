"""Android APK entry point.

Buildozer packages the repository root, so python-for-android starts this
module and delegates to the Kivy app in ``mobile.main``.
"""

from mobile.main import XianxiaApp


if __name__ == "__main__":
    XianxiaApp().run()
