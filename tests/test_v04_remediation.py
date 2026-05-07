import json

from hermes_flywheel_plugin import register
from hermes_flywheel_plugin.advance_wave import advance_wave
from hermes_flywheel_plugin.doctor import run_doctor
from hermes_flywheel_plugin.planning import create_tasks
from hermes_flywheel_plugin.remediate import remediate
from hermes_flywheel_plugin.state import StateStore


class FakeContext:
    def __init__(self):
        self.tools = []

    def register_tool(self, name, toolset, schema, handler, description):
        self.tools.append(
            {
                "name": name,
                "toolset": toolset,
                "schema": schema,
                "handler": handler,
                "description": description,
            }
        )


def test_doctor_v2_reports_structured_checks_and_remediations(tmp_path):
    doctor = run_doctor(tmp_path)

    assert doctor["schemaVersion"] == 2
    assert doctor["ok"] is False
    assert {check["name"] for check in doctor["checks"]} >= {
        "state_dir",
        "completion_report_dir",
        "checkpoints_dir",
        "checkpoint_valid",
    }
    assert all("severity" in check and "category" in check for check in doctor["checks"])
    remediation_ids = [item["id"] for item in doctor["remediations"]]
    assert remediation_ids == [
        "ensure_state_dir",
        "write_missing_checkpoint",
        "ensure_completion_report_dir",
        "ensure_checkpoints_dir",
    ]


def test_remediate_dry_run_default_makes_no_writes(tmp_path):
    result = remediate(tmp_path)

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert not (tmp_path / ".hermes-flywheel").exists()
    assert all(item["applied"] is False for item in result["results"])
    assert any(item.get("would_apply") for item in result["results"])


def test_remediate_apply_creates_dirs_and_checkpoint(tmp_path):
    result = remediate(tmp_path, dry_run=False)
    store = StateStore.for_cwd(tmp_path)

    assert result["ok"] is True
    assert store.state_dir.is_dir()
    assert (store.state_dir / "completion").is_dir()
    assert store.checkpoints_dir.is_dir()
    assert store.checkpoint_path.is_file()
    assert store.validate_checkpoint()["ok"] is True
    assert any(item["id"] == "write_missing_checkpoint" and item["applied"] for item in result["results"])


def test_remediate_skips_operator_action_for_incomplete_wave(tmp_path):
    create_tasks([{"id": "a", "title": "A"}], tmp_path)
    advance_wave(tmp_path, limit=1)

    doctor = run_doctor(tmp_path)
    assert any(item["id"] == "resolve_incomplete_started_wave" for item in doctor["remediations"])

    result = remediate(tmp_path, dry_run=False)
    operator = next(item for item in result["results"] if item["id"] == "resolve_incomplete_started_wave")
    assert operator["ok"] is True
    assert operator["skipped"] is True
    assert operator["reason"] == "operator_action_required"


def test_remediate_unknown_action_returns_structured_error(tmp_path):
    result = remediate(tmp_path, actions=["not_a_real_action"], dry_run=False)

    assert result["ok"] is False
    assert result["results"][0]["error"]["code"] == "unknown_remediation_action"
    assert result["results"][0]["error"]["details"]["id"] == "not_a_real_action"


def test_remediate_rejects_custom_or_outside_directory_writes(tmp_path):
    outside = tmp_path.parent / "outside-repo"
    custom = remediate(
        tmp_path,
        actions=[{"id": "custom", "action": "ensure_directory", "path": "safe-looking", "safe": True}],
        dry_run=False,
    )
    assert custom["ok"] is False
    assert custom["results"][0]["error"]["code"] == "unknown_remediation_action"
    assert not (tmp_path / "safe-looking").exists()

    outside_result = remediate(
        tmp_path,
        actions=[{"id": "ensure_state_dir", "action": "ensure_directory", "path": "../outside-repo", "safe": True}],
        dry_run=False,
    )
    assert outside_result["ok"] is True
    assert (tmp_path / ".hermes-flywheel").is_dir()
    assert not outside.exists()


def test_remediate_never_applies_unsafe_actions_even_when_included(tmp_path):
    result = remediate(
        tmp_path,
        actions=[{"id": "resolve_incomplete_started_wave", "action": "ensure_directory", "path": ".hermes-flywheel", "safe": True}],
        dry_run=False,
        include_unsafe=True,
    )
    assert result["ok"] is True
    assert result["results"][0]["skipped"] is True
    assert result["results"][0]["reason"] == "operator_action_required"
    assert not (tmp_path / ".hermes-flywheel").exists()


def test_known_remediation_dict_cannot_override_trusted_execution_fields(tmp_path):
    result = remediate(
        tmp_path,
        actions=[{"id": "ensure_state_dir", "action": "ensure_directory", "path": "unexpected-custom-dir", "safe": True}],
        dry_run=False,
    )
    assert result["ok"] is True
    assert (tmp_path / ".hermes-flywheel").is_dir()
    assert not (tmp_path / "unexpected-custom-dir").exists()


def test_remediate_handler_registration_and_dry_run(tmp_path):
    ctx = FakeContext()
    register(ctx)
    tool = next(tool for tool in ctx.tools if tool["name"] == "hermes_flywheel_remediate")

    assert tool["schema"]["properties"]["dry_run"]["type"] == "boolean"
    payload = json.loads(tool["handler"]({"cwd": str(tmp_path)}))

    assert payload["ok"] is True
    assert payload["remediation"]["dry_run"] is True
    assert not (tmp_path / ".hermes-flywheel").exists()
