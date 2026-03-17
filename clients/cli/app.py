import asyncio
import httpx
import json


class OClawCLI:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=None)

    def _classify_event(self, event_type: str, payload: dict) -> str | None:
        if event_type == "message_update":
            if payload.get("channel") == "thinking":
                return "thinking"
            if "tool_call" in payload:
                tool_call = payload.get("tool_call", {})
                name = tool_call.get("name", "unknown")
                args = tool_call.get("args", {})
                return f"tool_call:{name}({self._format_args(args)})"
            if payload.get("channel") == "content":
                return "response"
        if event_type == "tool_execution_start":
            return "tool_call"
        if event_type == "tool_execution_end":
            return "tool_output"
        if event_type == "error":
            return "error"
        return None

    def _format_args(self, args: dict[str, object] | str) -> str:
        if isinstance(args, str):
            try:
                parsed_args = json.loads(args)
            except (json.JSONDecodeError, TypeError):
                return args

            if not isinstance(parsed_args, dict):
                return str(parsed_args)
            args_dict: dict[str, object] = parsed_args
        else:
            args_dict = args

        if not args_dict:
            return ""
        parts = []
        for k, v in args_dict.items():
            if isinstance(v, str):
                parts.append(f'{k}="{v}"')
            else:
                parts.append(f"{k}={v}")
        return ", ".join(parts)

    def _print_header(self, section_type: str):
        if section_type.startswith("tool_call:"):
            print(f"\n[{section_type}] ", end="", flush=True)
        elif section_type == "tool_call":
            print("\n[tool_execution] ", end="", flush=True)
        elif section_type == "tool_output":
            print("\n[tool_output]\n", end="", flush=True)
        elif section_type == "thinking":
            print("\n[thinking] ", end="", flush=True)
        elif section_type == "response":
            print("\n[response] ", end="", flush=True)
        elif section_type == "error":
            print("\n[error] ", end="", flush=True)

    def _extract_content(self, event_type: str, payload: dict) -> str:
        if event_type == "message_update":
            if payload.get("channel") in {"content", "thinking"}:
                return str(payload.get("delta", ""))
        if event_type == "tool_execution_end":
            if "result" in payload:
                return str(payload.get("result"))
            if "error" in payload:
                return str(payload.get("error"))
        if event_type == "error":
            return str(payload.get("message", ""))
        return ""

    async def _fetch_latest_session_id(self) -> str:
        response = await self.client.get(f"{self.base_url}/sessions/list")
        response.raise_for_status()
        data = response.json()
        if not data["sessions"]:
            return await self._create_new_session()
        return data["sessions"][0]["session_id"]

    async def _create_new_session(self) -> str:
        response = await self.client.post(f"{self.base_url}/sessions/new")
        response.raise_for_status()
        data = response.json()
        return data["session_id"]

    async def _stream_response(self, message: str, session_id: str):
        url = f"{self.base_url}/chat/stream"
        current_section = None

        try:
            async with self.client.stream(
                "POST",
                url,
                json={"message": message, "session_id": session_id},
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue

                    data = json.loads(line[6:])
                    if data.get("schema_version") != "2.0":
                        continue

                    event_type = data.get("event_type", "")
                    payload = data.get("payload", {})
                    request_id = data.get("request_id", "")

                    if event_type == "tool_execution_update":
                        phase = payload.get("phase")
                        if phase == "approval_requested":
                            tool_name = payload.get("tool_name")
                            tool_args = payload.get("args", {})
                            formatted_args = self._format_args(tool_args)
                            print(
                                f"\n\nSystem: The agent wants to run the tool '{tool_name}({formatted_args})'."
                            )
                            ans = input("Allow execution? (y/n): ")

                            async with httpx.AsyncClient() as permit_client:
                                await permit_client.post(
                                    f"{self.base_url}/chat/permit",
                                    json={
                                        "request_id": request_id,
                                        "approved": ans.lower().startswith("y"),
                                    },
                                )
                        continue

                    if event_type in {
                        "agent_start",
                        "turn_start",
                        "message_start",
                        "message_end",
                        "turn_end",
                        "agent_end",
                        "stream_end",
                    }:
                        continue

                    content = self._extract_content(event_type, payload)
                    section_type = self._classify_event(event_type, payload)

                    if section_type is None:
                        continue

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
        print(
            r"""  
   ___   ____ _                
  / _ \ / ___| | __ ___      __
 | | | | |   | |/ _` \ \ /\ / /
 | |_| | |___| | (_| |\ V  V / 
  \___/ \____|_|\__,_| \_/\_/  
        CLI Client"""
        )
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

                if user_input.lower() == "/new":
                    print("\nCreating new session...")
                    session_id = await self._create_new_session()
                    print(f"New session created: {session_id}")
                    continue

                if not user_input:
                    continue

                session_id = await self._fetch_latest_session_id()
                await self._stream_response(user_input, session_id)

        finally:
            await self.client.aclose()
