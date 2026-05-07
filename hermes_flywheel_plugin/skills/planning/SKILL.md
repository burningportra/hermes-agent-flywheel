# Flywheel Planning Skill

Use this skill to turn an observed goal into a small task graph.

Task guidance:

- Keep task ids stable and human-readable.
- Express dependencies with `depends_on`.
- Prefer small tasks that can be reviewed independently.
- Avoid destructive operations unless the user explicitly requests them.
- Use checkpoints before risky local state transitions.

Suggested statuses:

- `pending` for future work.
- `ready` when dependencies are complete.
- `in_progress` once a wave starts.
- `blocked` when external input is required.
- `done` when a completion report validates success.
