"""Thread-local context for passing stream_callback across LangGraph nodes.

This avoids putting a non-serializable callable into the graph state,
which would cause msgpack checkpoint failures.
"""

from __future__ import annotations

import threading
from typing import Callable

_local = threading.local()


def set(callback: Callable[[str], None] | None) -> None:
    """Store the stream callback for the current thread."""
    _local.stream_callback = callback


def get() -> Callable[[str], None] | None:
    """Retrieve the stream callback for the current thread, or None."""
    return getattr(_local, "stream_callback", None)
