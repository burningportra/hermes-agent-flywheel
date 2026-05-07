import importlib.util
from pathlib import Path

from hermes_flywheel_plugin.state import StateStore

ROOT = Path(__file__).resolve().parents[1]
OBSOLETE_MODULES = ("worker_runtime", "assignment", "handoff")
OBSOLETE_TOOLS = {
    "hermes_flywheel_create_worker",
    "hermes_flywheel_update_worker",
    "hermes_flywheel_list_workers",
    "hermes_flywheel_assign_wave",
    "hermes_flywheel_create_handoffs",
}
OBSOLETE_STATE_KEYS = {
    "workers",
    "worker_events",
    "assignments",
    "assignment_events",
    "handoffs",
    "handoff_events",
}


def test_obsolete_worker_assignment_handoff_files_are_absent():
    for module in OBSOLETE_MODULES:
        assert not (ROOT / "hermes_flywheel_plugin" / f"{module}.py").exists()
        assert importlib.util.find_spec(f"hermes_flywheel_plugin.{module}") is None


def test_obsolete_tools_are_not_registered_or_listed():
    class FakeContext:
        def __init__(self):
            self.tools = []

        def register_tool(self, name, toolset, schema, handler, description):
            self.tools.append({"name": name, "schema": schema})

    from hermes_flywheel_plugin import register

    ctx = FakeContext()
    register(ctx)
    registered = {tool["name"] for tool in ctx.tools}
    assert registered.isdisjoint(OBSOLETE_TOOLS)

    plugin_yaml = (ROOT / "hermes_flywheel_plugin" / "plugin.yaml").read_text(encoding="utf-8")
    for tool in OBSOLETE_TOOLS:
        assert tool not in plugin_yaml


def test_default_state_has_no_obsolete_orchestration_keys(tmp_path):
    state = StateStore.for_cwd(tmp_path).load()
    assert OBSOLETE_STATE_KEYS.isdisjoint(state)
