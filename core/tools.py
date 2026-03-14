from abc import ABC, abstractmethod
import importlib.util
import inspect
import sys
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

from .logger import Logger
from .providers.base import ToolDefinition

if TYPE_CHECKING:
    from .sessions import SessionRecord, SessionsManager
    from .skills import SkillsManager


class Tool(ABC):
    """Base class for agent tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Tool description."""
        ...

    @property
    @abstractmethod
    def parameters(self) -> dict:
        """JSON schema for tool parameters."""
        ...

    @abstractmethod
    async def execute(self, **kwargs) -> str:
        """Execute the tool with given arguments.

        Returns:
            Result as string for LLM consumption
        """
        ...

    @property
    def definition(self) -> "ToolDefinition":
        """Get the standardized tool definition."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
        )


class ToolsManager:
    def __init__(self, autoload: bool = True, tools_dir: Path | None = None):
        self.logger = Logger.get("tools.py")
        self._tools: dict[str, Tool] = {}
        self._runtime_context: dict[str, object] = {}
        if autoload:
            self.autoload(tools_dir=tools_dir)

    def set_runtime_context(
        self,
        *,
        session: "SessionRecord",
        sessions_manager: "SessionsManager",
        skills_manager: "SkillsManager",
    ) -> None:
        self._runtime_context = {
            "session": session,
            "sessions_manager": sessions_manager,
            "skills_manager": skills_manager,
        }

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            self.logger.error("tools.register.duplicate", name=tool.name)
            raise ValueError(f"Duplicate tool name '{tool.name}'")
        self._tools[tool.name] = tool
        self.logger.info("tools.register.success", name=tool.name)

    def autoload(self, tools_dir: Path | None = None) -> None:
        base_dir = Path(__file__).resolve().parents[1]
        directory = tools_dir or (base_dir / "tools")
        self.logger.info("tools.autoload.start", directory=str(directory))

        for file_path in sorted(directory.glob("*.py")):
            if file_path.stem.startswith("_"):
                continue
            module = self._load_module(file_path)
            self._register_module_tools(module)
        self.logger.info("tools.autoload.done", count=len(self._tools))

    def _load_module(self, file_path: Path) -> ModuleType:
        module_name = f"oclaw_tool_{file_path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            self.logger.error("tools.module.load.failed", file_path=str(file_path))
            raise RuntimeError(f"Cannot load tool module: {file_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        self.logger.info("tools.module.load.success", file_path=str(file_path))
        return module

    def _register_module_tools(self, module: ModuleType) -> None:
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj is Tool or not issubclass(obj, Tool):
                continue
            if obj.__module__ != module.__name__:
                continue
            self.register(obj())

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def get_definitions(self) -> list["ToolDefinition"]:
        return [tool.definition for tool in self._tools.values()]

    async def execute(self, name: str, args: dict) -> str:
        tool = self.get(name)
        if not tool:
            self.logger.error(
                "tools.execute.unknown",
                name=name,
                arguments_count=len(args),
                argument_keys=sorted(str(key) for key in args.keys()),
            )
            return f"Error: Unknown tool '{name}'"

        try:
            bind_runtime_context = getattr(tool, "set_runtime_context", None)
            if callable(bind_runtime_context):
                bind_runtime_context(**self._runtime_context)
            result = await tool.execute(**args)
            self.logger.info(
                "tools.execute.success",
                name=name,
                arguments_count=len(args),
                argument_keys=sorted(str(key) for key in args.keys()),
                result_chars=len(result),
            )
            return result
        except Exception as e:
            self.logger.error(
                "tools.execute.failed",
                name=name,
                arguments_count=len(args),
                argument_keys=sorted(str(key) for key in args.keys()),
                error=str(e),
            )
            return f"Error: {str(e)}"
