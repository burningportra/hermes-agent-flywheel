"""Safe local remediation for doctor recommendations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .doctor import REMEDIATION_DEFINITIONS, run_doctor
from .state import StateStore

SAFE_CHECKPOINT_ACTIONS = {"write_checkpoint", "refresh_checkpoint", "rewrite_checkpoint"}


def _normalize_action(action: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(action, str):
        definition = REMEDIATION_DEFINITIONS.get(action)
        if definition is None:
            return {"id": action, "action": "unknown", "safe": False}
        return dict(definition)
    if isinstance(action, dict):
        remediation_id = str(action.get("id") or "")
        definition = REMEDIATION_DEFINITIONS.get(remediation_id)
        if definition is None:
            return {"id": remediation_id or str(action.get("action") or "unknown"), "action": "unknown", "safe": False}
        # Execution fields come only from trusted doctor definitions. Caller-provided
        # dictionaries may select a known id, but may not override action/path/safety.
        return dict(definition)
    return {"id": repr(action), "action": "unknown", "safe": False}


def _default_actions(cwd: Path) -> list[dict[str, Any]]:
    doctor = run_doctor(cwd)
    return [dict(action) for action in doctor.get("remediations", [])]


def remediate(
    cwd: str | Path | None = None,
    actions: list[str | dict[str, Any]] | None = None,
    dry_run: bool = True,
    include_unsafe: bool = False,
) -> dict[str, Any]:
    """Plan or apply safe local remediation actions.

    Dry-run is the default and performs no writes. With dry_run=False, only safe local
    directory creation and StateStore.checkpoint based checkpoint rewrites are applied.
    Operator actions are always skipped unless a future implementation explicitly handles
    them; include_unsafe only reports unsafe actions as skipped instead of filtered out.
    """

    root = Path(cwd or Path.cwd()).resolve()
    store = StateStore.for_cwd(root)
    selected = _default_actions(root) if actions is None else [_normalize_action(action) for action in actions]
    results: list[dict[str, Any]] = []

    for selected_action in selected:
        remediation_id = str(selected_action.get("id") or "")
        action = str(selected_action.get("action") or "")
        safe = bool(selected_action.get("safe", False))
        result: dict[str, Any] = {
            "id": remediation_id,
            "action": action or "unknown",
            "dry_run": dry_run,
            "applied": False,
            "skipped": False,
        }

        if remediation_id not in REMEDIATION_DEFINITIONS:
            result.update(
                {
                    "ok": False,
                    "skipped": True,
                    "error": {
                        "code": "unknown_remediation_action",
                        "message": "Unknown remediation action.",
                        "details": {"id": remediation_id, "action": action},
                    },
                }
            )
            results.append(result)
            continue

        if action == "operator_action":
            result.update({"ok": True, "skipped": True, "reason": "operator_action_required"})
            results.append(result)
            continue

        if not safe:
            result.update({"ok": True, "skipped": True, "reason": "unsafe_action_not_implemented"})
            results.append(result)
            continue

        if action == "ensure_directory":
            relative_path = selected_action.get("path")
            if not relative_path:
                result.update(
                    {
                        "ok": False,
                        "skipped": True,
                        "error": {
                            "code": "remediation_missing_path",
                            "message": "ensure_directory remediation requires a path.",
                            "details": {"id": remediation_id},
                        },
                    }
                )
            else:
                target = (root / str(relative_path)).resolve()
                try:
                    target.relative_to(root)
                except ValueError:
                    result.update(
                        {
                            "ok": False,
                            "skipped": True,
                            "path": str(target),
                            "error": {
                                "code": "remediation_path_outside_root",
                                "message": "Remediation paths must stay inside the target project root.",
                                "details": {"id": remediation_id, "path": str(relative_path), "root": str(root)},
                            },
                        }
                    )
                    results.append(result)
                    continue
                result["path"] = str(target)
                if dry_run:
                    result.update({"ok": True, "would_apply": True})
                else:
                    target.mkdir(parents=True, exist_ok=True)
                    result.update({"ok": True, "applied": True})
            results.append(result)
            continue

        if action in SAFE_CHECKPOINT_ACTIONS:
            if dry_run:
                result.update({"ok": True, "would_apply": True, "path": str(store.checkpoint_path)})
            else:
                label = {
                    "write_checkpoint": "remediate-missing-checkpoint",
                    "refresh_checkpoint": "remediate-stale-checkpoint",
                    "rewrite_checkpoint": "remediate-invalid-checkpoint",
                }[action]
                try:
                    checkpoint = store.checkpoint(label)
                except Exception as exc:  # noqa: BLE001 - return structured per-action failure
                    result.update(
                        {
                            "ok": False,
                            "skipped": True,
                            "error": {
                                "code": "remediation_failed",
                                "message": str(exc),
                                "details": {"id": remediation_id, "action": action, "type": exc.__class__.__name__},
                            },
                        }
                    )
                else:
                    result.update({"ok": True, "applied": True, "checkpoint": checkpoint})
            results.append(result)
            continue

        result.update(
            {
                "ok": False,
                "skipped": True,
                "error": {
                    "code": "unknown_remediation_action",
                    "message": "Unknown remediation action.",
                    "details": {"id": remediation_id, "action": action},
                },
            }
        )
        results.append(result)

    return {
        "schemaVersion": 1,
        "root": str(root),
        "dry_run": dry_run,
        "ok": all(item.get("ok") is True for item in results),
        "results": results,
    }
