"""Advance the next flywheel wave."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .completion_report import latest_success_report_by_task
from .errors import FlywheelError
from .state import StateStore, utc_now
from .task_graph import mark_tasks, ready_tasks


def _task_index(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(task.get("id")): task for task in graph.get("tasks", [])}


def incomplete_started_wave(state: dict[str, Any]) -> dict[str, Any] | None:
    """Return blocker details for the oldest started wave that lacks success evidence."""
    graph = state.setdefault("task_graph", {"tasks": []})
    tasks = _task_index(graph)
    for wave in state.get("waves", []):
        if wave.get("status") != "started":
            continue
        incomplete = []
        for task_id in wave.get("task_ids", []):
            task = tasks.get(str(task_id), {})
            if task.get("status") != "done" or latest_success_report_by_task(state, str(task_id)) is None:
                incomplete.append(str(task_id))
        if incomplete:
            return {
                "wave_id": wave.get("id"),
                "task_ids": [str(task_id) for task_id in wave.get("task_ids", [])],
                "incomplete_task_ids": incomplete,
                "reason": "started wave has tasks without done status and latest success completion reports",
            }
        wave["status"] = "completed"
        wave["completed_at"] = wave.get("completed_at") or utc_now()
    return None


def advance_wave(
    cwd: str | Path | None = None,
    limit: int = 3,
    start: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    root = Path(cwd or Path.cwd()).resolve()
    store = StateStore.for_cwd(root)
    state = store.load()
    graph = state.setdefault("task_graph", {"tasks": []})
    blocker = incomplete_started_wave(state)
    if blocker and not force:
        raise FlywheelError(
            "wave_blocked_incomplete",
            "Cannot advance a new wave until the active started wave has successful completion evidence.",
            blocker,
        )

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
    if force and blocker:
        wave["forced"] = True
        wave["forced_past"] = blocker
    state.setdefault("waves", []).append(wave)
    store.save(state)
    return {"wave": wave, "tasks": selected}
