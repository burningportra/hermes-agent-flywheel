import json

import pytest

from hermes_flywheel_plugin import register
from hermes_flywheel_plugin.advance_wave import advance_wave
from hermes_flywheel_plugin.completion_report import record_completion_report, safe_report_filename, validate_completion_report
from hermes_flywheel_plugin.doctor import run_doctor
from hermes_flywheel_plugin.errors import FlywheelError
from hermes_flywheel_plugin.observe import observe
from hermes_flywheel_plugin.planning import create_tasks
from hermes_flywheel_plugin.skills_bundle import get_skill
from hermes_flywheel_plugin.state import StateStore
from hermes_flywheel_plugin.task_lifecycle import update_task


class FakeContext:
    def __init__(self):
        self.tools = []

    def register_tool(self, name, toolset, schema, handler, description):
        self.tools.append({"name": name, "schema": schema, "handler": handler})


def test_advance_wave_blocks_until_prior_started_wave_has_success_reports(tmp_path):
    create_tasks(
        [
            {"id": "a", "title": "A"},
            {"id": "b", "title": "B"},
        ],
        tmp_path,
    )
    first = advance_wave(tmp_path, limit=1)
    assert first["wave"]["task_ids"] == ["a"]

    with pytest.raises(FlywheelError) as excinfo:
        advance_wave(tmp_path, limit=1)
    assert excinfo.value.code == "wave_blocked_incomplete"
    assert excinfo.value.details["wave_id"] == first["wave"]["id"]
    assert excinfo.value.details["incomplete_task_ids"] == ["a"]

    forced = advance_wave(tmp_path, limit=1, force=True)
    assert forced["wave"]["task_ids"] == ["b"]


def test_advance_wave_requires_latest_success_completion_report(tmp_path):
    create_tasks(
        [
            {"id": "a", "title": "A"},
            {"id": "b", "title": "B"},
        ],
        tmp_path,
    )
    advance_wave(tmp_path, limit=1)
    record_completion_report({"task_id": "a", "outcome": "success", "summary": "done"}, tmp_path)
    record_completion_report({"task_id": "a", "outcome": "failed", "summary": "regressed"}, tmp_path)

    with pytest.raises(FlywheelError) as excinfo:
        advance_wave(tmp_path, limit=1)
    assert excinfo.value.code == "wave_blocked_incomplete"

    record_completion_report({"task_id": "a", "outcome": "success", "summary": "fixed"}, tmp_path)
    second = advance_wave(tmp_path, limit=1)
    assert second["wave"]["task_ids"] == ["b"]


def test_success_completion_report_writes_atomic_disk_report_and_validates_lists(tmp_path):
    create_tasks([{"id": "a", "title": "A"}], tmp_path)
    report = record_completion_report(
        {
            "task_id": "a",
            "outcome": "success",
            "summary": "done",
            "changed_files": ["src/a.py"],
            "verification": ["pytest"],
            "self_review": "looks good",
            "reservations_released": True,
            "artifacts": ["artifact"],
        },
        tmp_path,
    )
    assert report["changed_files"] == ["src/a.py"]
    assert report["verification"] == ["pytest"]

    on_disk = tmp_path / ".hermes-flywheel" / "completion" / f"{safe_report_filename('a')}.json"
    assert on_disk.exists()
    payload = json.loads(on_disk.read_text(encoding="utf-8"))
    assert payload["task_id"] == "a"
    assert payload["outcome"] == "success"
    assert payload["changed_files"] == ["src/a.py"]

    failed = record_completion_report({"task_id": "a", "outcome": "failed", "summary": "regressed"}, tmp_path)
    assert failed["outcome"] == "failed"
    payload = json.loads(on_disk.read_text(encoding="utf-8"))
    assert payload["summary"] == "regressed"
    assert payload["outcome"] == "failed"

    with pytest.raises(FlywheelError) as excinfo:
        validate_completion_report({"task_id": "b", "outcome": "success", "summary": "bad", "changed_files": "x"})
    assert excinfo.value.code == "report_invalid_changed_files"

    with pytest.raises(FlywheelError) as excinfo:
        validate_completion_report({"task_id": "b", "outcome": "success", "summary": "bad", "verification": "pytest"})
    assert excinfo.value.code == "report_invalid_verification"


def test_safe_report_filename_is_collision_resistant_for_sanitized_ids():
    first = safe_report_filename("a/b")
    second = safe_report_filename("a?b")
    assert first != second
    assert first.startswith("a-b-")
    assert second.startswith("a-b-")
    assert first == safe_report_filename("a/b")


def test_update_task_lifecycle_tool_and_handler(tmp_path):
    create_tasks([{"id": "a", "title": "A"}], tmp_path)
    updated = update_task(tmp_path, "a", status="blocked", notes="needs input", blocker="missing key")
    task = updated["task"]
    assert task["status"] == "blocked"
    assert task["notes"] == "needs input"
    assert task["blocker"] == "missing key"

    ctx = FakeContext()
    register(ctx)
    names = {tool["name"] for tool in ctx.tools}
    assert "hermes_flywheel_update_task" in names
    handler = next(tool["handler"] for tool in ctx.tools if tool["name"] == "hermes_flywheel_update_task")
    payload = json.loads(handler({"cwd": str(tmp_path), "task_id": "a", "status": "ready", "notes": "unblocked", "blocker": ""}))
    assert payload["ok"] is True
    assert payload["task"]["status"] == "ready"


def test_observe_and_doctor_report_incomplete_active_wave_and_completion_dir(tmp_path):
    create_tasks([{"id": "a", "title": "A"}], tmp_path)
    advance_wave(tmp_path, limit=1)

    observation = observe(tmp_path)
    assert observation["blocked_wave"]["wave_id"] == "wave-1"
    assert observation["blocked_wave"]["incomplete_task_ids"] == ["a"]

    doctor = run_doctor(tmp_path)
    checks = {check["name"]: check for check in doctor["checks"]}
    assert checks["active_wave_complete"]["ok"] is False
    assert "a" in checks["active_wave_complete"]["detail"]
    assert checks["completion_report_dir"]["ok"] is False


def test_packaged_skill_lookup_uses_package_data():
    skill = get_skill("start")
    assert skill["name"] == "start"
    assert "Flywheel Start Skill" in skill["content"]
    assert "hermes_flywheel_plugin" in skill["path"]
