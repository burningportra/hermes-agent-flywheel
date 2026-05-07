import json

from hermes_flywheel_plugin import TOOLSET, register


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


def test_register_smoke_with_fake_context(tmp_path):
    ctx = FakeContext()

    register(ctx)

    names = {tool["name"] for tool in ctx.tools}
    assert names == {
        "hermes_flywheel_observe",
        "hermes_flywheel_profile",
        "hermes_flywheel_plan",
        "hermes_flywheel_create_tasks",
        "hermes_flywheel_advance_wave",
        "hermes_flywheel_update_task",
        "hermes_flywheel_review",
        "hermes_flywheel_doctor",
        "hermes_flywheel_get_skill",
    }
    assert all(tool["toolset"] == TOOLSET for tool in ctx.tools)
    assert all(callable(tool["handler"]) for tool in ctx.tools)
    assert all(tool["schema"]["type"] == "object" for tool in ctx.tools)
    assert all(tool["description"] for tool in ctx.tools)

    observe_tool = next(tool for tool in ctx.tools if tool["name"] == "hermes_flywheel_observe")
    payload = json.loads(observe_tool["handler"]({"cwd": str(tmp_path), "note": "smoke"}))
    assert payload["ok"] is True
    assert payload["observation"]["note"] == "smoke"
