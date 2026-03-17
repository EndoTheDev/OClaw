# Configuration Reference

## Overview

OClaw uses a JSON config with four categories:

- **provider** - LLM provider settings (for registered providers, such as Ollama/OpenAI/Anthropic)
- **agent** - Agent behavior settings
- **server** - FastAPI server settings
- **worker** - Worker process pool settings

Load order is `config.json`, then `.env`, then process environment variables.

Use `config.json` for non-sensitive settings and `.env` for secrets. With this load order, values in `.env` override `config.json`, and process environment variables override both.

## Configuration File Format

### Nested Structure

```json
{
  "provider": {
    "active": "ollama",
    "ollama": { "host": "http://localhost:11434" },
    "openai": { "host": "...", "api_key": "..." },
    "anthropic": { "host": "...", "api_key": "..." },
    "model": "model-name"
  },
  "agent": { "max_iterations": 5 },
  "server": { "host": "0.0.0.0", "port": 8000 },
  "worker": { "num_processes": 4, "timeout": 300 }
}
```

### Loading Priority

1. Process environment variables (highest)
2. `.env` file
3. `config.json` (lowest)

## Categories

### Provider Configuration

| Field               | Type   | Default                          | Required | Description                                         |
| ------------------- | ------ | -------------------------------- | -------- | --------------------------------------------------- |
| `active`            | string | `"ollama"`                       | No       | Active provider name. Must match a registered provider |
| `ollama.host`       | string | `"http://localhost:11434"`       | No       | Ollama server URL                                   |
| `openai.host`       | string | `"https://api.openai.com/v1"`    | No       | OpenAI API endpoint                                 |
| `openai.api_key`    | string | `null`                           | Yes\*    | OpenAI API key                                      |
| `anthropic.host`    | string | `"https://api.anthropic.com/v1"` | No       | Anthropic API endpoint                              |
| `anthropic.api_key` | string | `null`                           | Yes\*    | Anthropic API key                                   |
| `model`             | string | `null`                           | Yes      | Model name (provider-specific)                      |

\*Required when using that provider

`provider.active` is resolved at runtime by `core.providers.manager.ProvidersManager`, which autoloads provider modules from `core/providers/*.py`. A provider module is registered when it exports `PROVIDER_NAME` and `create_provider()`. The loader excludes `base.py`, `manager.py`, and files prefixed with `_`.

#### Provider Examples

**Ollama:**

```json
{
  "provider": {
    "active": "ollama",
    "ollama": { "host": "http://localhost:11434" },
    "model": "qwen3.5:9b"
  }
}
```

**OpenAI:**

```json
{
  "provider": {
    "active": "openai",
    "openai": {
      "host": "https://api.openai.com/v1",
      "api_key": "sk-..."
    },
    "model": "gpt-4o-mini"
  }
}
```

**Anthropic:**

```json
{
  "provider": {
    "active": "anthropic",
    "anthropic": {
      "host": "https://api.anthropic.com/v1",
      "api_key": "sk-ant-..."
    },
    "model": "claude-3-5-sonnet-20241022"
  }
}
```

### Agent Configuration

| Field            | Type    | Default | Required | Description                   |
| ---------------- | ------- | ------- | -------- | ----------------------------- |
| `max_iterations` | integer | `5`     | No       | Maximum agent loop iterations |

### Server Configuration

| Field  | Type    | Default     | Required | Description         |
| ------ | ------- | ----------- | -------- | ------------------- |
| `host` | string  | `"0.0.0.0"` | No       | Server bind address |
| `port` | integer | `8000`      | No       | Server port         |

### Worker Configuration

| Field           | Type    | Default | Required | Description                       |
| --------------- | ------- | ------- | -------- | --------------------------------- |
| `num_processes` | integer | `4`     | No       | Worker process pool size          |
| `timeout`       | integer | `300`   | No       | Worker shutdown timeout (seconds) |

## Environment Variables

### Provider Variables

| Variable                     | Maps To                      | Example                        |
| ---------------------------- | ---------------------------- | ------------------------------ |
| `PROVIDER_ACTIVE`            | `provider.active`            | `ollama`                       |
| `PROVIDER_OLLAMA_HOST`       | `provider.ollama_host`       | `http://localhost:11434`       |
| `PROVIDER_OPENAI_HOST`       | `provider.openai_host`       | `https://api.openai.com/v1`    |
| `PROVIDER_OPENAI_API_KEY`    | `provider.openai_api_key`    | `sk-...`                       |
| `PROVIDER_ANTHROPIC_HOST`    | `provider.anthropic_host`    | `https://api.anthropic.com/v1` |
| `PROVIDER_ANTHROPIC_API_KEY` | `provider.anthropic_api_key` | `sk-ant-...`                   |
| `PROVIDER_MODEL`             | `provider.model`             | `qwen3.5:9b`                   |

### Agent Variables

| Variable               | Maps To                | Example |
| ---------------------- | ---------------------- | ------- |
| `AGENT_MAX_ITERATIONS` | `agent.max_iterations` | `5`     |

### Server Variables

| Variable      | Maps To       | Example   |
| ------------- | ------------- | --------- |
| `SERVER_HOST` | `server.host` | `0.0.0.0` |
| `SERVER_PORT` | `server.port` | `8000`    |

### Worker Variables

| Variable               | Maps To                | Example |
| ---------------------- | ---------------------- | ------- |
| `WORKER_NUM_PROCESSES` | `worker.num_processes` | `4`     |
| `WORKER_TIMEOUT`       | `worker.timeout`       | `300`   |

### Example .env File

```bash
# Provider
PROVIDER_ACTIVE=ollama
PROVIDER_OLLAMA_HOST=http://localhost:11434
PROVIDER_MODEL=qwen3.5:9b

# Agent
AGENT_MAX_ITERATIONS=5

# Server
SERVER_HOST=0.0.0.0
SERVER_PORT=8000

# Worker
WORKER_NUM_PROCESSES=4
WORKER_TIMEOUT=300
```

## Minimal Configuration

Minimum working `config.json`:

```json
{
  "provider": {
    "active": "ollama",
    "ollama": { "host": "http://localhost:11434" },
    "model": "qwen3.5:9b"
  },
  "agent": { "max_iterations": 5 },
  "server": { "host": "0.0.0.0", "port": 8000 },
  "worker": { "num_processes": 4, "timeout": 300 }
}
```

## Full Configuration

All fields explicitly set:

```json
{
  "provider": {
    "active": "ollama",
    "ollama": { "host": "http://localhost:11434" },
    "openai": { "host": "https://api.openai.com/v1", "api_key": "sk-..." },
    "anthropic": {
      "host": "https://api.anthropic.com/v1",
      "api_key": "sk-ant-..."
    },
    "model": "qwen3.5:9b"
  },
  "agent": { "max_iterations": 5 },
  "server": { "host": "0.0.0.0", "port": 8000 },
  "worker": { "num_processes": 4, "timeout": 300 }
}
```

## Validation

### Required Fields

- `provider.model` - Must be non-empty string
- `provider.active` - Must match a registered provider name

### Common Errors

**Model not configured:**

```text
ValueError: Model not configured. Set 'provider.model' in config.json or OLLAMA_MODEL in .env
```

**Fix:** Add `provider.model` to `config.json` or set `PROVIDER_MODEL`.

**Invalid provider:**

```text
ValueError: Unsupported provider 'xxx'
```

**Fix:** Set `provider.active` to a registered provider name. Default built-ins are `ollama`, `openai`, and `anthropic`.

**Connection refused:**

```text
Cannot connect to Ollama server
```

**Fix:** Check `provider.ollama.host` URL and ensure Ollama is running

## Troubleshooting

### Check Configuration

```bash
# View key runtime config values
curl http://localhost:8000/health | jq
```

### Test Provider Connection

```bash
# Ollama
curl http://localhost:11434/api/tags

# OpenAI
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
  https://api.openai.com/v1/models

# Anthropic
curl -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  https://api.anthropic.com/v1/models
```

### Debug Config Loading

Enable verbose logging:

```bash
OCLAW_LOG_LEVEL=DEBUG uv run main.py --serve
```

## Quick Start

1. Copy example config:

   ```bash
   cp config.example.json config.json
   ```

2. Edit `config.json` for your provider.

   Example values:
   - Ollama (local): `"active": "ollama"`, `"model": "qwen3.5:9b"`
   - OpenAI (cloud): `"active": "openai"`, `"model": "gpt-4o-mini"`

3. Start server:

   ```bash
   uv run main.py --serve
   ```

4. Verify:

   ```bash
   curl http://localhost:8000/health
   ```
