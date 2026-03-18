import json
import os

import pytest

from core.config import Config


class TestConfig:
    def test_load_returns_config_with_defaults_when_no_files_exist(self, tmp_path):
        """Test that load() returns a Config with default values when no config files exist."""
        config = Config.load(
            config_path=str(tmp_path / "nonexistent.json"),
            env_file=str(tmp_path / "nonexistent.env"),
        )

        assert config.provider.active == "ollama"
        assert config.provider.ollama_host == "http://localhost:11434"
        assert config.provider.openai_host == "https://api.openai.com/v1"
        assert config.provider.openai_api_key is None
        assert config.provider.anthropic_host == "https://api.anthropic.com/v1"
        assert config.provider.anthropic_api_key is None
        assert config.provider.model is None
        assert config.agent.max_iterations == 5
        assert config.server.host == "0.0.0.0"
        assert config.server.port == 8000
        assert config.worker.num_processes == 4
        assert config.worker.timeout == 300

    def test_load_reads_config_json_and_maps_to_nested_structure(self, tmp_path):
        """Test that load() reads config.json and correctly maps to nested structure."""
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "provider": {
                        "active": "openai",
                        "model": "gpt-4",
                        "ollama_host": "http://custom:11434",
                    },
                    "agent": {"max_iterations": 10},
                    "server": {"host": "127.0.0.1", "port": 9000},
                    "worker": {"num_processes": 8, "timeout": 600},
                }
            )
        )

        config = Config.load(
            config_path=str(config_file), env_file=str(tmp_path / "nonexistent.env")
        )

        assert config.provider.active == "openai"
        assert config.provider.model == "gpt-4"
        assert config.provider.ollama_host == "http://custom:11434"
        assert config.agent.max_iterations == 10
        assert config.server.host == "127.0.0.1"
        assert config.server.port == 9000
        assert config.worker.num_processes == 8
        assert config.worker.timeout == 600

    def test_load_reads_env_file_and_overrides_config(self, tmp_path):
        """Test that load() reads .env file and overrides config.json values."""
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "provider": {"active": "ollama", "model": "llama3"},
                    "agent": {"max_iterations": 5},
                    "server": {"port": 8000},
                    "worker": {"num_processes": 4},
                }
            )
        )

        env_file = tmp_path / ".env"
        env_file.write_text(
            "PROVIDER_ACTIVE=anthropic\n"
            "PROVIDER_MODEL=claude-3\n"
            "AGENT_MAX_ITERATIONS=15\n"
            "SERVER_PORT=9999\n"
            "WORKER_NUM_PROCESSES=2\n"
        )

        config = Config.load(config_path=str(config_file), env_file=str(env_file))

        assert config.provider.active == "anthropic"
        assert config.provider.model == "claude-3"
        assert config.agent.max_iterations == 15
        assert config.server.port == 9999
        assert config.worker.num_processes == 2

    def test_load_reads_process_env_vars_and_overrides_all(self, tmp_path, monkeypatch):
        """Test that process environment variables override both config.json and .env."""
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "provider": {"active": "ollama", "model": "llama3"},
                    "agent": {"max_iterations": 5},
                }
            )
        )

        env_file = tmp_path / ".env"
        env_file.write_text(
            "PROVIDER_ACTIVE=anthropic\nPROVIDER_MODEL=claude-3\nAGENT_MAX_ITERATIONS=15"
        )

        monkeypatch.setenv("PROVIDER_ACTIVE", "openai")
        monkeypatch.setenv("PROVIDER_MODEL", "gpt-4-turbo")
        monkeypatch.setenv("AGENT_MAX_ITERATIONS", "20")

        config = Config.load(config_path=str(config_file), env_file=str(env_file))

        assert config.provider.active == "openai"
        assert config.provider.model == "gpt-4-turbo"
        assert config.agent.max_iterations == 20

    def test_load_priority_order_is_config_json_then_env_file_then_process_env(
        self, tmp_path, monkeypatch
    ):
        """Test that priority order is: config.json < .env < process environment variables."""
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "provider": {"active": "ollama", "model": "llama3"},
                    "agent": {"max_iterations": 5},
                    "server": {"port": 8000},
                    "worker": {"num_processes": 4},
                }
            )
        )

        env_file = tmp_path / ".env"
        env_file.write_text(
            "PROVIDER_ACTIVE=anthropic\n"
            "PROVIDER_MODEL=claude-3\n"
            "AGENT_MAX_ITERATIONS=10\n"
            "SERVER_PORT=9000\n"
            "WORKER_NUM_PROCESSES=8\n"
        )

        monkeypatch.setenv("PROVIDER_ACTIVE", "openai")
        monkeypatch.setenv("PROVIDER_MODEL", "gpt-4")
        monkeypatch.setenv("SERVER_PORT", "9999")

        config = Config.load(config_path=str(config_file), env_file=str(env_file))

        assert config.provider.active == "openai"
        assert config.provider.model == "gpt-4"
        assert config.agent.max_iterations == 10
        assert config.server.port == 9999
        assert config.worker.num_processes == 8

    def test_load_converts_string_integers_to_int_type(self, tmp_path):
        """Test that load() converts string integers to int type."""
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "provider": {"model": "llama3"},
                    "agent": {"max_iterations": "10"},
                    "server": {"port": "8080"},
                    "worker": {"num_processes": "6", "timeout": "450"},
                }
            )
        )

        config = Config.load(
            config_path=str(config_file), env_file=str(tmp_path / "nonexistent.env")
        )

        assert isinstance(config.agent.max_iterations, int)
        assert config.agent.max_iterations == 10
        assert isinstance(config.server.port, int)
        assert config.server.port == 8080
        assert isinstance(config.worker.num_processes, int)
        assert config.worker.num_processes == 6
        assert isinstance(config.worker.timeout, int)
        assert config.worker.timeout == 450

    def test_load_handles_invalid_json_gracefully(self, tmp_path):
        """Test that load() handles invalid JSON gracefully and uses defaults."""
        config_file = tmp_path / "config.json"
        config_file.write_text("{ invalid json }")

        config = Config.load(
            config_path=str(config_file), env_file=str(tmp_path / "nonexistent.env")
        )

        assert config.provider.active == "ollama"
        assert config.agent.max_iterations == 5
        assert config.server.port == 8000

    def test_load_handles_missing_env_file_gracefully(self, tmp_path):
        """Test that load() handles missing .env file gracefully."""
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps(
                {"provider": {"model": "llama3"}, "agent": {"max_iterations": 10}}
            )
        )

        config = Config.load(
            config_path=str(config_file), env_file=str(tmp_path / "nonexistent.env")
        )

        assert config.provider.model == "llama3"
        assert config.agent.max_iterations == 10

    def test_validate_raises_value_error_when_model_is_empty(self, config_instance):
        """Test that validate() raises ValueError when model is empty string."""
        config_instance.provider.model = None
        config_instance.validate()

        config_instance.provider.model = ""
        with pytest.raises(ValueError, match="Model cannot be empty string"):
            config_instance.validate()

        config_instance.provider.model = "   "
        with pytest.raises(ValueError, match="Model cannot be empty string"):
            config_instance.validate()

    def test_validate_passes_when_model_is_set(self, config_instance):
        """Test that validate() passes when model is properly set."""
        config_instance.provider.model = "llama3.2"
        config_instance.validate()

        config_instance.provider.model = "gpt-4"
        config_instance.validate()

    def test_normalize_keys_handles_nested_config(self, tmp_path):
        """Test that _normalize_keys() correctly handles nested config structure."""
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "provider": {
                        "active": "ollama",
                        "ollama_host": "http://localhost:11434",
                        "openai_host": "https://api.openai.com/v1",
                        "openai_api_key": "sk-test-key",
                        "anthropic_host": "https://api.anthropic.com/v1",
                        "anthropic_api_key": "sk-ant-key",
                        "model": "llama3",
                    }
                }
            )
        )

        config = Config.load(
            config_path=str(config_file), env_file=str(tmp_path / "nonexistent.env")
        )

        assert config.provider.active == "ollama"
        assert config.provider.ollama_host == "http://localhost:11434"
        assert config.provider.openai_host == "https://api.openai.com/v1"
        assert config.provider.openai_api_key == "sk-test-key"
        assert config.provider.anthropic_host == "https://api.anthropic.com/v1"
        assert config.provider.anthropic_api_key == "sk-ant-key"
        assert config.provider.model == "llama3"
