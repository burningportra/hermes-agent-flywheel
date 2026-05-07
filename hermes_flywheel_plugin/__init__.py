"""Hermes plugin entrypoint for hermes-agent-flywheel."""

from __future__ import annotations

from typing import Any, Callable

from .advance_wave import advance_wave
from .assignment import assign_wave
from .completion_report import record_completion_report
from .doctor import run_doctor
from .errors import error_json, ok
from .handoff import create_handoffs
from .observe import observe
from .planning import create_tasks, make_plan, scaffold_tasks_for_goal
from .profile import build_repo_profile
from .remediate import remediate
from .schemas import (
    ADVANCE_WAVE_SCHEMA,
    ASSIGN_WAVE_SCHEMA,
    CHECKPOINT_SCHEMA,
    CREATE_HANDOFFS_SCHEMA,
    CREATE_TASKS_SCHEMA,
    CREATE_WORKER_SCHEMA,
    DOCTOR_SCHEMA,
    GET_SKILL_SCHEMA,
    LIST_WORKERS_SCHEMA,
    OBSERVE_SCHEMA,
    PLAN_SCHEMA,
    PROFILE_SCHEMA,
    REMEDIATE_SCHEMA,
    REVIEW_SCHEMA,
    UPDATE_TASK_SCHEMA,
    UPDATE_WORKER_SCHEMA,
    VERIFY_TASKS_SCHEMA,
)
from .skills_bundle import get_skill
from .state import StateStore
from .task_lifecycle import update_task
from .verification import verify_tasks
from .worker_runtime import create_worker, list_workers, update_worker

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


def _create_worker(args: dict[str, Any]) -> dict[str, Any]:
    return create_worker(args.get("cwd"), args.get("task_id"), args.get("wave_id"), args.get("name", ""), args.get("runtime", "noop"), args.get("metadata"))


def _update_worker(args: dict[str, Any]) -> dict[str, Any]:
    return update_worker(args.get("cwd"), args.get("worker_id", ""), args.get("action", ""), args.get("message"), args.get("data"))


def _list_workers(args: dict[str, Any]) -> dict[str, Any]:
    return list_workers(args.get("cwd"), args.get("status"), args.get("task_id"), args.get("wave_id"))


def _assign_wave(args: dict[str, Any]) -> dict[str, Any]:
    return assign_wave(
        args.get("cwd"),
        args.get("wave_id", ""),
        args.get("runtime", "noop"),
        args.get("worker_name_prefix", "noop"),
        args.get("metadata"),
    )


def _create_handoffs(args: dict[str, Any]) -> dict[str, Any]:
    return create_handoffs(
        args.get("cwd"),
        args.get("assignment_ids"),
        args.get("wave_id", ""),
        args.get("reuse_existing", True),
        args.get("constraints"),
        args.get("evidence_requirements"),
        args.get("resume_metadata"),
    )


def _review(args: dict[str, Any]) -> dict[str, Any]:
    return {"completion_report": record_completion_report(args.get("report", {}), args.get("cwd"))}


def _doctor(args: dict[str, Any]) -> dict[str, Any]:
    return {"doctor": run_doctor(args.get("cwd"))}


def _remediate(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "remediation": remediate(
            args.get("cwd"),
            args.get("actions"),
            args.get("dry_run", True),
            args.get("include_unsafe", False),
        )
    }


def _get_skill(args: dict[str, Any]) -> dict[str, Any]:
    return {"skill": get_skill(args.get("name", ""))}


def _checkpoint(args: dict[str, Any]) -> dict[str, Any]:
    return {"checkpoint": StateStore.for_cwd(args.get("cwd")).checkpoint(args.get("label", "manual"))}


def _verify_tasks(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "verification": verify_tasks(
            args.get("cwd"),
            args.get("task_ids"),
            args.get("require_evidence", True),
        )
    }


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
    ctx.register_tool("hermes_flywheel_create_worker", TOOLSET, CREATE_WORKER_SCHEMA, _handler(_create_worker), "Create a state-backed no-op worker record without spawning processes.")
    ctx.register_tool("hermes_flywheel_update_worker", TOOLSET, UPDATE_WORKER_SCHEMA, _handler(_update_worker), "Advance a no-op worker lifecycle and append a worker event.")
    ctx.register_tool("hermes_flywheel_list_workers", TOOLSET, LIST_WORKERS_SCHEMA, _handler(_list_workers), "List state-backed no-op workers and recent events.")
    ctx.register_tool("hermes_flywheel_assign_wave", TOOLSET, ASSIGN_WAVE_SCHEMA, _handler(_assign_wave), "Create or reuse no-op worker records for assignable tasks in a wave without spawning anything.")
    ctx.register_tool("hermes_flywheel_create_handoffs", TOOLSET, CREATE_HANDOFFS_SCHEMA, _handler(_create_handoffs), "Create immutable local worker handoff packets from existing assignments without spawning anything.")
    ctx.register_tool("hermes_flywheel_review", TOOLSET, REVIEW_SCHEMA, _handler(_review), "Validate and record a completion report.")
    ctx.register_tool("hermes_flywheel_doctor", TOOLSET, DOCTOR_SCHEMA, _handler(_doctor), "Run local health checks for the flywheel plugin state.")
    ctx.register_tool("hermes_flywheel_remediate", TOOLSET, REMEDIATE_SCHEMA, _handler(_remediate), "Dry-run or apply safe local doctor remediations.")
    ctx.register_tool("hermes_flywheel_checkpoint", TOOLSET, CHECKPOINT_SCHEMA, _handler(_checkpoint), "Write an integrity-backed canonical local checkpoint.")
    ctx.register_tool("hermes_flywheel_verify_tasks", TOOLSET, VERIFY_TASKS_SCHEMA, _handler(_verify_tasks), "Read-only verification of task completion and evidence files.")
    ctx.register_tool("hermes_flywheel_get_skill", TOOLSET, GET_SKILL_SCHEMA, _handler(_get_skill), "Load a bundled flywheel skill document.")
