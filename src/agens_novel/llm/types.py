"""TypedDict definitions for LLM messages and responses."""

from __future__ import annotations

from typing import TypedDict


class Message(TypedDict, total=False):
    """A single chat message."""

    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
    name: str


class Usage(TypedDict, total=False):
    """Token usage reported by OpenAI-compatible APIs."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class LLMResponse(TypedDict, total=False):
    """Normalized LLM response — same shape for stream and non-stream."""

    text: str
    model: str
    usage: Usage
    finish_reason: str
    elapsed_ms: int
    raw: dict
