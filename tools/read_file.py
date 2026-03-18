import asyncio

from core.tools import Tool


class ReadFileTool(Tool):
    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Read the contents of a file at the specified path"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file to read"}
            },
            "required": ["path"],
        }

    async def execute(self, **kwargs) -> str:
        path = kwargs["path"]

        def _read():
            with open(path, "r", encoding="utf-8") as f:
                return f.read()

        try:
            content = await asyncio.to_thread(_read)
            return content
        except FileNotFoundError:
            return f"Error: File not found: {path}"
        except PermissionError:
            return f"Error: Permission denied: {path}"
        except Exception as e:
            return f"Error: {str(e)}"
