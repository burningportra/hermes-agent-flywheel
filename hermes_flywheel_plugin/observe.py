"""Observation tool implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .advance_wave import incomplete_started_wave
from .profile import build_repo_profile
from .state import StateStore, utc_now


def observe(cwd: str | Path | None = None, note: str = "") -> dict[str, Any]:
    root = Path(cwd or Path.cwd()).resolve()
    profile = build_repo_profile(root, persist=False)
    store = StateStore.for_cwd(root)
    state = store.load()
    blocker = incomplete_started_wave(state)
    observation = {
        "root": str(root),
        "created_at": utc_now(),
        "note": note,
        "profile": profile,
        "state_exists": (root / ".hermes-flywheel" / "state.json").exists(),
        "blocked_wave": blocker,
    }
    state.setdefault("observations", []).append(observation)
    store.save(state)
    return observation
