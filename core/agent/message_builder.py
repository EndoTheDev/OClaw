from __future__ import annotations

from datetime import datetime, timezone

from ..context import ContextManager
from ..skills import SkillsManager
from ..sessions import Message


class MessageBuilder:
    def __init__(
        self,
        context_manager: ContextManager,
        skills_manager: SkillsManager,
        default_system_prompt: str = "You are OClaw, a helpful assistant. Be concise and to the point.",
    ):
        self.context_manager = context_manager
        self.skills_manager = skills_manager
        self.default_system_prompt = default_system_prompt

    def build(
        self,
        active_skills: list[str],
        tool_definitions: list | None = None,
        system_prompt_override: str | None = None,
    ) -> list[Message]:
        messages = list(self.context_manager.messages)
        base_prompt = system_prompt_override or self.default_system_prompt
        system_prompt = self.skills_manager.build_system_prompt(
            base_prompt, active_skills
        )

        if system_prompt.strip():
            messages.insert(
                0,
                {
                    "role": "system",
                    "content": system_prompt,
                    "timestamp": self._now_iso(),
                },
            )

        return messages

    def get_context_messages(self) -> list[Message]:
        return list(self.context_manager.messages)

    def inject_user_message(self, content: str) -> None:
        self.context_manager.append_user(content)

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
