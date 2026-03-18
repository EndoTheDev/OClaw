import json
import httpx
from typing import AsyncGenerator

from ..logger import Logger
from ..sessions import Message
from .base import (
    DoneChunk,
    ErrorChunk,
    MetricsChunk,
    ResponseChunk,
    StreamingChunk,
    ThinkingChunk,
    ToolCallChunk,
    ToolDefinition,
)


class OpenAIProvider:
    def __init__(self, base_url: str | None = None, model: str | None = None):
        from ..config import Config

        config = Config.load()
        self.logger = Logger.get("openai.py")

        self.base_url = base_url or config.provider.openai_host
        self.model = model or config.provider.model
        self.api_key = config.provider.openai_api_key
        self.client = httpx.AsyncClient(timeout=300.0)
        self.logger.info(
            "provider.openai.init",
            base_url=self.base_url,
            model=self.model,
        )

    def _convert_tools(self, tools: list[ToolDefinition] | None) -> list[dict] | None:
        if not tools:
            return None
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in tools
        ]

    def _convert_messages(self, messages: list[Message]) -> list[dict]:
        provider_messages = []
        for msg in messages:
            provider_message: dict[str, object] = {
                "role": msg["role"],
                "content": msg.get("content", ""),
            }

            if "thinking" in msg:
                provider_message["thinking"] = msg["thinking"]

            if "tool_calls" in msg and msg["tool_calls"]:
                formatted_tool_calls = []
                for tc in msg["tool_calls"]:
                    func = tc.get("function")
                    if not func:
                        continue
                    arguments = func.get("arguments", {})
                    formatted_tc = {
                        "type": "function",
                        "function": {
                            "name": func.get("name", ""),
                            "arguments": json.dumps(arguments)
                            if isinstance(arguments, dict)
                            else arguments,
                        },
                    }
                    if "id" in tc:
                        formatted_tc["id"] = tc["id"]
                    formatted_tool_calls.append(formatted_tc)
                provider_message["tool_calls"] = formatted_tool_calls

            if msg["role"] == "tool":
                if "tool_name" in msg:
                    provider_message["name"] = msg["tool_name"]
                if "tool_call_id" in msg:
                    provider_message["tool_call_id"] = msg["tool_call_id"]

            provider_messages.append(provider_message)
        return provider_messages

    async def chat(
        self, messages: list[Message], tools: list[ToolDefinition] | None = None
    ) -> AsyncGenerator[StreamingChunk, None]:

        url = f"{self.base_url}/chat/completions"

        openai_messages = self._convert_messages(messages)

        payload = {
            "model": self.model,
            "messages": openai_messages,
            "stream": True,
        }

        openai_tools = self._convert_tools(tools)
        if openai_tools:
            payload["tools"] = openai_tools

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        self.logger.info(
            "provider.openai.chat.start",
            url=url,
            model=self.model,
            message_count=len(messages),
            tools_enabled=bool(tools),
        )

        try:
            async with self.client.stream(
                "POST", url, headers=headers, json=payload
            ) as response:
                response.raise_for_status()
                accumulated_tool_calls = {}

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue

                    data_str = line[5:].lstrip()

                    if data_str == "[DONE]":
                        for tc_idx, tc_data in accumulated_tool_calls.items():
                            try:
                                args_dict = (
                                    json.loads(tc_data["arguments"])
                                    if tc_data["arguments"]
                                    else {}
                                )
                            except json.JSONDecodeError as e:
                                self.logger.error(
                                    "provider.openai.tool_call.json_error",
                                    error=str(e),
                                    args=tc_data["arguments"],
                                )
                                args_dict = {}
                            yield ToolCallChunk(
                                id=tc_data.get("id", ""),
                                name=tc_data["name"],
                                arguments=args_dict,
                            )
                        yield DoneChunk(done_reason="stop")
                        break

                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    choice = data["choices"][0]
                    delta = choice.get("delta", {})

                    # Content
                    if content := delta.get("content"):
                        yield ResponseChunk(content=content)

                    # Thinking (reasoning models sometimes emit reasoning tokens)
                    if thinking := delta.get("reasoning"):
                        yield ThinkingChunk(content=thinking)

                    # Tool calls
                    if tool_calls := delta.get("tool_calls"):
                        for tc in tool_calls:
                            idx = tc.get("index")
                            if idx not in accumulated_tool_calls:
                                accumulated_tool_calls[idx] = {
                                    "name": "",
                                    "arguments": "",
                                    "id": tc.get("id", ""),
                                }
                            else:
                                if "id" in tc and tc["id"]:
                                    accumulated_tool_calls[idx]["id"] = tc["id"]

                            func = tc.get("function", {})
                            if "name" in func:
                                accumulated_tool_calls[idx]["name"] += func["name"]
                            if "arguments" in func:
                                accumulated_tool_calls[idx]["arguments"] += func[
                                    "arguments"
                                ]

                        # Yield incremental tool call chunks for each update
                        for idx, tc_data in accumulated_tool_calls.items():
                            if tc_data["name"]:
                                try:
                                    args_dict = (
                                        json.loads(tc_data["arguments"])
                                        if tc_data["arguments"]
                                        else {}
                                    )
                                except json.JSONDecodeError:
                                    args_dict = {}
                                yield ToolCallChunk(
                                    id=tc_data.get("id", ""),
                                    name=tc_data["name"],
                                    arguments=args_dict,
                                )

        except httpx.HTTPStatusError as e:
            self.logger.error(
                "provider.openai.http_error",
                status_code=e.response.status_code,
            )
            yield ErrorChunk(error=f"HTTP error: {e.response.status_code}")

        except httpx.ConnectError:
            self.logger.error("provider.openai.connect_error")
            yield ErrorChunk(error="Cannot connect to OpenAI API")

        except Exception as e:
            self.logger.error("provider.openai.unexpected_error", error=str(e))
            yield ErrorChunk(error=f"Unexpected error: {e}")


PROVIDER_NAME = "openai"


def create_provider() -> OpenAIProvider:
    return OpenAIProvider()
