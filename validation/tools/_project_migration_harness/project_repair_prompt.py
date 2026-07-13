from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .orchestration_facts import read_artifact_reference
from .project_repair_context import validate_project_repair_context
from .runtime_security import assert_model_payload_safe


MAX_PROJECT_REPAIR_PROMPT_BYTES = 262_144


def render_project_repair_prompt(
    request: Mapping[str, Any], *, harness_root: Path,
    max_prompt_bytes: int = MAX_PROJECT_REPAIR_PROMPT_BYTES,
) -> str:
    _validate_request(request)
    reference = request["project_repair_context"]
    data = read_artifact_reference(harness_root, reference)
    try:
        context = validate_project_repair_context(json.loads(data.decode("utf-8")))
    except (UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("project repair context artifact is invalid") from error
    if (
        reference.get("context_sha256") != context["context_sha256"]
        or request["repair_id"] != context["repair_id"]
        or request["project_repair_queue_sha256"]
        != context["project_repair_queue_sha256"]
        or request["base_rust_project_ir"]["ir_sha256"]
        != context["base_rust_project_ir_sha256"]
        or request["coordinator_binding"] != {
            "receipt_epoch": context["receipt_epoch"],
            "coordinator_receipt_sha256": context["coordinator_receipt_sha256"],
            "context_sha256": context["context_sha256"],
        }
    ):
        raise ValueError("project repair request/context binding drifted")
    payload = {
        "schema_version": 1,
        "task": "generic whole-project RustProjectIR conflict repair",
        "role": "project-repairer",
        "rules": [
            "Use only the visible project repair context; withheld records and source bodies were not visible.",
            "Return only bounded replace/remove operations for visible records.",
            "Do not change evidence, candidate source bindings, or unrelated modules.",
            "Do not generate glue, fixture-specific shims, Cargo files, or semantic pass claims.",
            "The host rebuilds the complete RustProjectIR and reruns the deterministic coordinator.",
            "Return exactly one JSON object matching output_schema.",
        ],
        "request": {
            "run_id": request["run_id"],
            "project_repair_queue_sha256": request["project_repair_queue_sha256"],
            "repair_id": request["repair_id"],
            "attempt_id": request["execution_binding"]["attempt_id"],
            "effective_input_sha256": request["effective_input_sha256"],
            "base_rust_project_ir_sha256": request["base_rust_project_ir"]["ir_sha256"],
            "context_sha256": context["context_sha256"],
        },
        "project_repair_context": context,
        "output_schema": {
            "schema_version": 1,
            "run_id": request["run_id"],
            "role": "project-repairer",
            "project_repair_queue_sha256": request["project_repair_queue_sha256"],
            "repair_id": request["repair_id"],
            "attempt_id": request["execution_binding"]["attempt_id"],
            "effective_input_sha256": request["effective_input_sha256"],
            "base_rust_project_ir_sha256": request["base_rust_project_ir"]["ir_sha256"],
            "context_sha256": context["context_sha256"],
            "operations": [{
                "section": "visible section name",
                "action": "replace | remove",
                "record_id": "visible record identity",
                "changes": "allowlisted field/value object; empty only for remove",
            }],
        },
    }
    assert_model_payload_safe(payload, "project_repair_prompt")
    encoded = canonical_json_bytes(payload)
    if len(encoded) > max_prompt_bytes:
        raise ValueError("project repair prompt exceeds its bounded size")
    return encoded.decode("utf-8")


def _validate_request(request: Mapping[str, Any]) -> None:
    if request.get("schema_version") != 1 or request.get("request_kind") != "project_repair_worker":
        raise ValueError("project repair request identity is invalid")
    if request.get("role") != "project-repairer":
        raise ValueError("project repair request role is invalid")
    claimed = request.get("effective_input_sha256")
    projection = {
        key: item for key, item in request.items()
        if key not in {"effective_input_sha256", "execution_binding"}
    }
    if not isinstance(claimed, str) or content_sha256(projection) != claimed:
        raise ValueError("project repair request effective input SHA drifted")
    binding = request.get("execution_binding")
    if not isinstance(binding, Mapping):
        raise ValueError("project repair execution binding is missing")
    binding_projection = {
        key: item for key, item in binding.items() if key != "binding_sha256"
    }
    if (
        binding.get("effective_input_sha256") != claimed
        or content_sha256(binding_projection) != binding.get("binding_sha256")
    ):
        raise ValueError("project repair execution binding drifted")
    for key in (
        "coordinator_binding", "base_rust_project_ir", "project_repair_context",
        "expected_projection", "model_input_policy", "output_contract",
    ):
        if not isinstance(request.get(key), Mapping):
            raise ValueError(f"project repair request {key} is invalid")


__all__ = ["MAX_PROJECT_REPAIR_PROMPT_BYTES", "render_project_repair_prompt"]
