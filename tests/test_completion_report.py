from hermes_flywheel_plugin.completion_report import record_completion_report, validate_completion_report
from hermes_flywheel_plugin.planning import create_tasks
from hermes_flywheel_plugin.state import StateStore


def test_completion_report_validation():
    report = validate_completion_report({"task_id": "a", "outcome": "success", "summary": "done", "artifacts": ["x"]})
    assert report["task_id"] == "a"
    assert report["outcome"] == "success"


def test_record_completion_marks_task_done(tmp_path):
    create_tasks([{"id": "a", "title": "A"}], tmp_path)
    record_completion_report({"task_id": "a", "outcome": "success", "summary": "done"}, tmp_path)

    state = StateStore.for_cwd(tmp_path).load()
    assert state["task_graph"]["tasks"][0]["status"] == "done"
    assert state["completion_reports"][0]["summary"] == "done"
