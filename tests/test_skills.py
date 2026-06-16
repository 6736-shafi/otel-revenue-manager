"""
Skill Tests - Phase 2
≥5 skill test cases.
"""
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

SKILLS_DIR = Path(__file__).parent.parent / "skills"

REQUIRED_SKILLS = [
    "otb-health",
    "segment-analysis",
    "pickup-analysis",
    "group-analysis",
    "cancellation-risk",
    "room-type-mix",
    "challenge-skill",
]


class TestSkillFiles:
    """Tests for skill file existence and structure."""

    def test_all_required_skills_exist(self):
        """All 6+ required skill subdirectories must have a SKILL.md."""
        for skill in REQUIRED_SKILLS:
            path = SKILLS_DIR / skill / "SKILL.md"
            assert path.exists(), f"Missing skill: {skill}/SKILL.md"

    def test_challenge_skill_has_correct_version(self):
        """challenge-skill/SKILL.md must have version otel-rm-v2."""
        content = (SKILLS_DIR / "challenge-skill" / "SKILL.md").read_text()
        assert "otel-rm-v2" in content, "challenge-skill/SKILL.md must contain 'otel-rm-v2'"

    def test_skills_have_frontmatter(self):
        """All skills must have YAML frontmatter."""
        for skill_file in SKILLS_DIR.rglob("SKILL.md"):
            content = skill_file.read_text()
            assert content.startswith("---"), f"{skill_file.parent.name}/SKILL.md missing frontmatter"

    def test_judgment_skills_have_thresholds(self):
        """At least 3 skills must encode numeric judgment thresholds."""
        skills_with_thresholds = []
        for skill_file in SKILLS_DIR.rglob("SKILL.md"):
            content = skill_file.read_text()
            has_threshold = any(indicator in content for indicator in [
                "%", "≥", "≤", ">", "<", "£", "threshold", "Threshold"
            ])
            if has_threshold:
                skills_with_thresholds.append(skill_file.parent.name)
        assert len(skills_with_thresholds) >= 3, \
            f"Only {len(skills_with_thresholds)} skills have thresholds, need ≥3"

    def test_skills_reference_correct_tools(self):
        """Skills must reference the 5 required tools by name."""
        all_skill_content = "".join(f.read_text() for f in SKILLS_DIR.rglob("SKILL.md"))
        required_tool_refs = [
            "get_otb_summary",
            "get_segment_mix",
            "get_pickup_delta",
            "get_as_of_otb",
            "get_block_vs_transient_mix",
        ]
        for tool_ref in required_tool_refs:
            assert tool_ref in all_skill_content, f"No skill references tool: {tool_ref}"

    def test_hitl_skill_warns_about_approval(self):
        """cancellation-risk skill must warn about get_as_of_otb approval."""
        content = (SKILLS_DIR / "cancellation-risk" / "SKILL.md").read_text()
        assert any(keyword in content.lower() for keyword in [
            "approval", "human", "approve", "hitl", "gate"
        ]), "Cancellation skill must mention HITL approval for get_as_of_otb"

    def test_segment_skill_covers_ota_dependency(self):
        """Segment analysis skill must cover OTA dependency risk."""
        content = (SKILLS_DIR / "segment-analysis" / "SKILL.md").read_text()
        assert "OTA" in content or "ota" in content.lower()
        assert "50%" in content or "dependency" in content.lower()

    def test_group_skill_covers_concentration_risk(self):
        """Group analysis skill must cover company concentration risk."""
        content = (SKILLS_DIR / "group-analysis" / "SKILL.md").read_text()
        assert "concentration" in content.lower() or "company" in content.lower()
