"""Read-only external wave export contract."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .errors import FlywheelError
from .state import FLYWHEEL_VERSION, StateStore, utc_now

EXPORT_CONTRACT_VERSION = "0.9"
ALLOWED_FORMATS = {"json", "markdown"}
EXPORTABLE_WAVE_STATUSES = {"ready", "started"}


def _task_index(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    tasks = state.get("task_graph", {}).get("tasks", [])
    if not isinstance(tasks, list):
        return {}
    return {str(task.get("id")): task for task in tasks if isinstance(task, dict) and task.get("id") is not None}


def _select_wave(state: dict[str, Any], wave_id: str | None) -> dict[str, Any]:
    waves = state.get("waves", [])
    if not isinstance(waves, list):
        waves = []

    if wave_id:
        for wave in waves:
            if isinstance(wave, dict) and str(wave.get("id")) == str(wave_id):
                if wave.get("status") not in EXPORTABLE_WAVE_STATUSES:
                    raise FlywheelError(
                        "wave_not_exportable",
                        "Explicit wave_id must reference a ready or started wave.",
                        {"wave_id": wave_id, "status": wave.get("status")},
                    )
                if not wave.get("task_ids"):
                    raise FlywheelError(
                        "wave_empty",
                        "Explicit wave_id references a wave with no task ids.",
                        {"wave_id": wave_id},
                    )
                return wave
        raise FlywheelError("wave_not_found", "Explicit wave_id does not exist.", {"wave_id": wave_id})

    for wave in reversed(waves):
        if not isinstance(wave, dict):
            continue
        if wave.get("status") in EXPORTABLE_WAVE_STATUSES and wave.get("task_ids"):
            return wave
    raise FlywheelError(
        "wave_not_found",
        "No ready or started wave with task ids is available to export.",
        {"statuses": sorted(EXPORTABLE_WAVE_STATUSES)},
    )


def _dependency_context(task: dict[str, Any], tasks_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    context = []
    for dep_id in task.get("depends_on", []) or []:
        dep_key = str(dep_id)
        dep = tasks_by_id.get(dep_key)
        if dep is None:
            context.append({"id": dep_key, "missing": True})
            continue
        context.append(
            {
                "id": dep_key,
                "title": dep.get("title", ""),
                "description": dep.get("description", ""),
                "status": dep.get("status", ""),
                "notes": dep.get("notes", ""),
                "blocker": dep.get("blocker", ""),
            }
        )
    return context


def build_wave_export(
    cwd: str | Path | None = None,
    wave_id: str | None = None,
    include_evidence_contract: bool = True,
) -> dict[str, Any]:
    """Build a read-only export payload for an external executor."""

    root = Path(cwd or Path.cwd()).resolve()
    state = StateStore.for_cwd(root).load()
    wave = _select_wave(state, wave_id)
    tasks_by_id = _task_index(state)
    task_ids = [str(task_id) for task_id in wave.get("task_ids", [])]
    missing_task_ids = [task_id for task_id in task_ids if task_id not in tasks_by_id]
    tasks = []
    for task_id in task_ids:
        task = tasks_by_id.get(task_id)
        if task is None:
            tasks.append({"id": task_id, "missing": True, "dependency_context": []})
            continue
        tasks.append(
            {
                "id": task.get("id"),
                "title": task.get("title", ""),
                "description": task.get("description", ""),
                "status": task.get("status", ""),
                "depends_on": [str(dep) for dep in task.get("depends_on", []) or []],
                "notes": task.get("notes", ""),
                "blocker": task.get("blocker", ""),
                "dependency_context": _dependency_context(task, tasks_by_id),
            }
        )

    export: dict[str, Any] = {
        "contract": "hermes-agent-flywheel.external_wave_export",
        "contract_version": EXPORT_CONTRACT_VERSION,
        "flywheel_version": FLYWHEEL_VERSION,
        "exported_at": utc_now(),
        "project_root": str(root),
        "wave": {
            "id": wave.get("id"),
            "status": wave.get("status"),
            "created_at": wave.get("created_at"),
            "task_ids": task_ids,
        },
        "tasks": tasks,
        "missing_task_ids": missing_task_ids,
        "verification_instructions": [
            "Do not mark tasks complete without making the requested code/doc/test changes.",
            "Run the tests, checks, or manual verification steps relevant to each task.",
            "Return a completion report per task with changed files, commands run, outcomes, and any blockers.",
            "If a task cannot be completed, report it as blocked or failed; do not fabricate success evidence.",
        ],
        "external_executor_constraints": [
            "This export is an external execution contract only; it does not create workers, assignments, or handoffs in flywheel state.",
            "External execution is responsible for its own process management outside this plugin.",
            "The export tool is read-only unless output_path is explicitly provided.",
        ],
    }
    if include_evidence_contract:
        export["evidence_contract"] = {
            "required_completion_report_fields": [
                "task_id",
                "outcome",
                "summary",
                "changed_files",
                "verification",
                "self_review",
                "reservations_released",
            ],
            "successful_outcome": "success",
            "completion_evidence_rule": "A task is complete only when its status is done and its latest completion report outcome is success.",
            "no_fabrication": "Do not claim tests, files, or evidence that were not actually produced.",
        }
    return export


def render_wave_export(export: dict[str, Any], fmt: str) -> str:
    fmt = str(fmt or "json").lower()
    if fmt not in ALLOWED_FORMATS:
        raise FlywheelError("export_invalid_format", "format must be 'json' or 'markdown'.", {"format": fmt})
    if fmt == "json":
        return json.dumps(export, indent=2, sort_keys=True) + "\n"

    lines = [
        f"# Hermes Flywheel External Wave Export: {export['wave']['id']}",
        "",
        f"Contract: {export['contract']} v{export['contract_version']}",
        f"Flywheel version: {export['flywheel_version']}",
        f"Project root: {export['project_root']}",
        f"Wave status: {export['wave']['status']}",
        f"Exported at: {export['exported_at']}",
        "",
        "## Tasks",
    ]
    for task in export.get("tasks", []):
        lines.extend(
            [
                "",
                f"### {task.get('id')} - {task.get('title', '')}",
                f"Status: {task.get('status', '')}",
                f"Depends on: {', '.join(task.get('depends_on', [])) or 'none'}",
                "",
                task.get("description", "") or "No description provided.",
            ]
        )
        if task.get("notes"):
            lines.extend(["", f"Notes: {task['notes']}"])
        if task.get("blocker"):
            lines.extend(["", f"Blocker: {task['blocker']}"])
        context = task.get("dependency_context", [])
        if context:
            lines.extend(["", "Dependency context:"])
            for dep in context:
                if dep.get("missing"):
                    lines.append(f"- {dep.get('id')}: missing from task graph")
                else:
                    lines.append(f"- {dep.get('id')} ({dep.get('status')}): {dep.get('title')}")
    if export.get("evidence_contract"):
        evidence = export["evidence_contract"]
        lines.extend(
            [
                "",
                "## Evidence contract",
                f"- Successful outcome: {evidence['successful_outcome']}",
                f"- Completion evidence rule: {evidence['completion_evidence_rule']}",
                f"- No fabrication: {evidence['no_fabrication']}",
                "- Required completion report fields: " + ", ".join(evidence["required_completion_report_fields"]),
            ]
        )
    lines.extend(["", "## Verification instructions"])
    lines.extend(f"- {item}" for item in export.get("verification_instructions", []))
    lines.extend(["", "## External executor constraints"])
    lines.extend(f"- {item}" for item in export.get("external_executor_constraints", []))
    return "\n".join(lines).rstrip() + "\n"


def _resolve_output_path(root: Path, output_path: str | Path) -> Path:
    raw = Path(output_path)
    candidate = raw if raw.is_absolute() else root / raw
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise FlywheelError(
            "export_path_outside_root",
            "output_path must resolve inside the project root.",
            {"project_root": str(root), "output_path": str(output_path), "resolved_path": str(resolved)},
        )
    return resolved


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    finally:
        tmp = Path(tmp_name)
        if tmp.exists():
            tmp.unlink()


def export_wave(
    cwd: str | Path | None = None,
    wave_id: str | None = None,
    fmt: str = "json",
    output_path: str | Path | None = None,
    include_evidence_contract: bool = True,
) -> dict[str, Any]:
    root = Path(cwd or Path.cwd()).resolve()
    export = build_wave_export(root, wave_id, include_evidence_contract)
    content = render_wave_export(export, fmt)
    result: dict[str, Any] = {
        "export": export,
        "format": str(fmt or "json").lower(),
        "content": content,
        "wrote": False,
        "output_path": None,
    }
    if output_path:
        destination = _resolve_output_path(root, output_path)
        _atomic_write_text(destination, content)
        result["wrote"] = True
        result["output_path"] = str(destination)
    return result
