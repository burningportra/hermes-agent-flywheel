from hermes_flywheel_plugin.advance_wave import advance_wave
from hermes_flywheel_plugin.planning import create_tasks
from hermes_flywheel_plugin.state import StateStore
from hermes_flywheel_plugin.status import flywheel_status


def test_status_is_read_only_and_recommends_initial_observation(tmp_path):
    result = flywheel_status(tmp_path)

    assert result["state"]["exists"] is False
    assert result["counts"]["tasks"] == 0
    assert result["next_tool"] == "hermes_flywheel_observe"
    assert result["integration_contract"]["hidden_runtime"] is False
    assert not (tmp_path / ".hermes-flywheel").exists()


def test_status_summarizes_started_wave_for_external_orchestration(tmp_path):
    create_tasks(
        [
            {"id": "setup", "title": "Set up"},
            {"id": "feature", "title": "Build feature", "depends_on": ["setup"]},
        ],
        tmp_path,
    )
    advance_wave(tmp_path, limit=1)
    store = StateStore.for_cwd(tmp_path)
    before = store.state_path.read_text(encoding="utf-8")

    result = flywheel_status(tmp_path)

    after = store.state_path.read_text(encoding="utf-8")
    assert after == before
    assert result["counts"]["tasks"] == 2
    assert result["tasks_by_status"]["in_progress"] == 1
    assert result["waves_by_status"]["started"] == 1
    assert result["blocked_wave"]["wave_id"] == "wave-1"
    assert result["blocked_wave"]["incomplete_task_ids"] == ["setup"]
    assert result["exportable_wave"]["wave_id"] == "wave-1"
    assert result["next_tool"] == "hermes_flywheel_export_wave"
