import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from typing import Any

from core.agent.agent import Agent
from core.agent.types import ExecutionContext
from core.providers.base import (
    Provider,
    ResponseChunk,
    ThinkingChunk,
    ToolCallChunk,
    MetricsChunk,
    DoneChunk,
    ErrorChunk,
    ToolDefinition,
)
from core.sessions import SessionsManager, Message
from core.skills import SkillsManager
from core.tools import ToolsManager
from core.context import ContextManager


@pytest.fixture
def mock_provider() -> Provider:
    """Create a mock Provider with configurable chat responses."""
    provider = MagicMock(spec=Provider)

    async def mock_chunk_stream(*args, **kwargs):
        for chunk in []:
            yield chunk

    provider.chat = mock_chunk_stream
    return provider


@pytest.fixture
def mock_tools_manager() -> ToolsManager:
    """Create a mock ToolsManager."""
    tools = MagicMock(spec=ToolsManager)
    tools.get_definitions = MagicMock(return_value=[])
    tools.execute = AsyncMock(return_value="mock_result")
    tools.set_runtime_context = MagicMock()
    return tools


@pytest.fixture
def mock_skills_manager() -> SkillsManager:
    """Create a mock SkillsManager."""
    skills = MagicMock(spec=SkillsManager)
    skills.build_system_prompt = MagicMock(return_value="You are OClaw")
    skills.get_body = MagicMock(return_value="skill body")
    skills.list_metadata = MagicMock(return_value=[])
    skills.has_skill = MagicMock(return_value=False)
    return skills


@pytest.fixture
def mock_sessions_manager(tmp_path) -> SessionsManager:
    """Create a mock SessionsManager."""
    sessions = MagicMock(spec=SessionsManager)
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    mock_session = MagicMock()
    mock_session.metadata.session_id = "test-session-123"
    mock_session.metadata.active_skills = []
    mock_session.messages = []

    sessions.get_session_by_id = MagicMock(return_value=mock_session)
    sessions.get_latest_session_id = MagicMock(return_value="test-session-123")
    sessions.overwrite = MagicMock()
    return sessions


@pytest.fixture
def mock_context() -> ContextManager:
    """Create a mock ContextManager."""
    context = MagicMock(spec=ContextManager)
    context.messages = []
    context.load = MagicMock()
    context.append_user = MagicMock()
    context.append_assistant = MagicMock()
    context.append_tool = MagicMock()
    return context


@pytest.fixture
def execution_context() -> ExecutionContext:
    """Create a default ExecutionContext."""
    return ExecutionContext(
        session_id="test-session-123",
        request_id="test-request-456",
        max_iterations=5,
    )


async def create_mock_chunk_stream(
    chunks: list | None = None,
    include_tool_call: bool = False,
    include_error: bool = False,
) -> AsyncMock:
    """Helper to create an async generator mock for provider responses."""
    if chunks is None:
        chunks = []

    async def mock_gen():
        for chunk in chunks:
            yield chunk

    mock = AsyncMock()
    mock.__aiter__ = mock_gen
    return mock


class TestAgent:
    """Test suite for Agent class stream() method."""

    async def test_stream_yields_agent_start_event_first(
        self,
        mock_provider: Provider,
        mock_tools_manager: ToolsManager,
        mock_skills_manager: SkillsManager,
        mock_sessions_manager: SessionsManager,
        mock_context: ContextManager,
        execution_context: ExecutionContext,
    ) -> None:
        """Verify agent_start event is the first event yielded."""
        agent = Agent(
            provider=mock_provider,
            tools=mock_tools_manager,
            skills=mock_skills_manager,
            sessions=mock_sessions_manager,
            context=mock_context,
        )

        async def mock_chunk_stream(*args, **kwargs):
            for chunk in []:
                yield chunk

        mock_provider.chat = mock_chunk_stream

        events = [
            event
            async for event in agent.stream("Hello", "session-1", execution_context)
        ]

        assert len(events) >= 1
        assert events[0]["event_type"] == "agent_start"
        assert events[0]["payload"]["status"] == "started"
        assert "max_iterations" in events[0]["payload"]

    async def test_stream_yields_turn_start_for_each_iteration(
        self,
        mock_provider: Provider,
        mock_tools_manager: ToolsManager,
        mock_skills_manager: SkillsManager,
        mock_sessions_manager: SessionsManager,
        mock_context: ContextManager,
        execution_context: ExecutionContext,
    ) -> None:
        """Verify turn_start event is yielded for each iteration."""
        agent = Agent(
            provider=mock_provider,
            tools=mock_tools_manager,
            skills=mock_skills_manager,
            sessions=mock_sessions_manager,
            context=mock_context,
        )

        chunks = [ResponseChunk(content="Hello"), DoneChunk()]

        async def mock_chunk_stream(*args, **kwargs):
            for chunk in chunks:
                yield chunk

        mock_provider.chat = mock_chunk_stream

        events = [
            event
            async for event in agent.stream("Hello", "session-1", execution_context)
        ]

        turn_start_events = [e for e in events if e["event_type"] == "turn_start"]
        assert len(turn_start_events) >= 1
        assert "iteration" in turn_start_events[0]["payload"]

    async def test_stream_yields_message_start_before_content(
        self,
        mock_provider: Provider,
        mock_tools_manager: ToolsManager,
        mock_skills_manager: SkillsManager,
        mock_sessions_manager: SessionsManager,
        mock_context: ContextManager,
        execution_context: ExecutionContext,
    ) -> None:
        """Verify message_start event precedes message_update events."""
        agent = Agent(
            provider=mock_provider,
            tools=mock_tools_manager,
            skills=mock_skills_manager,
            sessions=mock_sessions_manager,
            context=mock_context,
        )

        chunks = [ResponseChunk(content="Hello"), DoneChunk()]

        async def mock_chunk_stream(*args, **kwargs):
            for chunk in chunks:
                yield chunk

        mock_provider.chat = mock_chunk_stream

        events = [
            event
            async for event in agent.stream("Hello", "session-1", execution_context)
        ]

        message_start_idx = next(
            i for i, e in enumerate(events) if e["event_type"] == "message_start"
        )
        message_update_idx = next(
            i for i, e in enumerate(events) if e["event_type"] == "message_update"
        )

        assert message_start_idx < message_update_idx
        assert "message_id" in events[message_start_idx]["payload"]
        assert events[message_start_idx]["payload"]["role"] == "assistant"

    async def test_stream_yields_message_update_for_content_tokens(
        self,
        mock_provider: Provider,
        mock_tools_manager: ToolsManager,
        mock_skills_manager: SkillsManager,
        mock_sessions_manager: SessionsManager,
        mock_context: ContextManager,
        execution_context: ExecutionContext,
    ) -> None:
        """Verify message_update events are yielded for content tokens."""
        agent = Agent(
            provider=mock_provider,
            tools=mock_tools_manager,
            skills=mock_skills_manager,
            sessions=mock_sessions_manager,
            context=mock_context,
        )

        chunks = [
            ResponseChunk(content="Hello"),
            ResponseChunk(content=" World"),
            DoneChunk(),
        ]

        async def mock_chunk_stream(*args, **kwargs):
            for chunk in chunks:
                yield chunk

        mock_provider.chat = mock_chunk_stream

        events = [
            event
            async for event in agent.stream("Hello", "session-1", execution_context)
        ]

        content_updates = [
            e
            for e in events
            if e["event_type"] == "message_update"
            and e["payload"].get("channel") == "content"
        ]

        assert len(content_updates) >= 1
        assert "delta" in content_updates[0]["payload"]
        assert content_updates[0]["payload"]["delta"] == "Hello"

    async def test_stream_yields_message_update_for_thinking_tokens(
        self,
        mock_provider: Provider,
        mock_tools_manager: ToolsManager,
        mock_skills_manager: SkillsManager,
        mock_sessions_manager: SessionsManager,
        mock_context: ContextManager,
        execution_context: ExecutionContext,
    ) -> None:
        """Verify message_update events are yielded for thinking tokens."""
        agent = Agent(
            provider=mock_provider,
            tools=mock_tools_manager,
            skills=mock_skills_manager,
            sessions=mock_sessions_manager,
            context=mock_context,
        )

        chunks = [ThinkingChunk(content="Thinking..."), DoneChunk()]

        async def mock_chunk_stream(*args, **kwargs):
            for chunk in chunks:
                yield chunk

        mock_provider.chat = mock_chunk_stream

        events = [
            event
            async for event in agent.stream("Hello", "session-1", execution_context)
        ]

        thinking_updates = [
            e
            for e in events
            if e["event_type"] == "message_update"
            and e["payload"].get("channel") == "thinking"
        ]

        assert len(thinking_updates) >= 1
        assert "delta" in thinking_updates[0]["payload"]
        assert thinking_updates[0]["payload"]["delta"] == "Thinking..."

    async def test_stream_yields_message_update_for_tool_calls(
        self,
        mock_provider: Provider,
        mock_tools_manager: ToolsManager,
        mock_skills_manager: SkillsManager,
        mock_sessions_manager: SessionsManager,
        mock_context: ContextManager,
        execution_context: ExecutionContext,
    ) -> None:
        """Verify message_update events are yielded for tool calls."""
        agent = Agent(
            provider=mock_provider,
            tools=mock_tools_manager,
            skills=mock_skills_manager,
            sessions=mock_sessions_manager,
            context=mock_context,
        )

        chunks = [
            ToolCallChunk(name="test_tool", arguments={"arg": "value"}, id="call-1"),
            DoneChunk(),
        ]

        async def mock_chunk_stream(*args, **kwargs):
            for chunk in chunks:
                yield chunk

        mock_provider.chat = mock_chunk_stream

        events = [
            event
            async for event in agent.stream("Hello", "session-1", execution_context)
        ]

        tool_call_updates = [
            e
            for e in events
            if e["event_type"] == "message_update" and "tool_call" in e["payload"]
        ]

        assert len(tool_call_updates) >= 1
        assert tool_call_updates[0]["payload"]["tool_call"]["name"] == "test_tool"
        assert tool_call_updates[0]["payload"]["tool_call"]["id"] == "call-1"

    async def test_stream_yields_message_end_with_complete_status(
        self,
        mock_provider: Provider,
        mock_tools_manager: ToolsManager,
        mock_skills_manager: SkillsManager,
        mock_sessions_manager: SessionsManager,
        mock_context: ContextManager,
        execution_context: ExecutionContext,
    ) -> None:
        """Verify message_end event has completed status on success."""
        agent = Agent(
            provider=mock_provider,
            tools=mock_tools_manager,
            skills=mock_skills_manager,
            sessions=mock_sessions_manager,
            context=mock_context,
        )

        chunks = [ResponseChunk(content="Hello"), DoneChunk()]

        async def mock_chunk_stream(*args, **kwargs):
            for chunk in chunks:
                yield chunk

        mock_provider.chat = mock_chunk_stream

        events = [
            event
            async for event in agent.stream("Hello", "session-1", execution_context)
        ]

        message_end_events = [e for e in events if e["event_type"] == "message_end"]
        assert len(message_end_events) >= 1
        assert message_end_events[0]["payload"]["status"] == "completed"
        assert "content" in message_end_events[0]["payload"]
        assert "tool_call_count" in message_end_events[0]["payload"]

    async def test_stream_yields_tool_execution_start_when_tool_called(
        self,
        mock_provider: Provider,
        mock_tools_manager: ToolsManager,
        mock_skills_manager: SkillsManager,
        mock_sessions_manager: SessionsManager,
        mock_context: ContextManager,
        execution_context: ExecutionContext,
    ) -> None:
        """Verify tool_execution_start event is yielded when tool is called."""
        agent = Agent(
            provider=mock_provider,
            tools=mock_tools_manager,
            skills=mock_skills_manager,
            sessions=mock_sessions_manager,
            context=mock_context,
        )

        chunks = [
            ToolCallChunk(name="test_tool", arguments={"arg": "value"}, id="call-1"),
            DoneChunk(),
        ]

        async def mock_chunk_stream(*args, **kwargs):
            for chunk in chunks:
                yield chunk

        mock_provider.chat = mock_chunk_stream

        events = [
            event
            async for event in agent.stream("Hello", "session-1", execution_context)
        ]

        tool_start_events = [
            e for e in events if e["event_type"] == "tool_execution_start"
        ]
        assert len(tool_start_events) >= 1
        assert tool_start_events[0]["payload"]["tool_name"] == "test_tool"
        assert "tool_call_id" in tool_start_events[0]["payload"]

    async def test_stream_yields_tool_execution_update_during_execution(
        self,
        mock_provider: Provider,
        mock_tools_manager: ToolsManager,
        mock_skills_manager: SkillsManager,
        mock_sessions_manager: SessionsManager,
        mock_context: ContextManager,
        execution_context: ExecutionContext,
    ) -> None:
        """Verify tool_execution_update events are yielded during tool execution."""
        agent = Agent(
            provider=mock_provider,
            tools=mock_tools_manager,
            skills=mock_skills_manager,
            sessions=mock_sessions_manager,
            context=mock_context,
        )

        chunks = [
            ToolCallChunk(name="test_tool", arguments={"arg": "value"}, id="call-1"),
            DoneChunk(),
        ]

        async def mock_chunk_stream(*args, **kwargs):
            for chunk in chunks:
                yield chunk

        mock_provider.chat = mock_chunk_stream

        events = [
            event
            async for event in agent.stream("Hello", "session-1", execution_context)
        ]

        tool_update_events = [
            e for e in events if e["event_type"] == "tool_execution_update"
        ]
        assert len(tool_update_events) >= 1
        assert "phase" in tool_update_events[0]["payload"]
        assert tool_update_events[0]["payload"]["tool_name"] == "test_tool"

    async def test_stream_yields_tool_execution_end_with_result(
        self,
        mock_provider: Provider,
        mock_tools_manager: ToolsManager,
        mock_skills_manager: SkillsManager,
        mock_sessions_manager: SessionsManager,
        mock_context: ContextManager,
        execution_context: ExecutionContext,
    ) -> None:
        """Verify tool_execution_end event includes result on success."""
        agent = Agent(
            provider=mock_provider,
            tools=mock_tools_manager,
            skills=mock_skills_manager,
            sessions=mock_sessions_manager,
            context=mock_context,
        )

        chunks = [
            ToolCallChunk(name="test_tool", arguments={"arg": "value"}, id="call-1"),
            DoneChunk(),
        ]

        async def mock_chunk_stream(*args, **kwargs):
            for chunk in chunks:
                yield chunk

        mock_provider.chat = mock_chunk_stream
        mock_tools_manager.execute = AsyncMock(return_value="tool_result")

        events = [
            event
            async for event in agent.stream("Hello", "session-1", execution_context)
        ]

        tool_end_events = [e for e in events if e["event_type"] == "tool_execution_end"]
        assert len(tool_end_events) >= 1
        assert tool_end_events[0]["payload"]["status"] == "succeeded"
        assert tool_end_events[0]["payload"]["result"] == "tool_result"

    async def test_stream_yields_turn_end_after_tools_complete(
        self,
        mock_provider: Provider,
        mock_tools_manager: ToolsManager,
        mock_skills_manager: SkillsManager,
        mock_sessions_manager: SessionsManager,
        mock_context: ContextManager,
        execution_context: ExecutionContext,
    ) -> None:
        """Verify turn_end event is yielded after tool execution completes."""
        agent = Agent(
            provider=mock_provider,
            tools=mock_tools_manager,
            skills=mock_skills_manager,
            sessions=mock_sessions_manager,
            context=mock_context,
        )

        chunks = [
            ToolCallChunk(name="test_tool", arguments={"arg": "value"}, id="call-1"),
            DoneChunk(),
        ]

        async def mock_chunk_stream(*args, **kwargs):
            for chunk in chunks:
                yield chunk

        mock_provider.chat = mock_chunk_stream
        mock_tools_manager.execute = AsyncMock(return_value="tool_result")

        events = [
            event
            async for event in agent.stream("Hello", "session-1", execution_context)
        ]

        turn_end_events = [e for e in events if e["event_type"] == "turn_end"]
        assert len(turn_end_events) >= 1
        assert "iteration" in turn_end_events[0]["payload"]
        assert turn_end_events[0]["payload"]["status"] == "succeeded"

    async def test_stream_stops_when_no_tool_calls_returned(
        self,
        mock_provider: Provider,
        mock_tools_manager: ToolsManager,
        mock_skills_manager: SkillsManager,
        mock_sessions_manager: SessionsManager,
        mock_context: ContextManager,
        execution_context: ExecutionContext,
    ) -> None:
        """Verify stream stops after first turn when no tool calls are returned."""
        agent = Agent(
            provider=mock_provider,
            tools=mock_tools_manager,
            skills=mock_skills_manager,
            sessions=mock_sessions_manager,
            context=mock_context,
        )

        chunks = [ResponseChunk(content="Hello"), DoneChunk()]

        async def mock_chunk_stream(*args, **kwargs):
            for chunk in chunks:
                yield chunk

        mock_provider.chat = mock_chunk_stream

        events = [
            event
            async for event in agent.stream("Hello", "session-1", execution_context)
        ]

        turn_start_events = [e for e in events if e["event_type"] == "turn_start"]
        assert len(turn_start_events) == 1

        agent_end_events = [e for e in events if e["event_type"] == "agent_end"]
        assert len(agent_end_events) == 1

    async def test_stream_respects_max_iterations_limit(
        self,
        mock_provider: Provider,
        mock_tools_manager: ToolsManager,
        mock_skills_manager: SkillsManager,
        mock_sessions_manager: SessionsManager,
        mock_context: ContextManager,
    ) -> None:
        """Verify stream respects max_iterations limit from context."""
        agent = Agent(
            provider=mock_provider,
            tools=mock_tools_manager,
            skills=mock_skills_manager,
            sessions=mock_sessions_manager,
            context=mock_context,
        )

        chunks = [
            ToolCallChunk(name="test_tool", arguments={}, id="call-1"),
            DoneChunk(),
        ]

        async def mock_chunk_stream(*args, **kwargs):
            for chunk in chunks:
                yield chunk

        mock_provider.chat = mock_chunk_stream
        mock_tools_manager.execute = AsyncMock(return_value="result")

        context = ExecutionContext(
            session_id="session-1",
            request_id="req-1",
            max_iterations=2,
        )

        events = [event async for event in agent.stream("Hello", "session-1", context)]

        turn_start_events = [e for e in events if e["event_type"] == "turn_start"]
        assert len(turn_start_events) <= 2

        iterations = [e["payload"]["iteration"] for e in turn_start_events]
        assert iterations == [1, 2]

    async def test_stream_yields_error_event_on_provider_error(
        self,
        mock_provider: Provider,
        mock_tools_manager: ToolsManager,
        mock_skills_manager: SkillsManager,
        mock_sessions_manager: SessionsManager,
        mock_context: ContextManager,
        execution_context: ExecutionContext,
    ) -> None:
        """Verify error event is yielded when provider returns error."""
        agent = Agent(
            provider=mock_provider,
            tools=mock_tools_manager,
            skills=mock_skills_manager,
            sessions=mock_sessions_manager,
            context=mock_context,
        )

        chunks = [ErrorChunk(error="Provider connection failed")]

        async def mock_chunk_stream(*args, **kwargs):
            for chunk in chunks:
                yield chunk

        mock_provider.chat = mock_chunk_stream

        events = [
            event
            async for event in agent.stream("Hello", "session-1", execution_context)
        ]

        error_events = [e for e in events if e["event_type"] == "error"]
        assert len(error_events) >= 1
        assert "Provider connection failed" in error_events[0]["payload"]["message"]
        assert error_events[0]["payload"]["fatal"] is True

    async def test_stream_yields_error_event_on_tool_execution_failed(
        self,
        mock_provider: Provider,
        mock_tools_manager: ToolsManager,
        mock_skills_manager: SkillsManager,
        mock_sessions_manager: SessionsManager,
        mock_context: ContextManager,
        execution_context: ExecutionContext,
    ) -> None:
        """Verify error event is yielded when tool execution fails."""
        agent = Agent(
            provider=mock_provider,
            tools=mock_tools_manager,
            skills=mock_skills_manager,
            sessions=mock_sessions_manager,
            context=mock_context,
        )

        chunks = [
            ToolCallChunk(name="test_tool", arguments={}, id="call-1"),
            DoneChunk(),
        ]

        async def mock_chunk_stream(*args, **kwargs):
            for chunk in chunks:
                yield chunk

        mock_provider.chat = mock_chunk_stream
        mock_tools_manager.execute = AsyncMock(
            side_effect=Exception("Tool execution failed")
        )

        events = [
            event
            async for event in agent.stream("Hello", "session-1", execution_context)
        ]

        error_events = [e for e in events if e["event_type"] == "error"]
        assert len(error_events) >= 1
        assert "Tool execution failed" in error_events[0]["payload"]["message"]
        assert error_events[0]["payload"]["fatal"] is True

    async def test_stream_yields_error_event_on_tool_execution_denied(
        self,
        mock_provider: Provider,
        mock_tools_manager: ToolsManager,
        mock_skills_manager: SkillsManager,
        mock_sessions_manager: SessionsManager,
        mock_context: ContextManager,
        execution_context: ExecutionContext,
    ) -> None:
        """Verify error event is yielded when tool execution is denied."""
        import asyncio

        agent = Agent(
            provider=mock_provider,
            tools=mock_tools_manager,
            skills=mock_skills_manager,
            sessions=mock_sessions_manager,
            context=mock_context,
        )

        chunks = [
            ToolCallChunk(name="test_tool", arguments={}, id="call-1"),
            DoneChunk(),
        ]

        async def mock_chunk_stream(*args, **kwargs):
            for chunk in chunks:
                yield chunk

        mock_provider.chat = mock_chunk_stream

        permission_queue = asyncio.Queue()
        permission_queue.put_nowait(False)

        events = [
            event
            async for event in agent.stream(
                "Hello", "session-1", execution_context, input_queue=permission_queue
            )
        ]

        denied_events = [
            e
            for e in events
            if e["event_type"] == "tool_execution_end"
            and e["payload"].get("status") == "denied"
        ]
        assert len(denied_events) >= 1

    async def test_stream_yields_agent_end_event_last(
        self,
        mock_provider: Provider,
        mock_tools_manager: ToolsManager,
        mock_skills_manager: SkillsManager,
        mock_sessions_manager: SessionsManager,
        mock_context: ContextManager,
        execution_context: ExecutionContext,
    ) -> None:
        """Verify agent_end event is yielded before stream_end."""
        agent = Agent(
            provider=mock_provider,
            tools=mock_tools_manager,
            skills=mock_skills_manager,
            sessions=mock_sessions_manager,
            context=mock_context,
        )

        chunks = [ResponseChunk(content="Hello"), DoneChunk()]

        async def mock_chunk_stream(*args, **kwargs):
            for chunk in chunks:
                yield chunk

        mock_provider.chat = mock_chunk_stream

        events = [
            event
            async for event in agent.stream("Hello", "session-1", execution_context)
        ]

        agent_end_idx = next(
            i for i, e in enumerate(events) if e["event_type"] == "agent_end"
        )
        stream_end_idx = next(
            i for i, e in enumerate(events) if e["event_type"] == "stream_end"
        )

        assert agent_end_idx == len(events) - 2
        assert stream_end_idx == len(events) - 1
        assert "status" in events[agent_end_idx]["payload"]

    async def test_stream_yields_stream_end_event_after_agent_end(
        self,
        mock_provider: Provider,
        mock_tools_manager: ToolsManager,
        mock_skills_manager: SkillsManager,
        mock_sessions_manager: SessionsManager,
        mock_context: ContextManager,
        execution_context: ExecutionContext,
    ) -> None:
        """Verify stream_end event is the final event."""
        agent = Agent(
            provider=mock_provider,
            tools=mock_tools_manager,
            skills=mock_skills_manager,
            sessions=mock_sessions_manager,
            context=mock_context,
        )

        chunks = [ResponseChunk(content="Hello"), DoneChunk()]

        async def mock_chunk_stream(*args, **kwargs):
            for chunk in chunks:
                yield chunk

        mock_provider.chat = mock_chunk_stream

        events = [
            event
            async for event in agent.stream("Hello", "session-1", execution_context)
        ]

        assert events[-1]["event_type"] == "stream_end"
        assert "status" in events[-1]["payload"]
        assert events[-1]["payload"]["status"] == "succeeded"

    async def test_stream_persists_session_after_completion(
        self,
        mock_provider: Provider,
        mock_tools_manager: ToolsManager,
        mock_skills_manager: SkillsManager,
        mock_sessions_manager: SessionsManager,
        mock_context: ContextManager,
        execution_context: ExecutionContext,
    ) -> None:
        """Verify session is persisted after stream completion."""
        agent = Agent(
            provider=mock_provider,
            tools=mock_tools_manager,
            skills=mock_skills_manager,
            sessions=mock_sessions_manager,
            context=mock_context,
        )

        chunks = [ResponseChunk(content="Hello"), DoneChunk()]
        mock_provider.chat = AsyncMock(return_value=chunks)

        events = [
            event
            async for event in agent.stream("Hello", "session-1", execution_context)
        ]

        overwrite_mock: MagicMock = mock_sessions_manager.overwrite  # type: ignore
        get_session_mock: MagicMock = mock_sessions_manager.get_session_by_id  # type: ignore
        overwrite_mock.assert_called()
        get_session_mock.assert_called()

    async def test_stream_includes_request_id_in_all_events(
        self,
        mock_provider: Provider,
        mock_tools_manager: ToolsManager,
        mock_skills_manager: SkillsManager,
        mock_sessions_manager: SessionsManager,
        mock_context: ContextManager,
        execution_context: ExecutionContext,
    ) -> None:
        """Verify request_id is included in all stream events."""
        agent = Agent(
            provider=mock_provider,
            tools=mock_tools_manager,
            skills=mock_skills_manager,
            sessions=mock_sessions_manager,
            context=mock_context,
        )

        chunks = [
            ResponseChunk(content="Hello"),
            ThinkingChunk(content="thinking"),
            DoneChunk(),
        ]
        mock_provider.chat = AsyncMock(return_value=chunks)

        events = [
            event
            async for event in agent.stream("Hello", "session-1", execution_context)
        ]

        assert len(events) >= 3
        for event in events:
            assert "request_id" in event
            assert event["request_id"] == "test-request-456"
