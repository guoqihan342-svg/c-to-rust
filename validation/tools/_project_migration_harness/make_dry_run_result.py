from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .build_ir import is_sha256


MAKE_OUTCOME_KIND = "project-migration-make-dry-run-runner-outcome"


@dataclass(frozen=True, slots=True)
class MakeDryRunExecution:
    stdout: bytes
    stderr: bytes
    returncode: int
    timed_out: bool
    command_started: bool
    cleanup_verified: bool
    plan_sha256: str
    command_sha256: str
    output_limit_exceeded: bool = False


@dataclass(frozen=True, slots=True)
class MakeDryRunOutcome:
    status: str
    blocker: str | None
    make_started: bool
    returncode: int | None
    timed_out: bool
    output_flooded: bool
    cleanup_verified: bool
    plan_sha256: str | None
    sandbox_sha256: str | None
    stdout: bytes | None = None
    stderr: bytes | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "artifact_kind": MAKE_OUTCOME_KIND,
            "status": self.status,
            "blocker": self.blocker,
            "make_started": self.make_started,
            "returncode": self.returncode,
            "timed_out": self.timed_out,
            "output_flooded": self.output_flooded,
            "cleanup_verified": self.cleanup_verified,
            "plan_sha256": self.plan_sha256,
            "sandbox_sha256": self.sandbox_sha256,
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
        }


def validate_successful_make_outcome(value: Any) -> MakeDryRunOutcome:
    if not isinstance(value, MakeDryRunOutcome):
        raise ValueError("make_runner_outcome_type_invalid")
    if (
        value.status != "ready" or value.blocker is not None
        or value.make_started is not True or value.returncode != 0
        or value.timed_out is not False or value.output_flooded is not False
        or value.cleanup_verified is not True or not is_sha256(value.plan_sha256)
        or not is_sha256(value.sandbox_sha256)
        or not isinstance(value.stdout, bytes) or not isinstance(value.stderr, bytes)
    ):
        raise ValueError("make_runner_outcome_not_successful")
    return value


__all__ = [
    "MakeDryRunExecution", "MakeDryRunOutcome", "validate_successful_make_outcome",
]
