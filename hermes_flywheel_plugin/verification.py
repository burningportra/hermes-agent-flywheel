"""Read-only task verification contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .completion_report import safe_report_filename
from .state import StateStore


def _latest_report_by_task(state: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    latest = None
    for report in state.get("completion_reports", []):
        if str(report.get("task_id")) == task_id:
            latest = report
    return latest


def _active_started_wave_task_ids(state: dict[str, Any]) -> list[str]:
    for wave in state.get("waves", []):
        if wave.get("status") == "started":
            return [str(task_id) for task_id in wave.get("task_ids", [])]
    return []


def _completion_path(store: StateStore, task_id: str) -> Path:
    return store.state_dir / "completion" / f"{safe_report_filename(task_id)}.json"


def verify_tasks(
    cwd: str | Path | None = None,
    task_ids: list[str] | tuple[str, ...] | None = None,
    require_evidence: bool = True,
) -> dict[str, Any]:
    """Verify task completion against state and completion-report files.

    This function is read-only: it loads state and report files but never writes.
    If task_ids is omitted, it verifies the first active started wave.
    """
    store = StateStore.for_cwd(cwd)
    state = store.load()
    requested = [str(task_id) for task_id in (task_ids if task_ids is not None else _active_started_wave_task_ids(state))]
    tasks = {str(task.get("id")): task for task in state.get("task_graph", {}).get("tasks", [])}

    verified: list[str] = []
    not_done: list[str] = []
    missing_evidence: list[str] = []
    invalid_evidence: list[str] = []
    unknown: list[str] = []

    for task_id in requested:
        task = tasks.get(task_id)
        if task is None:
            unknown.append(task_id)
            continue
        latest = _latest_report_by_task(state, task_id)
        if task.get("status") != "done" or latest is None or latest.get("outcome") != "success":
            not_done.append(task_id)
            continue
        if require_evidence:
            path = _completion_path(store, task_id)
            if not path.exists():
                missing_evidence.append(task_id)
                continue
            try:
                with path.open("r", encoding="utf-8") as fh:
                    on_disk = json.load(fh)
            except (OSError, json.JSONDecodeError):
                invalid_evidence.append(task_id)
                continue
            if on_disk != latest:
                invalid_evidence.append(task_id)
                continue
        verified.append(task_id)

    ok = not (not_done or missing_evidence or invalid_evidence or unknown)
    return {
        "ok": ok,
        "verified": verified,
        "not_done": not_done,
        "missing_evidence": missing_evidence,
        "invalid_evidence": invalid_evidence,
        "unknown": unknown,
        "task_ids": requested,
    }
