import json
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi.testclient import TestClient

from server.gateway import AgentGateway


@pytest.fixture
def client(sessions_manager):
    """Create a TestClient for the AgentGateway."""
    with patch("server.gateway.SessionsManager", return_value=sessions_manager):
        with patch("server.gateway.AgentWorker"):
            gateway = AgentGateway(num_workers=2, timeout=60)
            gateway.app.state.gateway = gateway
            return TestClient(gateway.app, raise_server_exceptions=False)


class TestAgentGateway:
    def test_health_returns_200_with_status_healthy(self, client) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_health_includes_worker_count_and_timeout(self, client) -> None:
        response = client.get("/health")
        data = response.json()
        assert data["workers"] == 2
        assert data["timeout"] == 60

    def test_health_includes_provider_configuration(self, client) -> None:
        response = client.get("/health")
        data = response.json()
        assert "provider" in data
        assert "ollama_host" in data
        assert "openai_host" in data
        assert "model" in data

    def test_chat_stream_validates_session_exists(
        self, client, sessions_manager
    ) -> None:
        """Chat stream should check if session exists before processing."""
        session = sessions_manager.create_new_session()
        payload = {"message": "test", "session_id": session.metadata.session_id}
        response = client.post("/chat/stream", json=payload)
        assert response.status_code == 200

    def test_chat_stream_returns_400_when_session_not_found(self, client) -> None:
        invalid_session_id = "00000000-0000-0000-0000-000000000000"
        payload = {"message": "test", "session_id": invalid_session_id}
        response = client.post("/chat/stream", json=payload)
        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert "not found" in data["error"].lower()

    def test_chat_stream_returns_sse_response_with_correct_media_type(
        self, client, sessions_manager
    ) -> None:
        session = sessions_manager.create_new_session()
        payload = {"message": "test", "session_id": session.metadata.session_id}
        response = client.post("/chat/stream", json=payload)
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    def test_chat_stream_yields_agent_start_event_first(
        self, client, sessions_manager
    ) -> None:
        session = sessions_manager.create_new_session()
        payload = {"message": "test", "session_id": session.metadata.session_id}

        mock_events = [
            {"event_type": "agent_start", "payload": {"status": "started"}},
            {"event_type": "chunk", "payload": {"content": "hello"}},
            {"event_type": "stream_end", "payload": {"status": "completed"}},
        ]

        with patch.object(client.app.state.gateway.worker, "run_agent") as mock_run:

            async def mock_generator():
                for event in mock_events:
                    yield event

            mock_run.return_value = mock_generator()

            response = client.post("/chat/stream", json=payload)
            lines = response.text.strip().split("\n")
            first_data_line = [
                l for l in lines if l.strip() and l.startswith("data: ")
            ][0]
            first_event = json.loads(first_data_line.replace("data: ", ""))
            assert first_event["event_type"] == "agent_start"

    def test_chat_stream_yields_complete_event_sequence(
        self, client, sessions_manager
    ) -> None:
        session = sessions_manager.create_new_session()
        payload = {"message": "test", "session_id": session.metadata.session_id}

        mock_events = [
            {"event_type": "agent_start", "payload": {"status": "started"}},
            {"event_type": "chunk", "payload": {"content": "hello"}},
            {"event_type": "agent_end", "payload": {"status": "completed"}},
            {"event_type": "stream_end", "payload": {"status": "completed"}},
        ]

        with patch.object(client.app.state.gateway.worker, "run_agent") as mock_run:

            async def mock_generator():
                for event in mock_events:
                    yield event

            mock_run.return_value = mock_generator()

            response = client.post("/chat/stream", json=payload)
            lines = response.text.strip().split("\n")
            event_types = [
                json.loads(line.replace("data: ", ""))["event_type"]
                for line in lines
                if line.strip() and line.startswith("data: ")
            ]
            assert event_types == ["agent_start", "chunk", "agent_end", "stream_end"]

    def test_chat_stream_yields_error_event_on_failure(
        self, client, sessions_manager
    ) -> None:
        session = sessions_manager.create_new_session()
        payload = {"message": "test", "session_id": session.metadata.session_id}

        mock_events = [
            {"event_type": "agent_start", "payload": {"status": "started"}},
            {
                "event_type": "error",
                "payload": {"message": "something went wrong", "fatal": False},
            },
            {"event_type": "stream_end", "payload": {"status": "failed"}},
        ]

        with patch.object(client.app.state.gateway.worker, "run_agent") as mock_run:

            async def mock_generator():
                for event in mock_events:
                    yield event

            mock_run.return_value = mock_generator()

            response = client.post("/chat/stream", json=payload)
            lines = response.text.strip().split("\n")
            event_types = [
                json.loads(line.replace("data: ", ""))["event_type"]
                for line in lines
                if line.strip() and line.startswith("data: ")
            ]
            assert "error" in event_types

    def test_sessions_list_returns_empty_array_when_no_sessions(self, client) -> None:
        response = client.get("/sessions/list")
        assert response.status_code == 200
        data = response.json()
        assert data["sessions"] == []

    def test_sessions_list_returns_sorted_sessions(
        self, client, sessions_manager
    ) -> None:
        sessions_manager.create_new_session()
        sessions_manager.create_new_session()
        sessions_manager.create_new_session()

        response = client.get("/sessions/list")
        data = response.json()
        assert len(data["sessions"]) == 3

        dates = [s["date_created"] for s in data["sessions"]]
        assert dates == sorted(dates, reverse=True)

    def test_sessions_list_includes_message_count_per_session(
        self, client, sessions_manager
    ) -> None:
        session = sessions_manager.create_new_session()
        session.messages.append(
            {"role": "user", "content": "hello", "timestamp": "2024-01-01T00:00:00Z"}
        )
        session.messages.append(
            {"role": "assistant", "content": "hi", "timestamp": "2024-01-01T00:00:01Z"}
        )
        sessions_manager.overwrite(session)

        response = client.get("/sessions/list")
        data = response.json()
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["message_count"] == 2

    def test_sessions_new_creates_session_and_returns_id(self, client) -> None:
        response = client.post("/sessions/new")
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "file_path" in data
        assert "date_created" in data

    def test_admin_restart_calls_worker_restart(self, client) -> None:
        with patch.object(client.app.state.gateway.worker, "restart") as mock_restart:
            response = client.post("/admin/restart")
            assert response.status_code == 200
            assert response.json()["status"] == "workers restarted"
            mock_restart.assert_called_once()

    def test_chat_permit_sends_approval_to_worker_queue(
        self, client, sessions_manager
    ) -> None:
        session = sessions_manager.create_new_session()
        payload = {"message": "test", "session_id": session.metadata.session_id}

        mock_events = [
            {"event_type": "agent_start", "payload": {"status": "started"}},
            {
                "event_type": "awaiting_approval",
                "payload": {"request_id": "test-request-123"},
            },
        ]

        with patch.object(client.app.state.gateway.worker, "run_agent") as mock_run:
            with patch.object(
                client.app.state.gateway.worker, "pending_inputs"
            ) as mock_pending:
                mock_queue = MagicMock()
                mock_pending.__getitem__.return_value = mock_queue
                mock_pending.__contains__.return_value = True

                async def mock_generator():
                    for event in mock_events:
                        yield event

                mock_run.return_value = mock_generator()

                client.post("/chat/stream", json=payload)

                permit_payload = {"request_id": "test-request-123", "approved": True}
                response = client.post("/chat/permit", json=permit_payload)
                assert response.status_code == 200
                assert response.json()["status"] == "ok"

    def test_chat_permit_returns_error_when_request_id_not_found(self, client) -> None:
        permit_payload = {"request_id": "nonexistent-id", "approved": True}
        response = client.post("/chat/permit", json=permit_payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "not found" in data["message"].lower()
