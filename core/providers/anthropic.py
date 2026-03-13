import json
import httpx
from typing import AsyncGenerator

from ..logger import Logger
from .base import (
    DoneChunk,
    ErrorChunk,
    MetricsChunk,
    ResponseChunk,
    StreamingChunk,
    ThinkingChunk,
    ToolCallChunk,
)


class AnthropicProvider:
    def __init__(self, base_url: str | None = None, model: str | None = None):
        from ..config import Config

        config = Config.load()
        self.logger = Logger.get("anthropic.py")

        self.base_url = base_url or config.anthropic_host
        self.model = model or config.model
        self.api_key = config.anthropic_api_key
        self.client = httpx.AsyncClient(timeout=300.0)
        self.logger.info(
            "provider.anthropic.init", base_url=self.base_url, model=self.model,
        )

    def _convert_openai_tools_to_anthropic(self, openai_tools: list[dict] | None) -> list[dict] | None:
        if not openai_tools:
            return None
        
        anthropic_tools = []
        for tool in openai_tools:
            if tool["type"] != "function":
                continue
            
            func = tool["function"]
            anthropic_tool = {
                "name": func["name"],
                "description": func.get("description", ""),
                "input_schema": {
                    "type": "object",
                    "properties": func.get("parameters", {}).get("properties", {}),
                    "required": func.get("parameters", {}).get("required", []),
                },
            }
            anthropic_tools.append(anthropic_tool)
        
        return anthropic_tools if anthropic_tools else None

    async def chat(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> AsyncGenerator[StreamingChunk, None]:

        url = f"{self.base_url}/messages"

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 4096,
            "stream": True,
        }

        anthropic_tools = self._convert_openai_tools_to_anthropic(tools)
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
                current_tool_name = ""

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    event_type = data.get("type")

                    if event_type == "content_block_start":
                        content_block = data.get("content_block", {})
                        block_type = content_block.get("type")
                        
                        if block_type == "tool_use":
                            current_tool_name = content_block.get("name", "")
                            accumulated_tool_input[current_tool_name] = ""

                    elif event_type == "content_block_delta":
                        delta = data.get("delta", {})
                        delta_type = delta.get("type")
                        
                        if delta_type == "text_delta":
                            content = delta.get("text", "")
                            yield ResponseChunk(content=content)
                        
                        elif delta_type == "input_json_delta":
                            json_delta = delta.get("input_json", "")
                            if current_tool_name:
                                accumulated_tool_input[current_tool_name] += json_delta

                    elif event_type == "content_block_stop":
                        if current_tool_name and current_tool_name in accumulated_tool_input:
                            try:
                                args_dict = json.loads(accumulated_tool_input[current_tool_name])
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
