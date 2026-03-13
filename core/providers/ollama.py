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


class OllamaProvider:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
    ):
        from ..config import Config

        self.logger = Logger.get("ollama.py")
        config = Config.load()

        self.base_url = base_url or config.ollama_host
        self.model = model or config.model
        self.client = httpx.AsyncClient(timeout=300.0)
        self.logger.info(
            "provider.ollama.init", base_url=self.base_url, model=self.model
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
            provider_message = {
                "role": msg["role"],
                "content": msg.get("content", ""),
            }
            
            if "thinking" in msg:
                provider_message["thinking"] = msg["thinking"]
                
            if "tool_calls" in msg and msg["tool_calls"]:
                formatted_tool_calls = []
                for tc in msg["tool_calls"]:
                    formatted_tc = {
                        "type": "function",
                        "function": {
                            "name": tc["function"]["name"],
                            "arguments": json.dumps(tc["function"]["arguments"]) if isinstance(tc["function"]["arguments"], dict) else tc["function"]["arguments"]
                        }
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
        url = f"{self.base_url}/api/chat"
        self.logger.info(
            "provider.ollama.chat.start",
            url=url,
            model=self.model,
            message_count=len(messages),
            tools_enabled=bool(tools),
        )

        ollama_messages = self._convert_messages(messages)

        payload = {
            "model": self.model,
            "messages": ollama_messages,
            "stream": True,
        }

        ollama_tools = self._convert_tools(tools)
        if ollama_tools:
            payload["tools"] = ollama_tools

        try:
            async with self.client.stream("POST", url, json=payload) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if "error" in data:
                        self.logger.error(
                            "provider.ollama.chat.error", error=data["error"]
                        )
                        yield ErrorChunk(error=f"Ollama error: {data['error']}")
                        return

                    message = data.get("message", {})
                    content = message.get("content", "")
                    thinking = message.get("thinking", "")

                    if thinking:
                        yield ThinkingChunk(content=thinking)

                    if content:
                        yield ResponseChunk(content=content)

                    if tool_calls := message.get("tool_calls", []):
                        for tc in tool_calls:
                            func = tc.get("function", {})
                            yield ToolCallChunk(
                                name=func.get("name", ""),
                                arguments=func.get("arguments", {}),
                            )

                    if data.get("done", False):
                        done_reason = data.get("done_reason")
                        total_duration = data.get("total_duration", 0)
                        load_duration = data.get("load_duration", 0)
                        prompt_eval_count = data.get("prompt_eval_count", 0)
                        prompt_eval_duration = data.get("prompt_eval_duration", 0)
                        eval_count = data.get("eval_count", 0)
                        eval_duration = data.get("eval_duration", 0)

                        if eval_duration > 0:
                            tokens_per_second = eval_count / eval_duration * 1e9
                        else:
                            tokens_per_second = 0.0

                        metrics_data = {
                            "total_duration_ns": total_duration,
                            "load_duration_ns": load_duration,
                            "prompt_eval_count": prompt_eval_count,
                            "prompt_eval_duration_ns": prompt_eval_duration,
                            "eval_count": eval_count,
                            "eval_duration_ns": eval_duration,
                            "tokens_per_second": tokens_per_second,
                        }
                        self.logger.info(
                            "provider.ollama.chat.done", metrics=metrics_data
                        )
                        yield MetricsChunk(data=metrics_data)
                        yield DoneChunk(done_reason=done_reason)
                        break

        except httpx.HTTPStatusError as e:
            self.logger.error(
                "provider.ollama.http_error", status_code=e.response.status_code
            )
            yield ErrorChunk(error=f"HTTP error: {e.response.status_code}")
        except httpx.ConnectError:
            self.logger.error("provider.ollama.connect_error")
            yield ErrorChunk(error="Cannot connect to Ollama server")
        except Exception as e:
            self.logger.error("provider.ollama.unexpected_error", error=str(e))
            yield ErrorChunk(error=f"Unexpected error: {e}")
