from __future__ import annotations

import asyncio
import json
from asyncio import Queue
from json import JSONDecodeError
from typing import Any, AsyncGenerator

from ..tools import ToolsManager
from .types import StreamOutput, ToolCall, ToolEnd


class ToolExecutionHandler:
    def __init__(
        self,
        tools_manager: ToolsManager,
    ):
        self.tools_manager = tools_manager
        self._permission_queue: Any = None

    def set_permission_queue(self, queue: Any) -> None:
        self._permission_queue = queue

    async def execute_tool_calls(
        self,
        tool_calls: list[ToolCall],
        request_id: str | None = None,
    ) -> AsyncGenerator[StreamOutput, None]:
        for tool_call in tool_calls:
            function_payload = tool_call.get("function")
            if not function_payload:
                continue

            tool_name = function_payload.get("name", "")
            tool_args = function_payload.get("arguments", {})
            tool_call_id = tool_call.get("id")

            normalized_args = self._normalize_arguments(tool_args)

            if self._permission_queue is not None:
                permission_output: StreamOutput = {
                    "type": "permission_request",
                    "name": tool_name,
                    "args": normalized_args,
                    "request_id": request_id or "",
                }
                yield permission_output

                loop = asyncio.get_running_loop()
                approved = await loop.run_in_executor(None, self._permission_queue.get)

                if not approved:
                    result_msg = (
                        f"DENIED: The user has explicitly rejected your request "
                        f"to execute the '{tool_name}' tool."
                    )
                    denied_output: ToolEnd = {
                        "type": "tool_end",
                        "tool_name": tool_name,
                        "tool_call_id": tool_call_id,
                        "result": result_msg,
                    }
                    yield denied_output
                    continue

            tool_result = await self.tools_manager.execute(tool_name, normalized_args)
            tool_end_output: ToolEnd = {
                "type": "tool_end",
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                "result": tool_result,
            }
            yield tool_end_output

    def _normalize_arguments(self, args: dict[str, Any] | str) -> dict[str, Any]:
        if isinstance(args, str):
            try:
                parsed = json.loads(args)
                return parsed if isinstance(parsed, dict) else {}
            except JSONDecodeError:
                return {}
        if isinstance(args, dict):
            return args
        return {}

    def collect_tool_calls(
        self, tool_call_chunks: list[dict[str, Any]]
    ) -> list[ToolCall]:
        tool_calls: list[ToolCall] = []
        for chunk in tool_call_chunks:
            normalized_call: ToolCall = {
                "type": "function",
                "function": {
                    "name": chunk["name"],
                    "arguments": chunk["arguments"],
                },
            }
            if chunk.get("id"):
                normalized_call["id"] = chunk["id"]
            tool_calls.append(normalized_call)
        return tool_calls
