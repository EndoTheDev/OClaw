from dataclasses import dataclass
from typing import AsyncGenerator, Literal, Protocol


@dataclass
class ResponseChunk:
    """A content token from the model."""

    content: str


@dataclass
class ThinkingChunk:
    """Thinking/reasoning content from the model."""

    content: str


@dataclass
class ToolCallChunk:
    """A tool call from the model."""

    name: str
    arguments: dict


@dataclass
class MetricsChunk:
    """Performance metrics from the response."""

    data: dict


@dataclass
class DoneChunk:
    """Signal that the response is complete."""

    done_reason: str | None = None


@dataclass
class ErrorChunk:
    """An error occurred during streaming."""

    error: str


StreamingChunk = (
    ResponseChunk
    | ThinkingChunk
    | ToolCallChunk
    | MetricsChunk
    | DoneChunk
    | ErrorChunk
)


class Provider(Protocol):
    """Protocol for async LLM providers."""

    def chat(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> AsyncGenerator[StreamingChunk, None]:
        """Stream response chunks asynchronously.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool schemas

        Yields:
            StreamingChunk: ResponseChunk, ThinkingChunk, ToolCallChunk,
                         MetricsChunk, DoneChunk, or ErrorChunk
        """
        ...
