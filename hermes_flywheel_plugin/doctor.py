"""Doctor checks and remediation recommendations."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from .advance_wave import incomplete_started_wave
from .state import StateStore
from .worker_runtime import worker_summary

DOCTOR_SCHEMA_VERSION = 2

REMEDIATION_DEFINITIONS: dict[str, dict[str, Any]] = {
    "ensure_state_dir": {
        "id": "ensure_state_dir",
        "action": "ensure_directory",
        "path": ".hermes-flywheel",
        "safe": True,
        "category": "filesystem",
        "description": "Create the local flywheel state directory.",
    },
    "ensure_completion_report_dir": {
        "id": "ensure_completion_report_dir",
        "action": "ensure_directory",
        "path": ".hermes-flywheel/completion",
        "safe": True,
        "category": "filesystem",
        "description": "Create the local completion report directory.",
    },
    "ensure_checkpoints_dir": {
        "id": "ensure_checkpoints_dir",
        "action": "ensure_directory",
        "path": ".hermes-flywheel/checkpoints",
        "safe": True,
        "category": "filesystem",
        "description": "Create the local checkpoint history directory.",
    },
    "write_missing_checkpoint": {
        "id": "write_missing_checkpoint",
        "action": "write_checkpoint",
        "safe": True,
        "category": "checkpoint",
        "description": "Write the missing canonical checkpoint from current local state.",
    },
    "refresh_stale_checkpoint": {
        "id": "refresh_stale_checkpoint",
        "action": "refresh_checkpoint",
        "safe": True,
        "category": "checkpoint",
        "description": "Refresh the canonical checkpoint so it matches current local state.",
    },
    "rewrite_invalid_checkpoint": {
        "id": "rewrite_invalid_checkpoint",
        "action": "rewrite_checkpoint",
        "safe": True,
        "category": "checkpoint",
        "description": "Rewrite an invalid canonical checkpoint from current local state.",
    },
    "resolve_incomplete_started_wave": {
        "id": "resolve_incomplete_started_wave",
        "action": "operator_action",
        "safe": False,
        "category": "workflow",
        "description": "Operator must finish, block, or explicitly override the incomplete started wave.",
    },
    "resolve_stale_worker": {
        "id": "resolve_stale_worker",
        "action": "operator_action",
        "safe": False,
        "category": "worker",
        "description": "Operator must heartbeat, stop, fail, or complete stale no-op workers.",
    },
}


def _remediation(remediation_id: str, **extra: Any) -> dict[str, Any]:
    remediation = dict(REMEDIATION_DEFINITIONS[remediation_id])
    remediation.update(extra)
    return remediation


def _add_remediation(remediations: list[dict[str, Any]], remediation_id: str, **extra: Any) -> None:
    if any(item["id"] == remediation_id for item in remediations):
        return
    remediations.append(_remediation(remediation_id, **extra))


def _check(
    checks: list[dict[str, Any]],
    name: str,
    ok: bool,
    detail: str,
    *,
    severity: str = "info",
    category: str = "environment",
    data: dict[str, Any] | None = None,
    remediations: list[str] | None = None,
) -> None:
    check: dict[str, Any] = {
        "name": name,
        "ok": ok,
        "severity": "info" if ok else severity,
        "category": category,
        "detail": detail,
    }
    if data is not None:
        check["data"] = data
    if remediations:
        check["remediations"] = remediations
    checks.append(check)


def run_doctor(cwd: str | Path | None = None) -> dict[str, Any]:
    root = Path(cwd or Path.cwd()).resolve()
    store = StateStore.for_cwd(root)
    checks: list[dict[str, Any]] = []
    remediations: list[dict[str, Any]] = []

    _check(checks, "python_version", sys.version_info >= (3, 10), sys.version.split()[0], severity="error", category="environment")
    _check(checks, "root_exists", root.exists(), str(root), severity="error", category="filesystem")
    _check(checks, "root_writable", root.exists() and os_access_write(root), str(root), severity="error", category="filesystem")

    state_dir_ok = store.state_dir.exists() and store.state_dir.is_dir()
    if not state_dir_ok:
        _add_remediation(remediations, "ensure_state_dir", target=str(store.state_dir))
    _check(
        checks,
        "state_dir",
        state_dir_ok,
        str(store.state_dir),
        severity="warning",
        category="filesystem",
        remediations=[] if state_dir_ok else ["ensure_state_dir"],
    )

    state_load_ok = False
    try:
        state = store.load()
        state_load_ok = True
        _check(checks, "state_load", True, f"version={state.get('version')}", category="state")
        blocker = incomplete_started_wave(state, root)
        if blocker:
            _add_remediation(remediations, "resolve_incomplete_started_wave", data=blocker)
            _check(
                checks,
                "active_wave_complete",
                False,
                f"{blocker['wave_id']} incomplete tasks: {', '.join(blocker['incomplete_task_ids'])}",
                severity="warning",
                category="workflow",
                data=blocker,
                remediations=["resolve_incomplete_started_wave"],
            )
        else:
            _check(checks, "active_wave_complete", True, "no incomplete started wave", category="workflow")

        workers = state.get("workers", [])
        worker_events = state.get("worker_events", [])
        worker_shape_ok = isinstance(workers, list) and isinstance(worker_events, list)
        _check(
            checks,
            "worker_state_shape",
            worker_shape_ok,
            "workers and worker_events are lists" if worker_shape_ok else "workers and worker_events must be lists",
            severity="error",
            category="worker",
        )
        if worker_shape_ok:
            summary = worker_summary(state)
            stale = summary.get("stale", [])
            if stale:
                _add_remediation(remediations, "resolve_stale_worker", data={"worker_ids": stale})
                _check(
                    checks,
                    "active_workers",
                    False,
                    f"stale workers: {', '.join(stale)}",
                    severity="warning",
                    category="worker",
                    data=summary,
                    remediations=["resolve_stale_worker"],
                )
            else:
                _check(checks, "active_workers", True, f"active={len(summary.get('active', []))}", category="worker", data=summary)
    except Exception as exc:  # noqa: BLE001 - doctor should report failures as data
        _check(checks, "state_load", False, str(exc), severity="error", category="state")

    checkpoint = store.validate_checkpoint()
    checkpoint_remediation = None
    if checkpoint.get("reason") == "missing":
        checkpoint_remediation = "write_missing_checkpoint" if state_load_ok else None
        if checkpoint_remediation:
            _add_remediation(remediations, checkpoint_remediation, target=str(store.checkpoint_path))
        _check(
            checks,
            "checkpoint_valid",
            False,
            "missing canonical checkpoint",
            severity="warning",
            category="checkpoint",
            data=checkpoint,
            remediations=[] if checkpoint_remediation is None else [checkpoint_remediation],
        )
    elif checkpoint.get("ok"):
        current = bool(checkpoint.get("current"))
        if not current and state_load_ok:
            checkpoint_remediation = "refresh_stale_checkpoint"
            _add_remediation(remediations, checkpoint_remediation, target=str(store.checkpoint_path))
        _check(
            checks,
            "checkpoint_valid",
            current,
            "current" if current else "valid but not current",
            severity="warning",
            category="checkpoint",
            data=checkpoint,
            remediations=[] if checkpoint_remediation is None else [checkpoint_remediation],
        )
    else:
        checkpoint_remediation = "rewrite_invalid_checkpoint" if state_load_ok else None
        if checkpoint_remediation:
            _add_remediation(remediations, checkpoint_remediation, target=str(store.checkpoint_path))
        _check(
            checks,
            "checkpoint_valid",
            False,
            str(checkpoint.get("reason") or "invalid checkpoint"),
            severity="error",
            category="checkpoint",
            data=checkpoint,
            remediations=[] if checkpoint_remediation is None else [checkpoint_remediation],
        )

    completion_dir = store.state_dir / "completion"
    completion_ok = completion_dir.exists() and completion_dir.is_dir()
    if not completion_ok:
        _add_remediation(remediations, "ensure_completion_report_dir", target=str(completion_dir))
    _check(
        checks,
        "completion_report_dir",
        completion_ok,
        str(completion_dir),
        severity="warning",
        category="filesystem",
        remediations=[] if completion_ok else ["ensure_completion_report_dir"],
    )

    checkpoints_ok = store.checkpoints_dir.exists() and store.checkpoints_dir.is_dir()
    if not checkpoints_ok:
        _add_remediation(remediations, "ensure_checkpoints_dir", target=str(store.checkpoints_dir))
    _check(
        checks,
        "checkpoints_dir",
        checkpoints_ok,
        str(store.checkpoints_dir),
        severity="warning",
        category="filesystem",
        remediations=[] if checkpoints_ok else ["ensure_checkpoints_dir"],
    )

    return {
        "schemaVersion": DOCTOR_SCHEMA_VERSION,
        "ok": all(check["ok"] for check in checks),
        "root": str(root),
        "checks": checks,
        "remediations": remediations,
    }


def os_access_write(path: Path) -> bool:
    return os.access(path, os.W_OK)
