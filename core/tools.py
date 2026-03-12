from abc import ABC, abstractmethod


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
    def schema(self) -> dict:
        """Get OpenAI-compatible tool schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolsManager:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def get_schemas(self) -> list[dict]:
        return [tool.schema for tool in self._tools.values()]

    async def execute(self, name: str, args: dict) -> str:
        tool = self.get(name)
        if not tool:
            return f"Error: Unknown tool '{name}'"

        try:
            return await tool.execute(**args)
        except Exception as e:
            return f"Error: {str(e)}"
