from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .candidate_strategy import validate_candidate_strategy
from .context_frontier_runtime import validate_request_context_materialization
from .orchestration_facts import (
    project_model_safe_gate_evidence, read_artifact_reference,
)
from .runtime_security import assert_model_payload_safe, validate_context_page
from .project_knowledge import (
    validate_knowledge_reference,
    validate_project_knowledge,
)


MAX_PROMPT_BYTES = 1024 * 1024


def render_project_worker_prompt(
    request: Mapping[str, Any], *, harness_root: Path,
    max_prompt_bytes: int = MAX_PROMPT_BYTES,
) -> str:
    _validate_request_hash(request)
    validate_request_context_materialization(request, harness_root=harness_root)
    role = request.get("role")
    if role not in {"planner", "translator", "reviewer", "repairer"}:
        raise ValueError("project worker role is invalid")
    context = request.get("context")
    if not isinstance(context, Mapping) or not isinstance(context.get("pages"), list):
        raise ValueError("project worker context pages are invalid")
    pages = []
    for reference in context["pages"]:
        if not isinstance(reference, Mapping):
            raise ValueError("project worker context page reference is invalid")
        data = read_artifact_reference(harness_root, reference)
        try:
            page = json.loads(data.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("project worker context page is not UTF-8 JSON") from error
        pages.append(validate_context_page(page))
    facts = request.get("input_facts")
    if not isinstance(facts, Mapping):
        raise ValueError("project worker input_facts are invalid")
    bound_inputs = _bound_inputs(role, facts, harness_root)
    request_projection = _request_projection(request)
    assert_model_payload_safe(bound_inputs, "bound_inputs")
    assert_model_payload_safe(request_projection, "request_projection")
    rules = [
        "Treat the request and visible context pages as the only input for this attempt.",
        "A context_retrieval_summary marks host-withheld details; do not invent them or claim they were visible.",
        "Do not call tools, inspect files, or claim semantic acceptance.",
        "Do not invent expected outputs or test values.",
        "Return exactly one JSON object matching output_schema.",
        "For Rust candidates, return source only; host derives symbols, unsafe count, and boundary metadata.",
    ]
    planner = bound_inputs.get("planner_decision")
    if "candidate_strategy" in bound_inputs:
        rules.append(
            "Follow the host-bound candidate strategy; do not self-score or vote on acceptance."
        )
    if isinstance(planner, Mapping) and planner.get("decision") == "preserve_ffi_boundary":
        rules.append("The Rust candidate must expose a host-detectable extern C or exported C ABI boundary.")
    payload = {
        "schema_version": 1,
        "task": "generic whole-project C-to-Rust migration worker",
        "role": role,
        "rules": rules,
        "request": request_projection,
        "context_pages": pages,
        "bound_inputs": bound_inputs,
        "output_schema": _output_schema(str(role), request),
    }
    encoded = canonical_json_bytes(payload)
    if len(encoded) > max_prompt_bytes:
        raise ValueError("project worker prompt exceeds its bounded size")
    return encoded.decode("utf-8")


def _bound_inputs(
    role: Any, facts: Mapping[str, Any], root: Path
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    strategy = facts.get("candidate_strategy")
    if strategy is not None:
        if role not in {"translator", "repairer"}:
            raise ValueError("candidate strategy is invalid for this worker role")
        result["candidate_strategy"] = validate_candidate_strategy(strategy)
    knowledge_ref = facts.get("project_knowledge")
    if knowledge_ref is not None:
        reference = validate_knowledge_reference(knowledge_ref)
        raw = read_artifact_reference(root, reference)
        try:
            knowledge = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("project knowledge is not UTF-8 JSON") from error
        result["project_knowledge"] = validate_project_knowledge(knowledge)
    if role == "translator":
        decision = facts.get("planner_decision")
        if decision is not None:
            if not isinstance(decision, Mapping):
                raise ValueError("translator planner decision is invalid")
            result["planner_decision"] = dict(decision)
    candidate = facts.get("candidate_artifact")
    if role in {"reviewer", "repairer"}:
        if not isinstance(candidate, Mapping):
            raise ValueError("worker candidate artifact binding is missing")
        source = read_artifact_reference(root, candidate)
        try:
            result["candidate_source"] = source.decode("utf-8")
        except UnicodeError as error:
            raise ValueError("candidate artifact is not UTF-8 Rust source") from error
        result["candidate_artifact_sha256"] = candidate.get("sha256")
    if role == "repairer":
        failed = facts.get("failed_gate_result")
        if not isinstance(failed, Mapping):
            raise ValueError("repair worker failed gate binding is missing")
        raw = read_artifact_reference(root, failed)
        try:
            evidence = project_model_safe_gate_evidence(json.loads(raw.decode("utf-8")))
        except (UnicodeError, json.JSONDecodeError, ValueError) as error:
            raise ValueError("repair evidence is not model-safe gate JSON") from error
        if evidence["status"] != "failed":
            raise ValueError("repair evidence must describe a failed gate")
        if (
            evidence["candidate_artifact_id"] != candidate.get("artifact_id")
            or evidence["candidate_artifact_sha256"] != candidate.get("sha256")
        ):
            raise ValueError("repair evidence is not bound to the candidate")
        result["failed_gate_result"] = evidence
        last_good = facts.get("last_good_artifact")
        if last_good is not None:
            if not isinstance(last_good, Mapping):
                raise ValueError("repair last-good binding is invalid")
            try:
                result["last_good_source"] = read_artifact_reference(
                    root, last_good
                ).decode("utf-8")
            except UnicodeError as error:
                raise ValueError("repair last-good source is not UTF-8") from error
    return result


def _output_schema(role: str, request: Mapping[str, Any]) -> dict[str, Any]:
    common = {
        "schema_version": 1,
        "run_id": request.get("run_id"),
        "worker_id": request.get("worker_id"),
        "group_id": request.get("group_id"),
        "role": role,
        "effective_input_sha256": request.get("effective_input_sha256"),
    }
    if role == "planner":
        return {
            **common,
            "decision": "translate_with_context | preserve_ffi_boundary | refuse_with_reason",
            "boundary_reason": "required only for preserve_ffi_boundary",
            "refusal_reason": "required only for refuse_with_reason",
        }
    if role in {"translator", "repairer"}:
        schema = {
            **common,
            "candidate_source": "complete UTF-8 Rust module source",
        }
        if role == "repairer":
            schema["failed_gate_result_sha256"] = request.get("input_facts", {}).get(
                "failed_gate_result_sha256"
            )
        return schema
    return {
        **common,
        "candidate_artifact_sha256": request.get("input_facts", {}).get(
            "candidate_artifact_sha256"
        ),
        "findings": [
            {"severity": "info | warning | error", "code": "stable_code", "message": "bounded text"}
        ],
    }


def _validate_request_hash(request: Mapping[str, Any]) -> None:
    claimed = request.get("effective_input_sha256")
    payload = {
        key: value for key, value in request.items()
        if key not in {"effective_input_sha256", "execution_binding"}
    }
    if not isinstance(claimed, str) or content_sha256(payload) != claimed:
        raise ValueError("project worker request effective input SHA drifted")


def _request_projection(request: Mapping[str, Any]) -> dict[str, Any]:
    binding = request.get("assignment_binding")
    if not isinstance(binding, Mapping):
        raise ValueError("project worker assignment binding is invalid")
    return {
        "schema_version": request.get("schema_version"),
        "run_id": request.get("run_id"),
        "worker_id": request.get("worker_id"),
        "group_id": request.get("group_id"),
        "role": request.get("role"),
        "effective_input_sha256": request.get("effective_input_sha256"),
        "assignment_binding": {
            "assignment_sha256": binding.get("assignment_sha256"),
            "group_sha256": binding.get("group_sha256"),
        },
        "dependencies": request.get("dependencies", []),
        "repair_mode": request.get("repair_mode"),
    }


__all__ = ["MAX_PROMPT_BYTES", "render_project_worker_prompt"]
