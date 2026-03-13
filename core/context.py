from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .sessions import Message, ToolCall


@dataclass
class ContextManager:
    messages: list[Message] = field(default_factory=list)

    def load(self, messages: list[Message]) -> None:
        self.messages = list(messages)

    def append_user(self, content: str) -> Message:
        message: Message = {
            "role": "user",
            "content": content,
            "timestamp": self._now_iso(),
        }
        self.messages.append(message)
        return message

    def append_assistant(
        self,
        content: str,
        thinking: str | None = None,
        tool_calls: list[ToolCall] | None = None,
    ) -> Message:
        message: Message = {
            "role": "assistant",
            "content": content,
            "timestamp": self._now_iso(),
        }
        if thinking:
            message["thinking"] = thinking
        if tool_calls:
            message["tool_calls"] = tool_calls
        self.messages.append(message)
        return message

    def append_tool(self, tool_name: str, content: str, tool_call_id: str | None = None) -> Message:
        message: Message = {
            "role": "tool",
            "tool_name": tool_name,
            "content": content,
            "timestamp": self._now_iso(),
        }
        if tool_call_id:
            message["tool_call_id"] = tool_call_id
        self.messages.append(message)
        return message

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
