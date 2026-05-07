# hermes-agent-flywheel

Hermes Agent Flywheel is a first MVP scaffold for a Hermes-native version of an agent-flywheel/pi-orchestrator style workflow loop.

Product truth for this scaffold:

- Local-first and safe by default.
- Python stdlib only at runtime.
- Stores state as JSON under `.hermes-flywheel/` in the current working directory.
- Provides observation, repo profiling, planning/task graph creation, wave advancement, review/completion reporting, doctor checks, and skill text loading.
- Does not spawn agents or call external services during normal tool handling; repository hosting/remotes are managed outside the plugin.
- Intended to be commit-worthy scaffolding, not a complete production orchestrator.

## Repository layout

- `hermes_flywheel_plugin/plugin.yaml` - Hermes plugin metadata.
- `hermes_flywheel_plugin/__init__.py` - `register(ctx)` entrypoint and tool handlers.
- `hermes_flywheel_plugin/state.py` - JSON state store and atomic checkpoints.
- `hermes_flywheel_plugin/errors.py` - structured `FlywheelError` responses.
- `hermes_flywheel_plugin/profile.py` - local repository profile builder.
- `hermes_flywheel_plugin/task_graph.py` - task graph model and transitions.
- `hermes_flywheel_plugin/completion_report.py` - completion report validation.
- `hermes_flywheel_plugin/observe.py` - local repo observation.
- `hermes_flywheel_plugin/doctor.py` - environment and state checks.
- `hermes_flywheel_plugin/planning.py` - plan/task graph creation.
- `hermes_flywheel_plugin/advance_wave.py` - picks and advances the next wave of work.
- `hermes_flywheel_plugin/skills_bundle.py` - skill text loader.
- `skills/` - starter skill documents.
- `tests/` - pytest coverage for MVP behavior.

## Install for Hermes development

Hermes plugins are Python directories containing `plugin.yaml` and `__init__.py` with a `register(ctx)` function.

For local Hermes use, symlink or copy the plugin package directory into your Hermes plugin directory:

```sh
mkdir -p ~/.hermes/plugins
ln -s /Volumes/1tb/Projects/hermes-agent-flywheel/hermes_flywheel_plugin ~/.hermes/plugins/hermes-flywheel
```

Then restart or reload Hermes Agent as appropriate for your environment.

## Development

```sh
cd /Volumes/1tb/Projects/hermes-agent-flywheel
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest
```

## Tool names registered by the MVP

- `hermes_flywheel_observe`
- `hermes_flywheel_profile`
- `hermes_flywheel_plan`
- `hermes_flywheel_create_tasks`
- `hermes_flywheel_advance_wave`
- `hermes_flywheel_review`
- `hermes_flywheel_doctor`
- `hermes_flywheel_get_skill`

Handlers return JSON strings for Hermes compatibility.

## State and checkpoints

State lives in `.hermes-flywheel/state.json` below the active working directory. Checkpoints are written atomically to `.hermes-flywheel/checkpoints/`.

Checkpoint contract:

- Mutating tools persist local JSON state before returning a success response.
- Checkpoints are immutable JSON snapshots of the current state, named from a human-readable label.
- Completion reports are the handoff record for finished tasks and must include `task_id`, `outcome`, and `summary`.
- Tool handlers return structured JSON strings so Hermes can surface either `ok` results or normalized errors.

## Roadmap

- Keep the MVP local-first while tightening Hermes plugin compatibility.
- Add richer planning heuristics and dependency validation without introducing network side effects by default.
- Expand review/checkpoint workflows so parent agents can reliably verify task completion between waves.
- Document optional integrations, including GitHub remotes/CI, as external project operations rather than hidden plugin behavior.

## Current limitations

- No background agent execution.
- No network calls.
- Planning heuristics are intentionally simple and deterministic.
