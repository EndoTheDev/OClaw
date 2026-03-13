# OClaw (WIP)

OClaw is a Python-based AI agent runtime with a FastAPI streaming backend, Ollama provider integration, and an interactive CLI client.

## Prerequisites

- Python 3.14+
- [uv](https://docs.astral.sh/uv/)
- A reachable Ollama instance
- The model you want to use is available in Ollama

## Setup

```bash
uv sync
cp .env.example .env
```

## Configuration

Defaults are defined in `config.json`.
You can override them in `.env` (or process environment variables).

At minimum, set:

- `OLLAMA_MODEL` (required)
- `OLLAMA_HOST` (if Ollama is not reachable at the default host)

Example:

```env
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen3.5:9b
```

## Run the server

```bash
uv run main.py --serve
```

This starts the backend server (default: `0.0.0.0:8000` unless overridden).

## Health check

```bash
curl http://localhost:8000/health
```

If you changed `SERVER_PORT`, replace `8000` accordingly.

## Run the CLI

In a second terminal (with server already running):

```bash
uv run main.py --cli
```

## Troubleshooting

- **Cannot connect from containerized app to Ollama**: `localhost` inside a container points to the container itself. Use a host-reachable address (for example `host.docker.internal` where supported).
- **Model errors**: ensure your configured `OLLAMA_MODEL` exists in Ollama before starting the app.
- **CLI connection errors**: start backend first with `uv run main.py --serve`.

## Roadmap

- [ ] Add more providers (e.g. OpenAI, Anthropic)
- [ ] Add more CLI features (e.g. new session, list sessions, load session, delete session, etc)
- [ ] Add dynamic skill loading
- [ ] Add dynamic personality loading (e.g. AGENTS.md, USER.md, SOUL.md, etc)
- [ ] Add more configuration options
