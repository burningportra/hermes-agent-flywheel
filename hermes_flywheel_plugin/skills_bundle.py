"""Skill text loader."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from .errors import FlywheelError

VALID_SKILLS = {"start", "planning", "review"}


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _packaged_skill(skill: str) -> tuple[str, str] | None:
    try:
        candidate = resources.files(__package__).joinpath("skills", skill, "SKILL.md")
    except (AttributeError, ModuleNotFoundError, TypeError):
        return None
    try:
        if candidate.is_file():
            return str(candidate), candidate.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    return None


def get_skill(name: str) -> dict[str, str]:
    skill = str(name or "").strip().lower()
    if skill not in VALID_SKILLS:
        raise FlywheelError("skill_unknown", "Unknown skill requested.", {"requested": name, "valid": sorted(VALID_SKILLS)})
    packaged = _packaged_skill(skill)
    if packaged is not None:
        path, content = packaged
        return {"name": skill, "path": path, "content": content}

    path = repo_root() / "skills" / skill / "SKILL.md"
    if not path.exists():
        raise FlywheelError("skill_missing", "Skill file is missing.", {"path": str(path)})
    return {"name": skill, "path": str(path), "content": path.read_text(encoding="utf-8")}
