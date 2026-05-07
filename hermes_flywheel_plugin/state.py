"""JSON state store and integrity-backed checkpoints."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import FlywheelError

STATE_DIR = ".hermes-flywheel"
STATE_FILE = "state.json"
CHECKPOINT_FILE = "checkpoint.json"
CHECKPOINT_SCHEMA_VERSION = 1
FLYWHEEL_VERSION = "0.8.0"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_state() -> dict[str, Any]:
    now = utc_now()
    return {
        "version": 1,
        "created_at": now,
        "updated_at": now,
        "observations": [],
        "profiles": [],
        "plans": [],
        "task_graph": {"tasks": []},
        "waves": [],
        "completion_reports": [],
        "checkpoints": [],
    }


def canonical_json(value: Any) -> str:
    """Return deterministic JSON used for checkpoint hashing."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_state_hash(state: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(state).encode("utf-8")).hexdigest()


def _git_head(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    head = result.stdout.strip()
    return head or None


def checkpoint_envelope(state: dict[str, Any], root: Path) -> dict[str, Any]:
    envelope: dict[str, Any] = {
        "schemaVersion": CHECKPOINT_SCHEMA_VERSION,
        "writtenAt": utc_now(),
        "flywheelVersion": FLYWHEEL_VERSION,
        "state": state,
        "stateHash": canonical_state_hash(state),
    }
    head = _git_head(root)
    if head:
        envelope["gitHead"] = head
    return envelope


def _atomic_write_json(path: Path, data: Any, *, dir_path: Path | None = None) -> None:
    directory = dir_path or path.parent
    directory.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=f"{path.stem}-", suffix=".json", dir=directory)
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


@dataclass(slots=True)
class StateStore:
    root: Path

    @classmethod
    def for_cwd(cls, cwd: str | Path | None = None) -> "StateStore":
        return cls(Path(cwd or Path.cwd()).resolve())

    @property
    def state_dir(self) -> Path:
        return self.root / STATE_DIR

    @property
    def state_path(self) -> Path:
        return self.state_dir / STATE_FILE

    @property
    def checkpoint_path(self) -> Path:
        return self.state_dir / CHECKPOINT_FILE

    @property
    def checkpoints_dir(self) -> Path:
        return self.state_dir / "checkpoints"

    def load(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return default_state()
        try:
            with self.state_path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except json.JSONDecodeError as exc:
            raise FlywheelError(
                "state_invalid_json",
                "State file is not valid JSON.",
                {"path": str(self.state_path), "reason": str(exc)},
            ) from exc
        if not isinstance(data, dict):
            raise FlywheelError("state_invalid", "State root must be an object.", {"path": str(self.state_path)})
        return {**default_state(), **data}

    def save(self, state: dict[str, Any]) -> dict[str, Any]:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        state["updated_at"] = utc_now()
        _atomic_write_json(self.state_path, state)
        return state

    def read_checkpoint(self) -> dict[str, Any]:
        validation = self.validate_checkpoint()
        if not validation.get("ok"):
            raise FlywheelError("checkpoint_invalid", "Checkpoint is invalid.", validation)
        with self.checkpoint_path.open("r", encoding="utf-8") as fh:
            envelope = json.load(fh)
        return envelope

    def validate_checkpoint(self) -> dict[str, Any]:
        path = self.checkpoint_path
        if not path.exists():
            return {"ok": False, "path": str(path), "reason": "missing"}
        try:
            with path.open("r", encoding="utf-8") as fh:
                envelope = json.load(fh)
        except json.JSONDecodeError as exc:
            return {"ok": False, "path": str(path), "reason": "invalid_json", "detail": str(exc)}
        except OSError as exc:
            return {"ok": False, "path": str(path), "reason": "unreadable", "detail": str(exc)}
        if not isinstance(envelope, dict):
            return {"ok": False, "path": str(path), "reason": "invalid_envelope"}
        if envelope.get("schemaVersion") != CHECKPOINT_SCHEMA_VERSION:
            return {
                "ok": False,
                "path": str(path),
                "reason": "schema_version_mismatch",
                "schemaVersion": envelope.get("schemaVersion"),
            }
        state = envelope.get("state")
        if not isinstance(state, dict):
            return {"ok": False, "path": str(path), "reason": "missing_state"}
        expected = canonical_state_hash(state)
        observed = envelope.get("stateHash")
        if observed != expected:
            return {
                "ok": False,
                "path": str(path),
                "reason": "hash_mismatch",
                "stateHash": observed,
                "expectedStateHash": expected,
            }
        current_hash = None
        current = False
        try:
            current_state = self.load()
            current_hash = canonical_state_hash(current_state)
            current = current_hash == expected
        except Exception as exc:  # noqa: BLE001 - validation reports state-load failures as data
            return {
                "ok": True,
                "path": str(path),
                "stateHash": expected,
                "current": False,
                "stateLoadError": str(exc),
                "writtenAt": envelope.get("writtenAt"),
            }
        return {
            "ok": True,
            "path": str(path),
            "stateHash": expected,
            "currentStateHash": current_hash,
            "current": current,
            "writtenAt": envelope.get("writtenAt"),
            "gitHead": envelope.get("gitHead"),
            "flywheelVersion": envelope.get("flywheelVersion"),
        }

    def checkpoint(self, label: str = "checkpoint") -> dict[str, Any]:
        state = self.load()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        safe_label = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in label).strip("-") or "checkpoint"
        stamp = utc_now().replace(":", "").replace("+00:00", "Z")
        checkpoint_path = self.checkpoints_dir / f"{stamp}-{safe_label}.json"

        entry = {
            "label": label,
            "path": str(checkpoint_path),
            "canonical_path": str(self.checkpoint_path),
            "created_at": utc_now(),
            "schemaVersion": CHECKPOINT_SCHEMA_VERSION,
            "flywheelVersion": FLYWHEEL_VERSION,
        }
        state.setdefault("checkpoints", []).append(entry)
        self.save(state)
        state = self.load()

        # Keep historical snapshots as raw state for compatibility with v0.1/v0.2 callers.
        _atomic_write_json(checkpoint_path, state, dir_path=self.checkpoints_dir)

        envelope = checkpoint_envelope(state, self.root)
        _atomic_write_json(self.checkpoint_path, envelope, dir_path=self.state_dir)

        metadata = {**entry, "created_at": envelope["writtenAt"], "stateHash": envelope["stateHash"], "ok": True}
        if "gitHead" in envelope:
            metadata["gitHead"] = envelope["gitHead"]
        return metadata
