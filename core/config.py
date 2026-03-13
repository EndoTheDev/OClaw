import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .logger import Logger


@dataclass
class Config:
    provider: str = "ollama"
    ollama_host: str = "http://localhost:11434"
    openai_host: str = "https://api.openai.com/v1"
    openai_api_key: str | None = None
    anthropic_host: str = "https://api.anthropic.com/v1"
    anthropic_api_key: str | None = None
    model: str | None = None
    max_iterations: int = 5
    server_host: str = "0.0.0.0"
    server_port: int = 8000
    num_workers: int = 4
    worker_timeout: int = 300

    _ENV_MAPPING = {
        "PROVIDER": "provider",
        "OLLAMA_HOST": "ollama_host",
        "OPENAI_HOST": "openai_host",
        "OPENAI_API_KEY": "openai_api_key",
        "ANTHROPIC_HOST": "anthropic_host",
        "ANTHROPIC_API_KEY": "anthropic_api_key",
        "OLLAMA_MODEL": "model",
        "MAX_ITERATIONS": "max_iterations",
        "SERVER_HOST": "server_host",
        "SERVER_PORT": "server_port",
        "NUM_WORKERS": "num_workers",
        "WORKER_TIMEOUT": "worker_timeout",
    }

    _FIELD_NAMES = {
        "provider",
        "ollama_host",
        "openai_host",
        "openai_api_key",
        "anthropic_host",
        "anthropic_api_key",
        "model",
        "max_iterations",
        "server_host",
        "server_port",
        "num_workers",
        "worker_timeout",
    }

    @classmethod
    def load(cls, config_path: str = "config.json", env_file: str = ".env") -> "Config":
        logger = Logger.get("config.py")
        logger.info("config.load.start", config_path=config_path, env_file=env_file)
        values: dict[str, Any] = {}

        config_file = Path(config_path)
        if config_file.exists():
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    file_config = json.load(f)
                    values.update(cls._normalize_keys(file_config))
                logger.info("config.load.file.success", path=str(config_file))
            except (json.JSONDecodeError, IOError):
                logger.error("config.load.file.failed", path=str(config_file))
                pass

        env_file_values: dict[str, Any] = {}
        env_path = Path(env_file)
        if env_path.exists():
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, _, value = line.partition("=")
                        key = key.strip().upper()
                        value = value.strip().strip("\"'")
                        if key:
                            env_file_values[key] = value
                logger.info("config.load.env.success", path=str(env_path))
            except IOError:
                logger.error("config.load.env.failed", path=str(env_path))
                pass

        values.update(cls._normalize_keys(env_file_values))

        process_env_values: dict[str, Any] = {}
        for env_key, config_key in cls._ENV_MAPPING.items():
            env_value = os.getenv(env_key)
            if env_value is not None:
                process_env_values[config_key] = env_value

        values.update(process_env_values)

        values = cls._convert_types(values)

        config = cls(**values)
        config.validate()
        logger.info(
            "config.load.done",
            provider=config.provider,
            ollama_host=config.ollama_host,
            openai_host=config.openai_host,
            model=config.model,
            max_iterations=config.max_iterations,
            server_host=config.server_host,
            server_port=config.server_port,
            num_workers=config.num_workers,
            worker_timeout=config.worker_timeout,
        )
        return config

    @classmethod
    def _normalize_keys(cls, values: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for key, value in values.items():
            key_text = str(key)
            mapped_key = cls._ENV_MAPPING.get(key_text.upper(), key_text)
            if mapped_key in cls._FIELD_NAMES:
                normalized[mapped_key] = value
        return normalized

    @staticmethod
    def _convert_types(values: dict[str, Any]) -> dict[str, Any]:
        converters = {
            "max_iterations": int,
            "server_port": int,
            "num_workers": int,
            "worker_timeout": int,
        }

        for key, converter in converters.items():
            if key in values and isinstance(values[key], str):
                try:
                    values[key] = converter(values[key])
                except (ValueError, TypeError):
                    pass

        return values

    def validate(self) -> None:
        if not self.model or not self.model.strip():
            raise ValueError(
                "Model not configured. Set 'model' in config.json or OLLAMA_MODEL in .env"
            )

    # def to_dict(self) -> dict[str, Any]:
    #     """Convert config to dictionary."""
    #     return {
    #         "ollama_host": self.ollama_host,
    #         "model": self.model,
    #         "max_iterations": self.max_iterations,
    #         "server_host": self.server_host,
    #         "server_port": self.server_port,
    #         "num_workers": self.num_workers,
    #         "worker_timeout": self.worker_timeout,
    #     }
