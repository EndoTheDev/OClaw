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


class AnthropicProvider:
    def __init__(self, base_url: str | None = None, model: str | None = None):
        from ..config import Config

        config = Config.load()
        self.logger = Logger.get("anthropic.py")

        self.base_url = base_url or config.provider.anthropic_host
        self.model = model or config.provider.model
        self.api_key = config.provider.anthropic_api_key
        self.client = httpx.AsyncClient(timeout=300.0)
        self.logger.info(
            "provider.anthropic.init",
            base_url=self.base_url,
            model=self.model,
        )

    def _convert_tools_to_anthropic(
        self, tools: list[ToolDefinition] | None
    ) -> list[dict] | None:
        if not tools:
            return None

        anthropic_tools = []
        for tool in tools:
            anthropic_tool = {
                "name": tool.name,
                "description": tool.description,
                "input_schema": {
                    "type": "object",
                    "properties": tool.parameters.get("properties", {}),
                    "required": tool.parameters.get("required", []),
                },
            }
            anthropic_tools.append(anthropic_tool)

        return anthropic_tools if anthropic_tools else None

    def _convert_messages_to_anthropic(self, messages: list[Message]) -> list[dict]:
        """Convert standard message format to Anthropic's format."""
        if not messages:
            return []

        anthropic_messages = []
        for msg in messages:
            role = msg["role"]

            if role == "system":
                continue

            content = msg.get("content", "")

            if role == "tool":
                block = {
                    "type": "tool_result",
                    "tool_use_id": msg.get("tool_call_id", ""),
                    "content": content,
                }

                if anthropic_messages and anthropic_messages[-1]["role"] == "user":
                    if isinstance(anthropic_messages[-1]["content"], list):
                        anthropic_messages[-1]["content"].append(block)
                    else:
                        anthropic_messages[-1]["content"] = [
                            {"type": "text", "text": anthropic_messages[-1]["content"]},
                            block,
                        ]
                else:
                    anthropic_messages.append({"role": "user", "content": [block]})
                continue

            tool_calls = msg.get("tool_calls")
            if role == "assistant" and tool_calls:
                blocks = []
                if content:
                    blocks.append({"type": "text", "text": content})

                for tool_call in tool_calls:
                    func = tool_call.get("function")
                    if not func:
                        continue
                    args = func.get("arguments", {})

                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}

                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": tool_call.get("id", ""),
                            "name": func.get("name", ""),
                            "input": args,
                        }
                    )

                anthropic_messages.append({"role": "assistant", "content": blocks})
                continue

            anthropic_messages.append({"role": role, "content": content})

        return anthropic_messages

    async def chat(
        self, messages: list[Message], tools: list[ToolDefinition] | None = None
    ) -> AsyncGenerator[StreamingChunk, None]:

        url = f"{self.base_url}/messages"

        system_prompt = next(
            (
                m.get("content")
                for m in messages
                if m["role"] == "system" and m.get("content")
            ),
            None,
        )

        anthropic_messages = self._convert_messages_to_anthropic(messages)

        payload = {
            "model": self.model,
            "messages": anthropic_messages,
            "max_tokens": 4096,
            "stream": True,
        }

        if system_prompt:
            payload["system"] = system_prompt

        anthropic_tools = self._convert_tools_to_anthropic(tools)
        if anthropic_tools:
            payload["tools"] = anthropic_tools

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        self.logger.info(
            "provider.anthropic.chat.start",
            url=url,
            model=self.model,
            message_count=len(messages),
            tools_enabled=bool(anthropic_tools),
        )

        try:
            async with self.client.stream(
                "POST", url, headers=headers, json=payload
            ) as response:
                response.raise_for_status()
                accumulated_tool_input = {}
                accumulated_tool_ids = {}
                current_tool_name = ""

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue

                    data_str = line[5:].lstrip()

                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    # Handle both array and object formats
                    if isinstance(data, list):
                        data = data[0] if data else {}

                    event_type = data.get("type")

                    if event_type == "content_block_start":
                        content_block = data.get("content_block", {})
                        block_type = content_block.get("type")

                        if block_type == "tool_use":
                            current_tool_name = content_block.get("name", "")
                            accumulated_tool_input[current_tool_name] = ""
                            accumulated_tool_ids[current_tool_name] = content_block.get(
                                "id"
                            )
                            # Yield initial ToolCallChunk with empty arguments
                            yield ToolCallChunk(
                                name=current_tool_name,
                                arguments={},
                                id=accumulated_tool_ids[current_tool_name],
                            )

                    elif event_type == "content_block_delta":
                        delta = data.get("delta", {})
                        delta_type = delta.get("type")

                        if delta_type == "text_delta":
                            content = delta.get("text", "")
                            yield ResponseChunk(content=content)

                        elif delta_type == "input_json_delta":
                            json_delta = delta.get("partial_json", "")
                            if current_tool_name:
                                accumulated_tool_input[current_tool_name] += json_delta

                    elif event_type == "content_block_stop":
                        if (
                            current_tool_name
                            and current_tool_name in accumulated_tool_input
                        ):
                            try:
                                args_dict = (
                                    json.loads(
                                        accumulated_tool_input[current_tool_name]
                                    )
                                    if accumulated_tool_input[current_tool_name]
                                    else {}
                                )
                            except json.JSONDecodeError as e:
                                self.logger.error(
                                    "provider.anthropic.tool_call.json_error",
                                    error=str(e),
                                    input=accumulated_tool_input[current_tool_name],
                                )
                                args_dict = {}

                            yield ToolCallChunk(
                                name=current_tool_name,
                                arguments=args_dict,
                                id=accumulated_tool_ids.get(current_tool_name, ""),
                            )
                            current_tool_name = ""

                    elif event_type == "message_stop":
                        yield DoneChunk(done_reason="end_turn")

                    elif event_type == "message_delta":
                        usage = data.get("usage", {})
                        if usage:
                            metrics_data = {
                                "input_tokens": usage.get("input_tokens", 0),
                                "output_tokens": usage.get("output_tokens", 0),
                            }
                            self.logger.info(
                                "provider.anthropic.chat.metrics",
                                metrics=metrics_data,
                            )
                            yield MetricsChunk(data=metrics_data)

        except httpx.HTTPStatusError as e:
            self.logger.error(
                "provider.anthropic.http_error",
                status_code=e.response.status_code,
            )
            yield ErrorChunk(error=f"HTTP error: {e.response.status_code}")

        except httpx.ConnectError:
            self.logger.error("provider.anthropic.connect_error")
            yield ErrorChunk(error="Cannot connect to Anthropic API")

        except Exception as e:
            self.logger.error("provider.anthropic.unexpected_error", error=str(e))
            yield ErrorChunk(error=f"Unexpected error: {e}")


PROVIDER_NAME = "anthropic"


def create_provider() -> AnthropicProvider:
    return AnthropicProvider()
