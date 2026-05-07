"""Read-only flywheel status summary for external supervisors."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .state import StateStore, utc_now
from .verification import verify_tasks


def _tasks_by_status(tasks: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"pending": 0, "ready": 0, "in_progress": 0, "blocked": 0, "done": 0, "other": 0}
    for task in tasks:
        status = str(task.get("status") or "other")
        counts[status if status in counts else "other"] += 1
    return counts


def _waves_by_status(waves: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for wave in waves:
        status = str(wave.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _oldest_incomplete_started_wave(root: Path, waves: list[dict[str, Any]]) -> dict[str, Any] | None:
    for wave in waves:
        if wave.get("status") != "started":
            continue
        task_ids = [str(task_id) for task_id in wave.get("task_ids", [])]
        verification = verify_tasks(cwd=root, task_ids=task_ids)
        incomplete = [task_id for task_id in verification["task_ids"] if task_id not in verification["verified"]]
        if incomplete:
            return {
                "wave_id": wave.get("id"),
                "task_ids": task_ids,
                "incomplete_task_ids": incomplete,
                "verification": verification,
                "reason": "started wave has tasks without done status and matching latest success completion evidence",
            }
    return None


def _latest_exportable_wave(waves: list[dict[str, Any]]) -> dict[str, Any] | None:
    for wave in reversed(waves):
        if wave.get("status") in {"ready", "started"} and wave.get("task_ids"):
            return {
                "wave_id": wave.get("id"),
                "status": wave.get("status"),
                "task_ids": [str(task_id) for task_id in wave.get("task_ids", [])],
            }
    return None


def _ready_task_ids(tasks: list[dict[str, Any]]) -> list[str]:
    done = {str(task.get("id")) for task in tasks if task.get("status") == "done"}
    ready: list[str] = []
    for task in tasks:
        if task.get("status") not in {"pending", "ready"}:
            continue
        if all(str(dep) in done for dep in task.get("depends_on", [])):
            ready.append(str(task.get("id")))
    return ready


def flywheel_status(cwd: str | Path | None = None) -> dict[str, Any]:
    """Return a read-only status summary suitable for external orchestration.

    This function deliberately does not create directories, save state, spawn processes,
    call networks, mutate git, or mark tasks complete. It only reads existing local
    flywheel state plus completion evidence files used by verification.
    """

    root = Path(cwd or Path.cwd()).resolve()
    store = StateStore.for_cwd(root)
    state_path_exists = store.state_path.exists()
    state = store.load()
    tasks = list(state.get("task_graph", {}).get("tasks", []))
    waves = list(state.get("waves", []))
    blocked_wave = _oldest_incomplete_started_wave(root, waves)
    ready_task_ids = _ready_task_ids(tasks)
    exportable = _latest_exportable_wave(waves)
    checkpoint_validation = store.validate_checkpoint()

    if not state_path_exists:
        next_action = "observe_or_create_tasks"
        next_tool = "hermes_flywheel_observe"
    elif not tasks:
        next_action = "plan_or_create_tasks"
        next_tool = "hermes_flywheel_plan"
    elif blocked_wave:
        next_action = "external_execution_or_review_started_wave"
        next_tool = "hermes_flywheel_export_wave" if exportable else "hermes_flywheel_review"
    elif ready_task_ids:
        next_action = "advance_next_wave"
        next_tool = "hermes_flywheel_advance_wave"
    elif any(task.get("status") != "done" for task in tasks):
        next_action = "resolve_blocked_or_pending_tasks"
        next_tool = "hermes_flywheel_update_task"
    elif not checkpoint_validation.get("current"):
        next_action = "write_current_checkpoint"
        next_tool = "hermes_flywheel_checkpoint"
    else:
        next_action = "verify_or_checkpoint_complete_work"
        next_tool = "hermes_flywheel_verify_tasks"

    return {
        "root": str(root),
        "generated_at": utc_now(),
        "state": {
            "exists": state_path_exists,
            "path": str(store.state_path),
            "created_at": state.get("created_at"),
            "updated_at": state.get("updated_at"),
        },
        "counts": {
            "observations": len(state.get("observations", [])),
            "profiles": len(state.get("profiles", [])),
            "plans": len(state.get("plans", [])),
            "tasks": len(tasks),
            "waves": len(waves),
            "completion_reports": len(state.get("completion_reports", [])),
            "checkpoints": len(state.get("checkpoints", [])),
        },
        "tasks_by_status": _tasks_by_status(tasks),
        "waves_by_status": _waves_by_status(waves),
        "ready_task_ids": ready_task_ids,
        "blocked_wave": blocked_wave,
        "exportable_wave": exportable,
        "checkpoint": checkpoint_validation,
        "next_action": next_action,
        "next_tool": next_tool,
        "integration_contract": {
            "local_state_dir": ".hermes-flywheel",
            "hidden_runtime": False,
            "external_execution_tool": "hermes_flywheel_export_wave",
            "completion_report_tool": "hermes_flywheel_review",
            "verification_tool": "hermes_flywheel_verify_tasks",
        },
    }
