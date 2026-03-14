from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .logger import Logger


@dataclass(frozen=True)
class SkillMetadata:
    skill_id: str
    name: str
    description: str
    file_path: Path


class SkillsManager:
    def __init__(self, autoload: bool = True, skills_dir: Path | None = None):
        self.logger = Logger.get("skills.py")
        base_dir = Path(__file__).resolve().parents[1]
        self._skills_dir = skills_dir or (base_dir / "skills")
        self._registry: dict[str, SkillMetadata] = {}
        self._body_cache: dict[str, str] = {}
        if autoload:
            self.autoload()

    def autoload(self) -> None:
        directory = self._skills_dir
        self.logger.info("skills.autoload.start", directory=str(directory))
        if not directory.exists() or not directory.is_dir():
            self.logger.info("skills.autoload.done", count=0)
            return

        registry: dict[str, SkillMetadata] = {}
        for skill_dir in sorted(path for path in directory.iterdir() if path.is_dir()):
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists() or not skill_file.is_file():
                continue
            metadata = self._parse_metadata(skill_dir.name, skill_file)
            if metadata.skill_id in registry:
                self.logger.error(
                    "skills.autoload.duplicate",
                    skill_id=metadata.skill_id,
                    file_path=str(skill_file),
                )
                raise ValueError(f"Duplicate skill id '{metadata.skill_id}'")
            registry[metadata.skill_id] = metadata

        self._registry = registry
        self._body_cache = {}
        self.logger.info("skills.autoload.done", count=len(self._registry))

    def list_metadata(self) -> list[SkillMetadata]:
        return [self._registry[key] for key in sorted(self._registry.keys())]

    def has_skill(self, skill_id: str) -> bool:
        return skill_id in self._registry

    def get_metadata(self, skill_id: str) -> SkillMetadata:
        metadata = self._registry.get(skill_id)
        if metadata is None:
            raise ValueError(f"Unknown skill '{skill_id}'")
        return metadata

    def get_body(self, skill_id: str) -> str:
        if skill_id in self._body_cache:
            return self._body_cache[skill_id]

        metadata = self.get_metadata(skill_id)
        content = metadata.file_path.read_text(encoding="utf-8")
        _, body = self._split_frontmatter(content)
        full_body = body.strip()
        if not full_body:
            raise ValueError(f"Skill '{skill_id}' has empty SKILL.md body")
        self._body_cache[skill_id] = full_body
        return full_body

    def build_system_prompt(self, base_prompt: str, active_skills: list[str]) -> str:
        chunks: list[str] = []
        base_text = base_prompt.strip()
        if base_text:
            chunks.append(base_text)

        metadata_lines = [
            f"- {item.skill_id}: {item.description}" for item in self.list_metadata()
        ]
        if metadata_lines:
            chunks.append("Available skills:\n" + "\n".join(metadata_lines))

        if active_skills:
            rendered_active: list[str] = []
            seen: set[str] = set()
            for skill_id in active_skills:
                if skill_id in seen:
                    continue
                seen.add(skill_id)
                metadata = self.get_metadata(skill_id)
                body = self.get_body(skill_id)
                rendered_active.append(
                    f'<active_skill id="{metadata.skill_id}" name="{metadata.name}">\n{body}\n</active_skill>'
                )
            if rendered_active:
                chunks.append("Active skills:\n" + "\n\n".join(rendered_active))

        return "\n\n".join(chunks).strip()

    def _parse_metadata(self, skill_id: str, file_path: Path) -> SkillMetadata:
        content = file_path.read_text(encoding="utf-8")
        frontmatter, _ = self._split_frontmatter(content)
        fields = self._parse_frontmatter_map(frontmatter)
        name = fields.get("name", "").strip()
        description = fields.get("description", "").strip()
        if not name:
            raise ValueError(f"Skill '{skill_id}' missing frontmatter field 'name'")
        if not description:
            raise ValueError(
                f"Skill '{skill_id}' missing frontmatter field 'description'"
            )
        return SkillMetadata(
            skill_id=skill_id,
            name=name,
            description=description,
            file_path=file_path,
        )

    def _split_frontmatter(self, content: str) -> tuple[str, str]:
        if not content.startswith("---\n"):
            raise ValueError("SKILL.md must start with YAML frontmatter")
        end_marker = "\n---\n"
        end_index = content.find(end_marker, 4)
        if end_index == -1:
            raise ValueError("SKILL.md frontmatter closing delimiter not found")
        frontmatter = content[4:end_index]
        body = content[end_index + len(end_marker) :]
        return frontmatter, body

    def _parse_frontmatter_map(self, frontmatter: str) -> dict[str, str]:
        values: dict[str, str] = {}
        for raw_line in frontmatter.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                raise ValueError(f"Invalid frontmatter line '{raw_line}'")
            key, value = line.split(":", 1)
            normalized_key = key.strip()
            normalized_value = value.strip().strip('"').strip("'")
            if not normalized_key:
                raise ValueError(f"Invalid frontmatter key in line '{raw_line}'")
            values[normalized_key] = normalized_value
        return values
