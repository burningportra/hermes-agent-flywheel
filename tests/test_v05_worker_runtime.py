import json
from datetime import datetime, timedelta, timezone

import pytest

from hermes_flywheel_plugin import register
from hermes_flywheel_plugin.advance_wave import advance_wave
from hermes_flywheel_plugin.doctor import run_doctor
from hermes_flywheel_plugin.errors import FlywheelError
from hermes_flywheel_plugin.observe import observe
from hermes_flywheel_plugin.planning import create_tasks
from hermes_flywheel_plugin.state import StateStore
from hermes_flywheel_plugin.task_graph import mark_tasks
from hermes_flywheel_plugin.worker_runtime import create_worker, list_workers, update_worker


class FakeContext:
    def __init__(self):
        self.tools = []

    def register_tool(self, name, toolset, schema, handler, description):
        self.tools.append({"name": name, "schema": schema, "handler": handler, "description": description})


def test_default_state_includes_worker_substrate(tmp_path):
    state = StateStore.for_cwd(tmp_path).load()
    assert state["workers"] == []
    assert state["worker_events"] == []


def test_create_noop_worker_records_state_and_event_without_process_fields(tmp_path):
    create_tasks([{"id": "a", "title": "A"}], tmp_path)
    created = create_worker(tmp_path, task_id="a", name="local-a", metadata={"role": "implementer"})

    worker = created["worker"]
    assert worker["id"] == "worker-1"
    assert worker["runtime"] == "noop"
    assert worker["status"] == "created"
    assert worker["task_id"] == "a"
    assert created["event"]["kind"] == "worker_created"
    assert not ({"pid", "command", "session", "pane"} & set(worker))

    state = StateStore.for_cwd(tmp_path).load()
    assert state["workers"] == [worker]
    assert state["worker_events"][0]["worker_id"] == "worker-1"


def test_create_worker_validates_task_wave_and_runtime(tmp_path):
    with pytest.raises(FlywheelError) as excinfo:
        create_worker(tmp_path, runtime="ntm")
    assert excinfo.value.code == "worker_runtime_unsupported"

    with pytest.raises(FlywheelError) as excinfo:
        create_worker(tmp_path, task_id="missing")
    assert excinfo.value.code == "worker_unknown_task"

    create_tasks([{"id": "a", "title": "A"}], tmp_path)
    with pytest.raises(FlywheelError) as excinfo:
        create_worker(tmp_path, task_id="a", wave_id="missing-wave")
    assert excinfo.value.code == "worker_unknown_wave"


def test_update_worker_lifecycle_appends_ordered_events_without_task_completion(tmp_path):
    create_tasks([{"id": "a", "title": "A"}], tmp_path)
    create_worker(tmp_path, task_id="a")
    update_worker(tmp_path, "worker-1", "start", "started")
    update_worker(tmp_path, "worker-1", "heartbeat", data={"tick": 1})
    update_worker(tmp_path, "worker-1", "idle")
    update_worker(tmp_path, "worker-1", "start")
    completed = update_worker(tmp_path, "worker-1", "complete", "done")

    assert completed["worker"]["status"] == "completed"
    state = StateStore.for_cwd(tmp_path).load()
    assert [event["kind"] for event in state["worker_events"]] == [
        "worker_created",
        "worker_started",
        "worker_heartbeat",
        "worker_idled",
        "worker_started",
        "worker_completed",
    ]
    task = state["task_graph"]["tasks"][0]
    assert task["status"] == "pending"


def test_update_worker_rejects_unknown_worker_and_terminal_mutation(tmp_path):
    with pytest.raises(FlywheelError) as excinfo:
        update_worker(tmp_path, "worker-missing", "start")
    assert excinfo.value.code == "worker_unknown_id"

    create_worker(tmp_path)
    update_worker(tmp_path, "worker-1", "complete")
    with pytest.raises(FlywheelError) as excinfo:
        update_worker(tmp_path, "worker-1", "heartbeat")
    assert excinfo.value.code == "worker_terminal"


def test_list_workers_filters_and_summarizes(tmp_path):
    create_tasks([{"id": "a", "title": "A"}, {"id": "b", "title": "B"}], tmp_path)
    create_worker(tmp_path, task_id="a", name="A")
    create_worker(tmp_path, task_id="b", name="B")
    update_worker(tmp_path, "worker-1", "start")
    update_worker(tmp_path, "worker-2", "fail")

    running = list_workers(tmp_path, status="running")
    assert [worker["id"] for worker in running["workers"]] == ["worker-1"]
    task_a = list_workers(tmp_path, task_id="a")
    assert [worker["id"] for worker in task_a["workers"]] == ["worker-1"]
    assert running["summary"]["by_status"] == {"running": 1, "failed": 1}


def test_worker_tools_register_and_handlers_return_json(tmp_path):
    create_tasks([{"id": "a", "title": "A"}], tmp_path)
    ctx = FakeContext()
    register(ctx)
    names = {tool["name"] for tool in ctx.tools}
    assert "hermes_flywheel_create_worker" in names
    assert "hermes_flywheel_update_worker" in names
    assert "hermes_flywheel_list_workers" in names

    create_handler = next(tool["handler"] for tool in ctx.tools if tool["name"] == "hermes_flywheel_create_worker")
    update_handler = next(tool["handler"] for tool in ctx.tools if tool["name"] == "hermes_flywheel_update_worker")
    list_handler = next(tool["handler"] for tool in ctx.tools if tool["name"] == "hermes_flywheel_list_workers")

    created = json.loads(create_handler({"cwd": str(tmp_path), "task_id": "a", "name": "handler"}))
    assert created["ok"] is True
    assert created["worker"]["id"] == "worker-1"
    updated = json.loads(update_handler({"cwd": str(tmp_path), "worker_id": "worker-1", "action": "start"}))
    assert updated["ok"] is True
    listed = json.loads(list_handler({"cwd": str(tmp_path), "status": "running"}))
    assert listed["ok"] is True
    assert [worker["id"] for worker in listed["workers"]] == ["worker-1"]


def test_checkpoint_hash_includes_worker_state(tmp_path):
    create_worker(tmp_path)
    store = StateStore.for_cwd(tmp_path)
    checkpoint = store.checkpoint("workers")
    envelope = store.read_checkpoint()

    assert checkpoint["ok"] is True
    assert envelope["state"]["workers"][0]["id"] == "worker-1"
    update_worker(tmp_path, "worker-1", "start")
    validation = store.validate_checkpoint()
    assert validation["ok"] is True
    assert validation["current"] is False


def test_observe_and_doctor_report_worker_summary_and_stale_operator_action(tmp_path):
    create_tasks([{"id": "a", "title": "A"}], tmp_path)
    advance_wave(tmp_path, limit=1)
    create_worker(tmp_path, task_id="a")
    update_worker(tmp_path, "worker-1", "start")
    store = StateStore.for_cwd(tmp_path)
    state = store.load()
    state["workers"][0]["heartbeat_at"] = (datetime.now(timezone.utc) - timedelta(hours=2)).replace(microsecond=0).isoformat()
    store.save(state)

    observation = observe(tmp_path)
    assert observation["workers"]["total"] == 1
    assert observation["workers"]["stale"] == ["worker-1"]

    doctor = run_doctor(tmp_path)
    checks = {check["name"]: check for check in doctor["checks"]}
    assert checks["worker_state_shape"]["ok"] is True
    assert checks["active_workers"]["ok"] is False
    assert any(item["id"] == "resolve_stale_worker" for item in doctor["remediations"])
