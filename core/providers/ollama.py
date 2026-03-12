import json
import httpx
from typing import AsyncGenerator

from .base import (
    DoneChunk,
    ErrorChunk,
    MetricsChunk,
    ResponseChunk,
    StreamingChunk,
    ThinkingChunk,
    ToolCallChunk,
)


class OllamaProvider:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
    ):
        from ..config import Config

        config = Config.load()

        self.base_url = base_url or config.ollama_host
        self.model = model or config.model
        self.client = httpx.AsyncClient(timeout=300.0)

    async def chat(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> AsyncGenerator[StreamingChunk, None]:
        url = f"{self.base_url}/api/chat"

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }

        if tools:
            payload["tools"] = tools

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
                        yield MetricsChunk(data=metrics_data)
                        yield DoneChunk(done_reason=done_reason)
                        break

        except httpx.HTTPStatusError as e:
            yield ErrorChunk(error=f"HTTP error: {e.response.status_code}")
        except httpx.ConnectError:
            yield ErrorChunk(error="Cannot connect to Ollama server")
        except Exception as e:
            yield ErrorChunk(error=f"Unexpected error: {e}")
