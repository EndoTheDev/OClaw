from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient

from core.sessions import SessionsManager
from core.config import Config, ProviderConfig, AgentConfig, ServerConfig, WorkerConfig
from core.skills import SkillsManager
from core.tools import ToolsManager
from core.providers.base import Provider
from server.gateway import AgentGateway


pytestmark = pytest.mark.asyncio


@pytest.fixture
def tmp_sessions_dir(tmp_path: Path) -> Path:
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    return sessions_dir


@pytest.fixture
def sessions_manager(tmp_sessions_dir: Path) -> SessionsManager:
    return SessionsManager(sessions_dir=str(tmp_sessions_dir))


@pytest.fixture
def config_instance() -> Config:
    return Config(
        provider=ProviderConfig(
            active="ollama",
            ollama_host="http://localhost:11434",
            openai_host="https://api.openai.com/v1",
            openai_api_key=None,
            anthropic_host="https://api.anthropic.com/v1",
            anthropic_api_key=None,
            model="test-model",
        ),
        agent=AgentConfig(max_iterations=5),
        server=ServerConfig(host="0.0.0.0", port=8000),
        worker=WorkerConfig(num_processes=4, timeout=300),
    )


@pytest.fixture
def skills_manager(tmp_path: Path) -> SkillsManager:
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    return SkillsManager(autoload=False, skills_dir=skills_dir)


@pytest.fixture
def tools_manager(tmp_path: Path) -> ToolsManager:
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    return ToolsManager(autoload=False, tools_dir=tools_dir)


@pytest.fixture
def mock_provider() -> AsyncMock:
    mock = AsyncMock(spec=Provider)
    mock.chat.return_value.__aiter__.return_value = iter([])
    return mock


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[TestClient, None]:
    gateway = AgentGateway(num_workers=1, timeout=60)
    with TestClient(gateway.app) as test_client:
        yield test_client


@pytest.fixture
def mock_session_record(tmp_sessions_dir: Path) -> dict[str, Any]:
    session_id = str(uuid.uuid4())
    file_path = tmp_sessions_dir / f"{session_id}.jsonl"
    return {
        "session_id": session_id,
        "file_path": file_path,
        "messages": [],
        "active_skills": [],
    }


@pytest.fixture
def sample_message() -> dict[str, Any]:
    return {
        "role": "user",
        "content": "Test message",
        "timestamp": "2024-01-01T00:00:00Z",
    }


@pytest.fixture
def sample_tool_definition() -> dict[str, Any]:
    return {
        "name": "test_tool",
        "description": "A test tool",
        "parameters": {
            "type": "object",
            "properties": {"arg": {"type": "string"}},
            "required": ["arg"],
        },
    }


@pytest.fixture
def sample_skill_metadata(tmp_path: Path) -> dict[str, Any]:
    skill_dir = tmp_path / "skills" / "test_skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        "---\nname: Test Skill\ndescription: A test skill\n---\nTest skill body\n"
    )
    return {
        "skill_id": "test_skill",
        "name": "Test Skill",
        "description": "A test skill",
        "file_path": skill_file,
    }


@pytest_asyncio.fixture
async def httpx_client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient() as client:
        yield client
