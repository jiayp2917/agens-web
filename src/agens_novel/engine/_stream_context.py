"""Thread-local context for passing stream_callback across agent nodes.

This keeps a non-serializable callable out of the data-only graph state.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

_local = threading.local()


def set(callback: Callable[[str], None] | None) -> None:
    """Store the stream callback for the current thread."""
    _local.stream_callback = callback


def get() -> Callable[[str], None] | None:
    """Retrieve the stream callback for the current thread, or None."""
    return getattr(_local, "stream_callback", None)
