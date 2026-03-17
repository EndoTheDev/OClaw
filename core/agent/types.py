from __future__ import annotations

from dataclasses import dataclass
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
    session_id: str
    request_id: str | None
    iteration: int
    max_iterations: int


@dataclass
class ToolCallChunk:
    name: str
    arguments: dict[str, Any]
    id: str | None
