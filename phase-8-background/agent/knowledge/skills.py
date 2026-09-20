"""SkillLoader — two-layer knowledge injection.

Layer 1: Skill names + descriptions injected into the system prompt (~100 tokens each).
Layer 2: Full skill body loaded on demand via the load_skill tool (~2000 tokens).

Skills live in skills/<name>/SKILL.md with YAML frontmatter:
    ---
    name: code-review
    description: Review code for quality, bugs, and best practices.
    ---
    (full skill body here)

Two sources are scanned (project entries override bundled by name):
- BUNDLED: <repo-root>/skills — always loads regardless of CWD
- PROJECT: <cwd>/skills       — per-project skills when used from another repo
"""

import os
from pathlib import Path

BUNDLED_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"
PROJECT_SKILLS_DIR = Path(os.getcwd()) / "skills"

LOAD_SKILL_SCHEMA = {
    "name": "load_skill",
    "description": (
        "Load the full body of a specific skill into context. "
        "Only call this right before you need the detailed instructions to do "
        "a task the skill covers. Do NOT call this to answer questions like "
        "'what skills are available' — the skill names and summaries are "
        "already in the system prompt; just list them from there."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "skill_name": {
                "type": "string",
                "description": "Name of the skill to load.",
            },
        },
        "required": ["skill_name"],
    },
}


class SkillLoader:
    def __init__(self, skills_dirs: list[Path] | None = None):
        if skills_dirs is None:
            skills_dirs = [BUNDLED_SKILLS_DIR]
            if PROJECT_SKILLS_DIR.resolve() != BUNDLED_SKILLS_DIR.resolve():
                skills_dirs.append(PROJECT_SKILLS_DIR)
        self._skills_dirs = skills_dirs
        self._skills: dict[str, dict] = {}  # name -> {description, body, path}
        for d in skills_dirs:
            self._scan(d)

    def _scan(self, skills_dir: Path):
        """Scan a skills directory for SKILL.md files. Later scans override by name."""
        if not skills_dir.exists():
            return

        for skill_dir in skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue

            content = skill_file.read_text(encoding="utf-8")
            meta, body = self._parse_frontmatter(content)
            name = meta.get("name", skill_dir.name)
            self._skills[name] = {
                "description": meta.get("description", "No description"),
                "body": body.strip(),
                "path": str(skill_file),
            }

    def _parse_frontmatter(self, content: str) -> tuple[dict, str]:
        """Parse YAML frontmatter from a markdown file.

        Simple parser — no PyYAML dependency needed.
        """
        if not content.startswith("---"):
            return {}, content

        parts = content.split("---", 2)
        if len(parts) < 3:
            return {}, content

        meta = {}
        for line in parts[1].strip().splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                meta[key.strip()] = value.strip()

        return meta, parts[2]

    def get_system_prompt_section(self) -> str:
        """Layer 1: Return skill summaries for the system prompt."""
        if not self._skills:
            return ""

        count = len(self._skills)
        lines = [f"\nAvailable skills ({count} total) — you already know their names and summaries:"]
        for i, (name, info) in enumerate(sorted(self._skills.items()), 1):
            lines.append(f"  {i}. {name}: {info['description']}")
        lines.append(
            f"When asked 'what skills are available' or similar, list ALL {count} "
            "names above — do not omit any. Call load_skill ONLY when you need "
            "the full instructions for a specific skill to do a task."
        )
        return "\n".join(lines)

    def load(self, skill_name: str) -> str:
        """Layer 2: Return the full skill body."""
        skill = self._skills.get(skill_name)
        if not skill:
            available = ", ".join(sorted(self._skills.keys()))
            return f"Error: Skill '{skill_name}' not found. Available: {available}"
        return f"# Skill: {skill_name}\n\n{skill['body']}"

    @property
    def skill_names(self) -> list[str]:
        return sorted(self._skills.keys())
