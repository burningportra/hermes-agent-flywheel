"""Immutable worker handoff packet creation.

v0.7 materializes existing assignment records into local JSON packet files under
.hermes-flywheel/handoffs. Packets are static instructions/evidence contracts for
human or external worker pickup; this module never spawns or executes workers.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from .errors import FlywheelError
from .state import FLYWHEEL_VERSION, StateStore, canonical_json, utc_now
from .worker_runtime import _next_id

HANDOFF_SCHEMA_VERSION = 1
HANDOFF_DIR_NAME = "handoffs"
HANDOFF_EVENT_KINDS = {"handoff_created", "handoff_reused", "handoff_skipped"}
DEFAULT_CONSTRAINTS = [
    "stdlib-only runtime behavior in plugin code",
    "local-first; state is authoritative under .hermes-flywheel",
    "no subprocess, network, tmux, NTM, or git mutation from plugin code",
    "do not mutate task status from handoff creation",
    "do not fabricate completion evidence",
]
DEFAULT_EVIDENCE_REQUIREMENTS = [
    "Report actual changed files, if any.",
    "Report verification commands actually run and their outcomes.",
    "Completion requires an explicit successful completion report and task lifecycle update outside handoff creation.",
]


def _task_index(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(task.get("id")): task for task in state.get("task_graph", {}).get("tasks", [])}


def _wave_index(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(wave.get("id")): wave for wave in state.get("waves", [])}


def _worker_index(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(worker.get("id")): worker for worker in state.get("workers", [])}


def _assignment_index(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(assignment.get("id")): assignment for assignment in state.get("assignments", [])}


def handoff_identity(assignment: dict[str, Any]) -> str:
    identity = {
        "assignment_id": str(assignment.get("id", "")),
        "task_id": str(assignment.get("task_id", "")),
        "wave_id": str(assignment.get("wave_id", "")),
        "worker_id": str(assignment.get("worker_id", "")),
    }
    return hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest()


def handoff_filename(assignment: dict[str, Any]) -> str:
    assignment_id = _safe_segment(str(assignment.get("id", "assignment")))
    worker_id = _safe_segment(str(assignment.get("worker_id", "worker")))
    digest = handoff_identity(assignment)[:24]
    return f"{assignment_id}--{worker_id}--{digest}.json"


def _safe_segment(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in value).strip("-")
    return safe or "unknown"


def _packet_hash(packet_without_hash: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(packet_without_hash).encode("utf-8")).hexdigest()


def _atomic_create_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        try:
            os.link(tmp_name, path)
        except FileExistsError as exc:
            raise FlywheelError("handoff_exists", "Handoff packet already exists and will not be overwritten.", {"path": str(path)}) from exc
    finally:
        tmp = Path(tmp_name)
        if tmp.exists():
            tmp.unlink()


def _build_packet(
    *,
    root: Path,
    state: dict[str, Any],
    assignment: dict[str, Any],
    task: dict[str, Any],
    wave: dict[str, Any],
    worker: dict[str, Any],
    constraints: list[str],
    evidence_requirements: list[str],
    resume_metadata: dict[str, Any],
    created_at: str,
) -> dict[str, Any]:
    identity = handoff_identity(assignment)
    packet_without_hash: dict[str, Any] = {
        "schemaVersion": HANDOFF_SCHEMA_VERSION,
        "flywheelVersion": FLYWHEEL_VERSION,
        "kind": "hermes_flywheel_worker_handoff",
        "created_at": created_at,
        "root": str(root),
        "handoff_id": f"handoff-{identity[:24]}",
        "assignment_id": str(assignment.get("id", "")),
        "worker_id": str(worker.get("id", assignment.get("worker_id", ""))),
        "task_id": str(task.get("id", assignment.get("task_id", ""))),
        "wave_id": str(wave.get("id", assignment.get("wave_id", ""))),
        "task": task,
        "wave_context": wave,
        "assignment": assignment,
        "worker": worker,
        "constraints": constraints,
        "evidence_requirements": evidence_requirements,
        "resume_metadata": {
            "state_path": str(StateStore.for_cwd(root).state_path),
            "handoffs_dir": str(StateStore.for_cwd(root).state_dir / HANDOFF_DIR_NAME),
            **resume_metadata,
        },
        "state_hash_at_creation": hashlib.sha256(canonical_json(state).encode("utf-8")).hexdigest(),
    }
    return {**packet_without_hash, "packetHash": _packet_hash(packet_without_hash)}


def _existing_handoff_for_assignment(state: dict[str, Any], assignment_id: str) -> dict[str, Any] | None:
    for handoff in state.get("handoffs", []):
        if handoff.get("assignment_id") == assignment_id:
            return handoff
    return None


def _validate_existing_handoff(
    *,
    handoffs_dir: Path,
    existing: dict[str, Any],
    assignment: dict[str, Any],
    task: dict[str, Any],
    wave: dict[str, Any],
    worker: dict[str, Any],
) -> dict[str, Any]:
    raw_path = str(existing.get("path", ""))
    if not raw_path:
        raise FlywheelError("handoff_path_missing", "Existing handoff record is missing path.", {"handoff_id": existing.get("id")})
    path = Path(raw_path).expanduser().resolve()
    expected_dir = handoffs_dir.resolve()
    try:
        path.relative_to(expected_dir)
    except ValueError as exc:
        raise FlywheelError(
            "handoff_path_invalid",
            "Existing handoff path must stay under .hermes-flywheel/handoffs.",
            {"path": str(path), "handoffs_dir": str(expected_dir)},
        ) from exc
    if not path.is_file():
        raise FlywheelError("handoff_file_missing", "Existing handoff packet file is missing.", {"path": str(path)})
    try:
        packet = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FlywheelError("handoff_invalid_json", "Existing handoff packet is not valid JSON.", {"path": str(path)}) from exc
    if not isinstance(packet, dict):
        raise FlywheelError("handoff_invalid_packet", "Existing handoff packet must be a JSON object.", {"path": str(path)})

    packet_hash = str(packet.get("packetHash", ""))
    packet_without_hash = dict(packet)
    packet_without_hash.pop("packetHash", None)
    recomputed = _packet_hash(packet_without_hash)
    expected_hash = str(existing.get("packetHash", ""))
    if not packet_hash or packet_hash != recomputed or expected_hash != recomputed:
        raise FlywheelError(
            "handoff_integrity_mismatch",
            "Existing handoff packet hash does not match packet content and state record.",
            {"path": str(path), "packetHash": packet_hash, "statePacketHash": expected_hash, "recomputed": recomputed},
        )

    expected_identity = {
        "assignment_id": str(assignment.get("id", "")),
        "task_id": str(task.get("id", assignment.get("task_id", ""))),
        "wave_id": str(wave.get("id", assignment.get("wave_id", ""))),
        "worker_id": str(worker.get("id", assignment.get("worker_id", ""))),
    }
    packet_identity = {key: str(packet.get(key, "")) for key in expected_identity}
    if packet_identity != expected_identity:
        raise FlywheelError(
            "handoff_identity_mismatch",
            "Existing handoff packet identity does not match assignment context.",
            {"path": str(path), "expected": expected_identity, "actual": packet_identity},
        )
    if str(existing.get("id", "")) != str(packet.get("handoff_id", "")):
        raise FlywheelError(
            "handoff_identity_mismatch",
            "Existing handoff record id does not match packet handoff_id.",
            {"path": str(path), "state_id": existing.get("id"), "packet_id": packet.get("handoff_id")},
        )
    return packet


def _append_handoff_event(
    state: dict[str, Any],
    kind: str,
    *,
    assignment_id: str,
    worker_id: str = "",
    task_id: str = "",
    wave_id: str = "",
    handoff: dict[str, Any] | None = None,
    message: str = "",
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if kind not in HANDOFF_EVENT_KINDS:
        raise FlywheelError("handoff_invalid_event", "Handoff event kind is not valid.", {"kind": kind})
    events = state.setdefault("handoff_events", [])
    event = {
        "id": _next_id(events, "handoff-event"),
        "kind": kind,
        "created_at": utc_now(),
        "handoff_id": "" if handoff is None else str(handoff.get("id", "")),
        "assignment_id": assignment_id,
        "worker_id": worker_id,
        "task_id": task_id,
        "wave_id": wave_id,
        "message": str(message or ""),
        "data": data or {},
    }
    events.append(event)
    return event


def _selected_assignments(state: dict[str, Any], assignment_ids: list[str] | None, wave_id: str) -> list[dict[str, Any]]:
    assignments = state.get("assignments", [])
    if assignment_ids:
        index = _assignment_index(state)
        missing = [assignment_id for assignment_id in assignment_ids if assignment_id not in index]
        if missing:
            raise FlywheelError("handoff_unknown_assignment", "Handoff assignment_ids must reference existing assignments.", {"missing": missing})
        return [index[assignment_id] for assignment_id in assignment_ids]
    if wave_id:
        return [assignment for assignment in assignments if assignment.get("wave_id") == wave_id]
    return list(assignments)


def create_handoffs(
    cwd: str | Path | None = None,
    assignment_ids: list[str] | None = None,
    wave_id: str = "",
    reuse_existing: bool = True,
    constraints: list[str] | None = None,
    evidence_requirements: list[str] | None = None,
    resume_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create immutable handoff packet files from existing assignments."""

    if assignment_ids is not None and not isinstance(assignment_ids, list):
        raise FlywheelError("handoff_invalid_assignment_ids", "assignment_ids must be an array of strings.", {})
    if constraints is not None and not isinstance(constraints, list):
        raise FlywheelError("handoff_invalid_constraints", "constraints must be an array of strings.", {})
    if evidence_requirements is not None and not isinstance(evidence_requirements, list):
        raise FlywheelError("handoff_invalid_evidence_requirements", "evidence_requirements must be an array of strings.", {})
    if resume_metadata is not None and not isinstance(resume_metadata, dict):
        raise FlywheelError("handoff_invalid_resume_metadata", "resume_metadata must be an object.", {})

    root = Path(cwd or Path.cwd()).resolve()
    store = StateStore.for_cwd(root)
    state = store.load()
    tasks = _task_index(state)
    waves = _wave_index(state)
    workers = _worker_index(state)
    state.setdefault("handoffs", [])
    state.setdefault("handoff_events", [])

    selected = _selected_assignments(state, [str(item) for item in assignment_ids] if assignment_ids else None, str(wave_id or ""))
    if not selected:
        raise FlywheelError("handoff_no_assignments", "No assignments are available for handoff creation.", {"wave_id": wave_id, "assignment_ids": assignment_ids or []})

    results: list[dict[str, Any]] = []
    handoffs: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    created_count = 0
    handoffs_dir = store.state_dir / HANDOFF_DIR_NAME

    for assignment in selected:
        assignment_id = str(assignment.get("id", ""))
        task_id = str(assignment.get("task_id", ""))
        wave_id_value = str(assignment.get("wave_id", ""))
        worker_id = str(assignment.get("worker_id", ""))
        task = tasks.get(task_id)
        wave = waves.get(wave_id_value)
        worker = workers.get(worker_id)
        if task is None or wave is None or worker is None:
            event = _append_handoff_event(
                state,
                "handoff_skipped",
                assignment_id=assignment_id,
                worker_id=worker_id,
                task_id=task_id,
                wave_id=wave_id_value,
                message="assignment references missing task, wave, or worker",
                data={"has_task": task is not None, "has_wave": wave is not None, "has_worker": worker is not None},
            )
            events.append(event)
            results.append({"assignment_id": assignment_id, "status": "skipped", "reason": "missing_reference", "event": event})
            continue

        existing = _existing_handoff_for_assignment(state, assignment_id)
        if existing is not None:
            if reuse_existing:
                packet = _validate_existing_handoff(
                    handoffs_dir=handoffs_dir,
                    existing=existing,
                    assignment=assignment,
                    task=task,
                    wave=wave,
                    worker=worker,
                )
                event = _append_handoff_event(
                    state,
                    "handoff_reused",
                    assignment_id=assignment_id,
                    worker_id=worker_id,
                    task_id=task_id,
                    wave_id=wave_id_value,
                    handoff=existing,
                    message="reused existing immutable handoff packet",
                    data={"path": str(Path(str(existing.get("path", ""))).resolve()), "packetHash": packet.get("packetHash")},
                )
                handoffs.append(existing)
                events.append(event)
                results.append({"assignment_id": assignment_id, "status": "reused", "handoff": existing, "packet": packet, "event": event})
                continue
            raise FlywheelError("handoff_exists", "Handoff already exists for assignment; pass reuse_existing true to validate/read/reuse it.", {"assignment_id": assignment_id, "path": str(existing.get("path", ""))})

        filename = handoff_filename(assignment)
        path = handoffs_dir / filename
        created_at = utc_now()
        packet = _build_packet(
            root=root,
            state=state,
            assignment=assignment,
            task=task,
            wave=wave,
            worker=worker,
            constraints=[str(item) for item in (constraints or DEFAULT_CONSTRAINTS)],
            evidence_requirements=[str(item) for item in (evidence_requirements or DEFAULT_EVIDENCE_REQUIREMENTS)],
            resume_metadata=resume_metadata or {},
            created_at=created_at,
        )
        _atomic_create_json(path, packet)
        handoff = {
            "id": packet["handoff_id"],
            "schemaVersion": HANDOFF_SCHEMA_VERSION,
            "created_at": created_at,
            "assignment_id": assignment_id,
            "worker_id": worker_id,
            "task_id": task_id,
            "wave_id": wave_id_value,
            "path": str(path),
            "filename": filename,
            "packetHash": packet["packetHash"],
            "immutable": True,
        }
        state["handoffs"].append(handoff)
        event = _append_handoff_event(
            state,
            "handoff_created",
            assignment_id=assignment_id,
            worker_id=worker_id,
            task_id=task_id,
            wave_id=wave_id_value,
            handoff=handoff,
            message="created immutable worker handoff packet",
            data={"path": str(path), "packetHash": packet["packetHash"]},
        )
        created_count += 1
        handoffs.append(handoff)
        events.append(event)
        results.append({"assignment_id": assignment_id, "status": "created", "handoff": handoff, "packet": packet, "event": event})

    store.save(state)
    return {
        "handoffs": handoffs,
        "results": results,
        "events": events,
        "created": created_count,
        "reused": sum(1 for result in results if result["status"] == "reused"),
        "skipped": sum(1 for result in results if result["status"] == "skipped"),
        "summary": handoff_summary(state),
    }


def handoff_summary(state: dict[str, Any]) -> dict[str, Any]:
    handoffs = state.get("handoffs", [])
    events = state.get("handoff_events", [])
    by_wave = dict(Counter(str(handoff.get("wave_id", "")) for handoff in handoffs))
    return {
        "total": len(handoffs),
        "by_wave": by_wave,
        "recent_events": events[-10:],
    }
