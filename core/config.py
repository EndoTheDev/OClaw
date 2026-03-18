import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .logger import Logger


@dataclass
class ProviderConfig:
    active: str = "ollama"
    ollama_host: str = "http://localhost:11434"
    openai_host: str = "https://api.openai.com/v1"
    openai_api_key: str | None = None
    anthropic_host: str = "https://api.anthropic.com/v1"
    anthropic_api_key: str | None = None
    model: str | None = None


@dataclass
class AgentConfig:
    max_iterations: int = 5


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8000


@dataclass
class WorkerConfig:
    num_processes: int = 4
    timeout: int = 300


@dataclass
class Config:
    provider: ProviderConfig
    agent: AgentConfig
    server: ServerConfig
    worker: WorkerConfig

    _ENV_MAPPING = {
        "PROVIDER_ACTIVE": "provider.active",
        "PROVIDER_OLLAMA_HOST": "provider.ollama_host",
        "PROVIDER_OPENAI_HOST": "provider.openai_host",
        "PROVIDER_OPENAI_API_KEY": "provider.openai_api_key",
        "PROVIDER_ANTHROPIC_HOST": "provider.anthropic_host",
        "PROVIDER_ANTHROPIC_API_KEY": "provider.anthropic_api_key",
        "PROVIDER_MODEL": "provider.model",
        "AGENT_MAX_ITERATIONS": "agent.max_iterations",
        "SERVER_HOST": "server.host",
        "SERVER_PORT": "server.port",
        "WORKER_NUM_PROCESSES": "worker.num_processes",
        "WORKER_TIMEOUT": "worker.timeout",
    }

    _FIELD_NAMES = {
        "provider.active",
        "provider.ollama_host",
        "provider.openai_host",
        "provider.openai_api_key",
        "provider.anthropic_host",
        "provider.anthropic_api_key",
        "provider.model",
        "agent.max_iterations",
        "server.host",
        "server.port",
        "worker.num_processes",
        "worker.timeout",
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
            except (json.JSONDecodeError, OSError) as e:
                logger.error(
                    "config.load.file.failed", path=str(config_file), error=str(e)
                )
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
            except OSError as e:
                logger.error("config.load.env.failed", path=str(env_path), error=str(e))
                pass

        values.update(cls._normalize_keys(env_file_values))

        process_env_values: dict[str, Any] = {}
        for env_key, config_path in cls._ENV_MAPPING.items():
            env_value = os.getenv(env_key)
            if env_value is not None:
                process_env_values[config_path] = env_value

        values.update(process_env_values)

        values = cls._convert_types(values)
        values = cls._build_nested_structure(values)

        config = cls(
            provider=ProviderConfig(**values.get("provider", {})),
            agent=AgentConfig(**values.get("agent", {})),
            server=ServerConfig(**values.get("server", {})),
            worker=WorkerConfig(**values.get("worker", {})),
        )
        config.validate()
        logger.info(
            "config.load.done",
            provider=config.provider.active,
            ollama_host=config.provider.ollama_host,
            openai_host=config.provider.openai_host,
            model=config.provider.model,
            max_iterations=config.agent.max_iterations,
            server_host=config.server.host,
            server_port=config.server.port,
            num_workers=config.worker.num_processes,
            worker_timeout=config.worker.timeout,
        )
        return config

    @classmethod
    def _normalize_keys(cls, values: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for key, value in values.items():
            if isinstance(value, dict):
                if key == "provider":
                    for nested_key, nested_value in value.items():
                        if isinstance(nested_value, dict):
                            for sub_key, sub_value in nested_value.items():
                                env_key = f"{key}_{nested_key}_{sub_key}".upper()
                                mapped_key = cls._ENV_MAPPING.get(env_key)
                                if mapped_key:
                                    normalized[mapped_key] = sub_value
                                else:
                                    normalized[f"{key}.{nested_key}.{sub_key}"] = (
                                        sub_value
                                    )
                        else:
                            env_key = f"{key}_{nested_key}".upper()
                            mapped_key = cls._ENV_MAPPING.get(env_key)
                            if mapped_key:
                                normalized[mapped_key] = nested_value
                            else:
                                normalized[f"{key}.{nested_key}"] = nested_value
                elif key == "agent":
                    for nested_key, nested_value in value.items():
                        env_key = f"{key}_{nested_key}".upper()
                        mapped_key = cls._ENV_MAPPING.get(env_key)
                        if mapped_key:
                            normalized[mapped_key] = nested_value
                        else:
                            normalized[f"{key}.{nested_key}"] = nested_value
                elif key == "server":
                    for nested_key, nested_value in value.items():
                        env_key = f"{key}_{nested_key}".upper()
                        mapped_key = cls._ENV_MAPPING.get(env_key)
                        if mapped_key:
                            normalized[mapped_key] = nested_value
                        else:
                            normalized[f"{key}.{nested_key}"] = nested_value
                elif key == "worker":
                    for nested_key, nested_value in value.items():
                        env_key = f"{key}_{nested_key}".upper()
                        mapped_key = cls._ENV_MAPPING.get(env_key)
                        if mapped_key:
                            normalized[mapped_key] = nested_value
                        else:
                            normalized[f"{key}.{nested_key}"] = nested_value
            else:
                key_text = str(key)
                mapped_key = cls._ENV_MAPPING.get(key_text.upper(), key_text)
                if mapped_key in cls._FIELD_NAMES:
                    normalized[mapped_key] = value
        return normalized

    @staticmethod
    def _convert_types(values: dict[str, Any]) -> dict[str, Any]:
        logger = Logger.get("config._convert_types")
        converters = {
            "agent.max_iterations": int,
            "server.port": int,
            "worker.num_processes": int,
            "worker.timeout": int,
        }

        for key, converter in converters.items():
            if key in values and isinstance(values[key], str):
                try:
                    values[key] = converter(values[key])
                except (ValueError, TypeError) as e:
                    logger.debug(
                        "config.normalize.type_conversion.failed",
                        key=key,
                        value=values[key],
                        converter=converter.__name__,
                        error=str(e),
                    )

        return values

    @classmethod
    def _build_nested_structure(
        cls, values: dict[str, Any]
    ) -> dict[str, dict[str, Any]]:
        nested: dict[str, dict[str, Any]] = {
            "provider": {},
            "agent": {},
            "server": {},
            "worker": {},
        }

        for key, value in values.items():
            if "." in key:
                category, _, field = key.partition(".")
                if category in nested:
                    nested[category][field] = value

        return nested

    def validate(self) -> None:
        if self.provider.model is not None and not self.provider.model.strip():
            raise ValueError("Model cannot be empty string")
