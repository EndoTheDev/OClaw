# Development

## Local workflow

1. Install dependencies:

   ```bash
   uv sync
   ```

2. Configure provider/model values in `config.json`, `.env`, or process environment.

3. Start server:

   ```bash
   uv run main.py --serve
   ```

4. Start CLI in another terminal:

   ```bash
   uv run main.py --cli
   ```

## Common commands

```bash
uv sync
uv run main.py --serve
uv run main.py --cli
curl http://localhost:8000/health
uv run pytest          # Run all 108 tests
uv run pytest -v       # Verbose output
```

## Test structure

```
tests/
├── test_agent.py         # 20 tests - Agent stream logic
├── test_api.py           # 16 tests - HTTP endpoints
├── test_config.py        # 11 tests - Configuration loading
├── test_sessions.py      # 13 tests - Session persistence
├── test_skills.py        # 17 tests - Skills system
├── test_tools.py         # 13 tests - Tool loading
└── test_providers/
    ├── test_ollama.py    # 6 tests - Ollama HTTP
    ├── test_openai.py    # 6 tests - OpenAI HTTP
    └── test_anthropic.py # 6 tests - Anthropic HTTP
```

All 108 tests should pass with 0 failures.

## Safe extension points

### Add a tool

Path: `tools/<name>.py`

Requirements from `core.tools.Tool`:

- implement `name`
- implement `description`
- implement `parameters` (JSON schema object)
- implement async `execute(...) -> str`

Registration behavior:

- `ToolsManager.autoload()` loads `tools/*.py` (excluding names starting with `_`).
- Any class that subclasses `Tool` in the module is registered.

Runtime context:

- If the tool defines `set_runtime_context(...)`, `ToolsManager.execute(...)` calls it before `execute(...)`.
- Current context fields are `session`, `sessions_manager`, `skills_manager`.

### Add a skill

Path pattern: `skills/<skill_id>/SKILL.md`

Requirements from `core.skills.SkillsManager`:

- `SKILL.md` must start with YAML frontmatter delimited by `---`.
- Frontmatter must include `name` and `description`.
- Body must be non-empty.

Usage flow:

- Skills are autoloaded at runtime.
- `load_tool` and `unload_tool` update `session.metadata.active_skills`.
- Active skill bodies are injected into the system prompt by `SkillsManager.build_system_prompt(...)`.

### Add a provider

Path pattern: `core/providers/<provider>.py`

Provider contract from `core.providers.base.Provider`:

- implement `chat(messages, tools=None)` as an async generator
- yield chunk types compatible with `ResponseChunk`, `ThinkingChunk`, `ToolCallChunk`, `MetricsChunk`, `DoneChunk`, `ErrorChunk`
- export `PROVIDER_NAME` as the provider id string
- export `create_provider()` that returns a provider instance

Registration and selection behavior:

- `ProvidersManager.autoload()` scans `core/providers/*.py` and loads provider modules dynamically.
- Loader excludes `base.py`, `manager.py`, and files with names that start with `_`.
- `ProvidersManager` registers modules that expose both `PROVIDER_NAME` and `create_provider()`.
- Worker resolves `config.provider.active` through `ProvidersManager.create(...)`.
- Existing values `ollama`, `openai`, and `anthropic` are still supported.

## Basic troubleshooting

- CLI cannot connect:
  - Ensure server is running with `uv run main.py --serve`.
  - Default CLI base URL is `http://localhost:8000`.

- Unicode encoding errors in CLI:
  - Caused by surrogate characters in terminal input
  - Fixed automatically (input sanitized)
  - Permanent fix: set `LANG=en_US.UTF-8` in shell config

- Import errors when running tests:
  - Install package: `uv pip install -e .`
  - Required for pytest to discover modules

- Session id errors from `/chat/stream`:
  - Create a new session in CLI with `/new`.
  - Verify session files exist under `.sessions/`.

- Provider initialization or request errors:
  - Check active provider and model in your config sources.
  - Confirm API key/host values for remote providers.

- Tool permission flow stalls:
  - Confirm the stream emitted `tool_execution_update` with `phase: "approval_requested"`.
  - Confirm CLI is waiting for `Allow execution? (y/n):` input.
  - Ensure `POST /chat/permit` uses the same top-level `request_id` as the active `/chat/stream` event envelope.
  - If `/chat/permit` returns `Request ID not found or expired`, the stream likely already terminated and the pending request was removed by the worker.
