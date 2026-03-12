import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Config:
    ollama_host: str = "http://localhost:11434"
    model: str | None = None
    max_iterations: int = 5
    server_host: str = "0.0.0.0"
    server_port: int = 8000
    num_workers: int = 4
    worker_timeout: int = 300

    @classmethod
    def load(cls, config_path: str = "config.json", env_file: str = ".env") -> "Config":
        values: dict[str, Any] = {}

        config_file = Path(config_path)
        if config_file.exists():
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    file_config = json.load(f)
                    values.update(file_config)
            except (json.JSONDecodeError, IOError):
                pass

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
                            values[key] = value
            except IOError:
                pass

        env_mapping = {
            "OLLAMA_HOST": "ollama_host",
            "OLLAMA_MODEL": "model",
            "MAX_ITERATIONS": "max_iterations",
            "SERVER_HOST": "server_host",
            "SERVER_PORT": "server_port",
            "NUM_WORKERS": "num_workers",
            "WORKER_TIMEOUT": "worker_timeout",
        }

        for env_key, config_key in env_mapping.items():
            env_value = os.getenv(env_key)
            if env_value is not None:
                values[config_key] = env_value

        values = cls._convert_types(values)

        config = cls(**values)
        config.validate()
        return config

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
