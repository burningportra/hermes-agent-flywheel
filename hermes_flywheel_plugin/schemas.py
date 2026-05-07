"""Lightweight Hermes tool schemas for the MVP."""

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
    "properties": {"cwd": {"type": "string"}, "limit": {"type": "integer"}, "start": {"type": "boolean"}},
}

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "cwd": {"type": "string"},
        "report": {"type": "object"},
    },
    "required": ["report"],
}

DOCTOR_SCHEMA = {"type": "object", "properties": {"cwd": {"type": "string"}}}

GET_SKILL_SCHEMA = {
    "type": "object",
    "properties": {"name": {"type": "string", "enum": ["start", "planning", "review"]}},
    "required": ["name"],
}
