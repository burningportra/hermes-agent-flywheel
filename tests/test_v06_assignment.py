import json

import pytest

from hermes_flywheel_plugin import register
from hermes_flywheel_plugin.advance_wave import advance_wave
from hermes_flywheel_plugin.assignment import assign_wave
from hermes_flywheel_plugin.doctor import run_doctor
from hermes_flywheel_plugin.errors import FlywheelError
from hermes_flywheel_plugin.observe import observe
from hermes_flywheel_plugin.planning import create_tasks
from hermes_flywheel_plugin.state import StateStore
from hermes_flywheel_plugin.task_lifecycle import update_task
from hermes_flywheel_plugin.worker_runtime import update_worker


class FakeContext:
    def __init__(self):
        self.tools = []

    def register_tool(self, name, toolset, schema, handler, description):
        self.tools.append({"name": name, "schema": schema, "handler": handler, "description": description})


def test_default_state_includes_assignment_substrate(tmp_path):
    state = StateStore.for_cwd(tmp_path).load()
    assert state["assignments"] == []
    assert state["assignment_events"] == []


def test_assign_wave_creates_noop_workers_and_append_only_assignment_events(tmp_path):
    create_tasks([{"id": "a", "title": "A"}, {"id": "b", "title": "B"}], tmp_path)
    wave = advance_wave(tmp_path, limit=2)["wave"]

    assigned = assign_wave(tmp_path, wave_id=wave["id"], metadata={"role": "implementer"})

    assert [result["status"] for result in assigned["results"]] == ["created", "created"]
    assert [worker["id"] for worker in assigned["workers"]] == ["worker-1", "worker-2"]
    assert [worker["runtime"] for worker in assigned["workers"]] == ["noop", "noop"]
    assert not any({"pid", "command", "session", "pane"} & set(worker) for worker in assigned["workers"])
    assert [event["kind"] for event in assigned["events"]] == ["assignment_created", "assignment_created"]
    assert [event["kind"] for event in assigned["worker_events"]] == ["worker_created", "worker_created"]

    state = StateStore.for_cwd(tmp_path).load()
    assert len(state["assignments"]) == 2
    assert len(state["assignment_events"]) == 2
    assert [event["kind"] for event in state["worker_events"]] == ["worker_created", "worker_created"]
    assert [task["status"] for task in state["task_graph"]["tasks"]] == ["in_progress", "in_progress"]


def test_assign_wave_reuses_active_worker_without_duplicate_assignment(tmp_path):
    create_tasks([{"id": "a", "title": "A"}], tmp_path)
    wave = advance_wave(tmp_path, limit=1)["wave"]
    first = assign_wave(tmp_path, wave_id=wave["id"])
    second = assign_wave(tmp_path, wave_id=wave["id"])

    assert first["workers"][0]["id"] == second["workers"][0]["id"] == "worker-1"
    assert second["results"][0]["status"] == "reused"
    state = StateStore.for_cwd(tmp_path).load()
    assert len(state["assignments"]) == 1
    assert [event["kind"] for event in state["assignment_events"]] == ["assignment_created", "assignment_reused"]


def test_assign_wave_creates_replacement_after_terminal_worker_without_completing_task(tmp_path):
    create_tasks([{"id": "a", "title": "A"}], tmp_path)
    wave = advance_wave(tmp_path, limit=1)["wave"]
    assign_wave(tmp_path, wave_id=wave["id"])
    update_worker(tmp_path, "worker-1", "complete", "worker done is not task done")
    replacement = assign_wave(tmp_path, wave_id=wave["id"])

    assert replacement["workers"][0]["id"] == "worker-2"
    state = StateStore.for_cwd(tmp_path).load()
    assert state["task_graph"]["tasks"][0]["status"] == "in_progress"
    assert state["completion_reports"] == []
    assert len(state["assignments"]) == 2


def test_assign_wave_skips_unassignable_task_statuses(tmp_path):
    create_tasks([{"id": "a", "title": "A"}], tmp_path)
    wave = advance_wave(tmp_path, limit=1, start=False)["wave"]
    update_task(tmp_path, "a", status="blocked", blocker="manual hold")

    assigned = assign_wave(tmp_path, wave_id=wave["id"])

    assert assigned["assignments"] == []
    assert assigned["workers"] == []
    assert assigned["results"][0]["status"] == "skipped"
    assert assigned["events"][0]["kind"] == "assignment_skipped"


def test_assign_wave_validates_wave_runtime_and_metadata(tmp_path):
    with pytest.raises(FlywheelError) as excinfo:
        assign_wave(tmp_path)
    assert excinfo.value.code == "assignment_no_wave"

    create_tasks([{"id": "a", "title": "A"}], tmp_path)
    wave = advance_wave(tmp_path, limit=1)["wave"]

    with pytest.raises(FlywheelError) as excinfo:
        assign_wave(tmp_path, wave_id="missing")
    assert excinfo.value.code == "assignment_unknown_wave"

    with pytest.raises(FlywheelError) as excinfo:
        assign_wave(tmp_path, wave_id=wave["id"], runtime="tmux")
    assert excinfo.value.code == "assignment_runtime_unsupported"

    with pytest.raises(FlywheelError) as excinfo:
        assign_wave(tmp_path, wave_id=wave["id"], metadata=[])
    assert excinfo.value.code == "assignment_invalid_metadata"


def test_assign_wave_rejects_explicit_non_assignable_wave_status(tmp_path):
    create_tasks([{"id": "a", "title": "A"}], tmp_path)
    wave = advance_wave(tmp_path, limit=1)["wave"]
    store = StateStore.for_cwd(tmp_path)
    state = store.load()
    state["waves"][0]["status"] = "completed"
    store.save(state)

    with pytest.raises(FlywheelError) as excinfo:
        assign_wave(tmp_path, wave_id=wave["id"])

    assert excinfo.value.code == "assignment_wave_not_assignable"
    assert excinfo.value.details["wave_id"] == wave["id"]
    assert excinfo.value.details["status"] == "completed"
    assert StateStore.for_cwd(tmp_path).load()["workers"] == []


def test_assignment_tool_registers_and_handler_returns_json(tmp_path):
    create_tasks([{"id": "a", "title": "A"}], tmp_path)
    wave = advance_wave(tmp_path, limit=1)["wave"]
    ctx = FakeContext()
    register(ctx)
    names = {tool["name"] for tool in ctx.tools}
    assert "hermes_flywheel_assign_wave" in names
    handler = next(tool["handler"] for tool in ctx.tools if tool["name"] == "hermes_flywheel_assign_wave")

    response = json.loads(handler({"cwd": str(tmp_path), "wave_id": wave["id"]}))

    assert response["ok"] is True
    assert response["workers"][0]["id"] == "worker-1"
    assert response["assignments"][0]["task_id"] == "a"


def test_observe_and_doctor_report_assignment_summary(tmp_path):
    create_tasks([{"id": "a", "title": "A"}], tmp_path)
    wave = advance_wave(tmp_path, limit=1)["wave"]
    assign_wave(tmp_path, wave_id=wave["id"])

    observation = observe(tmp_path)
    assert observation["assignments"]["total"] == 1
    assert observation["assignments"]["by_wave"] == {wave["id"]: 1}

    doctor = run_doctor(tmp_path)
    checks = {check["name"]: check for check in doctor["checks"]}
    assert checks["assignment_state_shape"]["ok"] is True
    assert checks["assignment_state_shape"]["data"]["total"] == 1
