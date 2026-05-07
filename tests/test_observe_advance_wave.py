from hermes_flywheel_plugin.advance_wave import advance_wave
from hermes_flywheel_plugin.observe import observe
from hermes_flywheel_plugin.planning import create_tasks
from hermes_flywheel_plugin.state import StateStore


def test_observe_persists_observation(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    observation = observe(tmp_path, note="start")

    assert observation["note"] == "start"
    assert observation["profile"]["markers"] == ["pyproject.toml"]
    state = StateStore.for_cwd(tmp_path).load()
    assert len(state["observations"]) == 1


def test_advance_wave_respects_dependencies(tmp_path):
    create_tasks(
        [
            {"id": "a", "title": "A"},
            {"id": "b", "title": "B", "depends_on": ["a"]},
        ],
        tmp_path,
    )

    first = advance_wave(tmp_path, limit=5)
    assert [task["id"] for task in first["tasks"]] == ["a"]

    state = StateStore.for_cwd(tmp_path).load()
    assert state["task_graph"]["tasks"][0]["status"] == "in_progress"
    assert state["waves"][0]["status"] == "started"
