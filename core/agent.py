from typing import TYPE_CHECKING

from .context import ContextManager
from .logger import Logger
from .sessions import SessionsManager, ToolCall

from .providers.base import (
    DoneChunk,
    ErrorChunk,
    MetricsChunk,
    ResponseChunk,
    ThinkingChunk,
    ToolCallChunk,
)

if TYPE_CHECKING:
    from .providers.base import Provider
    from .tools import ToolsManager


class Agent:
    def __init__(
        self,
        provider: "Provider",
        tools: "ToolsManager",
        system_prompt: str = "You are a helpful assistant. Be concise and to the point.",
    ):
        self.provider = provider
        self.tools = tools
        self.context = ContextManager()
        self.sessions = SessionsManager()
        self.system_prompt = system_prompt
        self.logger = Logger.get("agent.py")

    async def stream(
        self,
        user_message: str,
        max_iterations: int = 5,
        request_id: str | None = None,
        input_queue = None,
    ):
        session = self.sessions.load_latest_or_create()
        session_id = session.metadata.session_id
        self.logger.info(
            "agent.start",
            request_id=request_id,
            session_id=session_id,
            max_iterations=max_iterations,
        )
        self.logger.info(
            "agent.user_input",
            request_id=request_id,
            session_id=session_id,
            message_chars=len(user_message),
        )
        self.context.load(session.messages)
        self.context.append_user(user_message)

        tool_defs = self.tools.get_definitions()

        try:
            for iteration in range(1, max_iterations + 1):
                response_content = ""
                response_thinking = ""
                tool_calls: list[ToolCall] = []

                messages = list(self.context.messages)

                if self.system_prompt.strip():
                    messages.insert(0, {
                        "role": "system",
                        "content": self.system_prompt,
                        "timestamp": self.context._now_iso()
                    })

                async for chunk in self.provider.chat(
                    messages,
                    tools=tool_defs if tool_defs else None,
                ):
                    if isinstance(chunk, ResponseChunk):
                        response_content += chunk.content
                        self.logger.debug(
                            "assistant.response.chunk",
                            request_id=request_id,
                            session_id=session_id,
                            iteration=iteration,
                            content=chunk.content,
                        )
                        yield {"type": "token", "content": chunk.content}

                    elif isinstance(chunk, ThinkingChunk):
                        response_thinking += chunk.content
                        self.logger.debug(
                            "assistant.thinking.chunk",
                            request_id=request_id,
                            session_id=session_id,
                            iteration=iteration,
                            content=chunk.content,
                        )
                        yield {"type": "thinking", "content": chunk.content}

                    elif isinstance(chunk, ToolCallChunk):
                        normalized_call: ToolCall = {
                            "type": "function",
                            "function": {
                                "name": chunk.name,
                                "arguments": chunk.arguments,
                            },
                        }
                        if chunk.id:
                            normalized_call["id"] = chunk.id
                        tool_calls.append(normalized_call)
                        self.logger.info(
                            "assistant.tool_call",
                            request_id=request_id,
                            session_id=session_id,
                            iteration=iteration,
                            name=chunk.name,
                            id=chunk.id,
                            arguments=chunk.arguments,
                        )
                        yield {
                            "type": "tool_call",
                            "name": chunk.name,
                            "id": chunk.id,
                            "args": chunk.arguments,
                        }

                    elif isinstance(chunk, MetricsChunk):
                        self.logger.info(
                            "assistant.metrics",
                            request_id=request_id,
                            session_id=session_id,
                            iteration=iteration,
                            data=chunk.data,
                        )
                        yield {"type": "metrics", "data": chunk.data}

                    elif isinstance(chunk, DoneChunk):
                        continue

                    elif isinstance(chunk, ErrorChunk):
                        self.logger.error(
                            "agent.error",
                            request_id=request_id,
                            session_id=session_id,
                            iteration=iteration,
                            message=chunk.error,
                        )
                        yield {"type": "error", "message": chunk.error}
                        return

                self.logger.info(
                    "assistant.thinking.final",
                    request_id=request_id,
                    session_id=session_id,
                    iteration=iteration,
                    chars=len(response_thinking),
                )
                self.logger.info(
                    "assistant.response.final",
                    request_id=request_id,
                    session_id=session_id,
                    iteration=iteration,
                    chars=len(response_content),
                )

                self.context.append_assistant(
                    content=response_content,
                    thinking=response_thinking or None,
                    tool_calls=tool_calls or None,
                )

                if not tool_calls:
                    yield {"type": "done"}
                    return

                for tool_call in tool_calls:
                    tool_name = tool_call["function"]["name"]
                    tool_args = tool_call["function"]["arguments"]
                    tool_call_id = tool_call.get("id")
                    
                    if input_queue is not None:
                        yield {
                            "type": "permission_request",
                            "name": tool_name,
                            "args": tool_args,
                            "request_id": request_id, 
                        }
                        
                        import asyncio
                        loop = asyncio.get_running_loop()
                        approved = await loop.run_in_executor(None, input_queue.get)
                        
                        if not approved:
                            result_msg = f"DENIED: The user has explicitly rejected your request to execute the '{tool_name}' tool."
                            yield {"type": "tool_end", "result": result_msg}
                            self.context.append_tool(tool_name=tool_name, content=result_msg, tool_call_id=tool_call_id)
                            continue

                    tool_result = await self.tools.execute(tool_name, tool_args)
                    self.logger.info(
                        "tool.output",
                        request_id=request_id,
                        session_id=session_id,
                        iteration=iteration,
                        name=tool_name,
                        arguments_count=len(tool_args),
                        result_chars=len(tool_result),
                    )

                    yield {"type": "tool_end", "result": tool_result}

                    self.context.append_tool(tool_name=tool_name, content=tool_result, tool_call_id=tool_call_id)

            yield {"type": "done"}
        finally:
            session.messages = self.context.messages
            self.sessions.overwrite(session)
            self.logger.info(
                "agent.end",
                request_id=request_id,
                session_id=session_id,
                message_count=len(self.context.messages),
            )
