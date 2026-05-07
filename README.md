# hermes-agent-flywheel

Hermes Agent Flywheel is a local-first Hermes plugin for an agent-flywheel/pi-orchestrator style workflow loop.

v0.6 keeps the runtime stdlib-only and adds a safe wave-to-worker assignment contract: Hermes can now bridge selected task waves to reusable no-op worker records without spawning agents, processes, tmux panes, NTM sessions, or network services.

Product truth for this scaffold:

- Local-first and safe by default.
- Python stdlib only at runtime.
- Stores state as JSON under `.hermes-flywheel/` in the current working directory.
- Provides observation, repo profiling, planning/task graph creation, task lifecycle updates, no-op worker lifecycle records, wave-to-worker assignment records, evidence-gated wave advancement, standalone task verification, integrity checkpoints, review/completion reporting, doctor checks, safe remediation, and packaged skill text loading.
- Does not spawn agents or call external services during normal tool handling; repository hosting/remotes are managed outside the plugin.
- Intended to be commit-worthy scaffolding, not a complete production orchestrator.

## v0.6 capabilities

- Wave-to-worker assignment: `hermes_flywheel_assign_wave` creates or reuses state-backed no-op worker records for assignable tasks in a ready/started wave.
- Assignment contract: assignment records live in `.hermes-flywheel/state.json` under `assignments`, while append-only facts live under `assignment_events` with `assignment_created`, `assignment_reused`, and `assignment_skipped` event kinds.
- Safety boundary: assignment never spawns anything, never marks tasks `done`, and never creates completion evidence; worker completion remains only a worker lifecycle fact.
- Observation/doctor awareness: observation includes assignment summaries and doctor validates assignment state shape.

## v0.5 capabilities

- No-op worker runtime substrate: `hermes_flywheel_create_worker`, `hermes_flywheel_update_worker`, and `hermes_flywheel_list_workers` create state-backed worker records and append-only worker events without spawning processes or agents.
- Worker lifecycle contract: workers can move through `created`, `running`, `idle`, `completed`, `failed`, and `stopped`; terminal workers reject further mutation.
- Observation/doctor awareness: observation includes worker summary and recent events; doctor reports worker state shape plus stale active workers as `resolve_stale_worker` operator actions.

## v0.4 capabilities

- Doctor/remediate split: `hermes_flywheel_doctor` now returns `schemaVersion: 2`, severity/category on checks, and a stable ordered `remediations` list.
- Safe remediation workflow: `hermes_flywheel_remediate` defaults to `dry_run: true` and performs no writes. With `dry_run: false`, it can create `.hermes-flywheel/`, `.hermes-flywheel/completion/`, `.hermes-flywheel/checkpoints/`, and write/refresh/rewrite the canonical checkpoint through `StateStore.checkpoint`.
- Operator actions remain manual: incomplete started waves surface `resolve_incomplete_started_wave` as an operator action and remediation skips it rather than changing task or wave state.

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
- `hermes_flywheel_plugin/worker_runtime.py` - state-backed no-op worker records and append-only events.
- `hermes_flywheel_plugin/assignment.py` - safe wave-to-worker assignment records and append-only assignment events.
- `hermes_flywheel_plugin/completion_report.py` - completion report validation and atomic success report files.
- `hermes_flywheel_plugin/observe.py` - local repo observation.
- `hermes_flywheel_plugin/doctor.py` - environment and state checks plus stable remediation recommendations.
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

## Tool names registered in v0.6

- `hermes_flywheel_observe`
- `hermes_flywheel_profile`
- `hermes_flywheel_plan`
- `hermes_flywheel_create_tasks`
- `hermes_flywheel_update_task`
- `hermes_flywheel_create_worker`
- `hermes_flywheel_update_worker`
- `hermes_flywheel_list_workers`
- `hermes_flywheel_assign_wave`
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

Completion reports are the handoff record for finished tasks and must include `task_id`, `outcome`, and `summary`. Successful completion reports also produce an atomic disk copy under `.hermes-flywheel/completion/`.

Checkpoint contract:

- Mutating tools persist local JSON state before returning a success response.
- Checkpoints include an integrity envelope whose `stateHash` is the SHA-256 of canonical JSON state; validation detects missing, invalid JSON, and hash-mismatched checkpoints.
- A wave is considered complete only when each wave task has status `done` and its latest completion report has outcome `success`.
- Tool handlers return structured JSON strings so Hermes can surface either `ok` results or normalized errors.
- Worker records and worker events are state-backed no-op lifecycle facts only; v0.6 never spawns processes, agents, panes, or network services.
- Assignment records bridge a wave task to a no-op worker. Repeated assignment reuses an active worker for the same `(wave_id, task_id, runtime)` and appends an `assignment_reused` event instead of duplicating the record.
- Assignment skips non-assignable task statuses and never marks task completion or writes completion evidence; successful task completion still requires explicit task lifecycle update plus successful completion report evidence.

Remediation contract:

- `hermes_flywheel_remediate` is dry-run by default and must be called with `dry_run: false` to write anything.
- Safe actions are local-only directory creation and checkpoint writes via the state store.
- Unknown remediation ids return structured per-action errors; operator actions are reported as skipped.

## Roadmap

- Keep the plugin local-first while tightening Hermes plugin compatibility.
- Add richer planning heuristics and dependency validation without introducing network side effects by default.
- Expand review/checkpoint workflows so parent agents can reliably verify task completion between waves.
- Document optional integrations, including GitHub remotes/CI, as external project operations rather than hidden plugin behavior.

## Current limitations

- No background agent execution.
- No network calls.
- Planning heuristics are intentionally simple and deterministic.
