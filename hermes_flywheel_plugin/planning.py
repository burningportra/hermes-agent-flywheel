"""Planning and task creation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .state import StateStore, utc_now
from .task_graph import create_task_graph


def make_plan(goal: str, cwd: str | Path | None = None) -> dict[str, Any]:
    goal = str(goal or "").strip() or "Improve repository using the Hermes flywheel loop."
    root = Path(cwd or Path.cwd()).resolve()
    plan = {
        "goal": goal,
        "created_at": utc_now(),
        "steps": [
            "Observe repository state and constraints.",
            "Create a minimal task graph with safe local tasks.",
            "Advance one wave at a time and record completion reports.",
            "Review outcomes before selecting the next wave.",
        ],
    }
    store = StateStore.for_cwd(root)
    state = store.load()
    state.setdefault("plans", []).append(plan)
    store.save(state)
    return plan


def create_tasks(tasks: list[dict[str, Any]], cwd: str | Path | None = None) -> dict[str, Any]:
    graph = create_task_graph(tasks)
    store = StateStore.for_cwd(cwd)
    state = store.load()
    state["task_graph"] = graph
    store.save(state)
    return graph


def scaffold_tasks_for_goal(goal: str) -> list[dict[str, Any]]:
    goal = str(goal or "Hermes flywheel goal").strip()
    return [
        {"id": "observe", "title": f"Observe context for: {goal}", "description": "Gather repo profile and constraints."},
        {"id": "plan", "title": "Create task graph", "description": "Turn the goal into ordered tasks.", "depends_on": ["observe"]},
        {"id": "review", "title": "Review completion reports", "description": "Validate work and decide the next wave.", "depends_on": ["plan"]},
    ]
