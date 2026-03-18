from __future__ import annotations

import asyncio
import json
from json import JSONDecodeError
from typing import Any, AsyncGenerator

from ..logger import Logger
from ..tools import ToolsManager
from .types import ExecutionContext, ToolCall, ToolExecutionOutput


class ToolExecutionHandler:
    def __init__(
        self,
        tools_manager: ToolsManager,
        logger: Logger | None = None,
    ):
        self.tools_manager = tools_manager
        self.logger = logger or Logger.get("tool_execution_handler.py")
        self._permission_queue: Any = None

    def set_permission_queue(self, queue: Any) -> None:
        self._permission_queue = queue

    async def execute_tool_calls(
        self,
        tool_calls: list[ToolCall],
        context: ExecutionContext,
    ) -> AsyncGenerator[ToolExecutionOutput, None]:
        for tool_call in tool_calls:
            function_payload = tool_call.get("function")
            if not function_payload:
                continue

            tool_name = function_payload.get("name", "")
            tool_args = function_payload.get("arguments", {})
            tool_call_id = tool_call.get("id")

            self.logger.info(
                "tool.execute",
                session_id=context.session_id,
                request_id=context.request_id,
                iteration=context.iteration,
                tool_name=tool_name,
            )

            normalized_args = self._normalize_arguments(tool_args)
            execution_start: ToolExecutionOutput = {
                "kind": "tool_execution_start",
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                "args": normalized_args,
            }
            yield execution_start

            if self._permission_queue is not None:
                approval_requested: ToolExecutionOutput = {
                    "kind": "tool_execution_update",
                    "tool_name": tool_name,
                    "tool_call_id": tool_call_id,
                    "args": normalized_args,
                    "phase": "approval_requested",
                }
                yield approval_requested

                if isinstance(self._permission_queue, asyncio.Queue):
                    approved = await self._permission_queue.get()
                else:
                    loop = asyncio.get_running_loop()
                    approved = await loop.run_in_executor(
                        None, self._permission_queue.get
                    )

                if not approved:
                    result_msg = (
                        f"DENIED: The user has explicitly rejected your request "
                        f"to execute the '{tool_name}' tool."
                    )
                    approval_denied: ToolExecutionOutput = {
                        "kind": "tool_execution_update",
                        "tool_name": tool_name,
                        "tool_call_id": tool_call_id,
                        "phase": "approval_denied",
                    }
                    yield approval_denied
                    denied_output: ToolExecutionOutput = {
                        "kind": "tool_execution_end",
                        "tool_name": tool_name,
                        "tool_call_id": tool_call_id,
                        "status": "denied",
                        "result": result_msg,
                    }
                    yield denied_output
                    continue

                approval_granted: ToolExecutionOutput = {
                    "kind": "tool_execution_update",
                    "tool_name": tool_name,
                    "tool_call_id": tool_call_id,
                    "phase": "approval_granted",
                }
                yield approval_granted

            executing_update: ToolExecutionOutput = {
                "kind": "tool_execution_update",
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                "phase": "executing",
                "args": normalized_args,
            }
            yield executing_update

            try:
                tool_result = await self.tools_manager.execute(
                    tool_name, normalized_args
                )
                tool_end_output: ToolExecutionOutput = {
                    "kind": "tool_execution_end",
                    "tool_name": tool_name,
                    "tool_call_id": tool_call_id,
                    "status": "succeeded",
                    "result": tool_result,
                }
                yield tool_end_output
            except Exception as error:
                tool_end_output: ToolExecutionOutput = {
                    "kind": "tool_execution_end",
                    "tool_name": tool_name,
                    "tool_call_id": tool_call_id,
                    "status": "failed",
                    "error": str(error),
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
