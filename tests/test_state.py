import json

from hermes_flywheel_plugin.state import StateStore


def test_state_save_load_and_checkpoint(tmp_path):
    store = StateStore.for_cwd(tmp_path)
    state = store.load()
    state["observations"].append({"note": "hello"})
    store.save(state)

    loaded = store.load()
    assert loaded["observations"] == [{"note": "hello"}]

    checkpoint = store.checkpoint("unit test")
    assert checkpoint["path"].endswith("unit-test.json")
    with open(checkpoint["path"], encoding="utf-8") as fh:
        payload = json.load(fh)
    assert payload["observations"] == [{"note": "hello"}]
