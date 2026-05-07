"""Completion reports."""

from __future__ import annotations

from typing import Any

from .errors import FlywheelError
from .state import StateStore, utc_now
from .task_graph import mark_tasks

VALID_OUTCOMES = {"success", "partial", "blocked", "failed"}


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
    artifacts = report.get("artifacts", []) or []
    if not isinstance(artifacts, list):
        raise FlywheelError("report_invalid_artifacts", "artifacts must be a list.", {"task_id": task_id})
    return {
        "task_id": task_id,
        "outcome": outcome,
        "summary": summary,
        "artifacts": [str(item) for item in artifacts],
        "notes": str(report.get("notes") or ""),
        "created_at": report.get("created_at") or utc_now(),
    }


def record_completion_report(report: dict[str, Any], cwd: str | None = None) -> dict[str, Any]:
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
    return validated
