# OClaw

OClaw is a Python agent app. It gives you a FastAPI streaming server, a terminal CLI, provider adapters (`ollama`, `openai`, `anthropic`), and local tools/skills.

## Quick start

1. Install dependencies:

```bash
uv sync
```

1. Configure provider and model (see [docs/configuration.md](docs/configuration.md)).

   Keep secrets in `.env` and keep non-sensitive settings in `config.json`.

1. Start the server:

```bash
uv run main.py --serve
```

1. Start the CLI in another terminal:

```bash
uv run main.py --cli
```

## Minimal usage

- Type a prompt in the CLI and wait for streamed output sections (`[thinking]`, `[response]`, `[tool_call]`, `[tool_output]`).
- If the agent requests a tool execution, the CLI asks for approval (`y`/`n`).
- Use `/new` in the CLI to create a new session.
- Use `exit` or `quit` to stop the CLI.

API endpoints exposed by the server:

- `GET /health`
- `POST /chat/stream`
- `POST /chat/permit`
- `GET /sessions/list`
- `POST /sessions/new`
- `POST /admin/restart`

## Documentation

- [Configuration](docs/configuration.md)
- [Architecture](docs/architecture.md)
- [Development](docs/development.md)
