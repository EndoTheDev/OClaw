import pytest
from pathlib import Path

from core.skills import SkillsManager, SkillMetadata


class TestSkillsManager:
    """Tests for the SkillsManager class."""

    def test_autoload_finds_all_skill_directories_with_SKILL_md(
        self, skills_manager: SkillsManager, tmp_path: Path
    ) -> None:
        """Verify autoload discovers all directories containing SKILL.md files."""
        skill_a = tmp_path / "skills" / "alpha"
        skill_a.mkdir(parents=True)
        (skill_a / "SKILL.md").write_text(
            "---\nname: Alpha\ndescription: First skill\n---\nBody A"
        )

        skill_b = tmp_path / "skills" / "beta"
        skill_b.mkdir(parents=True)
        (skill_b / "SKILL.md").write_text(
            "---\nname: Beta\ndescription: Second skill\n---\nBody B"
        )

        skill_c = tmp_path / "skills" / "gamma"
        skill_c.mkdir(parents=True)
        (skill_c / "SKILL.md").write_text(
            "---\nname: Gamma\ndescription: Third skill\n---\nBody C"
        )

        skills_manager.autoload()

        assert skills_manager.has_skill("alpha")
        assert skills_manager.has_skill("beta")
        assert skills_manager.has_skill("gamma")
        assert len(skills_manager.list_metadata()) == 3

    def test_autoload_skips_directories_without_SKILL_md(
        self, skills_manager: SkillsManager, tmp_path: Path
    ) -> None:
        """Verify autoload ignores directories that lack SKILL.md files."""
        with_skill = tmp_path / "skills" / "valid"
        with_skill.mkdir(parents=True)
        (with_skill / "SKILL.md").write_text(
            "---\nname: Valid\ndescription: Has skill file\n---\nContent"
        )

        without_skill = tmp_path / "skills" / "invalid"
        without_skill.mkdir(parents=True)
        (without_skill / "README.md").write_text("No skill file here")

        skills_manager.autoload()

        assert skills_manager.has_skill("valid")
        assert not skills_manager.has_skill("invalid")
        assert len(skills_manager.list_metadata()) == 1

    def test_autoload_parses_name_from_frontmatter(
        self, skills_manager: SkillsManager, tmp_path: Path
    ) -> None:
        """Verify autoload correctly extracts the name field from YAML frontmatter."""
        skill_dir = tmp_path / "skills" / "test_skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: Custom Skill Name\ndescription: Test\n---\nBody"
        )

        skills_manager.autoload()

        metadata = skills_manager.get_metadata("test_skill")
        assert metadata.name == "Custom Skill Name"

    def test_autoload_parses_description_from_frontmatter(
        self, skills_manager: SkillsManager, tmp_path: Path
    ) -> None:
        """Verify autoload correctly extracts the description field from YAML frontmatter."""
        skill_dir = tmp_path / "skills" / "desc_test"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: Test\ndescription: A detailed description here\n---\nBody"
        )

        skills_manager.autoload()

        metadata = skills_manager.get_metadata("desc_test")
        assert metadata.description == "A detailed description here"

    def test_autoload_caches_body_content(
        self, skills_manager: SkillsManager, tmp_path: Path
    ) -> None:
        """Verify autoload initializes empty body cache that gets populated on get_body calls."""
        skill_dir = tmp_path / "skills" / "cache_test"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: Cache\ndescription: Testing\n---\nCached body content"
        )

        skills_manager.autoload()

        assert skills_manager.has_skill("cache_test")
        assert "cache_test" not in skills_manager._body_cache

        body = skills_manager.get_body("cache_test")
        assert body == "Cached body content"
        assert "cache_test" in skills_manager._body_cache

    def test_list_metadata_returns_skills_sorted_by_id(
        self, skills_manager: SkillsManager, tmp_path: Path
    ) -> None:
        """Verify list_metadata returns skills in alphabetical order by skill_id."""
        for skill_id in ["zebra", "alpha", "mike", "bravo"]:
            skill_dir = tmp_path / "skills" / skill_id
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                f"---\nname: {skill_id.title()}\ndescription: Desc\n---\nBody"
            )

        skills_manager.autoload()

        metadata_list = skills_manager.list_metadata()
        skill_ids = [m.skill_id for m in metadata_list]
        assert skill_ids == ["alpha", "bravo", "mike", "zebra"]

    def test_has_skill_returns_true_for_existing_skill(
        self, skills_manager: SkillsManager, tmp_path: Path
    ) -> None:
        """Verify has_skill returns True for a skill that exists in the registry."""
        skill_dir = tmp_path / "skills" / "existing"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: Existing\ndescription: Present\n---\nBody"
        )

        skills_manager.autoload()

        assert skills_manager.has_skill("existing") is True

    def test_has_skill_returns_false_for_unknown_skill(
        self, skills_manager: SkillsManager, tmp_path: Path
    ) -> None:
        """Verify has_skill returns False for a skill ID not in the registry."""
        skill_dir = tmp_path / "skills" / "real"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: Real\ndescription: Real skill\n---\nBody"
        )

        skills_manager.autoload()

        assert skills_manager.has_skill("fake") is False
        assert skills_manager.has_skill("nonexistent") is False

    def test_get_metadata_returns_correct_skill_metadata(
        self, skills_manager: SkillsManager, tmp_path: Path
    ) -> None:
        """Verify get_metadata returns the correct SkillMetadata for a valid skill_id."""
        skill_dir = tmp_path / "skills" / "meta_test"
        skill_dir.mkdir(parents=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(
            "---\nname: Metadata Test\ndescription: Metadata description\n---\nBody"
        )

        skills_manager.autoload()

        metadata = skills_manager.get_metadata("meta_test")
        assert metadata.skill_id == "meta_test"
        assert metadata.name == "Metadata Test"
        assert metadata.description == "Metadata description"
        assert metadata.file_path == skill_file

    def test_get_metadata_raises_value_error_for_unknown_skill(
        self, skills_manager: SkillsManager, tmp_path: Path
    ) -> None:
        """Verify get_metadata raises ValueError when requesting an unknown skill_id."""
        skill_dir = tmp_path / "skills" / "known"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: Known\ndescription: Known skill\n---\nBody"
        )

        skills_manager.autoload()

        with pytest.raises(ValueError, match="Unknown skill 'unknown'"):
            skills_manager.get_metadata("unknown")

    def test_get_body_returns_cached_content_on_second_call(
        self, skills_manager: SkillsManager, tmp_path: Path
    ) -> None:
        """Verify get_body returns the same cached content on subsequent calls."""
        skill_dir = tmp_path / "skills" / "cached"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: Cached\ndescription: Cache test\n---\nCached body"
        )

        skills_manager.autoload()

        first_call = skills_manager.get_body("cached")
        second_call = skills_manager.get_body("cached")

        assert first_call == second_call
        assert first_call == "Cached body"

    def test_get_body_raises_when_SKILL_md_body_is_empty(
        self, skills_manager: SkillsManager, tmp_path: Path
    ) -> None:
        """Verify get_body raises ValueError when the SKILL.md body is empty or whitespace only."""
        skill_dir = tmp_path / "skills" / "empty_body"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: Empty\ndescription: Empty body test\n---\n   \n"
        )

        skills_manager.autoload()

        with pytest.raises(
            ValueError, match="Skill 'empty_body' has empty SKILL.md body"
        ):
            skills_manager.get_body("empty_body")

    def test_build_system_prompt_includes_base_prompt(
        self, skills_manager: SkillsManager, tmp_path: Path
    ) -> None:
        """Verify build_system_prompt includes the base_prompt text in the output."""
        skill_dir = tmp_path / "skills" / "prompt_test"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: Prompt\ndescription: Prompt skill\n---\nBody"
        )

        skills_manager.autoload()

        base = "You are a helpful assistant."
        result = skills_manager.build_system_prompt(base, [])

        assert "You are a helpful assistant." in result

    def test_build_system_prompt_includes_available_skills_list(
        self, skills_manager: SkillsManager, tmp_path: Path
    ) -> None:
        """Verify build_system_prompt includes the Available skills section with skill descriptions."""
        skill_dir = tmp_path / "skills" / "listed"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: Listed\ndescription: This skill is listed\n---\nBody"
        )

        skills_manager.autoload()

        result = skills_manager.build_system_prompt("", [])

        assert "Available skills:" in result
        assert "- listed: This skill is listed" in result

    def test_build_system_prompt_includes_active_skills_bodies(
        self, skills_manager: SkillsManager, tmp_path: Path
    ) -> None:
        """Verify build_system_prompt includes active skills wrapped in <active_skill> tags with their bodies."""
        skill_dir = tmp_path / "skills" / "active"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: Active Skill\ndescription: Active description\n---\nActive body content"
        )

        skills_manager.autoload()

        result = skills_manager.build_system_prompt("", ["active"])

        assert '<active_skill id="active" name="Active Skill">' in result
        assert "Active body content" in result
        assert "</active_skill>" in result

    def test_build_system_prompt_handles_empty_base_prompt(
        self, skills_manager: SkillsManager, tmp_path: Path
    ) -> None:
        """Verify build_system_prompt handles empty or whitespace-only base_prompt gracefully."""
        skill_dir = tmp_path / "skills" / "empty_base"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: EmptyBase\ndescription: Test\n---\nBody"
        )

        skills_manager.autoload()

        result_empty = skills_manager.build_system_prompt("", ["empty_base"])
        result_whitespace = skills_manager.build_system_prompt("   ", ["empty_base"])

        assert "Available skills:" in result_empty
        assert "Active skills:" in result_empty
        assert result_empty == result_whitespace

    def test_build_system_prompt_handles_empty_active_skills(
        self, skills_manager: SkillsManager, tmp_path: Path
    ) -> None:
        """Verify build_system_prompt handles empty active_skills list without errors."""
        skill_dir = tmp_path / "skills" / "no_active"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: NoActive\ndescription: No active skill\n---\nBody"
        )

        skills_manager.autoload()

        result = skills_manager.build_system_prompt("Base prompt here", [])

        assert "Base prompt here" in result
        assert "Available skills:" in result
        assert "Active skills:" not in result
