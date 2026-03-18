import asyncio

from core.tools import Tool


class ExecuteShellTool(Tool):
    @property
    def name(self) -> str:
        return "execute_shell"

    @property
    def description(self) -> str:
        return "Execute a bash command on the system"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The bash command to execute",
                }
            },
            "required": ["command"],
        }

    async def execute(self, **kwargs) -> str:
        command = kwargs["command"]
        proc = None
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

            output = stdout.decode("utf-8", errors="replace")
            if stderr:
                output += "\n" + stderr.decode("utf-8", errors="replace")

            return output if output else "Command executed successfully (no output)"

        except asyncio.TimeoutError:
            if proc:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
            return "Error: Command timed out after 30 seconds"
        except Exception as e:
            return f"Error: {str(e)}"
