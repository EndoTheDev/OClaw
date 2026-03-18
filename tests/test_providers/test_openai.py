import json
import httpx
import pytest
import pytest_httpx

from core.providers.openai import OpenAIProvider
from core.providers.base import (
    ResponseChunk,
    ToolCallChunk,
    ErrorChunk,
    ToolDefinition,
)
from core.sessions import Message


@pytest.fixture
def openai_provider(config_instance):
    return OpenAIProvider(model="test-model")


@pytest.fixture
def sample_messages() -> list[Message]:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "role": "system",
            "content": "You are helpful",
            "timestamp": now,
        },
        {"role": "user", "content": "Hello", "timestamp": now},
    ]


@pytest.fixture
def sample_tools() -> list[ToolDefinition]:
    return [
        ToolDefinition(
            name="test_tool",
            description="A test tool",
            parameters={
                "type": "object",
                "properties": {"arg": {"type": "string"}},
                "required": ["arg"],
            },
        )
    ]


def _create_sse_chunk(data: dict | str) -> str:
    if isinstance(data, str):
        return f"data: {data}\n\n"
    return f"data: {json.dumps(data)}\n\n"


class TestOpenAIProvider:
    async def test_chat_posts_to_chat_completions_endpoint(
        self, openai_provider: OpenAIProvider, httpx_mock: pytest_httpx.HTTPXMock
    ):
        """Verify chat() makes POST request to /v1/chat/completions endpoint."""
        httpx_mock.add_response(
            url="https://api.openai.com/v1/chat/completions",
            text=_create_sse_chunk("[DONE]"),
        )

        messages: list[Message] = [
            {"role": "user", "content": "test", "timestamp": "2024-01-01T00:00:00Z"}
        ]
        async for _chunk in openai_provider.chat(messages):
            pass

        request = httpx_mock.get_request()
        assert request is not None
        assert request.url.path == "/v1/chat/completions"
        assert request.method == "POST"

    async def test_chat_sends_bearer_auth_header(
        self, openai_provider: OpenAIProvider, httpx_mock: pytest_httpx.HTTPXMock
    ):
        """Verify chat() sends Authorization header with Bearer token."""
        httpx_mock.add_response(
            url="https://api.openai.com/v1/chat/completions",
            text=_create_sse_chunk("[DONE]"),
        )

        messages: list[Message] = [
            {"role": "user", "content": "test", "timestamp": "2024-01-01T00:00:00Z"}
        ]
        async for _chunk in openai_provider.chat(messages):
            pass

        request = httpx_mock.get_request()
        assert request is not None
        auth_header = request.headers.get("Authorization")
        assert auth_header is not None
        assert auth_header.startswith("Bearer ")

    async def test_chat_yields_content_chunks(
        self, openai_provider: OpenAIProvider, httpx_mock: pytest_httpx.HTTPXMock
    ):
        """Verify chat() yields ResponseChunk for content tokens."""
        chunk_data = {"choices": [{"delta": {"content": "Hello"}}]}
        httpx_mock.add_response(
            url="https://api.openai.com/v1/chat/completions",
            text=_create_sse_chunk(chunk_data),
        )

        messages: list[Message] = [
            {"role": "user", "content": "test", "timestamp": "2024-01-01T00:00:00Z"}
        ]
        chunks = []
        async for chunk in openai_provider.chat(messages):
            chunks.append(chunk)

        response_chunks = [c for c in chunks if isinstance(c, ResponseChunk)]
        assert len(response_chunks) >= 1

    async def test_chat_yields_tool_call_chunks(
        self,
        openai_provider: OpenAIProvider,
        httpx_mock: pytest_httpx.HTTPXMock,
        sample_tools: list[ToolDefinition],
    ):
        """Verify chat() yields ToolCallChunk for tool calls."""
        chunk_data = {
            "choices": [
                {"delta": {"tool_calls": [{"function": {"name": "test_tool"}}]}}
            ]
        }
        httpx_mock.add_response(
            url="https://api.openai.com/v1/chat/completions",
            text=_create_sse_chunk(chunk_data),
        )

        messages: list[Message] = [
            {"role": "user", "content": "test", "timestamp": "2024-01-01T00:00:00Z"}
        ]
        chunks = []
        async for chunk in openai_provider.chat(messages, tools=sample_tools):
            chunks.append(chunk)

        tool_call_chunks = [c for c in chunks if isinstance(c, ToolCallChunk)]
        assert len(tool_call_chunks) >= 1

    async def test_chat_yields_error_chunk_on_http_error(
        self, openai_provider: OpenAIProvider, httpx_mock: pytest_httpx.HTTPXMock
    ):
        """Verify chat() yields ErrorChunk on HTTP status error."""
        httpx_mock.add_response(
            url="https://api.openai.com/v1/chat/completions",
            status_code=401,
            content=b'{"error": "Unauthorized"}',
        )

        messages: list[Message] = [
            {"role": "user", "content": "test", "timestamp": "2024-01-01T00:00:00Z"}
        ]
        chunks = []
        async for chunk in openai_provider.chat(messages):
            chunks.append(chunk)

        error_chunks = [c for c in chunks if isinstance(c, ErrorChunk)]
        assert len(error_chunks) == 1
        assert "HTTP error" in str(error_chunks[0])

    async def test_chat_includes_model_and_messages_in_payload(
        self, openai_provider: OpenAIProvider, httpx_mock: pytest_httpx.HTTPXMock
    ):
        """Verify chat() includes model and messages in request payload."""
        httpx_mock.add_response(
            url="https://api.openai.com/v1/chat/completions",
            text=_create_sse_chunk("[DONE]"),
        )

        messages: list[Message] = [
            {"role": "user", "content": "test", "timestamp": "2024-01-01T00:00:00Z"}
        ]
        async for _chunk in openai_provider.chat(messages):
            pass

        request = httpx_mock.get_request()
        assert request is not None
        body = json.loads(request.content)
        assert "model" in body
        assert body["model"] == "test-model"
        assert "messages" in body
