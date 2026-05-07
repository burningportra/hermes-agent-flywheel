import json

from hermes_flywheel_plugin.completion_report import record_completion_report, safe_report_filename
from hermes_flywheel_plugin.planning import create_tasks
from hermes_flywheel_plugin.state import FLYWHEEL_VERSION, StateStore, canonical_state_hash
from hermes_flywheel_plugin.verification import verify_tasks


def test_checkpoint_writes_and_validates_canonical_envelope(tmp_path):
    store = StateStore.for_cwd(tmp_path)
    state = store.load()
    state["observations"].append({"note": "v03"})
    store.save(state)

    metadata = store.checkpoint("v03 contract")

    assert metadata["ok"] is True
    assert metadata["stateHash"] == canonical_state_hash(store.load())
    checkpoint_path = store.state_dir / "checkpoint.json"
    assert metadata["canonical_path"] == str(checkpoint_path)

    envelope = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert envelope["schemaVersion"] == 1
    assert envelope["flywheelVersion"] == FLYWHEEL_VERSION
    assert envelope["state"]["observations"] == [{"note": "v03"}]
    assert envelope["stateHash"] == canonical_state_hash(envelope["state"])

    validation = store.validate_checkpoint()
    assert validation["ok"] is True
    assert validation["stateHash"] == envelope["stateHash"]


def test_checkpoint_validation_detects_bad_json_and_hash(tmp_path):
    store = StateStore.for_cwd(tmp_path)
    store.save(store.load())
    store.checkpoint("valid")

    envelope = json.loads(store.checkpoint_path.read_text(encoding="utf-8"))
    envelope["state"]["observations"].append({"note": "tampered"})
    store.checkpoint_path.write_text(json.dumps(envelope), encoding="utf-8")
    bad_hash = store.validate_checkpoint()
    assert bad_hash["ok"] is False
    assert bad_hash["reason"] == "hash_mismatch"

    store.checkpoint_path.write_text("{not json", encoding="utf-8")
    bad_json = store.validate_checkpoint()
    assert bad_json["ok"] is False
    assert bad_json["reason"] == "invalid_json"


def test_verify_tasks_default_active_wave_success_and_evidence_contract(tmp_path):
    create_tasks([{"id": "a", "title": "A"}, {"id": "b", "title": "B"}], tmp_path)
    store = StateStore.for_cwd(tmp_path)
    state = store.load()
    state["waves"].append({"id": "wave-1", "status": "started", "task_ids": ["a", "b"]})
    store.save(state)

    record_completion_report({"task_id": "a", "outcome": "success", "summary": "done"}, tmp_path)
    pending = verify_tasks(tmp_path)
    assert pending["ok"] is False
    assert pending["verified"] == ["a"]
    assert pending["not_done"] == ["b"]
    assert pending["task_ids"] == ["a", "b"]

    record_completion_report({"task_id": "b", "outcome": "success", "summary": "done"}, tmp_path)
    verified = verify_tasks(tmp_path)
    assert verified["ok"] is True
    assert verified["verified"] == ["a", "b"]
    assert verified["missing_evidence"] == []
    assert verified["invalid_evidence"] == []

    report_path = store.state_dir / "completion" / f"{safe_report_filename('b')}.json"
    report_path.write_text(json.dumps({"task_id": "b", "outcome": "success", "summary": "tampered"}), encoding="utf-8")
    invalid = verify_tasks(tmp_path, ["b"])
    assert invalid["ok"] is False
    assert invalid["invalid_evidence"] == ["b"]


def test_verify_tasks_reports_unknown_and_missing_evidence(tmp_path):
    create_tasks([{"id": "a", "title": "A"}], tmp_path)
    record_completion_report({"task_id": "a", "outcome": "success", "summary": "done"}, tmp_path)
    report_path = StateStore.for_cwd(tmp_path).state_dir / "completion" / f"{safe_report_filename('a')}.json"
    report_path.unlink()

    result = verify_tasks(tmp_path, ["a", "missing"])

    assert result["ok"] is False
    assert result["verified"] == []
    assert result["missing_evidence"] == ["a"]
    assert result["unknown"] == ["missing"]
