# Flywheel Review Skill

Use this skill after a wave reports completion.

Review checklist:

1. Confirm each report has `task_id`, `outcome`, and `summary`.
2. Check artifacts are local paths or concise evidence strings.
3. Mark successful tasks as done through `hermes_flywheel_review`.
4. Leave blocked work blocked with a clear note.
5. Run `hermes_flywheel_advance_wave` only after reviewing the prior wave.

Completion report outcomes are `success`, `partial`, `blocked`, or `failed`.
