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


class OpenAIProvider:
    def __init__(self, base_url: str | None = None, model: str | None = None):
        from ..config import Config

        config = Config.load()
        self.logger = Logger.get("openai.py")

        self.base_url = base_url or config.openai_host
        self.model = model or config.model
        self.api_key = config.openai_api_key
        self.client = httpx.AsyncClient(timeout=300.0)
        self.logger.info(
            "provider.openai.init", base_url=self.base_url, model=self.model,
        )

    async def chat(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> AsyncGenerator[StreamingChunk, None]:

        url = f"{self.base_url}/chat/completions"

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }

        if tools:
            payload["tools"] = tools

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

                    data_str = line.removeprefix("data: ").strip()

                    if data_str == "[DONE]":
                        for tc_idx, tc_data in accumulated_tool_calls.items():
                            try:
                                args_dict = json.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
                            except json.JSONDecodeError as e:
                                self.logger.error("provider.openai.tool_call.json_error", error=str(e), args=tc_data["arguments"])
                                args_dict = {}
                            yield ToolCallChunk(
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
                                accumulated_tool_calls[idx] = {"name": "", "arguments": ""}
                            
                            func = tc.get("function", {})
                            if "name" in func:
                                accumulated_tool_calls[idx]["name"] += func["name"]
                            if "arguments" in func:
                                accumulated_tool_calls[idx]["arguments"] += func["arguments"]

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