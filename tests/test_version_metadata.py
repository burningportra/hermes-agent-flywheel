import re
from pathlib import Path

from hermes_flywheel_plugin.state import FLYWHEEL_VERSION


ROOT = Path(__file__).resolve().parent.parent


def _extract_version(text: str) -> str:
    match = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', text, flags=re.MULTILINE)
    assert match is not None
    return match.group(1)


def test_package_plugin_and_checkpoint_versions_stay_in_sync():
    pyproject_version = _extract_version((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    plugin_text = (ROOT / "hermes_flywheel_plugin" / "plugin.yaml").read_text(encoding="utf-8")
    plugin_match = re.search(r"^version:\s*([^\n]+)", plugin_text, flags=re.MULTILINE)
    assert plugin_match is not None
    plugin_version = plugin_match.group(1).strip().strip('"\'')

    assert pyproject_version == plugin_version == FLYWHEEL_VERSION
