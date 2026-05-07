"""State-backed no-op worker runtime substrate.

v0.5 deliberately records worker lifecycle only. It does not spawn processes,
agents, tmux panes, NTM sessions, network calls, or background jobs.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .errors import FlywheelError
from .state import StateStore, utc_now

WORKER_STATUSES = {"created", "running", "idle", "completed", "failed", "stopped"}
ACTIVE_WORKER_STATUSES = {"created", "running", "idle"}
TERMINAL_WORKER_STATUSES = {"completed", "failed", "stopped"}
WORKER_ACTIONS = {"start", "heartbeat", "idle", "complete", "fail", "stop"}
WORKER_RUNTIMES = {"noop"}
EVENT_KIND_BY_ACTION = {
    "start": "worker_started",
    "heartbeat": "worker_heartbeat",
    "idle": "worker_idled",
    "complete": "worker_completed",
    "fail": "worker_failed",
    "stop": "worker_stopped",
}
STALE_AFTER = timedelta(minutes=30)


def _task_exists(state: dict[str, Any], task_id: str) -> bool:
    return any(str(task.get("id")) == task_id for task in state.get("task_graph", {}).get("tasks", []))


def _wave_exists(state: dict[str, Any], wave_id: str) -> bool:
    return any(str(wave.get("id")) == wave_id for wave in state.get("waves", []))


def _next_id(items: list[dict[str, Any]], prefix: str) -> str:
    return f"{prefix}-{len(items) + 1}"


def _worker_index(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(worker.get("id")): worker for worker in state.get("workers", [])}


def _append_event(
    state: dict[str, Any],
    worker: dict[str, Any],
    kind: str,
    message: str = "",
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    events = state.setdefault("worker_events", [])
    event = {
        "id": _next_id(events, "worker-event"),
        "worker_id": worker["id"],
        "kind": kind,
        "created_at": utc_now(),
        "task_id": worker.get("task_id", ""),
        "wave_id": worker.get("wave_id", ""),
        "message": str(message or ""),
        "data": data or {},
    }
    events.append(event)
    return event


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def create_worker(
    cwd: str | Path | None = None,
    task_id: str | None = None,
    wave_id: str | None = None,
    name: str = "",
    runtime: str = "noop",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    runtime = str(runtime or "noop")
    if runtime not in WORKER_RUNTIMES:
        raise FlywheelError("worker_runtime_unsupported", "Only the no-op worker runtime is supported in v0.5.", {"runtime": runtime})
    if metadata is not None and not isinstance(metadata, dict):
        raise FlywheelError("worker_invalid_metadata", "Worker metadata must be an object.", {})

    store = StateStore.for_cwd(cwd)
    state = store.load()
    task = str(task_id or "").strip()
    wave = str(wave_id or "").strip()
    if task and not _task_exists(state, task):
        raise FlywheelError("worker_unknown_task", "Worker task_id must reference an existing task.", {"task_id": task})
    if wave and not _wave_exists(state, wave):
        raise FlywheelError("worker_unknown_wave", "Worker wave_id must reference an existing wave.", {"wave_id": wave})

    workers = state.setdefault("workers", [])
    worker = {
        "id": _next_id(workers, "worker"),
        "name": str(name or ""),
        "runtime": runtime,
        "status": "created",
        "task_id": task,
        "wave_id": wave,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "message": "",
        "metadata": metadata or {},
    }
    workers.append(worker)
    event = _append_event(state, worker, "worker_created", data={"runtime": runtime})
    store.save(state)
    return {"worker": worker, "event": event}


def update_worker(
    cwd: str | Path | None = None,
    worker_id: str = "",
    action: str = "",
    message: str | None = None,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    worker_id = str(worker_id or "").strip()
    action = str(action or "").strip().lower()
    if not worker_id:
        raise FlywheelError("worker_missing_id", "Worker update requires worker_id.", {})
    if action not in WORKER_ACTIONS:
        raise FlywheelError("worker_invalid_action", "Worker action is not valid.", {"action": action, "valid": sorted(WORKER_ACTIONS)})
    if data is not None and not isinstance(data, dict):
        raise FlywheelError("worker_invalid_event_data", "Worker event data must be an object.", {"worker_id": worker_id})

    store = StateStore.for_cwd(cwd)
    state = store.load()
    workers = _worker_index(state)
    worker = workers.get(worker_id)
    if worker is None:
        raise FlywheelError("worker_unknown_id", "Cannot update unknown worker id.", {"worker_id": worker_id})
    if worker.get("status") in TERMINAL_WORKER_STATUSES:
        raise FlywheelError("worker_terminal", "Terminal workers cannot be mutated.", {"worker_id": worker_id, "status": worker.get("status")})

    now = utc_now()
    if action == "start":
        worker["status"] = "running"
        worker["started_at"] = worker.get("started_at") or now
    elif action == "heartbeat":
        worker["status"] = "running"
        worker["heartbeat_at"] = now
    elif action == "idle":
        worker["status"] = "idle"
    elif action == "complete":
        worker["status"] = "completed"
        worker["completed_at"] = now
    elif action == "fail":
        worker["status"] = "failed"
        worker["failed_at"] = now
    elif action == "stop":
        worker["status"] = "stopped"
        worker["stopped_at"] = now

    worker["updated_at"] = now
    if message is not None:
        worker["message"] = str(message)
    event = _append_event(state, worker, EVENT_KIND_BY_ACTION[action], str(message or ""), data or {})
    store.save(state)
    return {"worker": worker, "event": event}


def worker_summary(state: dict[str, Any], *, stale_after: timedelta = STALE_AFTER) -> dict[str, Any]:
    workers = state.get("workers", [])
    by_status = dict(Counter(str(worker.get("status", "unknown")) for worker in workers))
    active = [str(worker.get("id")) for worker in workers if worker.get("status") in ACTIVE_WORKER_STATUSES]
    stale: list[str] = []
    now = datetime.now(timezone.utc)
    for worker in workers:
        if worker.get("status") not in ACTIVE_WORKER_STATUSES:
            continue
        observed = _parse_iso(str(worker.get("heartbeat_at") or worker.get("started_at") or worker.get("created_at") or ""))
        if observed is None or now - observed > stale_after:
            stale.append(str(worker.get("id")))
    return {
        "total": len(workers),
        "by_status": by_status,
        "active": active,
        "stale": stale,
        "recent_events": state.get("worker_events", [])[-10:],
    }


def list_workers(
    cwd: str | Path | None = None,
    status: str | None = None,
    task_id: str | None = None,
    wave_id: str | None = None,
) -> dict[str, Any]:
    store = StateStore.for_cwd(cwd)
    state = store.load()
    status_filter = str(status or "").strip()
    if status_filter and status_filter not in WORKER_STATUSES:
        raise FlywheelError("worker_invalid_status", "Worker status filter is not valid.", {"status": status_filter, "valid": sorted(WORKER_STATUSES)})
    task_filter = str(task_id or "").strip()
    wave_filter = str(wave_id or "").strip()
    workers = list(state.get("workers", []))
    if status_filter:
        workers = [worker for worker in workers if worker.get("status") == status_filter]
    if task_filter:
        workers = [worker for worker in workers if worker.get("task_id") == task_filter]
    if wave_filter:
        workers = [worker for worker in workers if worker.get("wave_id") == wave_filter]
    return {"workers": workers, "summary": worker_summary(state), "events": state.get("worker_events", [])[-20:]}
