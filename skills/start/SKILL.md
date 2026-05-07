# Flywheel Start Skill

Use this skill when beginning a Hermes flywheel run.

1. Run `hermes_flywheel_doctor` for the working directory.
2. Run `hermes_flywheel_observe` with a short note describing the user's goal.
3. Run `hermes_flywheel_profile` to capture repository markers and language shape.
4. Create a plan with `hermes_flywheel_plan`.
5. Create tasks with `hermes_flywheel_create_tasks` or request scaffold tasks through planning.
6. Use `hermes_flywheel_advance_wave`, `hermes_flywheel_update_task`, `hermes_flywheel_review`, and `hermes_flywheel_verify_tasks` to move work through waves and evidence-gated completion.

Rules:

- Stay local-first.
- Do not spawn agents or external services from this plugin.
- Record structured completion reports for meaningful work.
- Use checkpoints and doctor/remediate to keep local state recoverable.
