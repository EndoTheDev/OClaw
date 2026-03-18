import json
import uuid
from pathlib import Path

import pytest

from core.sessions import SessionMetadata, SessionRecord, SessionsManager


class TestSessionsManager:
    def test_list_sessions_returns_empty_list_when_no_sessions(
        self, sessions_manager: SessionsManager
    ) -> None:
        sessions = sessions_manager.list_sessions()
        assert sessions == []

    def test_list_sessions_returns_sorted_sessions_by_date(
        self, sessions_manager: SessionsManager, tmp_path: Path
    ) -> None:
        sessions_dir = tmp_path / "sessions"
        manager = SessionsManager(sessions_dir=str(sessions_dir))

        manager.create_new_session()
        manager.create_new_session()
        manager.create_new_session()

        sessions = manager.list_sessions()
        assert len(sessions) == 3

        dates = [s.metadata.date_created for s in sessions]
        assert dates == sorted(dates, reverse=True)

    def test_get_latest_session_id_creates_new_if_none_exist(
        self, sessions_manager: SessionsManager
    ) -> None:
        session_id = sessions_manager.get_latest_session_id()
        assert uuid.UUID(session_id)

        sessions = sessions_manager.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].metadata.session_id == session_id

    def test_get_latest_session_id_returns_newest_session(
        self, sessions_manager: SessionsManager
    ) -> None:
        first = sessions_manager.create_new_session()
        second = sessions_manager.create_new_session()
        third = sessions_manager.create_new_session()

        latest_id = sessions_manager.get_latest_session_id()
        assert latest_id == third.metadata.session_id
        assert latest_id != first.metadata.session_id
        assert latest_id != second.metadata.session_id

    def test_get_session_by_id_returns_correct_session(
        self, sessions_manager: SessionsManager
    ) -> None:
        session = sessions_manager.create_new_session()

        retrieved = sessions_manager.get_session_by_id(session.metadata.session_id)
        assert retrieved.metadata.session_id == session.metadata.session_id
        assert retrieved.metadata.date_created == session.metadata.date_created
        assert retrieved.messages == []

    def test_get_session_by_id_raises_value_error_when_not_found(
        self, sessions_manager: SessionsManager
    ) -> None:
        non_existent_id = str(uuid.uuid4())

        with pytest.raises(ValueError) as exc_info:
            sessions_manager.get_session_by_id(non_existent_id)

        assert "not found" in str(exc_info.value).lower()

    def test_create_new_session_generates_unique_uuid(
        self, sessions_manager: SessionsManager
    ) -> None:
        session1 = sessions_manager.create_new_session()
        session2 = sessions_manager.create_new_session()

        uuid.UUID(session1.metadata.session_id)
        uuid.UUID(session2.metadata.session_id)
        assert session1.metadata.session_id != session2.metadata.session_id

    def test_create_new_session_writes_metadata_to_jsonl(
        self, sessions_manager: SessionsManager
    ) -> None:
        session = sessions_manager.create_new_session()

        assert session.file_path.exists()
        assert session.file_path.suffix == ".jsonl"

        with open(session.file_path, "r", encoding="utf-8") as f:
            first_line = f.readline()
            metadata = json.loads(first_line)

        assert "session_id" in metadata
        assert "date_created" in metadata
        assert "last_updated" in metadata
        assert metadata["active_skills"] == []

    def test_create_new_session_initializes_empty_messages(
        self, sessions_manager: SessionsManager
    ) -> None:
        session = sessions_manager.create_new_session()
        assert session.messages == []

    def test_overwrite_updates_last_updated_timestamp(
        self, sessions_manager: SessionsManager
    ) -> None:
        import time

        session = sessions_manager.create_new_session()
        original_timestamp = session.metadata.last_updated

        time.sleep(1.1)

        session.metadata.active_skills.append("test_skill")
        sessions_manager.overwrite(session)

        loaded = sessions_manager.get_session_by_id(session.metadata.session_id)
        assert loaded.metadata.last_updated != original_timestamp

    def test_overwrite_uses_atomic_write_with_temp_file(
        self, sessions_manager: SessionsManager, tmp_path: Path
    ) -> None:
        session = sessions_manager.create_new_session()
        temp_file = session.file_path.with_suffix(".tmp")

        sessions_manager.overwrite(session)

        assert not temp_file.exists()
        assert session.file_path.exists()

    def test_load_session_handles_empty_file(
        self, sessions_manager: SessionsManager, tmp_path: Path
    ) -> None:
        sessions_dir = tmp_path / "sessions"
        manager = SessionsManager(sessions_dir=str(sessions_dir))

        empty_file = sessions_dir / "2024-01-01T00-00-00.jsonl"
        empty_file.write_text("")

        session = manager._load_session(empty_file)
        assert isinstance(session.metadata.session_id, str)
        assert session.messages == []
        assert session.metadata.active_skills == []

    def test_load_session_validates_active_skills_is_list_of_strings(
        self, sessions_manager: SessionsManager, tmp_path: Path
    ) -> None:
        sessions_dir = tmp_path / "sessions"
        manager = SessionsManager(sessions_dir=str(sessions_dir))

        invalid_file = sessions_dir / "2024-01-01T00-00-00.jsonl"
        metadata = {
            "session_id": str(uuid.uuid4()),
            "date_created": "2024-01-01T00:00:00+00:00",
            "last_updated": "2024-01-01T00:00:00+00:00",
            "active_skills": "not_a_list",
        }
        invalid_file.write_text(json.dumps(metadata) + "\n")

        with pytest.raises(ValueError) as exc_info:
            manager._load_session(invalid_file)

        assert "active_skills" in str(exc_info.value).lower()
