from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict

from .logger import Logger


Role = Literal["system", "user", "assistant", "tool"]


class ToolCallFunction(TypedDict):
    name: str
    arguments: dict[str, Any] | str


class ToolCall(TypedDict):
    type: Literal["function"]
    function: ToolCallFunction
    id: NotRequired[str]


class Message(TypedDict):
    role: Role
    content: NotRequired[str]
    thinking: NotRequired[str]
    tool_calls: NotRequired[list[ToolCall]]
    tool_name: NotRequired[str]
    tool_call_id: NotRequired[str]
    timestamp: str


@dataclass
class SessionMetadata:
    schema_version: int
    session_id: str
    date_created: str
    last_updated: str
    active_skills: list[str]


@dataclass
class SessionRecord:
    file_path: Path
    metadata: SessionMetadata
    messages: list[Message]


class SessionsManager:
    def __init__(self, sessions_dir: str = ".sessions"):
        self.sessions_dir = Path(sessions_dir)
        self.logger = Logger.get("sessions.py")

    def load_latest_or_create(self) -> SessionRecord:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        files = sorted(self.sessions_dir.glob("*.jsonl"))
        if not files:
            created_at = self._now_iso()
            metadata = SessionMetadata(
                schema_version=2,
                session_id=str(uuid.uuid4()),
                date_created=created_at,
                last_updated=created_at,
                active_skills=[],
            )
            return SessionRecord(
                file_path=self.sessions_dir / f"{created_at}.jsonl",
                metadata=metadata,
                messages=[],
            )
        self.logger.info("session.load.latest", file_path=str(files[-1]))
        return self._load_session(files[-1])

    def overwrite(self, session: SessionRecord) -> None:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        session.metadata.last_updated = self._now_iso()
        self.logger.info(
            "session.overwrite.start",
            file_path=str(session.file_path),
            message_count=len(session.messages),
        )

        temp_path = session.file_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as file:
            file.write(json.dumps(asdict(session.metadata), ensure_ascii=False) + "\n")
            for message in session.messages:
                file.write(json.dumps(message, ensure_ascii=False) + "\n")
        os.replace(temp_path, session.file_path)
        self.logger.info("session.overwrite.done", file_path=str(session.file_path))

    def _load_session(self, file_path: Path) -> SessionRecord:
        with open(file_path, "r", encoding="utf-8") as file:
            lines = [line.rstrip("\n") for line in file if line.strip()]

        if not lines:
            created_at = self._now_iso()
            metadata = SessionMetadata(
                schema_version=2,
                session_id=str(uuid.uuid4()),
                date_created=created_at,
                last_updated=created_at,
                active_skills=[],
            )
            return SessionRecord(file_path=file_path, metadata=metadata, messages=[])

        meta_data = json.loads(lines[0])
        schema_version = meta_data.get("schema_version")
        if schema_version != 2:
            raise ValueError(
                f"Unsupported session schema_version '{schema_version}'. Expected 2."
            )
        active_skills = meta_data.get("active_skills")
        if not isinstance(active_skills, list) or not all(
            isinstance(item, str) for item in active_skills
        ):
            raise ValueError("Session metadata field 'active_skills' must be list[str]")
        metadata = SessionMetadata(
            schema_version=schema_version,
            session_id=meta_data["session_id"],
            date_created=meta_data["date_created"],
            last_updated=meta_data["last_updated"],
            active_skills=active_skills,
        )
        messages = [json.loads(line) for line in lines[1:]]
        self.logger.info(
            "session.load.done",
            file_path=str(file_path),
            message_count=len(messages),
        )
        return SessionRecord(file_path=file_path, metadata=metadata, messages=messages)

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
