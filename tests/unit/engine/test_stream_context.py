"""Tests for the stream callback context (msgpack-friendly state).

Verifies that the streaming callback does not enter the LangGraph state
dict (msgpack cannot serialize callables) and that the thread-local
``_stream_context`` accessor works as expected.
"""

from __future__ import annotations

from agens_novel.session.game_session import GameSession


class TestStreamCallbackNotInState:
    """Verify stream_callback never enters the LangGraph state dict."""

    def test_state_dict_has_no_stream_callback_key(self):
        """run_turn_sync source must not inject stream_callback into state."""
        import agens_novel.engine.turn_runner as tr
        import inspect

        source = inspect.getsource(tr.run_turn_sync)
        # The old code had: state["stream_callback"] = stream_callback
        # The fix should NOT have that pattern anymore.
        assert 'state["stream_callback"]' not in source
        assert "state['stream_callback']" not in source

    def test_stream_context_module_importable(self):
        """The _stream_context module should be importable."""
        from agens_novel.engine import _stream_context

        assert hasattr(_stream_context, "get")
        assert hasattr(_stream_context, "set")
        # Clean up from any prior test.
        _stream_context.set(None)
        assert _stream_context.get() is None

    def test_stream_context_thread_local(self):
        """set/get should work in the current thread."""
        from agens_novel.engine import _stream_context

        cb = lambda text: None  # noqa: E731
        _stream_context.set(cb)
        assert _stream_context.get() is cb
        _stream_context.set(None)
        assert _stream_context.get() is None

    def test_game_session_has_no_stream_callback_attribute(self):
        """GameSession does not store the callback in its state dict."""
        session = GameSession()
        session.game_started = True
        assert "stream_callback" not in session.__dict__
