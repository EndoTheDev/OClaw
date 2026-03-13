import asyncio
import httpx
import json


class OClawCLI:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=None)

    def _classify_event(self, data: dict) -> str:
        """Map event type to section type."""
        event_type = data.get("type", "")

        if event_type == "tool_call":
            name = data.get("name", "unknown")
            args = data.get("args", {})
            return f"tool_call:{name}({self._format_args(args)})"
        elif event_type == "tool_end":
            return "tool_output"
        elif event_type == "thinking":
            return "thinking"
        else:
            return "response"

    def _format_args(self, args: dict | str) -> str:
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except (json.JSONDecodeError, TypeError):
                return args
        
        if not args:
            return ""
        parts = []
        for k, v in args.items():
            if isinstance(v, str):
                parts.append(f'{k}="{v}"')
            else:
                parts.append(f"{k}={v}")
        return ", ".join(parts)

    def _print_header(self, section_type: str):
        if section_type.startswith("tool_call:"):
            print(f"\n[{section_type}] ", end="", flush=True)
        elif section_type == "tool_output":
            print("\n[tool_output]\n", end="", flush=True)
        elif section_type == "thinking":
            print("\n[thinking] ", end="", flush=True)
        elif section_type == "response":
            print("\n[response] ", end="", flush=True)

    def _extract_content(self, data: dict) -> str:
        for key in ["content", "text", "result", "output"]:
            if key in data:
                return str(data[key])
        return ""

    async def _stream_response(self, message: str):
        url = f"{self.base_url}/chat/stream"
        current_section = None

        try:
            async with self.client.stream(
                "POST",
                url,
                json={"message": message},
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue

                    data = json.loads(line[6:])

                    content = self._extract_content(data)
                    event_type = data.get("type", "")

                    if event_type in ("token", "metrics", "done") and not content:
                        continue

                    section_type = self._classify_event(data)

                    if section_type != current_section:
                        if current_section is not None:
                            print()
                        self._print_header(section_type)
                        current_section = section_type

                    if content:
                        print(content, end="", flush=True)

                print()

        except httpx.ConnectError:
            print("\nError: Cannot connect to backend server.")
            print("Make sure the server is running: uv run main.py --serve")
        except httpx.HTTPStatusError as e:
            print(f"\nError: Server returned {e.response.status_code}")
        except json.JSONDecodeError:
            print("\nError: Invalid response from server")

    async def _get_input_async(self) -> str:
        return await asyncio.to_thread(lambda: input("\nYou: ").strip())

    async def run(self):
        print("OClaw CLI Client")
        print(f"Connected to: {self.base_url}")
        print("Type 'exit' or 'quit' to leave\n")

        try:
            while True:
                try:
                    user_input = await self._get_input_async()
                except EOFError:
                    print()
                    break

                if user_input.lower() in ("exit", "quit"):
                    print("Goodbye!")
                    break

                if not user_input:
                    continue

                await self._stream_response(user_input)

        finally:
            await self.client.aclose()
