from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4
from typing import TYPE_CHECKING, Any, AsyncGenerator, cast

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
from .types import EventType, ExecutionContext, StreamEventEnvelope, StreamOutput


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
        context: ExecutionContext,
        input_queue: Queue | None = None,
    ) -> AsyncGenerator[StreamOutput, None]:
        active_request_id = context.request_id or str(uuid4())
        sequence = 0
        agent_status = "succeeded"
        stream_status = "succeeded"
        error_emitted = False
        turn_open = False
        message_open = False
        active_turn_id: str | None = None
        active_iteration: int | None = None
        active_message_id: str | None = None
        active_message_content = ""
        active_message_thinking = ""
        active_tool_call_count = 0

        def next_event(
            event_type: EventType,
            payload: dict[str, Any],
            turn_id: str | None,
        ) -> StreamEventEnvelope:
            nonlocal sequence
            sequence += 1
            return cast(
                StreamEventEnvelope,
                {
                    "schema_version": "2.0",
                    "event_id": str(uuid4()),
                    "sequence": sequence,
                    "timestamp": datetime.now(timezone.utc)
                    .isoformat(timespec="milliseconds")
                    .replace("+00:00", "Z"),
                    "event_type": event_type,
                    "request_id": active_request_id,
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "payload": payload,
                },
            )

        self._orchestrator.initialize_session(session_id)
        self._orchestrator.append_user_message(user_message)
        self._log_start(context)
        yield next_event(
            "agent_start",
            {"status": "started", "max_iterations": context.max_iterations},
            None,
        )

        try:
            for iteration in range(1, context.max_iterations + 1):
                turn_id = str(uuid4())
                message_id = str(uuid4())
                message_content = ""
                message_thinking = ""
                tool_call_chunks: list[dict[str, Any]] = []
                turn_status = "succeeded"
                active_turn_id = turn_id
                active_iteration = iteration
                active_message_id = message_id
                active_message_content = ""
                active_message_thinking = ""
                active_tool_call_count = 0

                yield next_event("turn_start", {"iteration": iteration}, turn_id)
                turn_open = True
                yield next_event(
                    "message_start",
                    {"message_id": message_id, "role": "assistant"},
                    turn_id,
                )
                message_open = True

                tool_definitions = self._orchestrator._tools_manager.get_definitions()
                active_skills = self._orchestrator.get_active_skills()

                messages = self._message_builder.build(
                    active_skills=active_skills,
                    tool_definitions=tool_definitions,
                )

                chunk_stream = self._provider.chat(messages, tool_definitions)
                provider_error_detected = False
                provider_error_message = ""

                async for output in self._dispatcher.dispatch(
                    chunk_stream,
                    context=context.with_turn(turn_id),
                ):
                    output_kind = output.get("kind")
                    if output_kind == "provider_error":
                        provider_error_detected = True
                        provider_error_message = output.get(
                            "message", "Unknown provider error"
                        )
                        break
                    if output_kind == "message_tool_call":
                        tool_call_chunks.append(
                            {
                                "name": output.get("name"),
                                "arguments": output.get("args"),
                                "id": output.get("id"),
                            }
                        )
                        yield next_event(
                            "message_update",
                            {
                                "message_id": message_id,
                                "tool_call": {
                                    "name": output.get("name"),
                                    "id": output.get("id"),
                                    "args": output.get("args", {}),
                                },
                            },
                            turn_id,
                        )
                    elif output_kind == "message_token":
                        delta = output.get("content", "")
                        message_content += delta
                        active_message_content = message_content
                        yield next_event(
                            "message_update",
                            {
                                "message_id": message_id,
                                "channel": "content",
                                "delta": delta,
                            },
                            turn_id,
                        )
                    elif output_kind == "message_thinking":
                        delta = output.get("content", "")
                        message_thinking += delta
                        active_message_thinking = message_thinking
                        yield next_event(
                            "message_update",
                            {
                                "message_id": message_id,
                                "channel": "thinking",
                                "delta": delta,
                            },
                            turn_id,
                        )
                    elif output_kind == "message_metrics":
                        yield next_event(
                            "message_update",
                            {
                                "message_id": message_id,
                                "metrics": output.get("data", {}),
                            },
                            turn_id,
                        )

                if provider_error_detected:
                    turn_status = "failed"
                    if message_content or message_thinking or tool_call_chunks:
                        self._orchestrator.append_assistant_message(
                            content=message_content,
                            thinking=message_thinking or None,
                            tool_calls=self._tool_handler.collect_tool_calls(
                                tool_call_chunks
                            ),
                        )
                    yield next_event(
                        "message_end",
                        {
                            "message_id": message_id,
                            "status": "failed",
                            "content": message_content,
                            "thinking": message_thinking,
                            "tool_call_count": len(tool_call_chunks),
                        },
                        turn_id,
                    )
                    message_open = False
                    yield next_event(
                        "turn_end",
                        {"iteration": iteration, "status": turn_status},
                        turn_id,
                    )
                    turn_open = False
                    yield next_event(
                        "error",
                        {
                            "message": provider_error_message,
                            "fatal": True,
                        },
                        turn_id,
                    )
                    error_emitted = True
                    agent_status = "failed"
                    stream_status = "failed"
                    break

                tool_calls = self._tool_handler.collect_tool_calls(tool_call_chunks)
                self._orchestrator.append_assistant_message(
                    content=message_content,
                    thinking=message_thinking or None,
                    tool_calls=tool_calls,
                )
                yield next_event(
                    "message_end",
                    {
                        "message_id": message_id,
                        "status": "completed",
                        "content": message_content,
                        "thinking": message_thinking,
                        "tool_call_count": len(tool_calls),
                    },
                    turn_id,
                )
                message_open = False
                active_tool_call_count = len(tool_calls)

                if not tool_calls:
                    yield next_event(
                        "turn_end",
                        {"iteration": iteration, "status": "succeeded"},
                        turn_id,
                    )
                    turn_open = False
                    break

                self._tool_handler.set_permission_queue(input_queue)
                turn_status = "succeeded"

                async for output in self._tool_handler.execute_tool_calls(
                    tool_calls, context
                ):
                    output_kind = output.get("kind")
                    tool_name = output.get("tool_name", "")
                    tool_call_id = output.get("tool_call_id")

                    if output_kind == "tool_execution_start":
                        yield next_event(
                            "tool_execution_start",
                            {
                                "tool_name": tool_name,
                                "tool_call_id": tool_call_id,
                                "args": output.get("args", {}),
                            },
                            turn_id,
                        )
                        continue

                    if output_kind == "tool_execution_update":
                        update_payload: dict[str, Any] = {
                            "tool_name": tool_name,
                            "tool_call_id": tool_call_id,
                            "phase": output.get("phase"),
                        }
                        if "args" in output:
                            update_payload["args"] = output.get("args", {})
                        yield next_event(
                            "tool_execution_update",
                            update_payload,
                            turn_id,
                        )
                        continue

                    if output_kind == "tool_execution_end":
                        status = output.get("status")
                        if status == "failed":
                            turn_status = "failed"
                        elif status == "denied" and turn_status != "failed":
                            turn_status = "denied"
                        payload: dict[str, Any] = {
                            "tool_name": tool_name,
                            "tool_call_id": tool_call_id,
                            "status": status,
                        }
                        if "result" in output:
                            payload["result"] = output.get("result")
                        if "error" in output:
                            payload["error"] = output.get("error")
                        yield next_event("tool_execution_end", payload, turn_id)

                        result_content = (
                            output.get("result") or output.get("error") or ""
                        )
                        self._orchestrator.append_tool_message(
                            tool_name=tool_name,
                            content=str(result_content),
                            tool_call_id=tool_call_id,
                        )
                yield next_event(
                    "turn_end",
                    {"iteration": iteration, "status": turn_status},
                    turn_id,
                )
                turn_open = False
                if turn_status != "succeeded":
                    agent_status = "failed"
                    stream_status = "failed"
                    yield next_event(
                        "error",
                        {
                            "message": (
                                "Tool execution denied"
                                if turn_status == "denied"
                                else "Tool execution failed"
                            ),
                            "fatal": True,
                        },
                        turn_id,
                    )
                    error_emitted = True
                    break
        except Exception as error:
            if message_open and active_message_id is not None:
                yield next_event(
                    "message_end",
                    {
                        "message_id": active_message_id,
                        "status": "failed",
                        "content": active_message_content,
                        "thinking": active_message_thinking,
                        "tool_call_count": active_tool_call_count,
                    },
                    active_turn_id,
                )
                message_open = False
            if turn_open and active_iteration is not None:
                yield next_event(
                    "turn_end",
                    {"iteration": active_iteration, "status": "failed"},
                    active_turn_id,
                )
                turn_open = False
            if not error_emitted:
                yield next_event(
                    "error",
                    {
                        "message": str(error),
                        "fatal": True,
                    },
                    active_turn_id if turn_open else None,
                )
            agent_status = "failed"
            stream_status = "failed"
        finally:
            self._orchestrator.persist()
            yield next_event("agent_end", {"status": agent_status}, None)
            yield next_event("stream_end", {"status": stream_status}, None)
            self._log_end(context)

    def _log_start(self, context: ExecutionContext) -> None:
        self._logger.info(
            "agent.start",
            request_id=context.request_id,
            session_id=context.session_id,
            max_iterations=context.max_iterations,
        )

    def _log_end(self, context: ExecutionContext) -> None:
        self._logger.info(
            "agent.end",
            request_id=context.request_id,
            session_id=context.session_id,
        )
