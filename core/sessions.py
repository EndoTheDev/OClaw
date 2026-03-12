from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict


Role = Literal["user", "assistant", "tool"]


class ToolCallFunction(TypedDict):
    name: str
    arguments: dict[str, Any]


class ToolCall(TypedDict):
    type: Literal["function"]
    function: ToolCallFunction


class Message(TypedDict):
    role: Role
    content: NotRequired[str]
    thinking: NotRequired[str]
    tool_calls: NotRequired[list[ToolCall]]
    tool_name: NotRequired[str]
    timestamp: str


@dataclass
class SessionMetadata:
    session_id: str
    date_created: str
    last_updated: str


@dataclass
class SessionRecord:
    file_path: Path
    metadata: SessionMetadata
    messages: list[Message]


class SessionsManager:
    def __init__(self, sessions_dir: str = ".sessions"):
        self.sessions_dir = Path(sessions_dir)

    def load_latest_or_create(self) -> SessionRecord:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        files = sorted(self.sessions_dir.glob("*.jsonl"))
        if not files:
            created_at = self._now_iso()
            metadata = SessionMetadata(
                session_id=str(uuid.uuid4()),
                date_created=created_at,
                last_updated=created_at,
            )
            return SessionRecord(
                file_path=self.sessions_dir / f"{created_at}.jsonl",
                metadata=metadata,
                messages=[],
            )
        return self._load_session(files[-1])

    def overwrite(self, session: SessionRecord) -> None:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        session.metadata.last_updated = self._now_iso()

        temp_path = session.file_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as file:
            file.write(json.dumps(asdict(session.metadata), ensure_ascii=False) + "\n")
            for message in session.messages:
                file.write(json.dumps(message, ensure_ascii=False) + "\n")
        os.replace(temp_path, session.file_path)

    def _load_session(self, file_path: Path) -> SessionRecord:
        with open(file_path, "r", encoding="utf-8") as file:
            lines = [line.rstrip("\n") for line in file if line.strip()]

        if not lines:
            created_at = self._now_iso()
            metadata = SessionMetadata(
                session_id=str(uuid.uuid4()),
                date_created=created_at,
                last_updated=created_at,
            )
            return SessionRecord(file_path=file_path, metadata=metadata, messages=[])

        meta_data = json.loads(lines[0])
        metadata = SessionMetadata(
            session_id=meta_data["session_id"],
            date_created=meta_data["date_created"],
            last_updated=meta_data["last_updated"],
        )
        messages = [json.loads(line) for line in lines[1:]]
        return SessionRecord(file_path=file_path, metadata=metadata, messages=messages)

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
