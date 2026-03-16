# Architecture

## Component map

- `main.py`
  - CLI/serve entrypoint.
  - `--serve` creates `server.gateway.AgentGateway`.
  - `--cli` creates `clients.cli.app.OClawCLI`.

- `server/gateway.py`
  - Builds the FastAPI app.
  - Starts/stops `AgentWorker` in app lifespan.
  - Exposes HTTP endpoints for health, streaming chat, session operations, worker restart, and tool permission decisions.

- `server/worker.py`
  - Manages a `ProcessPoolExecutor` and `multiprocessing.Manager` queues.
  - Runs one agent execution in a worker process via `_execute_agent`.
  - Streams events from worker queue back to gateway.
  - Tracks pending permission requests by `request_id`.

- `core/agent/`
  - `agent.py` coordinates the multi-iteration stream loop.
  - `session_orchestrator.py` loads session data into context and persists updates via `SessionsManager`.
  - `message_builder.py` builds provider messages from context + system prompt + active skills.
  - `chunk_dispatcher.py` normalizes provider chunks into agent events.
  - `tool_execution_handler.py` handles permission flow and tool execution via `ToolsManager`.

- `core/providers/*.py`
  - Provider adapters for `ollama`, `openai`, `anthropic`.
  - Convert internal message/tool format to provider-specific payloads.
  - Convert provider stream chunks into common chunk types.

- `core/sessions.py`
  - Session persistence in `.sessions/*.jsonl`.
  - First line is session metadata; following lines are messages.

- `clients/cli/app.py`
  - HTTP client for server endpoints.
  - Renders streamed event sections in terminal.
  - Handles permission prompts and posts decisions to `/chat/permit`.

- `core/tools.py` + `tools/*.py`
  - Tool base class and dynamic autoload from `tools/*.py`.
  - Registered built-ins include `read_file`, `write_file`, `execute_shell`, `load_tool`, `unload_tool`.

- `core/skills.py` + `skills/*/SKILL.md`
  - Loads skill metadata from YAML frontmatter.
  - Builds system prompt content from base prompt + available skill metadata + active skill bodies.

## Request lifecycle

1. You run `uv run main.py --cli` and send a message.
2. CLI resolves a session id (`/sessions/list` or `/sessions/new`).
3. CLI calls `POST /chat/stream` with `{message, session_id}`.
4. Gateway validates session id via `SessionsManager`.
5. Gateway calls `AgentWorker.run_agent(...)` and streams worker events as SSE.
6. Worker process creates provider, tools manager, skills manager, `SessionsManager`, `ContextManager`, then injects them into `Agent`.
7. `Agent.stream(...)` initializes session state through `SessionOrchestrator`, appends user message, and starts provider streaming.
8. Provider chunks are normalized into agent events and sent to client.
9. If provider emits tool calls, agent emits `permission_request`.
10. CLI asks for approval and posts decision to `POST /chat/permit` with `request_id`.
11. Worker receives approval from pending queue:
    - approved: executes tool, emits `tool_end`, appends tool result to context.
    - denied: emits denial message as `tool_end`, appends denial to context.
12. Agent continues iterations until no further tool calls, then emits `done`.
13. Agent writes updated session messages to `.sessions/*.jsonl`.
14. Gateway ends SSE stream after receiving terminal `done` event.

## Runtime boundaries

- HTTP boundary: CLI ↔ FastAPI server (`server/gateway.py`).
- Process boundary: gateway process ↔ worker process (`server/worker.py`) via manager queues.
- Provider boundary: provider adapter ↔ external model API.
