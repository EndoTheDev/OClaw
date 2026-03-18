import json
import pytest
import httpx
from pytest_httpx import HTTPXMock

from core.providers.ollama import OllamaProvider
from core.providers.base import (
    ResponseChunk,
    ToolCallChunk,
    ErrorChunk,
    ToolDefinition,
)
from core.sessions import Message


@pytest.fixture
def ollama_provider(tmp_path):
    """Create OllamaProvider with test configuration."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "provider": {
                    "active": "ollama",
                    "ollama_host": "http://host.docker.internal:11434",
                    "model": "test-model",
                },
                "skills_dir": str(skills_dir),
            }
        )
    )

    import os

    old_env = os.environ.get("XDG_CONFIG_HOME")
    os.environ["XDG_CONFIG_HOME"] = str(tmp_path)

    provider = OllamaProvider(model="test-model")

    if old_env:
        os.environ["XDG_CONFIG_HOME"] = old_env
    else:
        os.environ.pop("XDG_CONFIG_HOME", None)

    return provider


@pytest.fixture
def sample_messages() -> list[Message]:
    """Sample conversation messages."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    return [
        {"role": "user", "content": "Hello", "timestamp": now},
        {"role": "assistant", "content": "Hi there!", "timestamp": now},
    ]


@pytest.fixture
def sample_tools() -> list[ToolDefinition]:
    """Sample tool definitions."""
    return [
        ToolDefinition(
            name="test_tool",
            description="A test tool",
            parameters={"type": "object", "properties": {"arg": {"type": "string"}}},
        )
    ]


class TestOllamaProvider:
    async def test_chat_posts_to_api_chat_endpoint(
        self, ollama_provider, httpx_mock: HTTPXMock, sample_messages
    ):
        """Verify chat() makes POST request to /api/chat endpoint."""
        httpx_mock.add_response(
            url="http://host.docker.internal:11434/api/chat",
            method="POST",
            content=b'{"done": true}',
        )

        async for chunk in ollama_provider.chat(sample_messages):
            pass

        request = httpx_mock.get_request()
        assert request is not None
        assert request.url.path == "/api/chat"
        assert request.method == "POST"

    async def test_chat_yields_content_chunks(
        self, ollama_provider, httpx_mock: HTTPXMock, sample_messages
    ):
        """Verify chat() yields ResponseChunk for content tokens."""
        response_data = {"response": "Hello", "done": False}
        httpx_mock.add_response(
            url="http://host.docker.internal:11434/api/chat",
            method="POST",
            content=json.dumps(response_data).encode(),
        )

        chunks = []
        async for chunk in ollama_provider.chat(sample_messages):
            chunks.append(chunk)

        response_chunks = [c for c in chunks if isinstance(c, ResponseChunk)]
        assert len(response_chunks) >= 1

    async def test_chat_yields_tool_call_chunks(
        self, ollama_provider, httpx_mock: HTTPXMock, sample_messages, sample_tools
    ):
        """Verify chat() yields ToolCallChunk for tool calls."""
        response_data = {
            "tool_calls": [{"function": {"name": "test_tool", "arguments": "{}"}}],
            "done": False,
        }
        httpx_mock.add_response(
            url="http://host.docker.internal:11434/api/chat",
            method="POST",
            content=json.dumps(response_data).encode(),
        )

        chunks = []
        async for chunk in ollama_provider.chat(sample_messages, tools=sample_tools):
            chunks.append(chunk)

        tool_call_chunks = [c for c in chunks if isinstance(c, ToolCallChunk)]
        assert len(tool_call_chunks) >= 1

    async def test_chat_yields_error_chunk_on_http_error(
        self, ollama_provider, httpx_mock: HTTPXMock, sample_messages
    ):
        """Verify chat() yields ErrorChunk on HTTP status error."""
        httpx_mock.add_response(
            url="http://host.docker.internal:11434/api/chat",
            method="POST",
            status_code=401,
            content=b'{"error": "Unauthorized"}',
        )

        chunks = []
        async for chunk in ollama_provider.chat(sample_messages):
            chunks.append(chunk)

        error_chunks = [c for c in chunks if isinstance(c, ErrorChunk)]
        assert len(error_chunks) == 1
        assert "HTTP error" in str(error_chunks[0])

    async def test_chat_yields_error_chunk_on_connect_error(
        self, ollama_provider, httpx_mock: HTTPXMock, sample_messages
    ):
        """Verify chat() yields ErrorChunk when connection fails."""
        httpx_mock.add_exception(httpx.ConnectError("Connection refused"))

        chunks = []
        async for chunk in ollama_provider.chat(sample_messages):
            chunks.append(chunk)

        error_chunks = [c for c in chunks if isinstance(c, ErrorChunk)]
        assert len(error_chunks) == 1
        assert "Cannot connect to Ollama" in str(error_chunks[0])

    async def test_chat_includes_model_and_messages_in_payload(
        self, ollama_provider, httpx_mock: HTTPXMock, sample_messages
    ):
        """Verify chat() includes model and messages in request payload."""
        httpx_mock.add_response(
            url="http://host.docker.internal:11434/api/chat",
            method="POST",
            content=b'{"done": true}',
        )

        async for chunk in ollama_provider.chat(sample_messages):
            pass

        request = httpx_mock.get_request()
        assert request is not None
        body = json.loads(request.content)
        assert "model" in body
        assert body["model"] == "test-model"
        assert "messages" in body
        assert len(body["messages"]) == 2
