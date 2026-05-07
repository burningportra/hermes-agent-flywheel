"""Task lifecycle updates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .state import StateStore
from .task_graph import update_task_fields


def update_task(
    cwd: str | Path | None = None,
    task_id: str = "",
    status: str | None = None,
    notes: str | None = None,
    blocker: str | None = None,
) -> dict[str, Any]:
    store = StateStore.for_cwd(cwd)
    state = store.load()
    graph = state.setdefault("task_graph", {"tasks": []})
    task = update_task_fields(graph, task_id, status=status, notes=notes, blocker=blocker)
    store.save(state)
    return {"task": task, "task_graph": graph}
