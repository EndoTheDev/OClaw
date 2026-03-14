from core.sessions import SessionRecord, SessionsManager
from core.skills import SkillsManager
from core.tools import Tool


class UnloadTool(Tool):
    def __init__(self):
        self._session: SessionRecord | None = None
        self._sessions_manager: SessionsManager | None = None
        self._skills_manager: SkillsManager | None = None

    def set_runtime_context(self, **kwargs) -> None:
        session = kwargs.get("session")
        sessions_manager = kwargs.get("sessions_manager")
        skills_manager = kwargs.get("skills_manager")
        if isinstance(session, SessionRecord):
            self._session = session
        if isinstance(sessions_manager, SessionsManager):
            self._sessions_manager = sessions_manager
        if isinstance(skills_manager, SkillsManager):
            self._skills_manager = skills_manager

    @property
    def name(self) -> str:
        return "unload_tool"

    @property
    def description(self) -> str:
        return "Deactivate a skill by skill_id"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "skill_id": {
                    "type": "string",
                    "description": "Canonical skill id to deactivate",
                }
            },
            "required": ["skill_id"],
        }

    async def execute(self, **kwargs) -> str:
        if self._session is None or self._sessions_manager is None:
            return "Error: Runtime session context unavailable"
        if self._skills_manager is None:
            return "Error: Skills manager unavailable"

        skill_id = kwargs.get("skill_id")
        if not isinstance(skill_id, str):
            return "Error: skill_id is required"
        normalized = skill_id.strip()
        if not normalized:
            return "Error: skill_id cannot be empty"
        if not self._skills_manager.has_skill(normalized):
            return f"Error: Unknown skill '{normalized}'"

        active_skills = self._session.metadata.active_skills
        if normalized not in active_skills:
            return f"already_inactive:{normalized}"

        self._session.metadata.active_skills = [
            item for item in active_skills if item != normalized
        ]
        self._sessions_manager.overwrite(self._session)
        return f"unloaded:{normalized}"
