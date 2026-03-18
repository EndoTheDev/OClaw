from core.tools import Tool


class TestTool(Tool):
    @property
    def name(self) -> str:
        return "test_tool"

    @property
    def description(self) -> str:
        return "A test tool for unit testing"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {"arg": {"type": "string", "description": "Test argument"}},
            "required": ["arg"],
        }

    async def execute(self, **kwargs) -> str:
        arg = kwargs["arg"]
        return f"Test tool executed with arg: {arg}"
