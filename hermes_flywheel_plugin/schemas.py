"""Lightweight Hermes tool schemas for the flywheel plugin."""

OBSERVE_SCHEMA = {
    "type": "object",
    "properties": {"cwd": {"type": "string"}, "note": {"type": "string"}},
}

PROFILE_SCHEMA = {"type": "object", "properties": {"cwd": {"type": "string"}}}

PLAN_SCHEMA = {
    "type": "object",
    "properties": {"cwd": {"type": "string"}, "goal": {"type": "string"}},
}

CREATE_TASKS_SCHEMA = {
    "type": "object",
    "properties": {
        "cwd": {"type": "string"},
        "tasks": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["tasks"],
}

ADVANCE_WAVE_SCHEMA = {
    "type": "object",
    "properties": {
        "cwd": {"type": "string"},
        "limit": {"type": "integer"},
        "start": {"type": "boolean"},
        "force": {"type": "boolean"},
    },
}

UPDATE_TASK_SCHEMA = {
    "type": "object",
    "properties": {
        "cwd": {"type": "string"},
        "task_id": {"type": "string"},
        "status": {"type": "string", "enum": ["pending", "ready", "in_progress", "blocked", "done"]},
        "notes": {"type": "string"},
        "blocker": {"type": "string"},
    },
    "required": ["task_id"],
}

CREATE_WORKER_SCHEMA = {
    "type": "object",
    "properties": {
        "cwd": {"type": "string"},
        "task_id": {"type": "string"},
        "wave_id": {"type": "string"},
        "name": {"type": "string"},
        "runtime": {"type": "string", "enum": ["noop"]},
        "metadata": {"type": "object"},
    },
}

UPDATE_WORKER_SCHEMA = {
    "type": "object",
    "properties": {
        "cwd": {"type": "string"},
        "worker_id": {"type": "string"},
        "action": {"type": "string", "enum": ["start", "heartbeat", "idle", "complete", "fail", "stop"]},
        "message": {"type": "string"},
        "data": {"type": "object"},
    },
    "required": ["worker_id", "action"],
}

LIST_WORKERS_SCHEMA = {
    "type": "object",
    "properties": {
        "cwd": {"type": "string"},
        "status": {"type": "string", "enum": ["created", "running", "idle", "completed", "failed", "stopped"]},
        "task_id": {"type": "string"},
        "wave_id": {"type": "string"},
    },
}

ASSIGN_WAVE_SCHEMA = {
    "type": "object",
    "properties": {
        "cwd": {"type": "string"},
        "wave_id": {"type": "string"},
        "runtime": {"type": "string", "enum": ["noop"]},
        "worker_name_prefix": {"type": "string"},
        "metadata": {"type": "object"},
    },
}

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "cwd": {"type": "string"},
        "report": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "outcome": {"type": "string", "enum": ["success", "partial", "blocked", "failed"]},
                "summary": {"type": "string"},
                "changed_files": {"type": "array", "items": {"type": "string"}},
                "verification": {"type": "array", "items": {"type": "string"}},
                "self_review": {"type": "string"},
                "reservations_released": {"type": "boolean"},
                "artifacts": {"type": "array"},
                "created_at": {"type": "string"},
            },
        },
    },
    "required": ["report"],
}

DOCTOR_SCHEMA = {"type": "object", "properties": {"cwd": {"type": "string"}}}

REMEDIATE_SCHEMA = {
    "type": "object",
    "properties": {
        "cwd": {"type": "string"},
        "actions": {
            "type": "array",
            "items": {
                "oneOf": [
                    {"type": "string"},
                    {"type": "object"},
                ]
            },
        },
        "dry_run": {"type": "boolean"},
        "include_unsafe": {"type": "boolean"},
    },
}

CHECKPOINT_SCHEMA = {
    "type": "object",
    "properties": {"cwd": {"type": "string"}, "label": {"type": "string"}},
}

VERIFY_TASKS_SCHEMA = {
    "type": "object",
    "properties": {
        "cwd": {"type": "string"},
        "task_ids": {"type": "array", "items": {"type": "string"}},
        "require_evidence": {"type": "boolean"},
    },
}

GET_SKILL_SCHEMA = {
    "type": "object",
    "properties": {"name": {"type": "string", "enum": ["start", "planning", "review"]}},
    "required": ["name"],
}
