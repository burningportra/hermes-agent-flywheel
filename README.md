# hermes-agent-flywheel

Hermes Agent Flywheel is a local-first Hermes plugin for repository observation, profiling, planning, task/wave state, checkpoints, doctor/remediate, and review workflows.

Product truth for this scaffold:

- Local-first and safe by default.
- Python stdlib only at runtime.
- Stores state as JSON under `.hermes-flywheel/` in the current working directory.
- Provides observation, repo profiling, planning/task graph creation, task lifecycle updates, evidence-gated wave advancement, standalone task verification, integrity checkpoints, review/completion reporting, doctor checks, safe remediation, and packaged skill text loading.
- Does not run background execution substrate or call external services during normal tool handling.
- Repository hosting/remotes are managed outside the plugin.

## Current capabilities

- Observation/profile: inspect the target repository and persist local observations/profiles.
- Planning/tasks: generate a simple plan, create task graphs, and update task status/notes/blockers.
- Waves: advance the next ready task wave while blocking on incomplete prior started waves unless explicitly forced.
- Review/completion: validate completion reports and atomically persist successful task evidence under `.hermes-flywheel/completion/`.
- Verification: read-only task verification against task status and matching completion report evidence.
- Checkpoints: write integrity-backed canonical checkpoints plus historical state snapshots.
- Doctor/remediate: report local health checks and apply safe, dry-run-first filesystem/checkpoint remediations.
- Skills: load bundled `start`, `planning`, and `review` skill documents.

## Repository layout

- `hermes_flywheel_plugin/plugin.yaml` - Hermes plugin metadata.
- `hermes_flywheel_plugin/__init__.py` - `register(ctx)` entrypoint and JSON-string tool handlers.
- `hermes_flywheel_plugin/state.py` - JSON state store and integrity-backed atomic checkpoints.
- `hermes_flywheel_plugin/errors.py` - structured `FlywheelError` responses.
- `hermes_flywheel_plugin/profile.py` - local repository profile builder.
- `hermes_flywheel_plugin/task_graph.py` - task graph model and transitions.
- `hermes_flywheel_plugin/task_lifecycle.py` - task status/notes/blocker updates.
- `hermes_flywheel_plugin/completion_report.py` - completion report validation and atomic success report files.
- `hermes_flywheel_plugin/observe.py` - local repo observation.
- `hermes_flywheel_plugin/doctor.py` - environment/state checks plus stable remediation recommendations.
- `hermes_flywheel_plugin/remediate.py` - dry-run-first safe local remediation actions.
- `hermes_flywheel_plugin/planning.py` - plan/task graph creation.
- `hermes_flywheel_plugin/advance_wave.py` - picks and advances the next wave of work with evidence gates.
- `hermes_flywheel_plugin/verification.py` - read-only task verification helper/tool contract.
- `hermes_flywheel_plugin/skills_bundle.py` - packaged skill text loader.
- `hermes_flywheel_plugin/skills/` - packaged starter skill documents.
- `skills/` - repo-level starter skill documents/fallback.
- `tests/` - pytest coverage.

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

## Tool names registered in v0.8

- `hermes_flywheel_observe`
- `hermes_flywheel_profile`
- `hermes_flywheel_plan`
- `hermes_flywheel_create_tasks`
- `hermes_flywheel_update_task`
- `hermes_flywheel_advance_wave`
- `hermes_flywheel_review`
- `hermes_flywheel_doctor`
- `hermes_flywheel_remediate`
- `hermes_flywheel_checkpoint`
- `hermes_flywheel_verify_tasks`
- `hermes_flywheel_get_skill`

Handlers return JSON strings for Hermes compatibility.

## State, reports, and checkpoints

State lives in `.hermes-flywheel/state.json` below the active working directory. The canonical checkpoint is written atomically to `.hermes-flywheel/checkpoint.json`; compatibility snapshots are written to `.hermes-flywheel/checkpoints/`.

Completion reports must include `task_id`, `outcome`, and `summary`. Successful completion reports also produce an atomic disk copy under `.hermes-flywheel/completion/`.

Checkpoint contract:

- Mutating tools persist local JSON state before returning a success response.
- Checkpoints include an integrity envelope whose `stateHash` is the SHA-256 of canonical JSON state; validation detects missing, invalid JSON, and hash-mismatched checkpoints.
- A wave is considered complete only when each wave task has status `done` and its latest completion report has outcome `success`.
- Tool handlers return structured JSON strings so Hermes can surface either `ok` results or normalized errors.

Remediation contract:

- `hermes_flywheel_remediate` is dry-run by default and must be called with `dry_run: false` to write anything.
- Safe actions are local-only state/completion/checkpoints directory creation and checkpoint writes via the state store.
- Unknown remediation ids return structured per-action errors; operator actions are reported as skipped.

## Current limitations

- No background agent execution.
- No background execution substrate.
- No network calls.
- Planning heuristics are intentionally simple and deterministic.
