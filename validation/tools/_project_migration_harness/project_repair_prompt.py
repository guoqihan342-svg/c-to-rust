from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .build_ir import validate_artifact_reference
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
    native_planning = context.get("native_link_planning")
    _validate_native_request_binding(request, context, native_planning)
    native_mode = context["schema_version"] == 3
    payload = {
        "schema_version": 1,
        "task": (
            "select generic native-link plans for a Rust project"
            if native_mode
            else "generic whole-project RustProjectIR conflict repair"
        ),
        "role": "project-repairer",
        "rules": _rules(native_mode),
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
            "operations": _operation_schema(context, native_planning),
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
        "expected_projection", "preflight_binding", "model_input_policy",
        "output_contract",
    ):
        if not isinstance(request.get(key), Mapping):
            raise ValueError(f"project repair request {key} is invalid")


def _rules(native_mode: bool) -> list[str]:
    if native_mode:
        return [
            "Use only grouped portable library identities from native_link_planning.",
            "Return one complete proposal set covering every requirement exactly once.",
            "Never emit absolute paths, search paths, shell flags, or project-specific shims.",
            "Use defer when evidence is insufficient; the model cannot claim resolution.",
            "The host reopens BuildIR and decides Cargo, ABI, symbol, and semantic gates.",
            "Return exactly one JSON object matching output_schema.",
        ]
    return [
        "Use only the visible project repair context; withheld records and source bodies were not visible.",
        "Return only bounded replace/remove operations for visible records.",
        "Do not change evidence, candidate source bindings, or unrelated modules.",
        "Do not generate glue, fixture-specific shims, Cargo files, or semantic pass claims.",
        "The host rebuilds the complete RustProjectIR and reruns the deterministic coordinator.",
        "Return exactly one JSON object matching output_schema.",
    ]


def _operation_schema(
    context: Mapping[str, Any], native_planning: Any,
) -> list[dict[str, Any]]:
    if context["schema_version"] == 3:
        return [{
            "section": "native_link_plans",
            "action": "bind",
            "record_id": native_planning["plan_set_id"],
            "changes": {"proposals": [{
                "requirement_id": "one visible requirement_id",
                "strategy": "rustc-link-lib | ffi-boundary | defer",
                "rustc_link_name": "portable name or null",
                "rustc_link_kind": "dylib | static | null",
            }]},
        }]
    return [{
        "section": "visible section name",
        "action": "replace | remove",
        "record_id": "visible record identity",
        "changes": "allowlisted field/value object; empty only for remove",
    }]


def _validate_native_request_binding(
    request: Mapping[str, Any], context: Mapping[str, Any], planning: Any,
) -> None:
    reference = request.get("native_link_context")
    if context["schema_version"] != 3:
        if reference is not None:
            raise ValueError("native link context is unexpected for record repair")
        return
    model_context = planning.get("context") if isinstance(planning, Mapping) else None
    if not isinstance(reference, Mapping) or set(reference) != {
        "path", "sha256", "size_bytes", "context_sha256",
    }:
        raise ValueError("native link context reference is invalid")
    validate_artifact_reference(
        reference, "native link context reference is invalid",
    )
    if (
        not isinstance(model_context, Mapping)
        or reference.get("context_sha256") != model_context.get("context_sha256")
        or request["output_contract"] != {
            "kind": "native-link-plan-set", "max_operations": 1,
            "host_rebuilds_complete_ir": True,
            "semantic_acceptance": False,
        }
    ):
        raise ValueError("native link request/context binding drifted")


__all__ = ["MAX_PROJECT_REPAIR_PROMPT_BYTES", "render_project_repair_prompt"]
