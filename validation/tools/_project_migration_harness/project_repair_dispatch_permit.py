from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import content_sha256
from .project_preflight import (
    FIXED_AGENT, FIXED_COMMAND, FIXED_VARIANT,
    validate_project_worker_preflight,
)


_ISSUER = object()


class ProjectRepairDispatchPermit:
    __slots__ = ("_authority", "_binding")

    def __init__(self, authority: object, binding: dict[str, Any]) -> None:
        if authority is not _ISSUER:
            raise TypeError("project repair dispatch permits are host-issued")
        self._authority = authority
        self._binding = binding


def issue_project_repair_dispatch_permit(
    action: Mapping[str, Any], preflight_reference: Mapping[str, Any], *,
    harness_root: Path, run_id: str, logical_model: str,
    resolved_model: str,
) -> ProjectRepairDispatchPermit:
    if (
        action.get("status") != "preflight-required"
        or action.get("stage") != "project-repair-preflight-required"
        or action.get("run_id") != run_id
        or action.get("item_status") not in {"queued", "retry-ready"}
    ):
        raise ValueError("project repair dispatch permit action is not ready")
    preflight = validate_project_worker_preflight(
        preflight_reference, harness_root=harness_root, run_id=run_id,
        logical_model=logical_model, resolved_model=resolved_model,
        opencode_command=FIXED_COMMAND, agent=FIXED_AGENT,
        variant=FIXED_VARIANT,
    )
    reference = _reference(preflight_reference)
    payload = {
        "schema_version": 1,
        "run_id": run_id,
        "receipt_epoch": _positive_int(action.get("receipt_epoch")),
        "coordinator_receipt_sha256": _sha(
            action.get("coordinator_receipt_sha256")
        ),
        "project_repair_queue_sha256": _sha(
            action.get("project_repair_queue_sha256")
        ),
        "repair_id": _text(action.get("repair_id")),
        "expected_status": str(action["item_status"]),
        "expected_state_version": _nonnegative_int(action.get("state_version")),
        "recovered_attempts": _texts(action.get("recovered_attempts", [])),
        "preflight": reference,
        "logical_model": logical_model,
        "resolved_model": resolved_model,
        "agent_sha256": _sha(preflight.get("agent_sha256")),
        "runtime_input_sha256": _sha(preflight.get("runtime_input_sha256")),
        "proof_scope": str(preflight.get("proof_scope")),
    }
    binding = {**payload, "permit_sha256": content_sha256(payload)}
    return ProjectRepairDispatchPermit(_ISSUER, binding)


def project_repair_dispatch_binding(
    permit: ProjectRepairDispatchPermit,
) -> dict[str, Any]:
    if (
        type(permit) is not ProjectRepairDispatchPermit
        or permit._authority is not _ISSUER
    ):
        raise TypeError("project repair dispatch permit is not host-issued")
    binding = dict(permit._binding)
    payload = {key: value for key, value in binding.items() if key != "permit_sha256"}
    if content_sha256(payload) != binding.get("permit_sha256"):
        raise ValueError("project repair dispatch permit drifted")
    return binding


def assert_project_repair_request_preflight_binding(
    request: Mapping[str, Any], reference: Mapping[str, Any],
    logical_model: str, resolved_model: str,
) -> None:
    binding = request.get("preflight_binding")
    if (
        not isinstance(binding, Mapping)
        or binding.get("preflight") != dict(reference)
        or binding.get("logical_model") != logical_model
        or binding.get("resolved_model") != resolved_model
    ):
        raise ValueError("project repair worker changed its preflight binding")


def _reference(value: Mapping[str, Any]) -> dict[str, Any]:
    if set(value) != {"path", "sha256", "size_bytes"}:
        raise ValueError("project repair preflight reference is invalid")
    size = _nonnegative_int(value.get("size_bytes"))
    return {
        "path": _text(value.get("path")),
        "sha256": _sha(value.get("sha256")),
        "size_bytes": size,
    }


def _sha(value: Any) -> str:
    if (
        not isinstance(value, str) or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError("project repair permit SHA-256 is invalid")
    return value


def _text(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 512:
        raise ValueError("project repair permit text is invalid")
    return value


def _positive_int(value: Any) -> int:
    result = _nonnegative_int(value)
    if result == 0:
        raise ValueError("project repair permit epoch is invalid")
    return result


def _texts(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > 64:
        raise ValueError("project repair permit recovery list is invalid")
    result = [_text(item) for item in value]
    if len(set(result)) != len(result):
        raise ValueError("project repair permit recovery list is duplicated")
    return result


def _nonnegative_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("project repair permit integer is invalid")
    return value


__all__ = [
    "ProjectRepairDispatchPermit",
    "assert_project_repair_request_preflight_binding",
    "issue_project_repair_dispatch_permit", "project_repair_dispatch_binding",
]
