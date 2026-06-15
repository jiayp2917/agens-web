"""Mobile-specific save manager setup.

Configures the agens_novel save manager to use the app's internal storage
directory instead of the default runtime/saves/ path.
"""

from __future__ import annotations

from pathlib import Path


def set_mobile_save_dir(app) -> None:
    """Set the save directory to the app's user_data_dir.

    Args:
        app: The Kivy App instance (provides user_data_dir).
    """
    try:
        save_dir = Path(app.user_data_dir) / "saves"
    except Exception:
        save_dir = Path.home() / ".agens_novel" / "saves"

    from agens_novel.persistence.save_manager import set_save_dir
    set_save_dir(save_dir)
