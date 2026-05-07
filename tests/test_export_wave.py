import json

import pytest

from hermes_flywheel_plugin.errors import FlywheelError
from hermes_flywheel_plugin.export_wave import export_wave
from hermes_flywheel_plugin.planning import create_tasks
from hermes_flywheel_plugin.state import StateStore


def _seed_started_wave(tmp_path):
    create_tasks(
        [
            {"id": "setup", "title": "Set up", "description": "Prepare fixtures", "status": "done"},
            {
                "id": "feature",
                "title": "Build feature",
                "description": "Implement the user-visible change",
                "depends_on": ["setup"],
                "status": "in_progress",
                "notes": "Keep the public API stable.",
            },
        ],
        tmp_path,
    )
    store = StateStore.for_cwd(tmp_path)
    state = store.load()
    state["waves"] = [
        {"id": "wave-old", "status": "completed", "task_ids": ["setup"], "created_at": "2026-05-07T00:00:00+00:00"},
        {"id": "wave-1", "status": "started", "task_ids": ["feature"], "created_at": "2026-05-07T00:01:00+00:00"},
    ]
    store.save(state)
    return store


def test_export_wave_returns_json_content_without_writing_or_mutating_state(tmp_path):
    store = _seed_started_wave(tmp_path)
    before = store.state_path.read_text(encoding="utf-8")

    result = export_wave(tmp_path)

    after = store.state_path.read_text(encoding="utf-8")
    assert after == before
    assert result["wrote"] is False
    assert result["output_path"] is None
    assert not (tmp_path / ".hermes-flywheel" / "exports").exists()
    payload = json.loads(result["content"])
    assert payload["contract"] == "hermes-agent-flywheel.external_wave_export"
    assert payload["contract_version"] == "0.9"
    assert payload["wave"]["id"] == "wave-1"
    assert payload["tasks"][0]["id"] == "feature"
    assert payload["tasks"][0]["dependency_context"][0]["id"] == "setup"
    assert "evidence_contract" in payload


def test_export_wave_writes_markdown_atomically_to_explicit_path_inside_root(tmp_path):
    _seed_started_wave(tmp_path)

    result = export_wave(tmp_path, fmt="markdown", output_path=".hermes-flywheel/exports/wave-1.md")

    output = tmp_path / ".hermes-flywheel" / "exports" / "wave-1.md"
    assert result["wrote"] is True
    assert result["output_path"] == str(output.resolve())
    assert output.read_text(encoding="utf-8") == result["content"]
    assert "# Hermes Flywheel External Wave Export: wave-1" in result["content"]
    assert "## Evidence contract" in result["content"]


def test_export_wave_rejects_paths_outside_root(tmp_path):
    _seed_started_wave(tmp_path)

    with pytest.raises(FlywheelError) as excinfo:
        export_wave(tmp_path, output_path="../escape.json")

    assert excinfo.value.code == "export_path_outside_root"
    assert not (tmp_path.parent / "escape.json").exists()


def test_export_wave_validates_explicit_wave_status_and_format(tmp_path):
    _seed_started_wave(tmp_path)

    with pytest.raises(FlywheelError) as excinfo:
        export_wave(tmp_path, wave_id="wave-old")
    assert excinfo.value.code == "wave_not_exportable"

    with pytest.raises(FlywheelError) as excinfo:
        export_wave(tmp_path, fmt="yaml")
    assert excinfo.value.code == "export_invalid_format"


def test_export_wave_can_omit_evidence_contract(tmp_path):
    _seed_started_wave(tmp_path)

    result = export_wave(tmp_path, include_evidence_contract=False)

    payload = json.loads(result["content"])
    assert "evidence_contract" not in payload
