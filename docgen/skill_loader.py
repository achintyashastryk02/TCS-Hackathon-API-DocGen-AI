"""Loads the 'documentation' skill (SKILL.md + sections.yaml + references/)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

SKILL_DIR = Path(__file__).resolve().parent.parent / "skills" / "documentation"


@dataclass
class Skill:
    name: str
    description: str
    instructions: str
    sections: list[dict]
    references: dict[str, str]

    @property
    def prompt(self) -> str:
        lines = [f"# SKILL: {self.name}", self.instructions, "", "## Required sections (exact titles, exact order)"]
        for i, s in enumerate(self.sections, 1):
            ev = "Evidence line required" if s.get("evidence", True) else "no Evidence line needed"
            lines.append(f"{i}. ## {i}. {s['title']}  [{ev}]\n   Purpose: {s['guidance']}")
        for fname, text in self.references.items():
            lines.append(f"\n## Reference: {fname}\n{text.strip()}")
        return "\n".join(lines)


def load_skill(skill_dir: Path = SKILL_DIR) -> Skill:
    raw = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.S)
    if not m:
        raise ValueError("SKILL.md must start with YAML frontmatter (name, description).")
    meta = yaml.safe_load(m.group(1)) or {}
    sections = yaml.safe_load((skill_dir / "sections.yaml").read_text(encoding="utf-8"))["sections"]
    refs = {p.name: p.read_text(encoding="utf-8") for p in sorted((skill_dir / "references").glob("*.md"))}
    return Skill(meta.get("name", "documentation"), meta.get("description", ""), m.group(2).strip(), sections, refs)
