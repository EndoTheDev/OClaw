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


class PermissionRequest(TypedDict):
    type: Literal["permission_request"]
    name: str
    args: dict[str, Any]
    request_id: str


class TokenOutput(TypedDict):
    type: Literal["token"]
    content: str


class ThinkingOutput(TypedDict):
    type: Literal["thinking"]
    content: str


class ToolCallOutput(TypedDict):
    type: Literal["tool_call"]
    name: str
    id: str | None
    args: dict[str, Any]


class ToolEnd(TypedDict):
    type: Literal["tool_end"]
    tool_name: str
    tool_call_id: NotRequired[str | None]
    result: Any


class MetricsOutput(TypedDict):
    type: Literal["metrics"]
    data: dict[str, Any]


class ErrorOutput(TypedDict):
    type: Literal["error"]
    message: str


class DoneOutput(TypedDict):
    type: Literal["done"]


StreamOutput = (
    PermissionRequest
    | TokenOutput
    | ThinkingOutput
    | ToolCallOutput
    | ToolEnd
    | MetricsOutput
    | ErrorOutput
    | DoneOutput
)


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
