from __future__ import annotations

from typing import TYPE_CHECKING, Any, AsyncGenerator

from ..context import ContextManager
from ..logger import Logger
from ..providers.base import Provider
from ..sessions import SessionsManager
from ..skills import SkillsManager
from ..tools import ToolsManager
from .chunk_dispatcher import ChunkDispatcher
from .message_builder import MessageBuilder
from .session_orchestrator import SessionOrchestrator
from .tool_execution_handler import ToolExecutionHandler
from .types import StreamOutput


if TYPE_CHECKING:
    from asyncio import Queue


class Agent:
    def __init__(
        self,
        provider: Provider,
        tools: ToolsManager,
        skills: SkillsManager,
        sessions: SessionsManager,
        context: ContextManager,
        system_prompt: str = "You are OClaw, a helpful assistant. Be concise and to the point.",
    ):
        self._provider = provider
        self._logger = Logger.get("agent.py")
        self._orchestrator = SessionOrchestrator(sessions, context, skills, tools)
        self._dispatcher = ChunkDispatcher(self._logger)
        self._message_builder = MessageBuilder(context, skills, system_prompt)
        self._tool_handler = ToolExecutionHandler(tools)

    async def stream(
        self,
        user_message: str,
        session_id: str,
        max_iterations: int = 5,
        request_id: str | None = None,
        input_queue: Queue | None = None,
    ) -> AsyncGenerator[StreamOutput, None]:
        self._orchestrator.initialize_session(session_id)
        self._orchestrator.append_user_message(user_message)
        self._log_start(request_id, session_id, max_iterations)

        try:
            for iteration in range(1, max_iterations + 1):
                tool_definitions = self._orchestrator._tools_manager.get_definitions()
                active_skills = self._orchestrator.get_active_skills()

                messages = self._message_builder.build(
                    active_skills=active_skills,
                    tool_definitions=tool_definitions,
                )

                chunk_stream = self._provider.chat(messages, tool_definitions)

                tool_call_chunks: list = []
                content = ""
                thinking = ""
                provider_error_detected = False

                async for output in self._dispatcher.dispatch(
                    chunk_stream, session_id, request_id, iteration
                ):
                    yield output

                    output_type = output.get("type")
                    if output_type == "error":
                        provider_error_detected = True
                        break
                    if output_type == "tool_call":
                        tool_call_chunks.append(
                            {
                                "name": output.get("name"),
                                "arguments": output.get("args"),
                                "id": output.get("id"),
                            }
                        )
                    elif output_type == "token":
                        content += output.get("content", "")
                    elif output_type == "thinking":
                        thinking += output.get("content", "")

                if provider_error_detected:
                    if content or thinking or tool_call_chunks:
                        self._orchestrator.append_assistant_message(
                            content=content,
                            thinking=thinking or None,
                            tool_calls=self._tool_handler.collect_tool_calls(
                                tool_call_chunks
                            ),
                        )
                    return

                tool_calls = self._tool_handler.collect_tool_calls(tool_call_chunks)
                self._orchestrator.append_assistant_message(
                    content=content,
                    thinking=thinking or None,
                    tool_calls=tool_calls,
                )

                if not tool_calls:
                    done_output: StreamOutput = {"type": "done"}
                    yield done_output
                    return

                self._tool_handler.set_permission_queue(input_queue)

                async for output in self._tool_handler.execute_tool_calls(
                    tool_calls, request_id
                ):
                    yield output

                    if output.get("type") == "tool_end":
                        result = output.get("result")
                        tool_name = output.get("tool_name", "unknown")
                        tool_call_id = output.get("tool_call_id")
                        self._orchestrator.append_tool_message(
                            tool_name=tool_name,
                            content=str(result),
                            tool_call_id=tool_call_id,
                        )
        finally:
            self._orchestrator.persist()
            self._log_end(request_id, session_id)

    def _log_start(
        self, request_id: str | None, session_id: str, max_iterations: int
    ) -> None:
        self._logger.info(
            "agent.start",
            request_id=request_id,
            session_id=session_id,
            max_iterations=max_iterations,
        )

    def _log_end(self, request_id: str | None, session_id: str) -> None:
        self._logger.info(
            "agent.end",
            request_id=request_id,
            session_id=session_id,
        )
