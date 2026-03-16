from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..context import ContextManager
    from ..sessions import SessionsManager, SessionRecord
    from ..skills import SkillsManager
    from ..tools import ToolsManager


class SessionOrchestrator:
    def __init__(
        self,
        sessions_manager: SessionsManager,
        context_manager: ContextManager,
        skills_manager: SkillsManager,
        tools_manager: ToolsManager,
    ):
        self._sessions_manager = sessions_manager
        self._context_manager = context_manager
        self._skills_manager = skills_manager
        self._tools_manager = tools_manager
        self._session_id: str | None = None

    def initialize_session(self, session_id: str) -> SessionRecord:
        session = self._sessions_manager.get_session_by_id(session_id)
        self._session_id = session.metadata.session_id
        self._context_manager.load(session.messages)
        self._tools_manager.set_runtime_context(
            session=session,
            sessions_manager=self._sessions_manager,
            skills_manager=self._skills_manager,
        )
        return session

    def append_user_message(self, content: str) -> None:
        self._context_manager.append_user(content)

    def append_assistant_message(
        self,
        content: str,
        thinking: str | None = None,
        tool_calls: list | None = None,
    ) -> None:
        self._context_manager.append_assistant(content, thinking, tool_calls)

    def append_tool_message(
        self,
        tool_name: str,
        content: str,
        tool_call_id: str | None = None,
    ) -> None:
        self._context_manager.append_tool(tool_name, content, tool_call_id)

    def persist(self) -> None:
        session_id = self._session_id or self._sessions_manager.get_latest_session_id()
        session = self._sessions_manager.get_session_by_id(session_id)
        session.messages = list(self._context_manager.messages)
        self._sessions_manager.overwrite(session)

    def get_message_count(self) -> int:
        return len(self._context_manager.messages)

    def get_session_id(self) -> str:
        return self._session_id or self._sessions_manager.get_latest_session_id()

    def get_active_skills(self) -> list[str]:
        session_id = self._session_id or self._sessions_manager.get_latest_session_id()
        session = self._sessions_manager.get_session_by_id(session_id)
        return list(session.metadata.active_skills)
