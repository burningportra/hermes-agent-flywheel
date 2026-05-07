"""JSON state store and checkpoints."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import FlywheelError

STATE_DIR = ".hermes-flywheel"
STATE_FILE = "state.json"


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
        payload = json.dumps(state, indent=2, sort_keys=True) + "\n"
        fd, tmp_name = tempfile.mkstemp(prefix="state-", suffix=".json", dir=self.state_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, self.state_path)
        finally:
            tmp = Path(tmp_name)
            if tmp.exists():
                tmp.unlink()
        return state

    def checkpoint(self, label: str = "checkpoint") -> dict[str, Any]:
        state = self.load()
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        safe_label = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in label).strip("-") or "checkpoint"
        stamp = utc_now().replace(":", "").replace("+00:00", "Z")
        checkpoint_path = self.checkpoints_dir / f"{stamp}-{safe_label}.json"
        payload = json.dumps(state, indent=2, sort_keys=True) + "\n"
        fd, tmp_name = tempfile.mkstemp(prefix="checkpoint-", suffix=".json", dir=self.checkpoints_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, checkpoint_path)
        finally:
            tmp = Path(tmp_name)
            if tmp.exists():
                tmp.unlink()
        entry = {"label": label, "path": str(checkpoint_path), "created_at": utc_now()}
        state.setdefault("checkpoints", []).append(entry)
        self.save(state)
        return entry
