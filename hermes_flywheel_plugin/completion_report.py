"""Completion reports."""

from __future__ import annotations

import json
import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any

from .errors import FlywheelError
from .state import StateStore, utc_now
from .task_graph import mark_tasks

VALID_OUTCOMES = {"success", "partial", "blocked", "failed"}


def _list_field(report: dict[str, Any], field: str, task_id: str) -> list[str]:
    value = report.get(field, []) or []
    if not isinstance(value, list):
        raise FlywheelError(f"report_invalid_{field}", f"{field} must be a list.", {"task_id": task_id})
    return [str(item) for item in value]


def validate_completion_report(report: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(report, dict):
        raise FlywheelError("report_invalid", "Completion report must be an object.", {})
    task_id = str(report.get("task_id") or "").strip()
    if not task_id:
        raise FlywheelError("report_missing_task_id", "Completion report requires task_id.", {})
    outcome = str(report.get("outcome") or "").strip().lower()
    if outcome not in VALID_OUTCOMES:
        raise FlywheelError("report_invalid_outcome", "Completion report outcome is invalid.", {"valid": sorted(VALID_OUTCOMES)})
    summary = str(report.get("summary") or "").strip()
    if not summary:
        raise FlywheelError("report_missing_summary", "Completion report requires summary.", {"task_id": task_id})

    validated: dict[str, Any] = {
        "task_id": task_id,
        "outcome": outcome,
        "summary": summary,
        "changed_files": _list_field(report, "changed_files", task_id),
        "verification": _list_field(report, "verification", task_id),
        "artifacts": _list_field(report, "artifacts", task_id),
        "created_at": report.get("created_at") or utc_now(),
    }
    if "self_review" in report:
        validated["self_review"] = str(report.get("self_review") or "")
    if "reservations_released" in report:
        validated["reservations_released"] = bool(report.get("reservations_released"))
    if "notes" in report:
        validated["notes"] = str(report.get("notes") or "")
    return validated


def safe_report_filename(task_id: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in task_id).strip(".-")
    prefix = (safe or "task")[:64].rstrip(".-") or "task"
    digest = hashlib.sha256(task_id.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def write_completion_report(store: StateStore, report: dict[str, Any]) -> Path:
    completion_dir = store.state_dir / "completion"
    completion_dir.mkdir(parents=True, exist_ok=True)
    path = completion_dir / f"{safe_report_filename(report['task_id'])}.json"
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix="completion-", suffix=".json", dir=completion_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    finally:
        tmp = Path(tmp_name)
        if tmp.exists():
            tmp.unlink()
    return path


def latest_success_report_by_task(state: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    latest = None
    for report in state.get("completion_reports", []):
        if report.get("task_id") == task_id:
            latest = report
    if latest and latest.get("outcome") == "success":
        return latest
    return None


def record_completion_report(report: dict[str, Any], cwd: str | Path | None = None) -> dict[str, Any]:
    validated = validate_completion_report(report)
    store = StateStore.for_cwd(cwd)
    state = store.load()
    state.setdefault("completion_reports", []).append(validated)
    graph = state.setdefault("task_graph", {"tasks": []})
    new_status = "done" if validated["outcome"] == "success" else "blocked" if validated["outcome"] == "blocked" else "in_progress"
    task_ids = [task.get("id") for task in graph.get("tasks", [])]
    if validated["task_id"] in task_ids:
        mark_tasks(graph, [validated["task_id"]], new_status)
    store.save(state)
    write_completion_report(store, validated)
    return validated
