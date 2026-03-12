from typing import TYPE_CHECKING

from .context import ContextManager
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

    async def stream(self, user_message: str, max_iterations: int = 5):
        session = self.sessions.load_latest_or_create()
        self.context.load(session.messages)
        self.context.append_user(user_message)

        tool_schemas = self.tools.get_schemas()

        try:
            for _ in range(max_iterations):
                response_content = ""
                response_thinking = ""
                tool_calls: list[ToolCall] = []

                provider_messages = self.context.as_provider_messages()

                messages = (
                    [
                        {"role": "system", "content": self.system_prompt},
                        *provider_messages,
                    ]
                    if self.system_prompt.strip()
                    else provider_messages
                )

                async for chunk in self.provider.chat(
                    messages,
                    tools=tool_schemas if tool_schemas else None,
                ):

                    if isinstance(chunk, ResponseChunk):
                        response_content += chunk.content
                        yield {"type": "token", "content": chunk.content}

                    elif isinstance(chunk, ThinkingChunk):
                        response_thinking += chunk.content
                        yield {"type": "thinking", "content": chunk.content}

                    elif isinstance(chunk, ToolCallChunk):
                        normalized_call: ToolCall = {
                            "type": "function",
                            "function": {
                                "name": chunk.name,
                                "arguments": chunk.arguments,
                            },
                        }
                        tool_calls.append(normalized_call)
                        yield {
                            "type": "tool_call",
                            "name": chunk.name,
                            "args": chunk.arguments,
                        }

                    elif isinstance(chunk, MetricsChunk):
                        yield {"type": "metrics", "data": chunk.data}

                    elif isinstance(chunk, DoneChunk):
                        continue

                    elif isinstance(chunk, ErrorChunk):
                        yield {"type": "error", "message": chunk.error}
                        return

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

                    tool_result = await self.tools.execute(tool_name, tool_args)

                    yield {"type": "tool_end", "result": tool_result}

                    self.context.append_tool(tool_name=tool_name, content=tool_result)

            yield {"type": "done"}
        finally:
            session.messages = self.context.messages
            self.sessions.overwrite(session)
