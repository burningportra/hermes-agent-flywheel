"""Task graph primitives."""

from __future__ import annotations

from typing import Any

from .errors import FlywheelError
from .state import utc_now

VALID_STATUSES = {"pending", "ready", "in_progress", "blocked", "done"}
TERMINAL_STATUSES = {"done"}


def normalize_task(raw: dict[str, Any], index: int = 0) -> dict[str, Any]:
    title = str(raw.get("title") or raw.get("name") or "").strip()
    if not title:
        raise FlywheelError("task_missing_title", "Each task requires a non-empty title.", {"task": raw})
    task_id = str(raw.get("id") or f"task-{index + 1}").strip()
    depends_on = raw.get("depends_on", []) or []
    if not isinstance(depends_on, list):
        raise FlywheelError("task_invalid_dependencies", "depends_on must be a list.", {"task_id": task_id})
    status = str(raw.get("status") or "pending")
    if status not in VALID_STATUSES:
        raise FlywheelError("task_invalid_status", "Task status is not valid.", {"task_id": task_id, "status": status})
    task = {
        "id": task_id,
        "title": title,
        "description": str(raw.get("description") or ""),
        "depends_on": [str(item) for item in depends_on],
        "status": status,
        "created_at": raw.get("created_at") or utc_now(),
        "updated_at": raw.get("updated_at") or utc_now(),
    }
    for field in ("notes", "blocker"):
        if field in raw:
            task[field] = str(raw.get(field) or "")
    return task


def create_task_graph(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = [normalize_task(task, idx) for idx, task in enumerate(tasks)]
    ids = [task["id"] for task in normalized]
    if len(ids) != len(set(ids)):
        raise FlywheelError("task_duplicate_id", "Task ids must be unique.", {"ids": ids})
    missing = sorted({dep for task in normalized for dep in task["depends_on"] if dep not in ids})
    if missing:
        raise FlywheelError("task_missing_dependency", "Task dependencies must reference existing tasks.", {"missing": missing})
    return {"tasks": normalized}


def ready_tasks(graph: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    tasks = graph.get("tasks", [])
    done = {task["id"] for task in tasks if task.get("status") in TERMINAL_STATUSES}
    ready = []
    for task in tasks:
        if task.get("status") not in {"pending", "ready"}:
            continue
        if all(dep in done for dep in task.get("depends_on", [])):
            task["status"] = "ready"
            task["updated_at"] = utc_now()
            ready.append(task)
        if len(ready) >= limit:
            break
    return ready


def mark_tasks(graph: dict[str, Any], task_ids: list[str], status: str) -> dict[str, Any]:
    if status not in VALID_STATUSES:
        raise FlywheelError("task_invalid_status", "Task status is not valid.", {"status": status})
    known = {task["id"]: task for task in graph.get("tasks", [])}
    missing = [task_id for task_id in task_ids if task_id not in known]
    if missing:
        raise FlywheelError("task_unknown_id", "Cannot update unknown task ids.", {"missing": missing})
    for task_id in task_ids:
        known[task_id]["status"] = status
        known[task_id]["updated_at"] = utc_now()
    return graph


def update_task_fields(
    graph: dict[str, Any],
    task_id: str,
    status: str | None = None,
    notes: str | None = None,
    blocker: str | None = None,
) -> dict[str, Any]:
    task_id = str(task_id or "").strip()
    if not task_id:
        raise FlywheelError("task_missing_id", "Task update requires task_id.", {})
    known = {task["id"]: task for task in graph.get("tasks", [])}
    if task_id not in known:
        raise FlywheelError("task_unknown_id", "Cannot update unknown task id.", {"task_id": task_id})
    task = known[task_id]
    if status is not None:
        status = str(status).strip()
        if status not in VALID_STATUSES:
            raise FlywheelError("task_invalid_status", "Task status is not valid.", {"task_id": task_id, "status": status})
        task["status"] = status
    if notes is not None:
        task["notes"] = str(notes)
    if blocker is not None:
        task["blocker"] = str(blocker)
    task["updated_at"] = utc_now()
    return task
