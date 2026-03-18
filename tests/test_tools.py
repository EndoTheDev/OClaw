import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from core.tools import ToolsManager, Tool
from core.sessions import SessionRecord, SessionsManager
from core.skills import SkillsManager


@pytest.fixture
def tools_manager(tmp_path: Path) -> ToolsManager:
    """Create a ToolsManager with a temporary tools directory."""
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    return ToolsManager(autoload=False, tools_dir=tools_dir)


@pytest.fixture
def runtime_context(tools_manager: ToolsManager, tmp_path: Path) -> dict:
    """Create runtime context for testing context binding."""
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    sessions_manager = SessionsManager(sessions_dir=str(sessions_dir))
    session = sessions_manager.create_new_session()
    skills_manager = SkillsManager(autoload=False)
    return {
        "session": session,
        "sessions_manager": sessions_manager,
        "skills_manager": skills_manager,
    }


class TestToolsManager:
    def test_register_adds_tool_to_internal_dict(
        self, tools_manager: ToolsManager
    ) -> None:
        """Test that register() adds a tool to the internal _tools dict."""

        class TestTool(Tool):
            @property
            def name(self) -> str:
                return "test_tool"

            @property
            def description(self) -> str:
                return "Test tool description"

            @property
            def parameters(self) -> dict:
                return {"type": "object", "properties": {}}

            async def execute(self, **kwargs) -> str:
                return "test result"

        tool = TestTool()
        tools_manager.register(tool)

        assert "test_tool" in tools_manager._tools
        assert tools_manager._tools["test_tool"] is tool

    def test_register_raises_on_duplicate_tool_name(
        self, tools_manager: ToolsManager
    ) -> None:
        """Test that register() raises ValueError on duplicate tool name."""

        class TestTool(Tool):
            @property
            def name(self) -> str:
                return "test_tool"

            @property
            def description(self) -> str:
                return "Test tool description"

            @property
            def parameters(self) -> dict:
                return {"type": "object", "properties": {}}

            async def execute(self, **kwargs) -> str:
                return "test result"

        tool1 = TestTool()
        tool2 = TestTool()

        tools_manager.register(tool1)

        with pytest.raises(ValueError, match="Duplicate tool name 'test_tool'"):
            tools_manager.register(tool2)

    def test_autoload_discovers_all_py_files_in_tools_dir(self, tmp_path: Path) -> None:
        """Test that autoload() discovers all .py files in the tools directory."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        manager = ToolsManager(autoload=False)
        tool_file = tools_dir / "my_tool.py"
        tool_file.write_text(
            """
from core.tools import Tool

class MyTool(Tool):
    @property
    def name(self) -> str:
        return "my_tool"

    @property
    def description(self) -> str:
        return "My tool"

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs) -> str:
        return "result"
"""
        )

        manager.autoload(tools_dir=tools_dir)

        assert "my_tool" in manager._tools

    def test_autoload_skips_files_starting_with_underscore(
        self, tmp_path: Path
    ) -> None:
        """Test that autoload() skips files starting with underscore."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        manager = ToolsManager(autoload=False)

        base_tool_file = tools_dir / "base_tool.py"
        base_tool_file.write_text(
            """
from core.tools import Tool

class BaseTool(Tool):
    @property
    def name(self) -> str:
        return "base_tool"

    @property
    def description(self) -> str:
        return "Base tool"

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs) -> str:
        return "result"
"""
        )

        helper_file = tools_dir / "_helper.py"
        helper_file.write_text(
            """
from core.tools import Tool

class HelperTool(Tool):
    @property
    def name(self) -> str:
        return "helper_tool"

    @property
    def description(self) -> str:
        return "Helper tool"

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs) -> str:
        return "result"
"""
        )

        manager.autoload(tools_dir=tools_dir)

        assert "base_tool" in manager._tools
        assert "helper_tool" not in manager._tools

    def test_autoload_instantiates_all_tool_subclasses(self, tmp_path: Path) -> None:
        """Test that autoload() instantiates all Tool subclasses found in modules."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        manager = ToolsManager(autoload=False)

        tool_file = tools_dir / "multi_tool.py"
        tool_file.write_text(
            """
from core.tools import Tool

class FirstTool(Tool):
    @property
    def name(self) -> str:
        return "first_tool"

    @property
    def description(self) -> str:
        return "First tool"

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs) -> str:
        return "first result"


class SecondTool(Tool):
    @property
    def name(self) -> str:
        return "second_tool"

    @property
    def description(self) -> str:
        return "Second tool"

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs) -> str:
        return "second result"
"""
        )

        manager.autoload(tools_dir=tools_dir)

        assert "first_tool" in manager._tools
        assert "second_tool" in manager._tools
        assert manager._tools["first_tool"].name == "first_tool"
        assert manager._tools["second_tool"].name == "second_tool"

    def test_autoload_raises_on_invalid_module_load(self, tmp_path: Path) -> None:
        """Test that autoload() raises RuntimeError when module cannot be loaded."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        manager = ToolsManager(autoload=False)

        invalid_file = tools_dir / "invalid.py"
        invalid_file.write_text(
            """
# This is syntactically invalid Python
def broken(
    # Missing closing parenthesis and body
"""
        )

        with pytest.raises(RuntimeError, match="Cannot load tool module"):
            manager.autoload(tools_dir=tools_dir)

    def test_get_returns_tool_by_name(self, tools_manager: ToolsManager) -> None:
        """Test that get() returns the correct tool by name."""

        class TestTool(Tool):
            @property
            def name(self) -> str:
                return "test_tool"

            @property
            def description(self) -> str:
                return "Test tool description"

            @property
            def parameters(self) -> dict:
                return {"type": "object", "properties": {}}

            async def execute(self, **kwargs) -> str:
                return "test result"

        tool = TestTool()
        tools_manager.register(tool)

        result = tools_manager.get("test_tool")

        assert result is tool
        assert tool.name == "test_tool"

    def test_get_returns_none_for_unknown_tool(
        self, tools_manager: ToolsManager
    ) -> None:
        """Test that get() returns None for an unknown tool name."""
        result = tools_manager.get("nonexistent_tool")

        assert result is None

    def test_get_definitions_returns_all_tool_definitions(
        self, tools_manager: ToolsManager
    ) -> None:
        """Test that get_definitions() returns all tool definitions."""

        class ToolOne(Tool):
            @property
            def name(self) -> str:
                return "tool_one"

            @property
            def description(self) -> str:
                return "Tool one description"

            @property
            def parameters(self) -> dict:
                return {"type": "object", "properties": {"param1": {"type": "string"}}}

            async def execute(self, **kwargs) -> str:
                return "result one"

        class ToolTwo(Tool):
            @property
            def name(self) -> str:
                return "tool_two"

            @property
            def description(self) -> str:
                return "Tool two description"

            @property
            def parameters(self) -> dict:
                return {"type": "object", "properties": {"param2": {"type": "integer"}}}

            async def execute(self, **kwargs) -> str:
                return "result two"

        tools_manager.register(ToolOne())
        tools_manager.register(ToolTwo())

        definitions = tools_manager.get_definitions()

        assert len(definitions) == 2
        definitions_by_name = {d.name: d for d in definitions}

        assert definitions_by_name["tool_one"].name == "tool_one"
        assert definitions_by_name["tool_one"].description == "Tool one description"
        assert definitions_by_name["tool_one"].parameters == {
            "type": "object",
            "properties": {"param1": {"type": "string"}},
        }

        assert definitions_by_name["tool_two"].name == "tool_two"
        assert definitions_by_name["tool_two"].description == "Tool two description"
        assert definitions_by_name["tool_two"].parameters == {
            "type": "object",
            "properties": {"param2": {"type": "integer"}},
        }

    @pytest.mark.asyncio
    async def test_execute_calls_tool_with_correct_arguments(
        self, tools_manager: ToolsManager
    ) -> None:
        """Test that execute() calls the tool with correct arguments."""

        class TestTool(Tool):
            @property
            def name(self) -> str:
                return "test_tool"

            @property
            def description(self) -> str:
                return "Test tool description"

            @property
            def parameters(self) -> dict:
                return {"type": "object", "properties": {"arg1": {"type": "string"}}}

            async def execute(self, **kwargs) -> str:
                return f"called with arg1={kwargs.get('arg1')}"

        tool = TestTool()
        tools_manager.register(tool)

        result = await tools_manager.execute("test_tool", {"arg1": "test_value"})

        assert result == "called with arg1=test_value"

    @pytest.mark.asyncio
    async def test_execute_returns_tool_result_string(
        self, tools_manager: ToolsManager
    ) -> None:
        """Test that execute() returns the tool's result as a string."""

        class TestTool(Tool):
            @property
            def name(self) -> str:
                return "test_tool"

            @property
            def description(self) -> str:
                return "Test tool description"

            @property
            def parameters(self) -> dict:
                return {"type": "object", "properties": {}}

            async def execute(self, **kwargs) -> str:
                return "expected result string"

        tool = TestTool()
        tools_manager.register(tool)

        result = await tools_manager.execute("test_tool", {})

        assert result == "expected result string"
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_execute_returns_error_string_for_unknown_tool(
        self, tools_manager: ToolsManager
    ) -> None:
        """Test that execute() returns error string for unknown tool instead of raising."""
        result = await tools_manager.execute("unknown_tool", {"some_arg": "value"})

        assert result == "Error: Unknown tool 'unknown_tool'"
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_execute_binds_runtime_context_when_available(
        self, tmp_path: Path, runtime_context: dict
    ) -> None:
        """Test that execute() binds runtime context when tool has set_runtime_context."""
        tools_dir = tmp_path / "test_tools"
        tools_dir.mkdir()
        manager = ToolsManager(autoload=False)

        tool_file = tools_dir / "context_tool.py"
        tool_file.write_text(
            """
from core.tools import Tool
from core.sessions import SessionRecord
from core.sessions import SessionsManager
from core.skills import SkillsManager


class ContextTool(Tool):
    def __init__(self):
        self._session: SessionRecord | None = None
        self._sessions_manager: SessionsManager | None = None
        self._skills_manager: SkillsManager | None = None

    def set_runtime_context(self, **kwargs) -> None:
        session = kwargs.get("session")
        sessions_manager = kwargs.get("sessions_manager")
        skills_manager = kwargs.get("skills_manager")
        if isinstance(session, SessionRecord):
            self._session = session
        if isinstance(sessions_manager, SessionsManager):
            self._sessions_manager = sessions_manager
        if isinstance(skills_manager, SkillsManager):
            self._skills_manager = skills_manager

    @property
    def name(self) -> str:
        return "context_tool"

    @property
    def description(self) -> str:
        return "Tool that uses runtime context"

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs) -> str:
        if self._session is None:
            return "Error: No session context"
        if self._sessions_manager is None:
            return "Error: No sessions manager"
        if self._skills_manager is None:
            return "Error: No skills manager"
        return f"context_bound:session={self._session.metadata.session_id}"
"""
        )

        manager.autoload(tools_dir=tools_dir)
        manager.set_runtime_context(**runtime_context)

        result = await manager.execute("context_tool", {})

        assert result.startswith("context_bound:session=")
        assert "Error:" not in result
