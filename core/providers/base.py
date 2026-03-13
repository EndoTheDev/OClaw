from dataclasses import dataclass
from typing import AsyncGenerator, Literal, Protocol

from ..sessions import Message

@dataclass
class ToolDefinition:
    """A standardized tool definition."""
    name: str
    description: str
    parameters: dict

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
    id: str | None = None


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
        self, messages: list[Message], tools: list[ToolDefinition] | None = None
    ) -> AsyncGenerator[StreamingChunk, None]:
        """Stream response chunks asynchronously.

        Args:
            messages: List of current conversation messages
            tools: Optional list of tool definitions

        Yields:
            StreamingChunk: ResponseChunk, ThinkingChunk, ToolCallChunk,
                         MetricsChunk, DoneChunk, or ErrorChunk
        """
        ...
