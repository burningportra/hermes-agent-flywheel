"""Hermes plugin entrypoint for hermes-agent-flywheel."""

from __future__ import annotations

from typing import Any, Callable

from .advance_wave import advance_wave
from .completion_report import record_completion_report
from .doctor import run_doctor
from .errors import error_json, ok
from .observe import observe
from .planning import create_tasks, make_plan, scaffold_tasks_for_goal
from .profile import build_repo_profile
from .schemas import (
    ADVANCE_WAVE_SCHEMA,
    CREATE_TASKS_SCHEMA,
    DOCTOR_SCHEMA,
    GET_SKILL_SCHEMA,
    OBSERVE_SCHEMA,
    PLAN_SCHEMA,
    PROFILE_SCHEMA,
    REVIEW_SCHEMA,
    UPDATE_TASK_SCHEMA,
)
from .skills_bundle import get_skill
from .state import StateStore
from .task_lifecycle import update_task

TOOLSET = "hermes_flywheel"


def _args(payload: dict[str, Any] | None) -> dict[str, Any]:
    return payload or {}


def _handler(fn: Callable[[dict[str, Any]], dict[str, Any]]) -> Callable[[dict[str, Any] | None], str]:
    def wrapped(payload: dict[str, Any] | None = None) -> str:
        try:
            return ok(fn(_args(payload)))
        except Exception as exc:  # noqa: BLE001 - Hermes handlers return structured JSON errors
            return error_json(exc)

    return wrapped


def _observe(args: dict[str, Any]) -> dict[str, Any]:
    return {"observation": observe(args.get("cwd"), args.get("note", ""))}


def _profile(args: dict[str, Any]) -> dict[str, Any]:
    return {"profile": build_repo_profile(args.get("cwd"))}


def _plan(args: dict[str, Any]) -> dict[str, Any]:
    goal = args.get("goal", "")
    plan = make_plan(goal, args.get("cwd"))
    if args.get("create_scaffold_tasks", False):
        graph = create_tasks(scaffold_tasks_for_goal(goal), args.get("cwd"))
        return {"plan": plan, "task_graph": graph}
    return {"plan": plan}


def _create_tasks(args: dict[str, Any]) -> dict[str, Any]:
    return {"task_graph": create_tasks(args.get("tasks", []), args.get("cwd"))}


def _advance_wave(args: dict[str, Any]) -> dict[str, Any]:
    return advance_wave(args.get("cwd"), args.get("limit", 3), args.get("start", True), args.get("force", False))


def _update_task(args: dict[str, Any]) -> dict[str, Any]:
    return update_task(args.get("cwd"), args.get("task_id", ""), args.get("status"), args.get("notes"), args.get("blocker"))


def _review(args: dict[str, Any]) -> dict[str, Any]:
    return {"completion_report": record_completion_report(args.get("report", {}), args.get("cwd"))}


def _doctor(args: dict[str, Any]) -> dict[str, Any]:
    return {"doctor": run_doctor(args.get("cwd"))}


def _get_skill(args: dict[str, Any]) -> dict[str, Any]:
    return {"skill": get_skill(args.get("name", ""))}


def _checkpoint(args: dict[str, Any]) -> dict[str, Any]:
    return {"checkpoint": StateStore.for_cwd(args.get("cwd")).checkpoint(args.get("label", "manual"))}


def register(ctx: Any) -> None:
    """Register Hermes tools.

    Hermes calls this function with a plugin context that exposes register_tool.
    Handlers return JSON strings and perform only local filesystem state changes.
    """

    ctx.register_tool("hermes_flywheel_observe", TOOLSET, OBSERVE_SCHEMA, _handler(_observe), "Observe the local repo and append observation state.")
    ctx.register_tool("hermes_flywheel_profile", TOOLSET, PROFILE_SCHEMA, _handler(_profile), "Build and persist a lightweight local repository profile.")
    ctx.register_tool("hermes_flywheel_plan", TOOLSET, PLAN_SCHEMA, _handler(_plan), "Create a simple flywheel plan, optionally with scaffold tasks.")
    ctx.register_tool("hermes_flywheel_create_tasks", TOOLSET, CREATE_TASKS_SCHEMA, _handler(_create_tasks), "Create or replace the local flywheel task graph.")
    ctx.register_tool("hermes_flywheel_advance_wave", TOOLSET, ADVANCE_WAVE_SCHEMA, _handler(_advance_wave), "Select the next ready task wave; blocks on incomplete prior waves unless forced.")
    ctx.register_tool("hermes_flywheel_update_task", TOOLSET, UPDATE_TASK_SCHEMA, _handler(_update_task), "Update a task status plus optional lifecycle notes and blocker fields.")
    ctx.register_tool("hermes_flywheel_review", TOOLSET, REVIEW_SCHEMA, _handler(_review), "Validate and record a completion report.")
    ctx.register_tool("hermes_flywheel_doctor", TOOLSET, DOCTOR_SCHEMA, _handler(_doctor), "Run local health checks for the flywheel plugin state.")
    ctx.register_tool("hermes_flywheel_get_skill", TOOLSET, GET_SKILL_SCHEMA, _handler(_get_skill), "Load a bundled flywheel skill document.")
