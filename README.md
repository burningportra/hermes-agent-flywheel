# hermes-agent-flywheel

Hermes Agent Flywheel is a local-first Hermes plugin for an agent-flywheel/pi-orchestrator style workflow loop.

v0.3 keeps the runtime stdlib-only and adds integrity-backed checkpoints plus standalone task verification so parent agents can verify one wave before starting the next.

Product truth for this scaffold:

- Local-first and safe by default.
- Python stdlib only at runtime.
- Stores state as JSON under `.hermes-flywheel/` in the current working directory.
- Provides observation, repo profiling, planning/task graph creation, task lifecycle updates, evidence-gated wave advancement, standalone task verification, integrity checkpoints, review/completion reporting, doctor checks, and packaged skill text loading.
- Does not spawn agents or call external services during normal tool handling; repository hosting/remotes are managed outside the plugin.
- Intended to be commit-worthy scaffolding, not a complete production orchestrator.

## v0.3 capabilities

- Integrity-backed canonical checkpoint: `hermes_flywheel_checkpoint` writes `.hermes-flywheel/checkpoint.json` with `schemaVersion`, `writtenAt`, `flywheelVersion`, optional `gitHead`, embedded `state`, and `stateHash` as SHA-256 over canonical JSON state. Historical raw snapshots remain under `.hermes-flywheel/checkpoints/` for compatibility.
- Standalone verification: `hermes_flywheel_verify_tasks` is read-only and verifies requested tasks, or the active started wave by default, against task status, latest successful completion report state, and matching completion report files.

## v0.2 capabilities

- Evidence-gated waves: `hermes_flywheel_advance_wave` refuses to select a new wave if an earlier `started` wave has any task that is not both `done` and backed by that task's latest `success` completion report. Pass `force: true` only for explicit operator override.
- Completion report files: successful reports are appended to state and atomically written to `.hermes-flywheel/completion/<task_id>.json`.
- Richer completion report schema: `task_id`, `outcome`, `summary`, `changed_files`, `verification`, optional `self_review`, optional `reservations_released`, optional `artifacts`, and `created_at`. Existing artifacts-only report use remains supported.
- Task lifecycle updates: `hermes_flywheel_update_task` updates task `status` plus optional `notes` and `blocker` fields.
- Observe/doctor awareness: observation includes blocked wave details when present; doctor reports incomplete active waves and completion report directory status.
- Packaged skills: skill documents are included as package data under `hermes_flywheel_plugin/skills/` while retaining compatibility with the repo-level `skills/` fallback.

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
- `hermes_flywheel_plugin/doctor.py` - environment and state checks.
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

## Tool names registered in v0.3

- `hermes_flywheel_observe`
- `hermes_flywheel_profile`
- `hermes_flywheel_plan`
- `hermes_flywheel_create_tasks`
- `hermes_flywheel_update_task`
- `hermes_flywheel_advance_wave`
- `hermes_flywheel_review`
- `hermes_flywheel_doctor`
- `hermes_flywheel_checkpoint`
- `hermes_flywheel_verify_tasks`
- `hermes_flywheel_get_skill`

Handlers return JSON strings for Hermes compatibility.

## State, reports, and checkpoints

State lives in `.hermes-flywheel/state.json` below the active working directory. The canonical checkpoint is written atomically to `.hermes-flywheel/checkpoint.json`; compatibility snapshots are written to `.hermes-flywheel/checkpoints/`.

Completion reports are the handoff record for finished tasks and must include `task_id`, `outcome`, and `summary`. Successful completion reports also produce an atomic disk copy under `.hermes-flywheel/completion/`.

Checkpoint contract:

- Mutating tools persist local JSON state before returning a success response.
- Checkpoints include an integrity envelope whose `stateHash` is the SHA-256 of canonical JSON state; validation detects missing, invalid JSON, and hash-mismatched checkpoints.
- A wave is considered complete only when each wave task has status `done` and its latest completion report has outcome `success`.
- Tool handlers return structured JSON strings so Hermes can surface either `ok` results or normalized errors.

## Roadmap

- Keep the plugin local-first while tightening Hermes plugin compatibility.
- Add richer planning heuristics and dependency validation without introducing network side effects by default.
- Expand review/checkpoint workflows so parent agents can reliably verify task completion between waves.
- Document optional integrations, including GitHub remotes/CI, as external project operations rather than hidden plugin behavior.

## Current limitations

- No background agent execution.
- No network calls.
- Planning heuristics are intentionally simple and deterministic.
