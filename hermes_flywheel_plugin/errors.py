"""Structured errors for hermes-agent-flywheel."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class FlywheelError(Exception):
    """A JSON-serializable operational error."""

    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


def ok(payload: dict[str, Any]) -> str:
    return json.dumps({"ok": True, **payload}, sort_keys=True)


def error_json(exc: Exception) -> str:
    if isinstance(exc, FlywheelError):
        return exc.to_json()
    return FlywheelError(
        code="unexpected_error",
        message=str(exc),
        details={"type": exc.__class__.__name__},
    ).to_json()
