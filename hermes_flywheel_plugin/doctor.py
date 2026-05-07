"""Doctor checks."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .advance_wave import incomplete_started_wave
from .state import StateStore


def run_doctor(cwd: str | Path | None = None) -> dict[str, Any]:
    root = Path(cwd or Path.cwd()).resolve()
    store = StateStore.for_cwd(root)
    checks = []

    checks.append({"name": "python_version", "ok": sys.version_info >= (3, 10), "detail": sys.version.split()[0]})
    checks.append({"name": "root_exists", "ok": root.exists(), "detail": str(root)})
    checks.append({"name": "root_writable", "ok": root.exists() and os_access_write(root), "detail": str(root)})
    checks.append({"name": "state_dir", "ok": store.state_dir.exists(), "detail": str(store.state_dir)})

    try:
        state = store.load()
        checks.append({"name": "state_load", "ok": True, "detail": f"version={state.get('version')}"})
        blocker = incomplete_started_wave(state)
        if blocker:
            checks.append(
                {
                    "name": "active_wave_complete",
                    "ok": False,
                    "detail": f"{blocker['wave_id']} incomplete tasks: {', '.join(blocker['incomplete_task_ids'])}",
                    "data": blocker,
                }
            )
        else:
            checks.append({"name": "active_wave_complete", "ok": True, "detail": "no incomplete started wave"})
    except Exception as exc:  # noqa: BLE001 - doctor should report failures as data
        checks.append({"name": "state_load", "ok": False, "detail": str(exc)})

    completion_dir = store.state_dir / "completion"
    checks.append(
        {
            "name": "completion_report_dir",
            "ok": completion_dir.exists() and completion_dir.is_dir(),
            "detail": str(completion_dir),
        }
    )

    return {"ok": all(check["ok"] for check in checks), "root": str(root), "checks": checks}


def os_access_write(path: Path) -> bool:
    try:
        probe = path / ".hermes-flywheel-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False
