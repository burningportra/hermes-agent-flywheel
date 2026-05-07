"""Local repository profile."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .state import StateStore, utc_now

LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".rs": "rust",
    ".go": "go",
    ".md": "markdown",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
}

IGNORE_DIRS = {".git", ".hermes-flywheel", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache"}


def _iter_files(root: Path):
    for path in root.rglob("*"):
        if any(part in IGNORE_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_file():
            yield path


def build_repo_profile(cwd: str | Path | None = None, persist: bool = True) -> dict[str, Any]:
    root = Path(cwd or Path.cwd()).resolve()
    files = list(_iter_files(root)) if root.exists() else []
    languages: dict[str, int] = {}
    for path in files:
        lang = LANGUAGE_BY_SUFFIX.get(path.suffix.lower())
        if lang:
            languages[lang] = languages.get(lang, 0) + 1
    markers = [name for name in ("pyproject.toml", "package.json", "Cargo.toml", "go.mod", "README.md") if (root / name).exists()]
    profile = {
        "root": str(root),
        "created_at": utc_now(),
        "file_count": len(files),
        "languages": dict(sorted(languages.items())),
        "markers": markers,
        "has_git": (root / ".git").exists(),
        "state_dir": str(root / ".hermes-flywheel"),
    }
    if persist:
        store = StateStore.for_cwd(root)
        state = store.load()
        state.setdefault("profiles", []).append(profile)
        store.save(state)
    return profile
