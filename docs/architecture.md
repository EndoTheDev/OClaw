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
  - Resolves provider instances through `core.providers.manager.ProvidersManager`.
  - Streams events from worker queue back to gateway.
  - Tracks pending permission requests by `request_id`.

- `core/agent/`
  - `agent.py` coordinates the multi-iteration stream loop.
  - `session_orchestrator.py` loads session data into context and persists updates via `SessionsManager`.
  - `message_builder.py` builds provider messages from context + system prompt + active skills.
  - `chunk_dispatcher.py` normalizes provider chunks into agent events.
  - `tool_execution_handler.py` handles permission flow and tool execution via `ToolsManager`.

- `core/providers/*.py`
  - Provider adapters for `ollama`, `openai`, `anthropic`, and future providers.
  - Convert internal message/tool format to provider-specific payloads.
  - Convert provider stream chunks into common chunk types.
  - Export `PROVIDER_NAME` and `create_provider()` for autoload registration.

- `core/providers/manager.py`
  - Autoloads `core/providers/*.py` modules, excluding `base.py`, `manager.py`, and private files.
  - Registers provider factories by `PROVIDER_NAME`.
  - Creates provider instances from `config.provider.active`.

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
9. Agent emits `agent_start`, then opens each iteration with `turn_start` and `message_start`.
10. Provider chunks are emitted as `message_update` events:
    - assistant text deltas: `payload.channel = "content"` + `payload.delta`
    - reasoning deltas: `payload.channel = "thinking"` + `payload.delta`
    - tool calls: `payload.tool_call = {name, id, args}`
    - metrics: `payload.metrics`
11. Agent closes each assistant message with `message_end` and includes final `content`, `thinking`, and `tool_call_count`.
12. If tool calls exist, agent runs tool execution lifecycle events:
    - `tool_execution_start`
    - `tool_execution_update` with `phase = "approval_requested"`
    - CLI sends decision to `POST /chat/permit` with the stream `request_id`
    - `tool_execution_update` with `phase = "approval_granted"` or `phase = "approval_denied"`
    - `tool_execution_end` with `status = "succeeded" | "failed" | "denied"`
13. Agent emits `turn_end` for each iteration. On failed or denied tool execution, it also emits terminal `error` (`fatal: true`).
14. Agent persists session updates to `.sessions/*.jsonl` and emits terminal lifecycle events in order: `agent_end`, then `stream_end`.
15. Gateway forwards all events as SSE and closes the HTTP stream after terminal `stream_end`.

## Terminal semantics (v2)

- `stream_end` is the only stream terminal event. Consumers should treat it as definitive end-of-stream.
- `agent_end` always precedes `stream_end` and reports aggregate agent status.
- `error` is terminal only when `payload.fatal = true`; in current implementation, fatal errors are followed by `agent_end` and `stream_end`.

## Runtime boundaries

- HTTP boundary: CLI ↔ FastAPI server (`server/gateway.py`).
- Process boundary: gateway process ↔ worker process (`server/worker.py`) via manager queues.
- Provider boundary: provider adapter ↔ external model API.
