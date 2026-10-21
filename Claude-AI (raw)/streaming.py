"""Request-scoped Ollama token streaming for the primary Carl chat agents."""

from contextvars import ContextVar, Token
from types import SimpleNamespace
from typing import Any, Callable, Dict, List

import ollama

StreamCallback = Callable[[str], None]

_stream_callback: ContextVar[StreamCallback | None] = ContextVar(
    "carl_stream_callback",
    default=None,
)


def set_stream_callback(callback: StreamCallback) -> Token[StreamCallback | None]:
    """Enable partial-response delivery in the current execution context."""
    return _stream_callback.set(callback)


def reset_stream_callback(token: Token[StreamCallback | None]) -> None:
    """Restore the previous request-scoped stream callback."""
    _stream_callback.reset(token)


def publish_stream_update(text_chunk: str) -> None:
    """Publish text only when the current request has opted into streaming."""
    callback = _stream_callback.get()
    if callback is not None:
        callback(text_chunk)


def chat_with_optional_stream(
    *,
    model: str,
    messages: List[Dict[str, str]],
    options: Dict[str, Any],
    keep_alive: str,
) -> Any:
    """Use normal Ollama chat unless the current request accepts partial output."""
    callback = _stream_callback.get()
    if callback is None:
        return ollama.chat(
            model=model,
            messages=messages,
            options=options,
            keep_alive=keep_alive,
        )

    response_chunks = ollama.chat(
        model=model,
        messages=messages,
        options=options,
        keep_alive=keep_alive,
        stream=True,
    )
    content_parts: List[str] = []
    for chunk in response_chunks:
        content = chunk.message.content
        if content:
            content_parts.append(content)
            callback(content)

    return SimpleNamespace(
        message=SimpleNamespace(content="".join(content_parts))
    )
