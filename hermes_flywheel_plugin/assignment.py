"""Wave-to-worker assignment substrate.

v0.6 bridges selected flywheel waves to state-backed no-op worker records. It
only mutates local JSON state under .hermes-flywheel and never spawns agents,
processes, panes, sessions, network calls, or background jobs.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .errors import FlywheelError
from .state import StateStore, utc_now
from .worker_runtime import ACTIVE_WORKER_STATUSES, _append_event, _next_id

ASSIGNMENT_SCHEMA_VERSION = 1
ASSIGNMENT_ELIGIBLE_WAVE_STATUSES = {"ready", "started"}
ASSIGNMENT_ELIGIBLE_TASK_STATUSES = {"ready", "in_progress"}
ASSIGNMENT_EVENT_KINDS = {"assignment_created", "assignment_reused", "assignment_skipped"}


def _ensure_assignable_wave(wave: dict[str, Any], wave_id: str) -> dict[str, Any]:
    status = str(wave.get("status", ""))
    if status not in ASSIGNMENT_ELIGIBLE_WAVE_STATUSES:
        raise FlywheelError(
            "assignment_wave_not_assignable",
            "Assignment wave must be ready or started.",
            {"wave_id": wave_id, "status": status, "valid": sorted(ASSIGNMENT_ELIGIBLE_WAVE_STATUSES)},
        )
    return wave


def _task_index(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(task.get("id")): task for task in state.get("task_graph", {}).get("tasks", [])}


def _wave_index(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(wave.get("id")): wave for wave in state.get("waves", [])}


def _worker_index(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(worker.get("id")): worker for worker in state.get("workers", [])}


def _next_assignable_wave(state: dict[str, Any], wave_id: str = "") -> dict[str, Any]:
    wave_id = str(wave_id or "").strip()
    waves = state.get("waves", [])
    if wave_id:
        wave = _wave_index(state).get(wave_id)
        if wave is None:
            raise FlywheelError("assignment_unknown_wave", "Assignment wave_id must reference an existing wave.", {"wave_id": wave_id})
        return _ensure_assignable_wave(wave, wave_id)
    for wave in reversed(waves):
        if wave.get("task_ids") and wave.get("status") in ASSIGNMENT_ELIGIBLE_WAVE_STATUSES:
            return wave
    raise FlywheelError("assignment_no_wave", "No assignable ready or started wave exists.", {})


def _active_worker_for_task(state: dict[str, Any], task_id: str, wave_id: str, runtime: str) -> dict[str, Any] | None:
    for worker in state.get("workers", []):
        if worker.get("task_id") != task_id:
            continue
        if worker.get("wave_id") != wave_id:
            continue
        if worker.get("runtime") != runtime:
            continue
        if worker.get("status") in ACTIVE_WORKER_STATUSES:
            return worker
    return None


def _existing_assignment(state: dict[str, Any], task_id: str, wave_id: str, worker_id: str) -> dict[str, Any] | None:
    for assignment in state.get("assignments", []):
        if assignment.get("task_id") == task_id and assignment.get("wave_id") == wave_id and assignment.get("worker_id") == worker_id:
            return assignment
    return None


def _append_assignment_event(
    state: dict[str, Any],
    kind: str,
    assignment: dict[str, Any] | None,
    *,
    task_id: str,
    wave_id: str,
    worker_id: str = "",
    message: str = "",
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if kind not in ASSIGNMENT_EVENT_KINDS:
        raise FlywheelError("assignment_invalid_event", "Assignment event kind is not valid.", {"kind": kind})
    events = state.setdefault("assignment_events", [])
    event = {
        "id": _next_id(events, "assignment-event"),
        "kind": kind,
        "created_at": utc_now(),
        "assignment_id": "" if assignment is None else str(assignment.get("id", "")),
        "worker_id": worker_id,
        "task_id": task_id,
        "wave_id": wave_id,
        "message": str(message or ""),
        "data": data or {},
    }
    events.append(event)
    return event


def _create_noop_worker_in_state(state: dict[str, Any], task_id: str, wave_id: str, name: str, metadata: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    workers = state.setdefault("workers", [])
    now = utc_now()
    worker = {
        "id": _next_id(workers, "worker"),
        "name": name,
        "runtime": "noop",
        "status": "created",
        "task_id": task_id,
        "wave_id": wave_id,
        "created_at": now,
        "updated_at": now,
        "message": "",
        "metadata": metadata,
    }
    workers.append(worker)
    event = _append_event(state, worker, "worker_created", data={"runtime": "noop", "source": "assign_wave"})
    return worker, event


def assign_wave(
    cwd: str | Path | None = None,
    wave_id: str = "",
    runtime: str = "noop",
    worker_name_prefix: str = "noop",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create or reuse no-op worker records for assignable tasks in a wave."""

    runtime = str(runtime or "noop")
    if runtime != "noop":
        raise FlywheelError("assignment_runtime_unsupported", "Only the no-op worker runtime is supported for wave assignment in v0.6.", {"runtime": runtime})
    if metadata is not None and not isinstance(metadata, dict):
        raise FlywheelError("assignment_invalid_metadata", "Assignment metadata must be an object.", {})

    root = Path(cwd or Path.cwd()).resolve()
    store = StateStore.for_cwd(root)
    state = store.load()
    wave = _next_assignable_wave(state, wave_id)
    task_ids = [str(task_id) for task_id in wave.get("task_ids", [])]
    if not task_ids:
        raise FlywheelError("assignment_empty_wave", "Cannot assign an empty wave.", {"wave_id": wave.get("id")})

    tasks = _task_index(state)
    missing = [task_id for task_id in task_ids if task_id not in tasks]
    if missing:
        raise FlywheelError("assignment_unknown_task", "Wave references unknown task ids.", {"wave_id": wave.get("id"), "missing": missing})

    assignments = state.setdefault("assignments", [])
    state.setdefault("assignment_events", [])
    results: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    worker_events: list[dict[str, Any]] = []
    now = utc_now()
    wave_id_value = str(wave.get("id"))

    for task_id in task_ids:
        task = tasks[task_id]
        status = str(task.get("status", ""))
        if status not in ASSIGNMENT_ELIGIBLE_TASK_STATUSES:
            event = _append_assignment_event(
                state,
                "assignment_skipped",
                None,
                task_id=task_id,
                wave_id=wave_id_value,
                message=f"task status {status!r} is not assignable",
                data={"task_status": status},
            )
            events.append(event)
            results.append({"task_id": task_id, "status": "skipped", "reason": "task_not_assignable", "event": event})
            continue

        worker = _active_worker_for_task(state, task_id, wave_id_value, runtime)
        action = "reused"
        if worker is None:
            worker_metadata = {"assignment": {"wave_id": wave_id_value, "task_id": task_id}, **(metadata or {})}
            worker, worker_event = _create_noop_worker_in_state(
                state,
                task_id,
                wave_id_value,
                f"{worker_name_prefix}-{task_id}" if worker_name_prefix else task_id,
                worker_metadata,
            )
            worker_events.append(worker_event)
            action = "created"

        assignment = _existing_assignment(state, task_id, wave_id_value, str(worker["id"]))
        if assignment is None:
            assignment = {
                "id": _next_id(assignments, "assignment"),
                "schemaVersion": ASSIGNMENT_SCHEMA_VERSION,
                "created_at": now,
                "updated_at": now,
                "status": "assigned",
                "task_id": task_id,
                "wave_id": wave_id_value,
                "worker_id": worker["id"],
                "runtime": runtime,
                "metadata": metadata or {},
            }
            assignments.append(assignment)
            event_kind = "assignment_created"
        else:
            assignment["updated_at"] = now
            event_kind = "assignment_reused"

        event = _append_assignment_event(
            state,
            event_kind,
            assignment,
            task_id=task_id,
            wave_id=wave_id_value,
            worker_id=str(worker["id"]),
            message=f"{action} no-op worker assignment",
            data={"worker_status": worker.get("status"), "worker_action": action},
        )
        events.append(event)
        results.append({"task_id": task_id, "status": action, "assignment": assignment, "worker": worker, "event": event})

    wave["assigned_at"] = wave.get("assigned_at") or now
    wave["assignment_status"] = "assigned" if any(result["status"] in {"created", "reused"} for result in results) else "none"
    store.save(state)
    return {
        "wave": wave,
        "assignments": [result["assignment"] for result in results if "assignment" in result],
        "workers": [result["worker"] for result in results if "worker" in result],
        "results": results,
        "events": events,
        "worker_events": worker_events,
        "summary": assignment_summary(state),
    }


def assignment_summary(state: dict[str, Any]) -> dict[str, Any]:
    assignments = state.get("assignments", [])
    events = state.get("assignment_events", [])
    by_status = dict(Counter(str(assignment.get("status", "unknown")) for assignment in assignments))
    by_wave = dict(Counter(str(assignment.get("wave_id", "")) for assignment in assignments))
    return {
        "total": len(assignments),
        "by_status": by_status,
        "by_wave": by_wave,
        "recent_events": events[-10:],
    }
