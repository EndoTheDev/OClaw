from __future__ import annotations

from dataclasses import dataclass
from multiprocessing import Queue
from typing import Any, Literal, NotRequired, TypedDict


class ToolCallFunction(TypedDict):
    name: str
    arguments: dict[str, Any] | str


class ToolCall(TypedDict):
    type: Literal["function"]
    function: ToolCallFunction
    id: NotRequired[str]


EventType = Literal[
    "agent_start",
    "turn_start",
    "message_start",
    "message_update",
    "message_end",
    "tool_execution_start",
    "tool_execution_update",
    "tool_execution_end",
    "turn_end",
    "agent_end",
    "error",
    "stream_end",
]

ApprovalPhase = Literal[
    "approval_requested",
    "approval_granted",
    "approval_denied",
]

ToolExecutionStatus = Literal["succeeded", "failed", "denied"]


class StreamEventEnvelope(TypedDict):
    schema_version: Literal["2.0"]
    event_id: str
    sequence: int
    timestamp: str
    event_type: EventType
    request_id: str
    session_id: str
    turn_id: str | None
    payload: dict[str, Any]


class ProviderDispatchOutput(TypedDict):
    kind: Literal[
        "message_token",
        "message_thinking",
        "message_tool_call",
        "message_metrics",
        "provider_error",
    ]
    content: NotRequired[str]
    name: NotRequired[str]
    id: NotRequired[str | None]
    args: NotRequired[dict[str, Any]]
    data: NotRequired[dict[str, Any]]
    message: NotRequired[str]


class ToolExecutionOutput(TypedDict):
    kind: Literal[
        "tool_execution_start",
        "tool_execution_update",
        "tool_execution_end",
    ]
    tool_name: str
    tool_call_id: str | None
    args: NotRequired[dict[str, Any]]
    phase: NotRequired[ApprovalPhase]
    status: NotRequired[ToolExecutionStatus]
    result: NotRequired[Any]
    error: NotRequired[str]


StreamOutput = StreamEventEnvelope


@dataclass
class ExecutionContext:
    """Runtime context for agent execution lifecycle."""

    session_id: str
    request_id: str | None = None
    iteration: int = 1
    max_iterations: int = 5
    turn_id: str | None = None
    input_queue: Queue | None = None

    def can_continue(self) -> bool:
        """Check if another iteration is allowed."""
        return self.iteration <= self.max_iterations

    def next_iteration(self) -> ExecutionContext:
        """Create new context with incremented iteration."""
        return ExecutionContext(
            session_id=self.session_id,
            request_id=self.request_id,
            iteration=self.iteration + 1,
            max_iterations=self.max_iterations,
            turn_id=None,
            input_queue=self.input_queue,
        )

    def with_turn(self, turn_id: str) -> ExecutionContext:
        """Create new context with specific turn_id."""
        return ExecutionContext(
            session_id=self.session_id,
            request_id=self.request_id,
            iteration=self.iteration,
            max_iterations=self.max_iterations,
            turn_id=turn_id,
            input_queue=self.input_queue,
        )


@dataclass
class ToolCallChunk:
    name: str
    arguments: dict[str, Any]
    id: str | None
