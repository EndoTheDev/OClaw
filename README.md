# OClaw (WIP)

OClaw is a Python AI agent runtime with:

- FastAPI streaming backend (SSE)
- Multi-provider support (`ollama`, `openai`, `anthropic`)
- Interactive CLI client
- Built-in tool calling (`read_file`, `write_file`, `execute_shell`)
- Tool execution permission flow in CLI (approve/deny before running a tool)

## Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/)
- For Ollama mode: reachable Ollama server + installed model
- For OpenAI mode: API key + model access
- For Anthropic mode: API key + model access

## Quick Start

### 1) Install

```bash
uv sync
cp .env.example .env
```

### 2) Configure

You can configure via `config.json`, `.env`, or environment variables.

Minimum required values:

#### Ollama

```env
PROVIDER=ollama
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen3.5:9b
```

#### OpenAI

```env
PROVIDER=openai
OPENAI_HOST=https://api.openai.com/v1
OPENAI_API_KEY=your_api_key
OLLAMA_MODEL=gpt-4o-mini
```

#### Anthropic

```env
PROVIDER=anthropic
ANTHROPIC_HOST=https://api.anthropic.com/v1
ANTHROPIC_API_KEY=your_api_key
OLLAMA_MODEL=claude-3-5-sonnet-20241022
```

> Note: `OLLAMA_MODEL` is currently used as the model field for all providers.

### 3) Run backend

```bash
uv run main.py --serve
```

Default server: `http://0.0.0.0:8000`

### 4) Health check

```bash
curl http://localhost:8000/health
```

### 5) Run CLI (new terminal)

```bash
uv run main.py --cli
```

## API

- `GET /health` — server + provider config snapshot
- `POST /chat/stream` — streaming chat events (SSE)
- `POST /admin/restart` — restart worker pool
- `POST /chat/permit` — approve or deny pending tool execution request

## Project Structure

- `main.py` — entrypoint (`--serve`, `--cli`)
- `server/` — FastAPI gateway + worker process orchestration
- `core/` — agent loop, config, sessions, logging, providers, tools manager
- `tools/` — built-in callable tools
- `clients/cli/` — terminal chat client

## Troubleshooting

- **Cannot connect to backend from CLI**  
  Start server first: `uv run main.py --serve`
- **Ollama connection fails in containers**  
  `localhost` inside containers is local to container; use host-reachable address
- **Model/provider errors**  
  Check `PROVIDER`, API key/host, and model name

## Current Status

Implemented:

- Streaming backend + CLI
- Ollama provider
- OpenAI provider
- Anthropic provider
- Tool autoloading
- Session persistence
- Structured logging
- Tool execution permission workflow
- Improved provider tool-call handling and CLI argument formatting

Planned next:

- More CLI session management features
- More provider support
- Dynamic skill/personality loading
- Additional config and safety improvements
