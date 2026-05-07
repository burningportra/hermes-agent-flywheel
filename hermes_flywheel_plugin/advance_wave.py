"""Advance the next flywheel wave."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .state import StateStore, utc_now
from .task_graph import mark_tasks, ready_tasks


def advance_wave(cwd: str | Path | None = None, limit: int = 3, start: bool = True) -> dict[str, Any]:
    root = Path(cwd or Path.cwd()).resolve()
    store = StateStore.for_cwd(root)
    state = store.load()
    graph = state.setdefault("task_graph", {"tasks": []})
    selected = ready_tasks(graph, limit=max(1, int(limit)))
    selected_ids = [task["id"] for task in selected]
    if start and selected_ids:
        mark_tasks(graph, selected_ids, "in_progress")
    wave = {
        "id": f"wave-{len(state.get('waves', [])) + 1}",
        "created_at": utc_now(),
        "task_ids": selected_ids,
        "status": "started" if start and selected_ids else "ready" if selected_ids else "empty",
    }
    state.setdefault("waves", []).append(wave)
    store.save(state)
    return {"wave": wave, "tasks": selected}
