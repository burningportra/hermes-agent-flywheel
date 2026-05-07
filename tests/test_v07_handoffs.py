import json
from pathlib import Path

import pytest

from hermes_flywheel_plugin import register
from hermes_flywheel_plugin.advance_wave import advance_wave
from hermes_flywheel_plugin.assignment import assign_wave
from hermes_flywheel_plugin.errors import FlywheelError
from hermes_flywheel_plugin.handoff import create_handoffs, handoff_filename
from hermes_flywheel_plugin.observe import observe
from hermes_flywheel_plugin.planning import create_tasks
from hermes_flywheel_plugin.state import FLYWHEEL_VERSION, StateStore, canonical_json
from hermes_flywheel_plugin.task_lifecycle import update_task


class FakeContext:
    def __init__(self):
        self.tools = []

    def register_tool(self, name, toolset, schema, handler, description):
        self.tools.append({"name": name, "schema": schema, "handler": handler, "description": description})


def _assigned_wave(tmp_path, tasks=None):
    create_tasks(tasks or [{"id": "a", "title": "A"}], tmp_path)
    wave = advance_wave(tmp_path, limit=10)["wave"]
    assigned = assign_wave(tmp_path, wave_id=wave["id"])
    return wave, assigned


def test_default_state_includes_handoff_substrate(tmp_path):
    state = StateStore.for_cwd(tmp_path).load()

    assert state["handoffs"] == []
    assert state["handoff_events"] == []


def test_create_handoffs_writes_immutable_packet_without_mutating_task_or_evidence(tmp_path):
    wave, assigned = _assigned_wave(tmp_path)

    result = create_handoffs(tmp_path, wave_id=wave["id"], resume_metadata={"operator": "test"})

    assert result["created"] == 1
    handoff = result["handoffs"][0]
    packet = result["results"][0]["packet"]
    path = Path(handoff["path"])
    assert path.is_file()
    assert path.parent == tmp_path / ".hermes-flywheel" / "handoffs"
    assert handoff["immutable"] is True
    assert handoff["packetHash"] == packet["packetHash"]
    assert packet["schemaVersion"] == 1
    assert packet["flywheelVersion"] == FLYWHEEL_VERSION
    assert packet["kind"] == "hermes_flywheel_worker_handoff"
    assert packet["assignment_id"] == assigned["assignments"][0]["id"]
    assert packet["worker_id"] == assigned["workers"][0]["id"]
    assert packet["task_id"] == "a"
    assert packet["wave_id"] == wave["id"]
    assert packet["resume_metadata"]["operator"] == "test"
    assert "no subprocess" in " ".join(packet["constraints"])
    assert "Completion requires" in " ".join(packet["evidence_requirements"])
    assert json.loads(path.read_text(encoding="utf-8")) == packet

    state = StateStore.for_cwd(tmp_path).load()
    assert state["task_graph"]["tasks"][0]["status"] == "in_progress"
    assert state["completion_reports"] == []
    assert [event["kind"] for event in state["handoff_events"]] == ["handoff_created"]


def test_create_handoffs_reuses_existing_packet_and_never_overwrites(tmp_path):
    wave, _assigned = _assigned_wave(tmp_path)
    first = create_handoffs(tmp_path, wave_id=wave["id"])
    path = Path(first["handoffs"][0]["path"])
    original = path.read_text(encoding="utf-8")

    second = create_handoffs(tmp_path, wave_id=wave["id"])

    assert second["created"] == 0
    assert second["reused"] == 1
    assert second["results"][0]["packet"] == json.loads(original)
    assert path.read_text(encoding="utf-8") == original
    state = StateStore.for_cwd(tmp_path).load()
    assert [event["kind"] for event in state["handoff_events"]] == ["handoff_created", "handoff_reused"]

    with pytest.raises(FlywheelError) as excinfo:
        create_handoffs(tmp_path, wave_id=wave["id"], reuse_existing=False)
    assert excinfo.value.code == "handoff_exists"
    assert path.read_text(encoding="utf-8") == original


def test_create_handoffs_rejects_tampered_reuse_packet(tmp_path):
    wave, _assigned = _assigned_wave(tmp_path)
    first = create_handoffs(tmp_path, wave_id=wave["id"])
    path = Path(first["handoffs"][0]["path"])
    packet = json.loads(path.read_text(encoding="utf-8"))
    packet["task_id"] = "tampered"
    path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(FlywheelError) as excinfo:
        create_handoffs(tmp_path, wave_id=wave["id"])

    assert excinfo.value.code == "handoff_integrity_mismatch"


def test_create_handoffs_rejects_state_path_outside_handoffs_dir(tmp_path):
    wave, _assigned = _assigned_wave(tmp_path)
    create_handoffs(tmp_path, wave_id=wave["id"])
    outside = tmp_path / "outside.json"
    outside.write_text("{}\n", encoding="utf-8")
    store = StateStore.for_cwd(tmp_path)
    state = store.load()
    state["handoffs"][0]["path"] = str(outside)
    store.save(state)

    with pytest.raises(FlywheelError) as excinfo:
        create_handoffs(tmp_path, wave_id=wave["id"])

    assert excinfo.value.code == "handoff_path_invalid"


def test_create_handoffs_rejects_state_packet_hash_mismatch(tmp_path):
    wave, _assigned = _assigned_wave(tmp_path)
    create_handoffs(tmp_path, wave_id=wave["id"])
    store = StateStore.for_cwd(tmp_path)
    state = store.load()
    state["handoffs"][0]["packetHash"] = "wrong"
    store.save(state)

    with pytest.raises(FlywheelError) as excinfo:
        create_handoffs(tmp_path, wave_id=wave["id"])

    assert excinfo.value.code == "handoff_integrity_mismatch"


def test_create_handoffs_validates_assignment_inputs_and_references(tmp_path):
    with pytest.raises(FlywheelError) as excinfo:
        create_handoffs(tmp_path)
    assert excinfo.value.code == "handoff_no_assignments"

    wave, assigned = _assigned_wave(tmp_path)

    with pytest.raises(FlywheelError) as excinfo:
        create_handoffs(tmp_path, assignment_ids="assignment-1")
    assert excinfo.value.code == "handoff_invalid_assignment_ids"

    with pytest.raises(FlywheelError) as excinfo:
        create_handoffs(tmp_path, assignment_ids=["missing"])
    assert excinfo.value.code == "handoff_unknown_assignment"

    store = StateStore.for_cwd(tmp_path)
    state = store.load()
    state["workers"] = []
    store.save(state)
    skipped = create_handoffs(tmp_path, assignment_ids=[assigned["assignments"][0]["id"]])
    assert skipped["skipped"] == 1
    assert skipped["results"][0]["reason"] == "missing_reference"
    assert skipped["events"][0]["kind"] == "handoff_skipped"


def test_handoff_filename_is_collision_resistant_for_similar_assignment_ids():
    one = {"id": "a/b", "task_id": "task", "wave_id": "wave", "worker_id": "worker"}
    two = {"id": "a?b", "task_id": "task", "wave_id": "wave", "worker_id": "worker"}

    assert handoff_filename(one) != handoff_filename(two)


def test_handoff_packet_hash_excludes_packet_hash_field(tmp_path):
    wave, _assigned = _assigned_wave(tmp_path)
    result = create_handoffs(tmp_path, wave_id=wave["id"])
    packet = result["results"][0]["packet"]
    packet_hash = packet.pop("packetHash")

    import hashlib

    assert hashlib.sha256(canonical_json(packet).encode("utf-8")).hexdigest() == packet_hash


def test_observe_reports_handoff_summary(tmp_path):
    wave, _assigned = _assigned_wave(tmp_path)
    create_handoffs(tmp_path, wave_id=wave["id"])

    observation = observe(tmp_path)

    assert observation["handoffs"]["total"] == 1
    assert observation["handoffs"]["by_wave"] == {wave["id"]: 1}


def test_create_handoffs_handler_returns_json(tmp_path):
    wave, _assigned = _assigned_wave(tmp_path)
    ctx = FakeContext()
    register(ctx)
    handler = next(tool["handler"] for tool in ctx.tools if tool["name"] == "hermes_flywheel_create_handoffs")

    response = json.loads(handler({"cwd": str(tmp_path), "wave_id": wave["id"]}))

    assert response["ok"] is True
    assert response["created"] == 1
    assert response["handoffs"][0]["task_id"] == "a"


def test_handoff_creation_does_not_hide_task_status_changes(tmp_path):
    wave, _assigned = _assigned_wave(tmp_path)
    update_task(tmp_path, "a", status="blocked", blocker="manual")

    create_handoffs(tmp_path, wave_id=wave["id"])

    state = StateStore.for_cwd(tmp_path).load()
    assert state["task_graph"]["tasks"][0]["status"] == "blocked"
    assert state["completion_reports"] == []
