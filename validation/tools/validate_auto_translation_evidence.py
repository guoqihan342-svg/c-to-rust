#!/usr/bin/env python3
"""Validate bounded auto-translation evidence against committed schemas."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import jsonschema


REPO_ROOT = Path(__file__).resolve().parents[2]
L4_REFUSED_FORBIDDEN_ARTIFACT_STATUSES = {
    "accepted_after_gates",
    "accepted_evidence_bound",
    "candidate",
    "candidate_generated",
    "draft_generated",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--slice-id", required=True)
    parser.add_argument("--slice-spec", type=Path)
    parser.add_argument("--evidence-root", default=REPO_ROOT / "validation" / "evidence", type=Path)
    parser.add_argument(
        "--require-semantic-pass",
        action="store_true",
        help="Require accepted C oracle/Rust replay/diff/negative/unsafe/final verification evidence, not just schema validity.",
    )
    args = parser.parse_args()

    evidence_dir = args.evidence_root / args.target_id / "auto-translation" / args.slice_id
    prefix = f"l3-{args.slice_id}"
    slice_spec = args.slice_spec or resolve_slice_spec(args.target_id, args.slice_id)
    checks = [
        ("validation/slice-spec-template/slice-spec.schema.json", slice_spec),
        ("validation/type-map-template/type-map.schema.json", evidence_dir / f"{prefix}-type-map.json"),
        ("validation/cfg-template/cfg.schema.json", evidence_dir / f"{prefix}-cfg.json"),
        ("validation/pointer-graph-template/pointer-graph.schema.json", evidence_dir / f"{prefix}-pointer-graph.json"),
        ("validation/test-translation-template/test-translation.schema.json", evidence_dir / f"{prefix}-test-translation-generated.json"),
        ("validation/l3-template/evidence-manifest.schema.json", evidence_dir / f"{prefix}-evidence-manifest.json"),
        ("validation/auto-translation-template/auto-translation-plan.schema.json", evidence_dir / f"{prefix}-auto-translation-plan.json"),
        ("validation/auto-translation-template/ai-candidate-manifest.schema.json", evidence_dir / f"{prefix}-ai-candidate-manifest.json"),
        ("validation/auto-translation-template/blocked-repairs.schema.json", evidence_dir / f"{prefix}-self-healing-blocked-repairs.json"),
        ("validation/auto-translation-template/c2rust-baseline-manifest.schema.json", evidence_dir / f"{prefix}-c2rust-baseline-manifest.json"),
        ("validation/auto-translation-template/route-decision.schema.json", evidence_dir / f"{prefix}-route-decision.json"),
        ("validation/auto-translation-template/validation-profile.schema.json", evidence_dir / f"{prefix}-validation-profile.json"),
    ]

    validated = []
    for schema_path, data_path in checks:
        validate_json(REPO_ROOT / schema_path, data_path)
        validated.append(rel(data_path))

    validate_alias_gate(evidence_dir, prefix)
    validate_route_baseline_profile_refs(evidence_dir, prefix, slice_spec)
    validate_oracle_harness_contract(evidence_dir, prefix, slice_spec)
    validate_global_dependency_requirements(evidence_dir, prefix, slice_spec)
    validate_schema_diff_contract(evidence_dir, prefix, slice_spec)
    validate_external_direct_callee_context_for_default_checks(evidence_dir, prefix, slice_spec)

    patch_schema = load_json(REPO_ROOT / "validation/auto-translation-template/patch-event.schema.json")
    patch_path = evidence_dir / f"{prefix}-patch-events.jsonl"
    patch_count = 0
    if patch_path.exists():
        for line in patch_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                jsonschema.validate(json.loads(line), patch_schema)
                patch_count += 1
    validated.append(rel(patch_path))

    event_schema = load_json(REPO_ROOT / "validation/auto-translation-template/auto-translation-event.schema.json")
    event_path = evidence_dir / f"{prefix}-auto-translation-events.jsonl"
    event_count = 0
    for line in event_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            jsonschema.validate(json.loads(line), event_schema)
            event_count += 1
    validated.append(rel(event_path))

    semantic = (
        validate_semantic_pass(evidence_dir, prefix, slice_spec)
        if args.require_semantic_pass
        else {"semantic_pass": False, "status": "not_required"}
    )

    print(
        json.dumps(
            {
                "status": "passed",
                "schema_status": "passed",
                "semantic_pass": bool(semantic.get("semantic_pass")),
                "semantic": semantic,
                "target_id": args.target_id,
                "slice_id": args.slice_id,
                "validated": validated,
                "patch_event_count": patch_count,
                "auto_translation_event_count": event_count,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def validate_json(schema_path: Path, data_path: Path) -> None:
    jsonschema.validate(load_json(data_path), load_json(schema_path))


def validate_alias_gate(evidence_dir: Path, prefix: str) -> None:
    pointer_graph_path = evidence_dir / f"{prefix}-pointer-graph.json"
    pointer_graph = load_json(pointer_graph_path)
    if pointer_graph.get("status") == "not_applicable":
        return

    nodes = pointer_graph.get("pointer_nodes", [])
    read_nodes = [node for node in nodes if node.get("read_effects")]
    write_nodes = [node for node in nodes if node.get("write_effects")]
    alias_pairs = [
        (str(read_node.get("id")), str(write_node.get("id")))
        for read_node in read_nodes
        for write_node in write_nodes
        if read_node.get("id") != write_node.get("id")
    ]
    if not alias_pairs:
        return

    required = ["alias_sets", "alias_risks", "alias_contract", "safe_boundary_preconditions"]
    missing = [key for key in required if key not in pointer_graph]
    triggers = pointer_graph.get("applicability", {}).get("triggers", [])
    if "alias_sensitive_state" not in triggers:
        missing.append("applicability.triggers.alias_sensitive_state")
    if missing:
        raise SystemExit(f"alias gate evidence missing fields in {pointer_graph_path}: {', '.join(missing)}")

    alias_contract = pointer_graph.get("alias_contract", {})
    decision = alias_contract.get("decision")
    if decision not in {"allow", "requires_noalias_contract", "candidate_only", "blocked"}:
        raise SystemExit(f"alias gate evidence has unsupported decision {decision!r} in {pointer_graph_path}")
    if decision == "allow" and not alias_contract.get("proven"):
        raise SystemExit(f"alias gate allow decision requires alias_contract.proven=true in {pointer_graph_path}")

    alias_sets = pointer_graph.get("alias_sets", [])
    alias_risks = pointer_graph.get("alias_risks", [])
    preconditions = pointer_graph.get("safe_boundary_preconditions", [])
    if not alias_sets:
        raise SystemExit(f"alias gate evidence requires non-empty alias_sets in {pointer_graph_path}")
    if not alias_risks:
        raise SystemExit(f"alias gate evidence requires non-empty alias_risks in {pointer_graph_path}")
    if decision == "requires_noalias_contract" and not preconditions:
        raise SystemExit(f"alias gate evidence requires noalias preconditions in {pointer_graph_path}")

    required_risk_keys = {"pointer_nodes", "risk_level", "evidence_source", "gate_decision", "requires_noalias"}
    precondition_sets = {
        frozenset(item.get("applies_to", []))
        for item in preconditions
        if item.get("kind") == "noalias" and item.get("required")
    }
    for risk in alias_risks:
        missing_risk_keys = sorted(required_risk_keys - set(risk))
        if missing_risk_keys:
            raise SystemExit(
                f"alias gate evidence risk missing fields in {pointer_graph_path}: {', '.join(missing_risk_keys)}"
            )
        risk_nodes = frozenset(risk.get("pointer_nodes", []))
        if len(risk_nodes) < 2:
            raise SystemExit(f"alias gate evidence risk must name at least two pointer nodes in {pointer_graph_path}")
        if risk.get("gate_decision") != decision:
            raise SystemExit(f"alias gate evidence risk gate_decision drift in {pointer_graph_path}")
        if decision == "requires_noalias_contract":
            if risk.get("risk_level") != "unknown_alias":
                raise SystemExit(f"alias gate evidence unknown alias risk level required in {pointer_graph_path}")
            if not risk.get("requires_noalias"):
                raise SystemExit(f"alias gate evidence risk requires_noalias=true required in {pointer_graph_path}")
            if risk_nodes not in precondition_sets:
                raise SystemExit(f"alias gate evidence missing matching noalias precondition in {pointer_graph_path}")

    plan_path = evidence_dir / f"{prefix}-auto-translation-plan.json"
    plan = load_json(plan_path)
    if "alias_gate" not in plan.get("translation_summary", {}):
        raise SystemExit(f"alias gate evidence missing translation_summary.alias_gate in {plan_path}")

    manifest_path = evidence_dir / f"{prefix}-auto-translation-manifest.json"
    if manifest_path.exists():
        manifest = load_json(manifest_path)
        if "alias_gate" not in manifest.get("claim_boundary", {}):
            raise SystemExit(f"alias gate evidence missing claim_boundary.alias_gate in {manifest_path}")

    l3_manifest_path = evidence_dir / f"{prefix}-evidence-manifest.json"
    l3_manifest = load_json(l3_manifest_path)
    if "alias_gate" not in l3_manifest.get("claim_boundary", {}):
        raise SystemExit(f"alias gate evidence missing claim_boundary.alias_gate in {l3_manifest_path}")

    final_path = evidence_dir / f"{prefix}-final-verification.json"
    final = load_json(final_path)
    if "alias_gate" not in final:
        raise SystemExit(f"alias gate evidence missing final_verification.alias_gate in {final_path}")


def validate_route_baseline_profile_refs(evidence_dir: Path, prefix: str, slice_spec_path: Path) -> None:
    baseline_path = evidence_dir / f"{prefix}-c2rust-baseline-manifest.json"
    route_path = evidence_dir / f"{prefix}-route-decision.json"
    profile_path = evidence_dir / f"{prefix}-validation-profile.json"
    baseline = load_json(baseline_path)
    route = load_json(route_path)
    profile = load_json(profile_path)
    slice_spec = load_json(slice_spec_path)

    if baseline.get("correctness_role") != "candidate_context_only":
        raise SystemExit(f"C2Rust baseline must be candidate context only in {baseline_path}")
    if route.get("verification_profile") != profile.get("profile"):
        raise SystemExit(f"route/profile mismatch: {route.get('verification_profile')} != {profile.get('profile')}")
    if route.get("level") != profile.get("route_level"):
        raise SystemExit(f"route/profile level mismatch: {route.get('level')} != {profile.get('route_level')}")
    if route.get("level") == "L4":
        if route.get("status") != "refused":
            raise SystemExit(f"L4 route requires refused status in {route_path}")
        if route.get("translator", {}).get("candidate_generation_allowed"):
            raise SystemExit(f"L4 route must not allow candidate generation in {route_path}")
    if profile.get("status") == "passed" and profile.get("skipped_gates"):
        raise SystemExit(f"passed validation profile cannot contain skipped required gates in {profile_path}")

    auto_manifest_path = evidence_dir / f"{prefix}-auto-translation-manifest.json"
    auto_manifest = load_json(auto_manifest_path)
    if l4_refuses_candidate_generation(route):
        if auto_manifest.get("status") == "candidate_generated":
            raise SystemExit(
                f"L4/refused route cannot have generated candidate evidence in {auto_manifest_path}"
            )
        if not accepted_evidence_authoritative_manifest(route, auto_manifest, slice_spec):
            if accepted_evidence_authoritative_artifacts_claimed(route, auto_manifest):
                raise SystemExit(
                    "L4/refused accepted_evidence_authoritative requires "
                    "slice spec claim_boundary.accepted_evidence_authoritative=true"
                )
            validate_l4_refused_has_no_candidate_artifact_status(
                evidence_dir,
                prefix,
                auto_manifest,
                auto_manifest_path,
            )
    validate_route_source_artifact_refs(evidence_dir, prefix, route, baseline_path)
    require_ref(auto_manifest.get("c2rust_baseline"), baseline_path, "auto_manifest.c2rust_baseline")
    require_ref(auto_manifest.get("route_decision"), route_path, "auto_manifest.route_decision")
    require_ref(auto_manifest.get("validation_profile"), profile_path, "auto_manifest.validation_profile")

    l3_manifest_path = evidence_dir / f"{prefix}-evidence-manifest.json"
    l3_manifest = load_json(l3_manifest_path)
    evidence = l3_manifest.get("evidence", {})
    require_ref(evidence.get("c2rust_baseline"), baseline_path, "l3_manifest.evidence.c2rust_baseline")
    require_ref(evidence.get("route_decision"), route_path, "l3_manifest.evidence.route_decision")
    require_ref(evidence.get("validation_profile"), profile_path, "l3_manifest.evidence.validation_profile")

    final_path = evidence_dir / f"{prefix}-final-verification.json"
    final = load_json(final_path)
    require_ref(final.get("c2rust_baseline"), baseline_path, "final_verification.c2rust_baseline")
    require_ref(final.get("route_decision"), route_path, "final_verification.route_decision")
    require_ref(final.get("validation_profile"), profile_path, "final_verification.validation_profile")
    if "skipped_gates" not in final:
        raise SystemExit(f"validation profile skipped gates missing from {final_path}")

    validate_typed_ir_candidate_binding(evidence_dir, prefix, route, profile)

    cache_path = evidence_dir / f"{prefix}-auto-cache-metadata.json"
    cache = load_json(cache_path)
    required_identities = {
        "c2rust_baseline_identity": artifact_cache_identity(baseline),
        "route_decision_identity": artifact_cache_identity(route),
        "validation_profile_identity": artifact_cache_identity(profile),
    }
    for key, expected_identity in required_identities.items():
        if key not in cache:
            raise SystemExit(f"cache metadata missing {key} in {cache_path}")
        if key not in cache.get("cache_input_fields", []):
            raise SystemExit(f"cache metadata cache_input_fields missing {key} in {cache_path}")
        if cache.get(key) != expected_identity:
            raise SystemExit(f"cache metadata {key} drift in {cache_path}")
    dependent = cache.get("dependent_artifacts", {})
    require_ref(dependent.get("c2rust_baseline"), baseline_path, "cache.dependent_artifacts.c2rust_baseline")
    require_ref(dependent.get("route_decision"), route_path, "cache.dependent_artifacts.route_decision")
    require_ref(dependent.get("validation_profile"), profile_path, "cache.dependent_artifacts.validation_profile")


def validate_oracle_harness_contract(evidence_dir: Path, prefix: str, slice_spec_path: Path) -> None:
    slice_spec = load_json(slice_spec_path)
    oracle_path = evidence_dir / f"{prefix}-c-oracle-status.json"
    oracle = load_json(oracle_path)
    harness_path = resolve_ref_path(str(oracle.get("harness_draft", "")))
    if not harness_path.exists():
        raise SystemExit(f"oracle harness draft missing: {harness_path}")

    expected_globals = global_dependency_requirements(slice_spec)
    contract = oracle.get("harness_contract")
    harness_ref = oracle.get("harness_draft_ref")
    if not isinstance(contract, dict):
        if expected_globals:
            raise SystemExit(f"oracle harness contract missing from {oracle_path}")
        if harness_ref is not None:
            expected_identity = validate_harness_draft_ref(harness_ref, harness_path, oracle_path)
            validate_cache_oracle_harness_identity(evidence_dir, prefix, expected_identity)
        validate_draft_oracle_fail_closed(evidence_dir, prefix, oracle, oracle_path)
        return

    expected_harness_identity = validate_harness_draft_ref(harness_ref, harness_path, oracle_path)
    validate_cache_oracle_harness_identity(evidence_dir, prefix, expected_harness_identity)

    expected_prototype = c_function_prototype(slice_spec)
    if contract.get("function_prototype") != expected_prototype:
        raise SystemExit(f"oracle harness contract function prototype drift in {oracle_path}")

    expected_fixture = oracle_fixture_binding(slice_spec)
    fixture = contract.get("fixture")
    if fixture != expected_fixture:
        raise SystemExit(f"oracle harness contract fixture drift in {oracle_path}")
    if oracle.get("fixture_binding") != expected_fixture:
        raise SystemExit(f"oracle fixture binding drift in {oracle_path}")

    expected_source_files = slice_spec.get("c_boundary", {}).get("files", [])
    if contract.get("source_files") != expected_source_files:
        raise SystemExit(f"oracle harness contract source_files drift in {oracle_path}")

    contract_globals = contract.get("global_dependencies", [])
    if contract_globals != expected_globals:
        raise SystemExit(f"oracle harness contract global_dependencies drift in {oracle_path}")

    compile_command = oracle.get("compile_command_draft")
    validate_compile_command_draft(compile_command, slice_spec, harness_path, oracle_path)
    validate_compile_execution(oracle.get("compile_execution"), compile_command, oracle, oracle_path)

    harness_text = harness_path.read_text(encoding="utf-8")
    if expected_prototype not in harness_text:
        raise SystemExit(f"oracle harness function prototype missing from {harness_path}")
    if f"fixture input: {fixture_path_from_spec(slice_spec)}" not in harness_text:
        raise SystemExit(f"oracle harness fixture binding missing from {harness_path}")
    for fixture_comment in oracle_fixture_comment_fragments(expected_fixture):
        if fixture_comment not in harness_text:
            raise SystemExit(f"oracle harness fixture binding missing from {harness_path}")
    for item in expected_source_files:
        if not isinstance(item, dict):
            continue
        source_comment = f"source file: {item.get('path', 'unknown')} (sha256: {item.get('sha256', 'unknown')})"
        if source_comment not in harness_text:
            raise SystemExit(f"oracle harness source file binding missing from {harness_path}")
    validate_draft_oracle_fail_closed(evidence_dir, prefix, oracle, oracle_path)


def validate_harness_draft_ref(ref: Any, harness_path: Path, oracle_path: Path) -> dict[str, Any]:
    if not isinstance(ref, dict) or not ref.get("path"):
        raise SystemExit(f"oracle harness draft ref missing from {oracle_path}")
    resolved = resolve_ref_path(str(ref["path"]))
    if resolved.resolve() != harness_path.resolve():
        raise SystemExit(f"oracle harness draft ref path mismatch in {oracle_path}: {resolved} != {harness_path}")
    expected_sha = sha256(harness_path)
    if ref.get("sha256") != expected_sha:
        raise SystemExit(f"oracle harness draft ref sha256 mismatch in {oracle_path}")
    if ref.get("status") != "draft":
        raise SystemExit(f"oracle harness draft ref status mismatch in {oracle_path}")
    return {
        "path": ref["path"],
        "status": ref["status"],
        "sha256": ref["sha256"],
    }


def validate_compile_command_draft(
    compile_command: Any,
    slice_spec: dict[str, Any],
    harness_path: Path,
    oracle_path: Path,
) -> None:
    if not isinstance(compile_command, dict):
        raise SystemExit(f"oracle harness compile command draft missing from {oracle_path}")
    source_root = compile_source_root(slice_spec)
    expected_includes = [
        resolve_source_root_path(source_root, path)
        for path in slice_spec.get("build_profile", {}).get("include_paths", [])
    ]
    expected_defines = [str(item) for item in slice_spec.get("build_profile", {}).get("defines", [])]
    expected_sources = compile_link_source_files(slice_spec, source_root)
    output_name = harness_path.with_suffix(".exe").name
    expected_argv = [
        "cc",
        "-std=c99",
        *[f"-D{item}" for item in expected_defines],
        *[f"-I{path}" for path in expected_includes],
        harness_path.name,
        *[item["resolved_path"] for item in expected_sources],
        "-o",
        output_name,
    ]
    if compile_command.get("working_directory") != rel(oracle_path.parent):
        raise SystemExit(f"oracle harness compile command working_directory drift in {oracle_path}")
    if compile_command.get("source_root") != source_root:
        raise SystemExit(f"oracle harness compile command source_root drift in {oracle_path}")
    if compile_command.get("defines") != expected_defines:
        raise SystemExit(f"oracle harness compile command defines drift in {oracle_path}")
    if compile_command.get("resolved_include_paths") != expected_includes:
        raise SystemExit(f"oracle harness compile command include path drift in {oracle_path}")
    if compile_command.get("link_source_files") != expected_sources:
        raise SystemExit(f"oracle harness compile command source linkage drift in {oracle_path}")
    if compile_command.get("link_strategy") != c_oracle_link_strategy(slice_spec):
        raise SystemExit(f"oracle harness compile command link strategy drift in {oracle_path}")
    if compile_command.get("argv") != expected_argv:
        raise SystemExit(f"oracle harness compile command argv drift in {oracle_path}")
    if compile_command.get("status") != "draft_not_executed":
        raise SystemExit(f"oracle harness compile command status drift in {oracle_path}")


def validate_compile_execution(
    compile_execution: Any,
    compile_command: dict[str, Any],
    oracle: dict[str, Any],
    oracle_path: Path,
) -> None:
    if not isinstance(compile_execution, dict):
        raise SystemExit(f"oracle harness compile execution missing from {oracle_path}")
    if compile_execution.get("argv") != compile_command.get("argv"):
        raise SystemExit(f"oracle harness compile execution argv drift in {oracle_path}")
    if compile_execution.get("working_directory") != compile_command.get("working_directory"):
        raise SystemExit(f"oracle harness compile execution working_directory drift in {oracle_path}")
    if compile_execution.get("semantic_pass") is not False:
        raise SystemExit(f"oracle harness compile execution cannot claim semantic_pass in {oracle_path}")

    status = compile_execution.get("status")
    expected_toolchain_by_status = {
        "skipped_by_flag": "DRAFT_NOT_EXECUTED",
        "missing_argv": "COMPILE_NOT_EXECUTED",
        "compiler_not_found": "COMPILE_NOT_EXECUTED",
        "compile_failed": "COMPILE_FAILED",
        "compile_timeout": "COMPILE_FAILED",
        "compile_succeeded_not_oracle": "COMPILE_SUCCEEDED_NOT_ORACLE",
    }
    if status not in expected_toolchain_by_status:
        raise SystemExit(f"oracle harness compile execution status drift in {oracle_path}")
    expected_toolchain_status = expected_toolchain_by_status[status]
    if compile_execution.get("toolchain_status_after_attempt") != expected_toolchain_status:
        raise SystemExit(f"oracle harness compile execution toolchain status drift in {oracle_path}")
    promoted_accepted = is_promoted_accepted_oracle_wrapper(oracle)
    if compile_execution.get("toolchain_status_after_attempt") != oracle.get("toolchain_status") and not (
        promoted_accepted and expected_toolchain_status == "COMPILE_SUCCEEDED_NOT_ORACLE"
    ):
        raise SystemExit(f"oracle harness compile execution toolchain status drift in {oracle_path}")

    attempted = compile_execution.get("attempted")
    if status == "skipped_by_flag":
        if attempted is not False:
            raise SystemExit(f"oracle harness compile execution skipped status drift in {oracle_path}")
        if compile_execution.get("diagnostics") != ["C oracle compile execution skipped by --skip-c-oracle."]:
            raise SystemExit(f"oracle harness compile execution diagnostics drift in {oracle_path}")
        return

    if status in {"missing_argv", "compiler_not_found"}:
        if attempted is not False:
            raise SystemExit(f"oracle harness compile execution non-attempted status drift in {oracle_path}")
        if not compile_execution.get("diagnostics"):
            raise SystemExit(f"oracle harness compile execution diagnostics missing in {oracle_path}")
        return

    if status in {"compile_failed", "compile_timeout", "compile_succeeded_not_oracle"}:
        if attempted is not True:
            raise SystemExit(f"oracle harness compile execution attempted status drift in {oracle_path}")
        if "compiler_path" not in compile_execution:
            raise SystemExit(f"oracle harness compile execution compiler path missing in {oracle_path}")
        validate_compile_toolchain_provenance(compile_execution, oracle_path)
        if not compile_execution.get("diagnostics"):
            raise SystemExit(f"oracle harness compile execution diagnostics missing in {oracle_path}")
        if status == "compile_succeeded_not_oracle" and oracle.get("semantic_pass") is True and not promoted_accepted:
            raise SystemExit(f"compiled oracle draft cannot claim semantic_pass=true in {oracle_path}")
        harness_execution = compile_execution.get("harness_execution")
        if status == "compile_succeeded_not_oracle" and not isinstance(harness_execution, dict):
            raise SystemExit(f"oracle harness execution missing in {oracle_path}")
        if harness_execution is not None:
            if status != "compile_succeeded_not_oracle":
                raise SystemExit(f"oracle harness execution status drift in {oracle_path}")
            validate_harness_execution(harness_execution, compile_execution, oracle_path)
        return


def is_promoted_accepted_oracle_wrapper(oracle: dict[str, Any]) -> bool:
    accepted = oracle.get("accepted_oracle")
    return (
        oracle.get("status") == "C_ORACLE_GENERATED"
        and oracle.get("semantic_pass") is True
        and oracle.get("toolchain_status") == "C_ORACLE_GENERATED"
        and isinstance(accepted, dict)
        and accepted.get("status") == "passed"
        and bool(accepted.get("path"))
    )


def validate_harness_execution(
    harness_execution: Any,
    compile_execution: dict[str, Any],
    oracle_path: Path,
) -> None:
    if not isinstance(harness_execution, dict):
        raise SystemExit(f"oracle harness execution missing from {oracle_path}")
    if harness_execution.get("working_directory") != compile_execution.get("working_directory"):
        raise SystemExit(f"oracle harness execution working_directory drift in {oracle_path}")
    if harness_execution.get("semantic_pass") is not False:
        raise SystemExit(f"oracle harness execution cannot claim semantic_pass in {oracle_path}")
    if not isinstance(harness_execution.get("timeout_seconds"), int) or harness_execution["timeout_seconds"] <= 0:
        raise SystemExit(f"oracle harness execution timeout drift in {oracle_path}")
    if not isinstance(harness_execution.get("stdout"), str) or not isinstance(harness_execution.get("stderr"), str):
        raise SystemExit(f"oracle harness execution stdio drift in {oracle_path}")
    if not harness_execution.get("diagnostics"):
        raise SystemExit(f"oracle harness execution diagnostics missing in {oracle_path}")
    validate_harness_toolchain_provenance(harness_execution, compile_execution, oracle_path)

    status = harness_execution.get("status")
    if status not in {
        "exited_zero_not_oracle",
        "exited_nonzero_not_oracle",
        "execution_timeout_not_oracle",
        "executable_missing_not_oracle",
        "execution_error_not_oracle",
    }:
        raise SystemExit(f"oracle harness execution status drift in {oracle_path}")

    attempted = harness_execution.get("attempted")
    if status == "exited_zero_not_oracle":
        if attempted is not True or harness_execution.get("returncode") != 0:
            raise SystemExit(f"oracle harness execution exit status drift in {oracle_path}")
    elif status == "exited_nonzero_not_oracle":
        returncode = harness_execution.get("returncode")
        if attempted is not True or not isinstance(returncode, int) or returncode == 0:
            raise SystemExit(f"oracle harness execution exit status drift in {oracle_path}")
    elif status == "execution_timeout_not_oracle":
        if attempted is not True or harness_execution.get("returncode") is not None:
            raise SystemExit(f"oracle harness execution timeout status drift in {oracle_path}")
    else:
        if attempted is not False or harness_execution.get("returncode") is not None:
            raise SystemExit(f"oracle harness execution non-attempted status drift in {oracle_path}")

    executable_path = harness_execution.get("executable_path")
    if not isinstance(executable_path, str) or not executable_path:
        raise SystemExit(f"oracle harness execution executable path drift in {oracle_path}")
    argv = harness_execution.get("argv")
    if executable_path != "missing" and argv != [executable_path]:
        raise SystemExit(f"oracle harness execution argv drift in {oracle_path}")
    if executable_path == "missing" and argv != []:
        raise SystemExit(f"oracle harness execution argv drift in {oracle_path}")
    if "output_gate" not in harness_execution:
        raise SystemExit(f"oracle harness output gate missing in {oracle_path}")
    validate_harness_output_gate(harness_execution.get("output_gate"), harness_execution, oracle_path)


def validate_compile_toolchain_provenance(compile_execution: dict[str, Any], oracle_path: Path) -> None:
    adapter = compile_execution.get("toolchain_adapter")
    execution_argv = compile_execution.get("execution_argv")
    if adapter is None and execution_argv is None:
        return
    if adapter not in {"local", "wsl"}:
        raise SystemExit(f"oracle harness compile execution toolchain provenance drift in {oracle_path}")
    execution = require_string_list(
        execution_argv,
        f"oracle harness compile execution toolchain provenance drift in {oracle_path}",
    )
    if not execution:
        raise SystemExit(f"oracle harness compile execution toolchain provenance drift in {oracle_path}")
    compiler_path = compile_execution.get("compiler_path")
    if not isinstance(compiler_path, str) or not compiler_path:
        raise SystemExit(f"oracle harness compile execution toolchain provenance drift in {oracle_path}")
    if adapter == "local":
        if execution[0] != compiler_path:
            raise SystemExit(f"oracle harness compile execution toolchain provenance drift in {oracle_path}")
        return
    validate_wsl_execution_argv(execution, compiler_path, oracle_path, "compile execution")


def validate_harness_toolchain_provenance(
    harness_execution: dict[str, Any],
    compile_execution: dict[str, Any],
    oracle_path: Path,
) -> None:
    compile_adapter = compile_execution.get("toolchain_adapter")
    adapter = harness_execution.get("toolchain_adapter")
    execution_argv = harness_execution.get("execution_argv")
    if compile_adapter != "wsl" and adapter is None and execution_argv is None:
        return
    if compile_adapter == "wsl" and adapter != "wsl":
        raise SystemExit(f"oracle harness execution toolchain provenance drift in {oracle_path}")
    if adapter not in {"wsl"}:
        raise SystemExit(f"oracle harness execution toolchain provenance drift in {oracle_path}")
    execution = require_string_list(
        execution_argv,
        f"oracle harness execution toolchain provenance drift in {oracle_path}",
    )
    if not execution:
        raise SystemExit(f"oracle harness execution toolchain provenance drift in {oracle_path}")
    executable_path = harness_execution.get("executable_path")
    if not isinstance(executable_path, str) or not executable_path:
        raise SystemExit(f"oracle harness execution toolchain provenance drift in {oracle_path}")
    validate_wsl_execution_argv(execution, executable_path, oracle_path, "harness execution")


def validate_wsl_execution_argv(
    execution: list[str],
    required_fragment: str,
    oracle_path: Path,
    label: str,
) -> None:
    launcher = execution[0].replace("\\", "/").lower()
    launcher_name = launcher.rsplit("/", 1)[-1]
    if launcher_name not in {"wsl", "wsl.exe"} or "-e" not in execution:
        raise SystemExit(f"oracle harness {label} toolchain provenance drift in {oracle_path}")
    required_fragments = wsl_equivalent_fragments(required_fragment)
    if not any(fragment in item for fragment in required_fragments for item in execution):
        raise SystemExit(f"oracle harness {label} toolchain provenance drift in {oracle_path}")


def wsl_equivalent_fragments(path_text: str) -> list[str]:
    fragments = [path_text.replace("\\", "/")]
    if path_text.startswith("/"):
        return fragments
    original_match = re.match(r"^([A-Za-z]):/(.*)$", fragments[0])
    if original_match:
        drive, rest = original_match.groups()
        fragments.append(f"/mnt/{drive.lower()}/{rest}")
    candidate = Path(path_text)
    resolved = candidate if candidate.is_absolute() else REPO_ROOT / candidate
    resolved_text = resolved.resolve().as_posix()
    fragments.append(resolved_text)
    match = re.match(r"^([A-Za-z]):/(.*)$", resolved_text)
    if match:
        drive, rest = match.groups()
        fragments.append(f"/mnt/{drive.lower()}/{rest}")
    return list(dict.fromkeys(fragments))


def validate_harness_output_gate(
    output_gate: Any,
    harness_execution: dict[str, Any],
    oracle_path: Path,
) -> None:
    if not isinstance(output_gate, dict):
        raise SystemExit(f"oracle harness output gate missing from {oracle_path}")
    if output_gate.get("semantic_pass") is not False:
        raise SystemExit(f"oracle harness output gate cannot claim semantic_pass in {oracle_path}")
    if output_gate.get("gate") != "c_oracle_harness_output":
        raise SystemExit(f"oracle harness output gate identity drift in {oracle_path}")
    require_string_list(
        output_gate.get("compared_fields"),
        f"oracle harness output gate compared fields drift in {oracle_path}",
    )
    if not isinstance(output_gate.get("fixture_expected_output_status"), str):
        raise SystemExit(f"oracle harness output gate fixture status drift in {oracle_path}")
    status = output_gate.get("status")
    if status not in {
        "matched_not_oracle",
        "mismatch_not_oracle",
        "unsupported_not_oracle",
        "not_run_not_oracle",
    }:
        raise SystemExit(f"oracle harness output gate status drift in {oracle_path}")
    expected = require_string_list(
        output_gate.get("expected_stdout_fragments"),
        f"oracle harness output gate expected stdout fragments drift in {oracle_path}",
    )
    matched = require_string_list(
        output_gate.get("matched_stdout_fragments"),
        f"oracle harness output gate matched stdout fragments drift in {oracle_path}",
    )
    missing = require_string_list(
        output_gate.get("missing_stdout_fragments"),
        f"oracle harness output gate missing stdout fragments drift in {oracle_path}",
    )
    diagnostics = require_string_list(
        output_gate.get("diagnostics"),
        f"oracle harness output gate diagnostics drift in {oracle_path}",
    )
    if not diagnostics:
        raise SystemExit(f"oracle harness output gate diagnostics missing in {oracle_path}")
    if status == "matched_not_oracle":
        if harness_execution.get("status") != "exited_zero_not_oracle" or harness_execution.get("returncode") != 0:
            raise SystemExit(f"oracle harness output gate matched status drift in {oracle_path}")
        if not expected or matched != expected or missing:
            raise SystemExit(f"oracle harness output gate matched fragments drift in {oracle_path}")
    elif status == "mismatch_not_oracle":
        if harness_execution.get("status") != "exited_zero_not_oracle" or harness_execution.get("returncode") != 0:
            raise SystemExit(f"oracle harness output gate mismatch status drift in {oracle_path}")
        if not expected or not missing:
            raise SystemExit(f"oracle harness output gate mismatch fragments drift in {oracle_path}")
        if sorted(matched + missing) != sorted(expected):
            raise SystemExit(f"oracle harness output gate fragment partition drift in {oracle_path}")
    elif status == "unsupported_not_oracle":
        if expected or matched or missing:
            raise SystemExit(f"oracle harness output gate unsupported fragments drift in {oracle_path}")
    else:
        if harness_execution.get("status") == "exited_zero_not_oracle" and harness_execution.get("returncode") == 0:
            raise SystemExit(f"oracle harness output gate not_run status drift in {oracle_path}")
        if matched:
            raise SystemExit(f"oracle harness output gate not_run matched fragments drift in {oracle_path}")


def require_string_list(value: Any, message: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise SystemExit(message)
    return value


def oracle_fixture_binding(spec: dict[str, Any]) -> dict[str, Any]:
    fixture = spec.get("fixture_contract", {})
    cases = fixture.get("cases") or []
    case_bindings = oracle_fixture_case_bindings(spec)
    if not cases:
        binding_status = "missing_or_empty"
    else:
        binding_status = "declared_not_executed"
    return {
        "path": fixture_path_from_spec(spec),
        "case_count": len(cases),
        "binding_status": binding_status,
        "behavior_fields": behavior_fields_from_spec(spec),
        "observable_outputs": behavior_fields_from_spec(spec),
        "case_bindings": case_bindings,
        "expected_output_status": fixture_expected_output_status(case_bindings),
    }


def oracle_fixture_case_bindings(spec: dict[str, Any]) -> list[dict[str, Any]]:
    fixture = spec.get("fixture_contract", {})
    fields = behavior_fields_from_spec(spec)
    bindings: list[dict[str, Any]] = []
    for index, raw_case in enumerate(fixture.get("cases") or []):
        case = raw_case if isinstance(raw_case, dict) else {}
        expected_outputs = case.get("expected_outputs")
        if expected_outputs is None:
            expected_outputs = case.get("expected", {})
        if not isinstance(expected_outputs, dict):
            expected_outputs = {}
        if not expected_outputs:
            expected_outputs = expected_outputs_from_fixture_refs(spec, case)
        normalized_expected = {str(key): expected_outputs[key] for key in sorted(expected_outputs)}
        missing_outputs = [field for field in fields if field not in normalized_expected]
        if normalized_expected and not missing_outputs:
            binding_status = "declared_not_executed"
        elif normalized_expected:
            binding_status = "partial_expected_outputs"
        elif case.get("expected_ref"):
            binding_status = "expected_ref_only"
        else:
            binding_status = "missing_expected_outputs"
        bindings.append(
            {
                "id": str(case.get("id") or f"case-{index}"),
                "input_ref": str(case.get("input_ref") or f"cases[{index}]"),
                "expected_ref": str(case.get("expected_ref") or "missing"),
                "expected_outputs": normalized_expected,
                "observable_outputs": fields,
                "missing_observable_outputs": missing_outputs,
                "binding_status": binding_status,
            }
        )
    return bindings


def expected_outputs_from_fixture_refs(spec: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    fields = behavior_fields_from_spec(spec)
    if not fields:
        return {}
    fixture = spec.get("fixture_contract", {})
    input_ref = str(case.get("input_ref") or "")
    candidate_refs = [case.get("expected_ref"), fixture.get("path") or fixture.get("input")]
    for candidate_ref in candidate_refs:
        payload = load_fixture_ref_payload(candidate_ref)
        if payload is None:
            continue
        case_payload = fixture_case_payload(payload, input_ref)
        if not isinstance(case_payload, dict):
            continue
        return {field: case_payload[field] for field in fields if field in case_payload}
    return {}


def load_fixture_ref_payload(ref: Any) -> Any | None:
    if not ref:
        return None
    ref_text = str(ref)
    if ref_text == "inline" or ref_text.startswith("cases["):
        return None
    path_text = ref_text.split("#", 1)[0]
    path = Path(path_text)
    if not path.is_absolute():
        path = REPO_ROOT / path_text
    if not path.exists() or not path.is_file():
        return None
    return load_json(path)


def fixture_case_payload(payload: Any, case_ref: str) -> Any | None:
    index = case_ref_index(case_ref)
    if index is None:
        return None
    cases = payload.get("cases") if isinstance(payload, dict) else payload
    if not isinstance(cases, list) or index < 0 or index >= len(cases):
        return None
    return cases[index]


def case_ref_index(case_ref: str) -> int | None:
    match = re.fullmatch(r"cases\[(\d+)\]", str(case_ref))
    if not match:
        return None
    return int(match.group(1))


def fixture_expected_output_status(case_bindings: list[dict[str, Any]]) -> str:
    if not case_bindings:
        return "missing_or_empty"
    statuses = {str(item.get("binding_status")) for item in case_bindings}
    if statuses == {"declared_not_executed"}:
        return "declared_not_executed"
    if "missing_expected_outputs" in statuses:
        return "missing_expected_outputs"
    if "partial_expected_outputs" in statuses:
        return "partial_expected_outputs"
    return "expected_ref_only"


def oracle_fixture_comment_fragments(fixture_binding: dict[str, Any]) -> list[str]:
    outputs = ", ".join(str(item) for item in fixture_binding.get("observable_outputs", [])) or "none"
    fragments = [
        f"fixture cases: {fixture_binding.get('case_count', 0)}",
        f"observable outputs: {outputs}",
    ]
    for case in fixture_binding.get("case_bindings", []):
        expected_outputs = json.dumps(case.get("expected_outputs", {}), sort_keys=True)
        fragments.append(
            "fixture case: "
            f"{case.get('id')} input_ref={case.get('input_ref')} "
            f"expected_ref={case.get('expected_ref')} expected_outputs={expected_outputs}"
        )
    return fragments


def compile_source_root(spec: dict[str, Any]) -> str:
    source_root = spec.get("source", {}).get("source_root")
    if not source_root:
        return "."
    return normalize_path_text(source_root)


def compile_link_source_files(spec: dict[str, Any], source_root: str) -> list[dict[str, Any]]:
    files = []
    for item in spec.get("c_boundary", {}).get("files", []):
        if not isinstance(item, dict) or not item.get("path"):
            continue
        path = normalize_path_text(item["path"])
        files.append(
            {
                "path": path,
                "resolved_path": resolve_source_root_path(source_root, path),
                "role": str(item.get("role") or "source"),
                "sha256": str(item.get("sha256") or "unknown"),
                "resolution": "source_root_relative" if source_root != "." else "declared_path",
            }
        )
    for item in spec.get("build_profile", {}).get("link_source_files", []):
        if not isinstance(item, dict) or not item.get("path"):
            continue
        path = normalize_path_text(item["path"])
        files.append(
            {
                "path": path,
                "resolved_path": resolve_source_root_path(source_root, path),
                "role": str(item.get("role") or "link_dependency"),
                "sha256": str(item.get("sha256") or "unknown"),
                "resolution": "source_root_relative" if source_root != "." else "declared_path",
            }
        )
    return files


def c_oracle_link_strategy(spec: dict[str, Any]) -> str:
    if spec.get("build_profile", {}).get("link_source_files"):
        return "compile_harness_with_declared_c_boundary_and_build_profile_sources"
    return "compile_harness_with_declared_c_boundary_sources"


def resolve_source_root_path(source_root: str, path: Any) -> str:
    path_text = normalize_path_text(path)
    if not path_text or path_is_absolute(path_text) or source_root == ".":
        return path_text
    if not path_is_absolute(source_root) and (
        path_text == source_root or path_text.startswith(f"{source_root}/")
    ):
        return path_text
    return normalize_path_text(f"{source_root}/{path_text}")


def path_is_absolute(path: str) -> bool:
    return (
        path.startswith("/")
        or path.startswith("//")
        or path.startswith("\\\\")
        or (len(path) >= 3 and path[1] == ":" and path[2] in {"/", "\\"})
    )


def normalize_path_text(path: Any) -> str:
    return str(path).strip().replace("\\", "/").rstrip("/")


def validate_cache_oracle_harness_identity(
    evidence_dir: Path, prefix: str, expected_identity: dict[str, Any]
) -> None:
    cache_path = evidence_dir / f"{prefix}-auto-cache-metadata.json"
    cache = load_json(cache_path)
    if "c_oracle_harness_identity" not in cache.get("cache_input_fields", []):
        raise SystemExit(f"cache metadata cache_input_fields missing c_oracle_harness_identity in {cache_path}")
    if cache.get("c_oracle_harness_identity") != expected_identity:
        raise SystemExit(f"oracle harness identity drift in {cache_path}")


def validate_draft_oracle_fail_closed(
    evidence_dir: Path, prefix: str, oracle: dict[str, Any], oracle_path: Path
) -> None:
    if (
        oracle.get("status") == "C_ORACLE_GENERATED"
        and oracle.get("toolchain_status") == "C_ORACLE_GENERATED"
        and oracle.get("semantic_pass") is True
    ):
        return

    if oracle.get("semantic_pass"):
        raise SystemExit(f"draft oracle cannot claim semantic_pass=true in {oracle_path}")

    final_path = evidence_dir / f"{prefix}-final-verification.json"
    manifest_path = evidence_dir / f"{prefix}-evidence-manifest.json"
    profile_path = evidence_dir / f"{prefix}-validation-profile.json"
    final = load_json(final_path)
    manifest = load_json(manifest_path)
    profile = load_json(profile_path)

    if final.get("status") == "passed" or final.get("semantic_pass"):
        raise SystemExit(f"draft oracle cannot coexist with passed final verification in {final_path}")
    if manifest.get("status") == "passed" or manifest.get("semantic_pass"):
        raise SystemExit(f"draft oracle cannot coexist with passed evidence manifest in {manifest_path}")
    if profile.get("status") == "passed":
        raise SystemExit(f"draft oracle cannot coexist with passed validation profile in {profile_path}")


def validate_schema_diff_contract(evidence_dir: Path, prefix: str, slice_spec_path: Path) -> None:
    slice_spec = load_json(slice_spec_path)
    diff_path = evidence_dir / f"{prefix}-diff.json"
    negative_path = evidence_dir / f"{prefix}-negative-diff.json"
    schema_diff = load_json(diff_path)
    negative_diff = load_json(negative_path)
    oracle = load_json(evidence_dir / f"{prefix}-c-oracle-status.json")
    rust_report = load_json(evidence_dir / f"{prefix}-rust-report.json")
    validate_draft_schema_diff_report(schema_diff, slice_spec, diff_path, oracle, rust_report)
    validate_draft_negative_diff_report(negative_diff, schema_diff, negative_path)


def validate_draft_schema_diff_report(
    report: dict[str, Any],
    slice_spec: dict[str, Any],
    path: Path,
    oracle: dict[str, Any] | None = None,
    rust_report: dict[str, Any] | None = None,
) -> None:
    status = report.get("status")
    if status == "passed":
        return
    if status not in {"incomplete", "draft", "blocked"}:
        raise SystemExit(f"schema diff status drift in {path}")
    if report.get("semantic_pass") is not False:
        raise SystemExit(f"schema diff draft cannot claim semantic_pass in {path}")
    if report.get("diff_gate") != "schema_aware_c_rust_diff":
        raise SystemExit(f"schema diff diff_gate drift in {path}")
    if report.get("accepted_diff_required") is not True:
        raise SystemExit(f"schema diff accepted_diff_required missing in {path}")
    if "accepted_diff" in report:
        raise SystemExit(f"schema diff draft cannot contain accepted_diff in {path}")
    validate_generated_candidate_diff_boundary(report, slice_spec, path, oracle, rust_report)
    required_inputs = report.get("required_inputs")
    if not isinstance(required_inputs, dict):
        raise SystemExit(f"schema diff required_inputs missing in {path}")
    if required_inputs.get("c_oracle_required_status") != "C_ORACLE_GENERATED":
        raise SystemExit(f"schema diff required_inputs.c_oracle_required_status drift in {path}")
    if required_inputs.get("rust_report_required_status") != "passed":
        raise SystemExit(f"schema diff required_inputs.rust_report_required_status drift in {path}")
    if not required_inputs.get("c_oracle_actual_status"):
        raise SystemExit(f"schema diff required_inputs.c_oracle_actual_status missing in {path}")
    if not required_inputs.get("rust_report_actual_status"):
        raise SystemExit(f"schema diff required_inputs.rust_report_actual_status missing in {path}")

    compared_fields = require_string_list(
        report.get("compared_fields"),
        f"schema diff compared_fields drift in {path}",
    )
    expected_fields = behavior_fields_from_spec(slice_spec)
    if expected_fields and not set(expected_fields).issubset(set(compared_fields)):
        raise SystemExit(f"schema diff compared_fields missing behavior fields in {path}")
    if report.get("first_mismatch") is not None:
        raise SystemExit(f"schema diff draft cannot contain first_mismatch evidence in {path}")


def validate_generated_candidate_diff_boundary(
    report: dict[str, Any],
    slice_spec: dict[str, Any],
    path: Path,
    oracle: dict[str, Any] | None = None,
    rust_report: dict[str, Any] | None = None,
) -> None:
    candidate_pass = report.get("generated_candidate_diff_pass") is True
    if not candidate_pass:
        if "candidate_diff" in report:
            raise SystemExit(f"schema diff candidate_diff present without generated_candidate_diff_pass in {path}")
        if report.get("blocked_by") != ["c_oracle", "rust_replay"]:
            raise SystemExit(f"schema diff blocked_by drift in {path}")
        return

    if report.get("blocked_by") != ["accepted_c_oracle"]:
        raise SystemExit(f"schema diff candidate blocked_by drift in {path}")
    candidate = report.get("candidate_diff")
    if not isinstance(candidate, dict):
        raise SystemExit(f"schema diff candidate_diff missing in {path}")
    if not isinstance(oracle, dict):
        raise SystemExit(f"schema diff candidate oracle report missing in {path}")
    if not isinstance(rust_report, dict):
        raise SystemExit(f"schema diff candidate rust report missing in {path}")
    compile_execution = oracle.get("compile_execution")
    if not isinstance(compile_execution, dict):
        raise SystemExit(f"schema diff candidate oracle compile_execution missing in {path}")
    harness_execution = compile_execution.get("harness_execution")
    if not isinstance(harness_execution, dict):
        raise SystemExit(f"schema diff candidate oracle harness_execution missing in {path}")
    output_gate = harness_execution.get("output_gate")
    if not isinstance(output_gate, dict):
        raise SystemExit(f"schema diff candidate oracle output_gate missing in {path}")
    replay = rust_report.get("replay")
    if not isinstance(replay, dict):
        raise SystemExit(f"schema diff candidate rust report replay missing in {path}")
    if candidate.get("status") != "matched_not_oracle":
        raise SystemExit(f"schema diff candidate_diff status drift in {path}")
    if candidate.get("semantic_pass") is not False:
        raise SystemExit(f"schema diff candidate_diff cannot claim semantic_pass in {path}")
    if oracle.get("status") != "DRAFT_GENERATED":
        raise SystemExit(f"schema diff candidate oracle status drift in {path}")
    if oracle.get("toolchain_status") != "COMPILE_SUCCEEDED_NOT_ORACLE":
        raise SystemExit(f"schema diff candidate oracle toolchain status drift in {path}")
    if oracle.get("semantic_pass") is True:
        raise SystemExit(f"schema diff candidate oracle cannot claim semantic_pass in {path}")
    if compile_execution.get("status") != "compile_succeeded_not_oracle":
        raise SystemExit(f"schema diff candidate oracle compile status drift in {path}")
    if harness_execution.get("status") != "exited_zero_not_oracle":
        raise SystemExit(f"schema diff candidate oracle harness status drift in {path}")
    if output_gate.get("status") != "matched_not_oracle":
        raise SystemExit(f"schema diff candidate_diff output gate drift in {path}")
    if output_gate.get("semantic_pass") is True:
        raise SystemExit(f"schema diff candidate oracle output gate cannot claim semantic_pass in {path}")
    if rust_report.get("status") != "passed":
        raise SystemExit(f"schema diff candidate rust report status drift in {path}")
    if rust_report.get("generated_draft_replay_pass") is not True:
        raise SystemExit(f"schema diff candidate rust report replay pass drift in {path}")
    if rust_report.get("generated_draft_semantic_pass") is True:
        raise SystemExit(f"schema diff candidate rust report cannot claim generated_draft_semantic_pass in {path}")
    if replay.get("status") != "passed":
        raise SystemExit(f"schema diff candidate rust replay status drift in {path}")
    if candidate.get("c_oracle_output_gate_status") != output_gate.get("status"):
        raise SystemExit(f"schema diff candidate_diff output gate drift in {path}")
    if candidate.get("rust_replay_status") != replay.get("status"):
        raise SystemExit(f"schema diff candidate_diff rust replay drift in {path}")
    if candidate.get("missing_stdout_fragments") != output_gate.get("missing_stdout_fragments"):
        raise SystemExit(f"schema diff candidate_diff missing stdout fragments in {path}")
    matched_fragments = candidate.get("matched_stdout_fragments")
    if not isinstance(matched_fragments, list) or not matched_fragments:
        raise SystemExit(f"schema diff candidate_diff matched stdout fragments missing in {path}")
    if matched_fragments != output_gate.get("matched_stdout_fragments"):
        raise SystemExit(f"schema diff candidate_diff matched stdout fragments drift in {path}")
    compared_fields = require_string_list(
        candidate.get("compared_fields"),
        f"schema diff candidate_diff compared_fields drift in {path}",
    )
    output_gate_fields = require_string_list(
        output_gate.get("compared_fields"),
        f"schema diff candidate oracle output gate compared_fields drift in {path}",
    )
    if compared_fields != output_gate_fields:
        raise SystemExit(f"schema diff candidate_diff compared_fields drift in {path}")
    expected_fields = behavior_fields_from_spec(slice_spec)
    if expected_fields and not set(expected_fields).issubset(set(compared_fields)):
        raise SystemExit(f"schema diff candidate_diff compared_fields missing behavior fields in {path}")
    required_inputs = report.get("required_inputs")
    if not isinstance(required_inputs, dict):
        raise SystemExit(f"schema diff candidate required_inputs missing in {path}")
    if required_inputs.get("c_oracle_actual_status") != oracle.get("status"):
        raise SystemExit(f"schema diff candidate required_inputs.c_oracle_actual_status drift in {path}")
    if required_inputs.get("c_oracle_actual_toolchain_status") != oracle.get("toolchain_status"):
        raise SystemExit(f"schema diff candidate required_inputs.c_oracle_actual_toolchain_status drift in {path}")
    if required_inputs.get("c_oracle_output_gate_actual_status") != output_gate.get("status"):
        raise SystemExit(f"schema diff candidate required_inputs.c_oracle_output_gate_actual_status drift in {path}")
    if required_inputs.get("rust_replay_actual_status") != replay.get("status"):
        raise SystemExit(f"schema diff candidate required_inputs.rust_replay_actual_status drift in {path}")
    if required_inputs.get("rust_report_actual_status") != rust_report.get("status"):
        raise SystemExit(f"schema diff candidate required_inputs.rust_report_actual_status drift in {path}")


def validate_draft_negative_diff_report(
    report: dict[str, Any],
    schema_diff: dict[str, Any],
    path: Path,
) -> None:
    status = report.get("status")
    if status not in {"incomplete", "draft", "blocked"}:
        return
    if report.get("semantic_pass", False) is not False:
        raise SystemExit(f"negative diff draft cannot claim semantic_pass in {path}")
    if report.get("negative_diff_gate") != "schema_aware_negative_diff":
        raise SystemExit(f"negative diff negative_diff_gate drift in {path}")
    if report.get("expected_failure") is not True:
        raise SystemExit(f"negative diff expected_failure drift in {path}")
    if report.get("mutation_detected") is not False:
        raise SystemExit(f"negative diff mutation_detected drift in {path}")
    if report.get("accepted_negative_diff_required") is not True:
        raise SystemExit(f"negative diff accepted_negative_diff_required missing in {path}")
    if "accepted_negative_diff" in report:
        raise SystemExit(f"negative diff draft cannot contain accepted_negative_diff in {path}")
    if report.get("blocked_by") != ["schema_diff"]:
        raise SystemExit(f"negative diff blocked_by drift in {path}")
    required_inputs = report.get("required_inputs")
    if not isinstance(required_inputs, dict):
        raise SystemExit(f"negative diff required_inputs missing in {path}")
    if required_inputs.get("schema_diff_required_status") != "passed":
        raise SystemExit(f"negative diff required_inputs.schema_diff_required_status drift in {path}")
    if required_inputs.get("schema_diff_actual_status") != schema_diff.get("status"):
        raise SystemExit(f"negative diff required_inputs.schema_diff_actual_status drift in {path}")
    if required_inputs.get("schema_diff_required_first_mismatch") is not None:
        raise SystemExit(f"negative diff required_inputs.schema_diff_required_first_mismatch drift in {path}")
    if report.get("first_mismatch") is not None:
        raise SystemExit(f"negative diff draft cannot contain first_mismatch evidence in {path}")


def validate_passed_schema_diff_report(report: dict[str, Any], slice_spec: dict[str, Any]) -> list[str]:
    if report.get("semantic_pass") is not True:
        raise SystemExit("semantic pass requires schema diff semantic_pass=true")
    if report.get("first_mismatch") is not None:
        raise SystemExit("semantic pass requires schema diff first_mismatch=null")
    if report.get("diff_gate") != "schema_aware_c_rust_diff":
        raise SystemExit("semantic pass schema diff diff_gate drift")
    if report.get("accepted_diff_required") is not True:
        raise SystemExit("semantic pass schema diff accepted_diff_required drift")
    if report.get("blocked_by") != []:
        raise SystemExit("semantic pass schema diff blocked_by must be empty")

    compared_fields = require_string_list(
        report.get("compared_fields"),
        "semantic pass schema diff compared_fields drift",
    )
    if not compared_fields:
        raise SystemExit("semantic pass schema diff compared_fields must be non-empty")
    expected_fields = behavior_fields_from_spec(slice_spec)
    if expected_fields and not set(expected_fields).issubset(set(compared_fields)):
        raise SystemExit("semantic pass schema diff compared_fields missing behavior fields")

    required_inputs = report.get("required_inputs")
    if not isinstance(required_inputs, dict):
        raise SystemExit("semantic pass schema diff required_inputs drift")
    if required_inputs.get("c_oracle_required_status") != "C_ORACLE_GENERATED":
        raise SystemExit("semantic pass schema diff required_inputs.c_oracle_required_status drift")
    if required_inputs.get("rust_report_required_status") != "passed":
        raise SystemExit("semantic pass schema diff required_inputs.rust_report_required_status drift")
    if required_inputs.get("schema_diff_actual_status") not in {None, "passed"}:
        raise SystemExit("semantic pass schema diff required_inputs.schema_diff_actual_status drift")

    require_embedded_evidence_ref(
        report.get("accepted_diff"),
        "schema diff accepted_diff",
        {"passed"},
        {"passed"},
    )
    return compared_fields


def validate_passed_negative_diff_report(report: dict[str, Any], compared_fields: list[str]) -> None:
    require_status(report, "negative_diff", {"passed", "expected_failed", "failed"})
    if report.get("negative_diff_gate") != "schema_aware_negative_diff":
        raise SystemExit("semantic pass negative diff negative_diff_gate drift")
    if report.get("expected_failure") is not True:
        raise SystemExit("semantic pass negative diff expected_failure=true required")
    if not mutation_detected(report):
        raise SystemExit("semantic pass requires negative_diff mutation_detected/detected=true")
    if report.get("blocked_by") != []:
        raise SystemExit("semantic pass negative diff blocked_by must be empty")
    if report.get("root_blocked_by") != []:
        raise SystemExit("semantic pass negative diff root_blocked_by must be empty")
    if report.get("accepted_negative_diff_required") is not True:
        raise SystemExit("semantic pass negative diff accepted_negative_diff_required drift")

    first_mismatch = report.get("first_mismatch")
    if not isinstance(first_mismatch, dict) or not first_mismatch:
        raise SystemExit("semantic pass negative diff first_mismatch evidence required")
    mismatch_field = first_mismatch.get("field") or first_mismatch.get("field_path")
    if isinstance(mismatch_field, str) and compared_fields:
        field_matches = any(mismatch_field == field or mismatch_field.endswith(f".{field}") for field in compared_fields)
        if not field_matches:
            raise SystemExit("semantic pass negative diff first_mismatch field outside compared_fields")

    required_inputs = report.get("required_inputs")
    if not isinstance(required_inputs, dict):
        raise SystemExit("semantic pass negative diff required_inputs drift")
    if required_inputs.get("schema_diff_required_status") != "passed":
        raise SystemExit("semantic pass negative diff required_inputs.schema_diff_required_status drift")
    if required_inputs.get("schema_diff_required_first_mismatch") is not None:
        raise SystemExit("semantic pass negative diff required_inputs.schema_diff_required_first_mismatch drift")
    if required_inputs.get("schema_diff_actual_status") not in {None, "passed"}:
        raise SystemExit("semantic pass negative diff required_inputs.schema_diff_actual_status drift")

    require_embedded_evidence_ref(
        report.get("accepted_negative_diff"),
        "negative diff accepted_negative_diff",
        {"passed"},
        {"passed", "expected_failed", "failed"},
    )


def require_embedded_evidence_ref(
    ref: Any,
    label: str,
    allowed_ref_statuses: set[str],
    allowed_payload_statuses: set[str],
) -> dict[str, Any]:
    if not isinstance(ref, dict) or not ref.get("path"):
        raise SystemExit(f"semantic pass requires {label}")
    status = str(ref.get("status", ""))
    if status not in allowed_ref_statuses:
        raise SystemExit(f"semantic pass requires {label}.status in {sorted(allowed_ref_statuses)}, got {status!r}")
    ref_sha = ref.get("sha256")
    if not isinstance(ref_sha, str) or not ref_sha:
        raise SystemExit(f"semantic pass requires {label}.sha256")
    resolved = resolve_ref_path(str(ref["path"]))
    if not resolved.exists():
        raise SystemExit(f"semantic pass requires existing {label}: {resolved}")
    actual_sha = sha256(resolved)
    if ref_sha != actual_sha:
        raise SystemExit(f"semantic pass {label}.sha256 mismatch: {ref_sha} != {actual_sha}")
    payload = load_json(resolved)
    payload_status = str(payload.get("status", ""))
    if payload_status not in allowed_payload_statuses:
        raise SystemExit(
            f"semantic pass requires {label} payload status in {sorted(allowed_payload_statuses)}, got {payload_status!r}"
        )
    return payload


def validate_route_source_artifact_refs(evidence_dir: Path, prefix: str, route: dict[str, Any], baseline_path: Path) -> None:
    source_artifacts = route.get("source_artifacts")
    if not isinstance(source_artifacts, dict):
        raise SystemExit("route_decision.source_artifacts missing")
    expected_paths = {
        "type_map": evidence_dir / f"{prefix}-type-map.json",
        "cfg": evidence_dir / f"{prefix}-cfg.json",
        "pointer_graph": evidence_dir / f"{prefix}-pointer-graph.json",
        "translation_plan": evidence_dir / f"{prefix}-auto-translation-plan.json",
        "c2rust_baseline": baseline_path,
    }
    for key, expected_path in expected_paths.items():
        require_ref(source_artifacts.get(key), expected_path, f"route_decision.source_artifacts.{key}")


def validate_typed_ir_candidate_binding(
    evidence_dir: Path,
    prefix: str,
    route: dict[str, Any],
    profile: dict[str, Any],
) -> None:
    route_candidate_generation = route.get("candidate_generation")
    if not isinstance(route_candidate_generation, dict):
        if profile.get("candidate_generation") is not None:
            raise SystemExit("validation_profile.candidate_generation must match route_decision.candidate_generation")
        return
    profile_candidate_generation = profile.get("candidate_generation")
    if profile_candidate_generation != route_candidate_generation:
        raise SystemExit("validation_profile.candidate_generation must match route_decision.candidate_generation")

    typed_ir = route_candidate_generation.get("typed_ir")
    if not isinstance(typed_ir, dict):
        return
    if typed_ir.get("semantic_pass") is not False:
        raise SystemExit("route_decision.candidate_generation.typed_ir cannot claim semantic_pass")

    report_path = evidence_dir / f"{prefix}-clang-lowering-report.json"
    source_artifact_ref = typed_ir.get("source_artifact")
    if typed_ir.get("status") == "generated" or ref_expects_existing_artifact(source_artifact_ref):
        require_ref(
            source_artifact_ref,
            report_path,
            "route_decision.candidate_generation.typed_ir.source_artifact",
            require_sha=True,
        )
    route_source_artifacts = route.get("source_artifacts", {})
    if isinstance(route_source_artifacts, dict):
        clang_report_ref = route_source_artifacts.get("clang_lowering_report")
        if typed_ir.get("status") == "generated" or ref_expects_existing_artifact(clang_report_ref):
            require_ref(
                clang_report_ref,
                report_path,
                "route_decision.source_artifacts.clang_lowering_report",
                require_sha=True,
            )

    if not report_path.exists():
        return
    report = load_json(report_path)
    report_candidate = report.get("typed_ir_candidate")
    if not isinstance(report_candidate, dict):
        if typed_ir.get("status") in {"generated", "unsupported"}:
            raise SystemExit(f"typed IR candidate evidence missing from {report_path}")
        return
    if report_candidate.get("semantic_pass") is not False:
        raise SystemExit(f"typed IR candidate report cannot claim semantic_pass in {report_path}")

    readonly_globals = report_candidate.get("readonly_globals", [])
    expected = {
        "status": report_candidate.get("status"),
        "candidate_route": report_candidate.get("candidate_route"),
        "readonly_globals": readonly_globals,
        "readonly_globals_identity": {
            "count": len(readonly_globals) if isinstance(readonly_globals, list) else 0,
            "names": [
                str(item.get("name", ""))
                for item in readonly_globals
                if isinstance(item, dict) and item.get("name")
            ]
            if isinstance(readonly_globals, list)
            else [],
            "sha256": sha256_json(readonly_globals if isinstance(readonly_globals, list) else []),
        },
        "rust_draft_generated": bool(report_candidate.get("rust_draft_generated", False)),
        "semantic_pass": False,
    }
    if report_candidate.get("reason"):
        expected["reason"] = report_candidate.get("reason")
    if report_candidate.get("unsupported_reason"):
        expected["unsupported_reason"] = report_candidate.get("unsupported_reason")
    actual = {
        "status": typed_ir.get("status"),
        "candidate_route": typed_ir.get("candidate_route"),
        "readonly_globals": typed_ir.get("readonly_globals", []),
        "readonly_globals_identity": typed_ir.get("readonly_globals_identity"),
        "rust_draft_generated": bool(typed_ir.get("rust_draft_generated", False)),
        "semantic_pass": typed_ir.get("semantic_pass"),
    }
    if typed_ir.get("reason"):
        actual["reason"] = typed_ir.get("reason")
    if typed_ir.get("unsupported_reason"):
        actual["unsupported_reason"] = typed_ir.get("unsupported_reason")
    if actual != expected:
        raise SystemExit("route_decision.candidate_generation.typed_ir drifted from clang-lowering-report")


def validate_global_dependency_requirements(evidence_dir: Path, prefix: str, slice_spec_path: Path) -> None:
    slice_spec = load_json(slice_spec_path)
    expected = global_dependency_requirements(slice_spec)
    expected_names = [item["name"] for item in expected]

    type_map_path = evidence_dir / f"{prefix}-type-map.json"
    context_path = evidence_dir / f"{prefix}-context-pack.json"
    oracle_path = evidence_dir / f"{prefix}-c-oracle-status.json"
    pointer_path = evidence_dir / f"{prefix}-pointer-graph.json"
    cache_path = evidence_dir / f"{prefix}-auto-cache-metadata.json"
    slice_contract_path = evidence_dir / f"{prefix}-slice-contract.json"

    type_map = load_json(type_map_path)
    context = load_json(context_path)
    oracle = load_json(oracle_path)
    pointer = load_json(pointer_path)
    cache = load_json(cache_path)
    slice_contract = load_json(slice_contract_path)

    if not expected:
        reject_unexpected_global_requirements(
            [
                (type_map.get("global_dependencies"), type_map_path, "type_map.global_dependencies"),
                (context.get("global_dependencies"), context_path, "context_pack.global_dependencies"),
                (oracle.get("global_linkage_requirements"), oracle_path, "c_oracle.global_linkage_requirements"),
                (
                    global_dependency_requirements(slice_contract),
                    slice_contract_path,
                    "slice_contract.c_boundary.direct_dependencies",
                ),
                (context.get("source_boundary", {}).get("globals", []), context_path, "source_boundary.globals"),
                (pointer.get("source_boundary", {}).get("globals", []), pointer_path, "source_boundary.globals"),
            ]
        )
        require_empty_global_dependency_identity(cache, cache_path)
        return

    require_global_requirements(type_map.get("global_dependencies"), expected, type_map_path, "type_map.global_dependencies")
    require_global_requirements(context.get("global_dependencies"), expected, context_path, "context_pack.global_dependencies")
    require_global_requirements(
        oracle.get("global_linkage_requirements"),
        expected,
        oracle_path,
        "c_oracle.global_linkage_requirements",
    )
    require_global_requirements(
        global_dependency_requirements(slice_contract),
        expected,
        slice_contract_path,
        "slice_contract.c_boundary.direct_dependencies",
    )

    context_globals = context.get("source_boundary", {}).get("globals", [])
    pointer_globals = pointer.get("source_boundary", {}).get("globals", [])
    require_exact_names(context_globals, expected_names, context_path, "source_boundary.globals")
    require_exact_names(pointer_globals, expected_names, pointer_path, "source_boundary.globals")

    identity = cache.get("global_dependency_identity")
    if not isinstance(identity, dict):
        raise SystemExit(f"global dependency identity missing from {cache_path}")
    identity_names = identity.get("names", [])
    require_exact_names(identity_names, expected_names, cache_path, "global_dependency_identity.names")
    if "global_dependency_identity" not in cache.get("cache_input_fields", []):
        raise SystemExit(f"global dependency identity missing from cache_input_fields in {cache_path}")
    expected_identity_sha = sha256_json(expected)
    if identity.get("count") != len(expected):
        raise SystemExit(f"global dependency identity count mismatch in {cache_path}")
    if identity.get("sha256") != expected_identity_sha:
        raise SystemExit(
            f"global dependency identity sha256 mismatch in {cache_path}: {identity.get('sha256')} != {expected_identity_sha}"
        )

    harness_path = resolve_ref_path(str(oracle.get("harness_draft", "")))
    if not harness_path.exists():
        raise SystemExit(f"global dependency oracle harness draft missing: {harness_path}")
    harness_text = harness_path.read_text(encoding="utf-8")
    for name in expected_names:
        if f"global dependency: {name}" not in harness_text:
            raise SystemExit(f"global dependency {name!r} missing from oracle harness draft {harness_path}")


def global_dependency_requirements(payload: dict[str, Any]) -> list[dict[str, Any]]:
    dependencies = payload.get("c_boundary", {}).get("direct_dependencies", [])
    requirements: list[dict[str, Any]] = []
    seen: set[str] = set()
    for dependency in dependencies:
        if dependency.get("kind") != "global":
            continue
        name = str(dependency.get("name") or "")
        if not name or name in seen:
            continue
        seen.add(name)
        span = dependency.get("source_span") if isinstance(dependency.get("source_span"), dict) else {
            "file": "slice-spec",
            "line_start": 1,
            "line_end": 1,
        }
        requirements.append(
            {
                "name": name,
                "kind": "global",
                "source": dependency.get("source", "slice_spec"),
                "definition_status": dependency.get("definition_status", "declared"),
                "source_span": span,
                "sha256": dependency.get("sha256") or span.get("sha256") or "",
                "linkage_requirement": "must be available to C oracle harness and Rust replay context",
                "semantic_status": "required_before_acceptance",
            }
        )
    return requirements


def require_global_requirements(value: Any, expected: list[dict[str, Any]], path: Path, label: str) -> None:
    if not isinstance(value, list):
        raise SystemExit(f"global dependency evidence missing {label} in {path}")
    by_name = {str(item.get("name")): item for item in value if isinstance(item, dict) and item.get("name")}
    expected_names = [item["name"] for item in expected]
    actual_names = [str(item.get("name")) for item in value if isinstance(item, dict) and item.get("name")]
    require_exact_names(actual_names, expected_names, path, label)
    for expected_item in expected:
        name = expected_item["name"]
        actual = by_name.get(name)
        if actual is None:
            raise SystemExit(f"global dependency {name!r} missing from {path}:{label}")
        if actual != expected_item:
            raise SystemExit(f"global dependency {name!r} drift in {path}:{label}")


def reject_unexpected_global_requirements(items: list[tuple[Any, Path, str]]) -> None:
    for value, path, label in items:
        if value is None:
            continue
        if isinstance(value, list):
            if value:
                raise SystemExit(f"unexpected global dependency evidence in {path}:{label}")
            continue
        raise SystemExit(f"unexpected global dependency evidence in {path}:{label}")


def require_empty_global_dependency_identity(cache: dict[str, Any], path: Path) -> None:
    identity = cache.get("global_dependency_identity")
    if identity is None:
        return
    expected_identity = {"sha256": sha256_json([]), "count": 0, "names": []}
    if identity != expected_identity:
        raise SystemExit(f"unexpected global dependency identity in {path}")


def require_exact_names(actual_names: Any, expected_names: list[str], path: Path, label: str) -> None:
    if not isinstance(actual_names, list):
        raise SystemExit(f"global dependency evidence missing {label} in {path}")
    if sorted(str(name) for name in actual_names) != sorted(expected_names):
        raise SystemExit(f"global dependency names drift in {path}:{label}")


def l4_refuses_candidate_generation(route: dict[str, Any]) -> bool:
    return (
        route.get("level") == "L4"
        and route.get("status") == "refused"
        and route.get("translator", {}).get("candidate_generation_allowed") is False
    )


def accepted_evidence_authoritative_artifacts_claimed(route: dict[str, Any], auto_manifest: dict[str, Any]) -> bool:
    binding = auto_manifest.get("accepted_evidence_binding", {})
    claim = auto_manifest.get("claim_boundary", {})
    return (
        l4_refuses_candidate_generation(route)
        and route.get("policy", {}).get("accepted_evidence_authoritative") is True
        and route.get("policy", {}).get("generated_draft_semantic_pass") is False
        and binding.get("status") == "accepted"
        and binding.get("generated_draft_semantic_pass") is False
        and claim.get("accepted_evidence_authoritative") is True
        and claim.get("generated_draft_semantic_pass") is False
    )


def accepted_evidence_authoritative_manifest(
    route: dict[str, Any],
    auto_manifest: dict[str, Any],
    slice_spec: dict[str, Any],
) -> bool:
    return (
        slice_spec.get("claim_boundary", {}).get("accepted_evidence_authoritative") is True
        and accepted_evidence_authoritative_artifacts_claimed(route, auto_manifest)
    )


def accepted_evidence_authoritative_semantic_pass(
    route: dict[str, Any],
    profile: dict[str, Any],
    manifest: dict[str, Any],
    final: dict[str, Any],
    slice_spec: dict[str, Any],
) -> bool:
    manifest_claim = manifest.get("claim_boundary", {})
    return (
        slice_spec.get("claim_boundary", {}).get("accepted_evidence_authoritative") is True
        and l4_refuses_candidate_generation(route)
        and route.get("policy", {}).get("accepted_evidence_authoritative") is True
        and route.get("policy", {}).get("generated_draft_semantic_pass") is False
        and profile.get("accepted_evidence_authoritative") is True
        and profile.get("generated_draft_semantic_pass") is False
        and manifest_claim.get("accepted_evidence_authoritative") is True
        and manifest_claim.get("generated_draft_semantic_pass") is False
        and final.get("accepted_evidence_authoritative") is True
        and final.get("generated_draft_semantic_pass") is False
    )


def validate_l4_refused_has_no_candidate_artifact_status(
    evidence_dir: Path,
    prefix: str,
    auto_manifest: dict[str, Any],
    auto_manifest_path: Path,
) -> None:
    documents = [
        (auto_manifest_path, auto_manifest),
        (evidence_dir / f"{prefix}-auto-translation-plan.json", load_json(evidence_dir / f"{prefix}-auto-translation-plan.json")),
        (
            evidence_dir / f"{prefix}-test-translation-generated.json",
            load_json(evidence_dir / f"{prefix}-test-translation-generated.json"),
        ),
        (evidence_dir / f"{prefix}-rust-report.json", load_json(evidence_dir / f"{prefix}-rust-report.json")),
    ]
    for label, payload in documents:
        for path in candidate_status_paths(payload):
            raise SystemExit(f"L4/refused route cannot contain candidate artifact status in {label}:{path}")

    events_path = evidence_dir / f"{prefix}-auto-translation-events.jsonl"
    for line_number, event in enumerate(load_jsonl(events_path), start=1):
        if event.get("event_kind") == "rust_draft_generated" and event.get("status") != "blocked":
            raise SystemExit(
                f"L4/refused route cannot contain candidate artifact status in {events_path}:line {line_number}"
            )
        for path in candidate_status_paths(event):
            raise SystemExit(
                f"L4/refused route cannot contain candidate artifact status in {events_path}:line {line_number}{path}"
            )


def candidate_status_paths(value: Any, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        if value.get("status") in L4_REFUSED_FORBIDDEN_ARTIFACT_STATUSES:
            hits.append(f"{path}.status")
        for key, child in value.items():
            hits.extend(candidate_status_paths(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            hits.extend(candidate_status_paths(child, f"{path}[{index}]"))
    return hits


def ref_expects_existing_artifact(ref: Any) -> bool:
    return isinstance(ref, dict) and str(ref.get("status", "")) != "missing"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def require_ref(ref: Any, expected_path: Path, label: str, *, require_sha: bool = False) -> None:
    if not isinstance(ref, dict) or not ref.get("path"):
        raise SystemExit(f"{label} missing path reference")
    resolved = resolve_ref_path(str(ref["path"]))
    if not resolved.exists():
        raise SystemExit(f"{label} points to missing evidence: {resolved}")
    if resolved.resolve() != expected_path.resolve():
        raise SystemExit(f"{label} path mismatch: {resolved} != {expected_path}")
    ref_sha = ref.get("sha256")
    if require_sha and (not isinstance(ref_sha, str) or not ref_sha):
        raise SystemExit(f"{label} missing sha256")
    if ref_sha and ref_sha != sha256(expected_path):
        raise SystemExit(f"{label} sha256 mismatch: {ref_sha} != {sha256(expected_path)}")
    payload = load_json(expected_path)
    if ref.get("status") and payload.get("status") and ref["status"] != payload["status"]:
        raise SystemExit(f"{label} status mismatch: {ref['status']} != {payload['status']}")


def resolve_ref_path(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else REPO_ROOT / candidate


def validate_semantic_pass(evidence_dir: Path, prefix: str, slice_spec_path: Path) -> dict[str, Any]:
    slice_spec = load_json(slice_spec_path)
    manifest_path = evidence_dir / f"{prefix}-evidence-manifest.json"
    manifest = load_json(manifest_path)
    if manifest.get("status") != "passed":
        raise SystemExit(f"semantic pass requires manifest.status=passed: {manifest_path}")

    evidence = manifest.get("evidence", {})
    reports = {
        "c2rust_baseline": load_ref(evidence, "c2rust_baseline"),
        "route_decision": load_ref(evidence, "route_decision"),
        "validation_profile": load_ref(evidence, "validation_profile"),
        "c_oracle": load_ref(evidence, "c_oracle"),
        "rust_report": load_ref(evidence, "rust_report"),
        "schema_diff": load_ref(evidence, "schema_diff"),
        "negative_diff": load_ref(evidence, "negative_diff"),
        "unsafe_scan": load_ref(evidence, "unsafe_scan"),
        "unsafe_ledger": load_ref(evidence, "unsafe_ledger"),
        "final_verification": load_ref(evidence, "final_verification"),
        "version_or_config_binding": load_ref(evidence, "version_or_config_binding"),
    }

    if reports["c2rust_baseline"].get("correctness_role") != "candidate_context_only":
        raise SystemExit("semantic pass requires C2Rust baseline to remain candidate_context_only")
    if reports["route_decision"].get("level") == "L4" and not accepted_evidence_authoritative_semantic_pass(
        reports["route_decision"],
        reports["validation_profile"],
        manifest,
        reports["final_verification"],
        slice_spec,
    ):
        raise SystemExit("semantic pass cannot accept L4 refused route")
    require_status(reports["validation_profile"], "validation_profile", {"passed"})
    if reports["validation_profile"].get("skipped_gates"):
        raise SystemExit("semantic pass requires validation_profile.skipped_gates=[]")
    require_status(reports["c_oracle"], "c_oracle", {"C_ORACLE_GENERATED", "passed"})
    if reports["c_oracle"].get("toolchain_status") != "C_ORACLE_GENERATED":
        raise SystemExit("semantic pass requires c_oracle.toolchain_status=C_ORACLE_GENERATED")
    if is_promoted_accepted_oracle_wrapper(reports["c_oracle"]):
        validate_accepted_c_oracle_file_binding(evidence_dir, prefix, reports["c_oracle"])
    require_status(reports["rust_report"], "rust_report", {"passed"})
    require_status(reports["schema_diff"], "schema_diff", {"passed"})
    schema_compared_fields = validate_passed_schema_diff_report(reports["schema_diff"], slice_spec)
    validate_passed_negative_diff_report(reports["negative_diff"], schema_compared_fields)
    require_status(reports["unsafe_scan"], "unsafe_scan", {"passed"})
    require_status(reports["unsafe_ledger"], "unsafe_ledger", {"passed"})
    require_status(reports["final_verification"], "final_verification", {"passed"})
    if not reports["final_verification"].get("semantic_pass"):
        raise SystemExit("semantic pass requires final_verification.semantic_pass=true")
    require_status(reports["version_or_config_binding"], "version_or_config_binding", {"recorded", "passed"})

    expected_commit = source_commit(slice_spec)
    for label, report in reports.items():
        report_commit = report.get("source_commit")
        if report_commit and report_commit != expected_commit:
            raise SystemExit(f"semantic pass source_commit mismatch in {label}: {report_commit} != {expected_commit}")

    fixture = reports["final_verification"].get("fixture", {})
    fixture_path = fixture.get("path") or fixture_path_from_spec(slice_spec)
    fixture_file = REPO_ROOT / fixture_path
    if fixture_file.exists() and fixture.get("sha256"):
        actual = sha256(fixture_file)
        if fixture["sha256"] != actual:
            raise SystemExit(f"semantic pass fixture sha256 mismatch: {fixture['sha256']} != {actual}")

    validate_external_direct_callee_context(slice_spec, evidence_dir, prefix, manifest, reports["final_verification"])

    return {
        "status": "passed",
        "semantic_pass": True,
        "manifest": rel(manifest_path),
        "source_commit": expected_commit,
        "fixture_path": fixture_path,
        "fixture_sha256": fixture.get("sha256"),
        "checked": sorted(reports),
    }


def validate_accepted_c_oracle_file_binding(evidence_dir: Path, prefix: str, c_oracle: dict[str, Any]) -> None:
    accepted = c_oracle.get("accepted_oracle")
    if not isinstance(accepted, dict):
        raise SystemExit("semantic pass accepted c_oracle reference missing")

    accepted_path = accepted.get("path")
    if not isinstance(accepted_path, str) or not accepted_path:
        raise SystemExit("semantic pass accepted c_oracle accepted_oracle.path missing")
    accepted_sha = accepted.get("sha256")
    if not isinstance(accepted_sha, str) or not accepted_sha:
        raise SystemExit("semantic pass accepted c_oracle accepted_oracle.sha256 missing")
    if accepted.get("status") != "passed":
        raise SystemExit("semantic pass accepted c_oracle accepted_oracle.status must be passed")

    auto_manifest_path = evidence_dir / f"{prefix}-auto-translation-manifest.json"
    auto_manifest = load_json(auto_manifest_path)
    binding = auto_manifest.get("accepted_evidence_binding")
    if not isinstance(binding, dict):
        raise SystemExit("semantic pass accepted c_oracle accepted_evidence_binding missing")
    paths = binding.get("paths")
    if not isinstance(paths, dict):
        raise SystemExit("semantic pass accepted c_oracle accepted_evidence_binding.paths missing")
    path_sha256 = binding.get("path_sha256")
    if not isinstance(path_sha256, dict):
        raise SystemExit("semantic pass accepted c_oracle accepted_evidence_binding.path_sha256 missing")

    binding_path = paths.get("c_oracle")
    if not isinstance(binding_path, str) or not binding_path:
        raise SystemExit("semantic pass accepted c_oracle accepted_evidence_binding.paths.c_oracle missing")
    binding_sha = path_sha256.get("c_oracle")
    if not isinstance(binding_sha, str) or not binding_sha:
        raise SystemExit("semantic pass accepted c_oracle accepted_evidence_binding.path_sha256.c_oracle missing")

    accepted_resolved = resolve_ref_path(accepted_path)
    binding_resolved = resolve_ref_path(binding_path)
    if not accepted_resolved.exists():
        raise SystemExit(f"semantic pass accepted c_oracle points to missing evidence: {accepted_resolved}")
    if not binding_resolved.exists():
        raise SystemExit(f"semantic pass accepted c_oracle binding points to missing evidence: {binding_resolved}")
    if accepted_resolved.resolve() != binding_resolved.resolve():
        raise SystemExit(
            f"semantic pass accepted c_oracle path mismatch: {accepted_resolved} != {binding_resolved}"
        )

    actual_sha = sha256(accepted_resolved)
    if accepted_sha != actual_sha:
        raise SystemExit(f"semantic pass accepted c_oracle accepted_oracle.sha256 mismatch: {accepted_sha} != {actual_sha}")
    if binding_sha != actual_sha:
        raise SystemExit(
            "semantic pass accepted c_oracle accepted_evidence_binding.path_sha256.c_oracle mismatch: "
            f"{binding_sha} != {actual_sha}"
        )


def validate_external_direct_callee_context(
    slice_spec: dict[str, Any],
    evidence_dir: Path,
    prefix: str,
    manifest: dict[str, Any],
    final_verification: dict[str, Any],
) -> None:
    declared = slice_spec.get("c_boundary", {}).get("external_direct_callees", [])
    if not declared:
        return

    declared_by_name = {str(item.get("name")): item for item in declared if item.get("name")}
    signatures = {
        str(item.get("id") or item.get("function")): item
        for item in slice_spec.get("c_boundary", {}).get("signatures", [])
        if item.get("id") or item.get("function")
    }
    plan_path = evidence_dir / f"{prefix}-auto-translation-plan.json"
    context_path = evidence_dir / f"{prefix}-context-pack.json"
    plan = load_json(plan_path)
    context = load_json(context_path)
    plan_callees = {
        str(item.get("name")): item
        for item in plan.get("translation_summary", {}).get("external_direct_callees", [])
        if item.get("name")
    }
    context_callees = {
        str(item.get("name")): item
        for item in context.get("external_direct_callees", [])
        if item.get("name")
    }
    plan_blocks = {
        str(item.get("name")): item
        for item in plan.get("translation_summary", {}).get("external_direct_callee_blocks", [])
        if item.get("name")
    }
    context_blocks = {
        str(item.get("name")): item
        for item in context.get("external_direct_callee_blocks", [])
        if item.get("name")
    }
    bindings: dict[str, list[dict[str, Any]]] = {}
    for item in context.get("signature_bindings", []):
        if item.get("callee"):
            bindings.setdefault(str(item.get("callee")), []).append(item)
    source_bindings: dict[str, list[dict[str, Any]]] = {}
    for item in context.get("callee_sources", []):
        if item.get("callee"):
            source_bindings.setdefault(str(item.get("callee")), []).append(item)
    call_bindings = [
        item
        for item in context.get("call_edge_to_callee_binding", [])
        if item.get("callee") in declared_by_name
    ]
    plan_call_edges = [
        item
        for item in plan.get("translation_summary", {}).get("call_expressions", [])
        if item.get("callee") in declared_by_name
    ]
    context_call_edges = [
        item
        for item in context.get("direct_call_edges", [])
        if item.get("callee") in declared_by_name
    ]
    contracts: dict[str, dict[str, Any]] = {}
    blocked_contracts: dict[str, dict[str, Any]] = {}
    active_names = {
        str(item.get("callee") or item.get("name"))
        for item in (
            plan_call_edges
            + context_call_edges
            + call_bindings
            + list(plan_callees.values())
            + list(context_callees.values())
            + list(plan_blocks.values())
            + list(context_blocks.values())
        )
        if item.get("callee") or item.get("name")
    }

    for name, declared_callee in declared_by_name.items():
        if name not in active_names:
            continue
        signature_ref = str(declared_callee.get("signature_ref") or "")
        if signature_ref not in signatures:
            raise SystemExit(f"external callee {name} signature_ref missing from slice spec signatures")
        if not declared_callee.get("source_files"):
            raise SystemExit(f"external callee {name} requires real source_files in slice spec")
        signature = signatures[signature_ref]
        contract = external_callee_expected_contract(name, declared_callee, signature)
        if name in plan_blocks or name in context_blocks:
            validate_external_callee_block_binding(
                name,
                plan_blocks.get(name),
                context_blocks.get(name),
            )
            blocked_contracts[name] = {
                **contract,
                "blocked_reason": str((plan_blocks.get(name) or context_blocks.get(name) or {}).get("reason") or ""),
            }
            if any(item.get("callee") == name for item in call_bindings):
                raise SystemExit(f"external callee {name} blocked call-site cannot have compile_only binding")
            continue
        plan_callee = plan_callees.get(name)
        if plan_callee is None:
            raise SystemExit(f"external callee {name} missing from translation plan")
        context_callee = context_callees.get(name)
        if context_callee is None:
            raise SystemExit(f"external callee {name} missing from context pack")
        if plan_callee.get("signature_ref") != signature_ref:
            raise SystemExit(f"external callee {name} signature_ref mismatch in translation plan")
        if context_callee.get("signature_ref") != signature_ref:
            raise SystemExit(f"external callee {name} signature_ref mismatch in context pack")
        validate_external_callee_signature_descriptor(name, signature, plan_callee, "translation plan")
        validate_external_callee_signature_descriptor(name, signature, context_callee, "context pack")
        contracts[name] = contract
        validate_external_callee_descriptor_binding(name, contract, plan_callee, "translation plan")
        validate_external_callee_descriptor_binding(name, contract, context_callee, "context pack")
        if plan_callee.get("stub_kind") != "compile_only" or context_callee.get("stub_kind") != "compile_only":
            raise SystemExit(f"external callee {name} must record compile_only stub boundary")
        if plan_callee.get("semantics_verified") or context_callee.get("semantics_verified"):
            raise SystemExit(f"external callee {name} compile-only stub must not claim semantics_verified")
        if len(bindings.get(name, [])) != 1:
            raise SystemExit(f"external callee {name} missing signature binding in context pack")
        validate_external_callee_signature_binding(name, signature_ref, bindings[name][0])
        if not source_bindings.get(name):
            raise SystemExit(f"external callee {name} missing callee source binding in context pack")
        validate_external_callee_source_bindings(name, contract, source_bindings[name])

    recorded_plan_call_edges = [edge for edge in plan_call_edges if edge.get("callee") in contracts]
    recorded_context_call_edges = [edge for edge in context_call_edges if edge.get("callee") in contracts]
    if recorded_plan_call_edges and not call_bindings:
        raise SystemExit("external callee context requires call_edge_to_callee_binding entries")
    if recorded_plan_call_edges or recorded_context_call_edges or call_bindings:
        validate_external_callee_call_site_bindings(
            contracts,
            recorded_plan_call_edges,
            recorded_context_call_edges,
            call_bindings,
        )
    validate_external_callee_blocked_call_sites(blocked_contracts, plan_call_edges, context_call_edges)

    claim_scope = manifest.get("claim_boundary", {}).get("external_callee_scope", {})
    final_scope = final_verification.get("external_callee_scope", claim_scope)
    expected_scope_stub_kind = "compile_only" if contracts else "none"
    for label, scope in [("manifest", claim_scope), ("final_verification", final_scope)]:
        if scope.get("stub_kind") != expected_scope_stub_kind:
            raise SystemExit(f"external callee {label} scope must record stub_kind={expected_scope_stub_kind}")
        if scope.get("semantics_verified"):
            raise SystemExit(f"external callee {label} scope must keep semantics_verified=false")


def validate_external_direct_callee_context_for_default_checks(
    evidence_dir: Path,
    prefix: str,
    slice_spec_path: Path,
) -> None:
    slice_spec = load_json(slice_spec_path)
    if not slice_spec.get("c_boundary", {}).get("external_direct_callees"):
        return
    manifest = load_json(evidence_dir / f"{prefix}-evidence-manifest.json")
    final_verification = {}
    final_ref = manifest.get("evidence", {}).get("final_verification")
    if isinstance(final_ref, dict) and final_ref.get("path") and str(final_ref.get("status", "")) != "missing":
        final_verification = load_ref(manifest.get("evidence", {}), "final_verification")
    validate_external_direct_callee_context(slice_spec, evidence_dir, prefix, manifest, final_verification)


def validate_external_callee_signature_descriptor(
    name: str,
    signature: dict[str, Any],
    descriptor: dict[str, Any],
    label: str,
) -> None:
    signature_function = str(signature.get("function") or "")
    if signature_function and signature_function != name:
        raise SystemExit(
            f"external callee signature function mismatch for {name}: {signature_function}"
        )
    expected_shape = external_callee_signature_shape(signature)
    actual_shape = external_callee_signature_shape(descriptor)
    if actual_shape != expected_shape:
        raise SystemExit(
            f"external callee signature shape mismatch for {name} in {label}"
        )


def external_callee_expected_contract(
    name: str,
    declared_callee: dict[str, Any],
    signature: dict[str, Any],
) -> dict[str, Any]:
    return {
        "name": name,
        "signature_ref": str(declared_callee.get("signature_ref") or signature.get("id") or name),
        "source_ref": str(declared_callee.get("source_ref") or signature.get("source_ref") or ""),
        "definition_status": str(
            declared_callee.get("definition_status") or signature.get("definition_status") or ""
        ),
        "source_files": external_callee_source_file_counter(declared_callee.get("source_files") or []),
    }


def validate_external_callee_descriptor_binding(
    name: str,
    contract: dict[str, Any],
    descriptor: dict[str, Any],
    label: str,
) -> None:
    expected_source_ref = str(contract.get("source_ref") or "")
    if expected_source_ref and descriptor.get("source_ref") != expected_source_ref:
        raise SystemExit(f"external callee source binding mismatch for {name} in {label}")
    expected_definition_status = str(contract.get("definition_status") or "")
    if expected_definition_status and descriptor.get("definition_status") != expected_definition_status:
        raise SystemExit(f"external callee source binding mismatch for {name} in {label}")
    expected_sources = contract.get("source_files")
    actual_sources = external_callee_source_file_counter(descriptor.get("source_files") or [])
    if expected_sources != actual_sources:
        raise SystemExit(f"external callee source binding mismatch for {name} in {label}")


def validate_external_callee_source_bindings(
    name: str,
    contract: dict[str, Any],
    bindings: list[dict[str, Any]],
) -> None:
    expected_sources = contract.get("source_files")
    actual_sources = external_callee_source_file_counter(bindings)
    if expected_sources != actual_sources:
        raise SystemExit(f"external callee source binding mismatch for {name}")


def external_callee_source_file_counter(sources: list[dict[str, Any]]) -> Counter[tuple[str, str]]:
    return Counter(
        (
            str(source.get("path") or ""),
            str(source.get("sha256") or ""),
        )
        for source in sources
        if isinstance(source, dict)
    )


def validate_external_callee_signature_binding(
    name: str,
    signature_ref: str,
    binding: dict[str, Any],
) -> None:
    if binding.get("signature_ref") != signature_ref:
        raise SystemExit(f"external callee signature binding mismatch for {name}")
    if binding.get("stub_kind") != "compile_only":
        raise SystemExit(
            f"external callee signature binding for {name} must record stub_kind=compile_only"
        )
    if binding.get("semantics_verified"):
        raise SystemExit(
            f"external callee signature binding for {name} must keep semantics_verified=false"
        )


def validate_external_callee_block_binding(
    name: str,
    plan_block: dict[str, Any] | None,
    context_block: dict[str, Any] | None,
) -> None:
    if plan_block is None:
        raise SystemExit(f"external callee {name} missing blocked entry in translation plan")
    if context_block is None:
        raise SystemExit(f"external callee {name} missing blocked entry in context pack")
    if plan_block.get("reason") != context_block.get("reason"):
        raise SystemExit(f"external callee {name} blocked reason mismatch")
    if plan_block.get("stub_kind") != "none" or context_block.get("stub_kind") != "none":
        raise SystemExit(f"external callee {name} blocked entry must record stub_kind=none")
    if plan_block.get("semantics_verified") or context_block.get("semantics_verified"):
        raise SystemExit(f"external callee {name} blocked entry must keep semantics_verified=false")


def external_callee_signature_shape(payload: dict[str, Any]) -> tuple[str, tuple[tuple[str, str], ...]]:
    return_type = str(payload.get("return_type") or payload.get("returns") or "")
    parameters = tuple(
        (
            str(param.get("name") or f"arg{index + 1}"),
            str(param.get("c_type") or param.get("type") or ""),
        )
        for index, param in enumerate(payload.get("parameters") or [])
        if isinstance(param, dict)
    )
    return return_type, parameters


def validate_external_callee_call_site_bindings(
    contracts: dict[str, dict[str, Any]],
    plan_call_edges: list[dict[str, Any]],
    context_call_edges: list[dict[str, Any]],
    call_bindings: list[dict[str, Any]],
) -> None:
    expected = external_call_site_counter(plan_call_edges)
    context_edges = external_call_site_counter(context_call_edges)
    bindings = external_call_site_counter(call_bindings)
    if expected != context_edges:
        raise SystemExit(
            "external callee call-site binding mismatch between translation plan and context pack direct_call_edges"
        )
    if expected != bindings:
        raise SystemExit(
            "external callee call-site binding mismatch between direct calls and call_edge_to_callee_binding"
        )

    for label, edges in [
        ("translation plan", plan_call_edges),
        ("context pack direct_call_edges", context_call_edges),
        ("context pack call_edge_to_callee_binding", call_bindings),
    ]:
        for edge in edges:
            callee = str(edge.get("callee") or "")
            contract = contracts.get(callee)
            if contract is None:
                continue
            expected_signature = str(contract.get("signature_ref") or "")
            actual_signature = external_call_site_signature_ref(edge)
            if actual_signature != expected_signature:
                raise SystemExit(
                    f"external callee call-site binding signature mismatch for {callee} in {label}"
                )
            if label == "context pack call_edge_to_callee_binding":
                if edge.get("stub_kind") != "compile_only":
                    raise SystemExit(
                        f"external callee call-site binding for {callee} must record stub_kind=compile_only"
                    )
                if edge.get("semantics_verified"):
                    raise SystemExit(
                        f"external callee call-site binding for {callee} must keep semantics_verified=false"
                    )
            else:
                validate_external_callee_call_site_metadata(callee, contract, edge, label)


def validate_external_callee_blocked_call_sites(
    blocked_contracts: dict[str, dict[str, Any]],
    plan_call_edges: list[dict[str, Any]],
    context_call_edges: list[dict[str, Any]],
) -> None:
    if not blocked_contracts:
        return
    plan_blocked_edges = [edge for edge in plan_call_edges if edge.get("callee") in blocked_contracts]
    context_blocked_edges = [edge for edge in context_call_edges if edge.get("callee") in blocked_contracts]
    if external_call_site_counter(plan_blocked_edges) != external_call_site_counter(context_blocked_edges):
        raise SystemExit(
            "external callee blocked call-site mismatch between translation plan and context pack direct_call_edges"
        )
    for label, edges in [
        ("translation plan", plan_blocked_edges),
        ("context pack direct_call_edges", context_blocked_edges),
    ]:
        for edge in edges:
            callee = str(edge.get("callee") or "")
            contract = blocked_contracts.get(callee)
            if contract is None:
                continue
            if edge.get("callee_scope") != "external_direct_callee":
                raise SystemExit(f"external callee blocked call-site metadata mismatch for {callee} in {label}")
            if edge.get("stub_status") != "blocked":
                raise SystemExit(f"external callee blocked call-site metadata mismatch for {callee} in {label}")
            expected_reason = str(contract.get("blocked_reason") or "")
            if expected_reason and edge.get("blocked_reason") != expected_reason:
                raise SystemExit(f"external callee blocked call-site metadata mismatch for {callee} in {label}")


def validate_external_callee_call_site_metadata(
    callee: str,
    contract: dict[str, Any],
    edge: dict[str, Any],
    label: str,
) -> None:
    if edge.get("callee_scope") != "external_direct_callee":
        raise SystemExit(f"external callee call-site metadata mismatch for {callee} in {label}")
    if edge.get("stub_status") != "compile_only":
        raise SystemExit(f"external callee call-site metadata mismatch for {callee} in {label}")
    expected_source_ref = str(contract.get("source_ref") or "")
    if expected_source_ref and edge.get("callee_source_ref") != expected_source_ref:
        raise SystemExit(f"external callee call-site metadata mismatch for {callee} in {label}")
    expected_definition_status = str(contract.get("definition_status") or "")
    if expected_definition_status and edge.get("definition_status") != expected_definition_status:
        raise SystemExit(f"external callee call-site metadata mismatch for {callee} in {label}")


def external_call_site_counter(edges: list[dict[str, Any]]) -> Counter[tuple[str, str, str, str]]:
    return Counter(external_call_site_key(edge) for edge in edges)


def external_call_site_key(edge: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(edge.get("callee") or ""),
        str(edge.get("source_expression") or ""),
        str(edge.get("statement_context") or ""),
        external_call_site_signature_ref(edge),
    )


def external_call_site_signature_ref(edge: dict[str, Any]) -> str:
    return str(edge.get("signature_ref") or edge.get("callee_signature_id") or "")


def load_ref(evidence: dict[str, Any], key: str) -> dict[str, Any]:
    ref = evidence.get(key, {})
    path = ref.get("path")
    if not path:
        raise SystemExit(f"semantic pass requires manifest evidence.{key}.path")
    status = ref.get("status")
    if not isinstance(status, str) or not status:
        raise SystemExit(f"semantic pass requires manifest evidence.{key}.status")
    ref_sha = ref.get("sha256")
    if not isinstance(ref_sha, str) or not ref_sha:
        raise SystemExit(f"semantic pass requires manifest evidence.{key}.sha256")
    resolved = resolve_ref_path(str(path))
    if not resolved.exists():
        raise SystemExit(f"semantic pass requires existing evidence.{key}: {resolved}")
    actual_sha = sha256(resolved)
    if ref_sha != actual_sha:
        raise SystemExit(f"semantic pass manifest evidence.{key}.sha256 mismatch: {ref_sha} != {actual_sha}")
    payload = load_json(resolved)
    payload_status = payload.get("status")
    if not isinstance(payload_status, str) or not payload_status:
        raise SystemExit(f"semantic pass manifest evidence.{key} payload status missing")
    if status != payload_status:
        raise SystemExit(f"semantic pass manifest evidence.{key}.status mismatch: {status} != {payload_status}")
    return payload


def require_status(report: dict[str, Any], label: str, allowed: set[str]) -> None:
    status = str(report.get("status", ""))
    if status not in allowed:
        raise SystemExit(f"semantic pass requires {label}.status in {sorted(allowed)}, got {status!r}")


def mutation_detected(report: dict[str, Any]) -> bool:
    return bool(report.get("mutation_detected") or report.get("detected"))


def source_commit(slice_spec: dict[str, Any]) -> str:
    return slice_spec.get("source_commit") or slice_spec.get("source", {}).get("source_commit") or "UNKNOWN0"


def fixture_path_from_spec(slice_spec: dict[str, Any]) -> str:
    fixture = slice_spec.get("fixture_contract", {})
    return fixture.get("path") or fixture.get("input") or "unknown-fixture"


def behavior_fields_from_spec(slice_spec: dict[str, Any]) -> list[str]:
    fixture = slice_spec.get("fixture_contract", {})
    fields = fixture.get("observable_outputs") or fixture.get("behavior_fields") or []
    return [str(item) for item in fields]


def c_function_prototype(slice_spec: dict[str, Any]) -> str:
    function_name = slice_spec.get("function_name") or ""
    signatures = slice_spec.get("c_boundary", {}).get("signatures", [])
    signature = next(
        (item for item in signatures if isinstance(item, dict) and item.get("function") == function_name),
        {},
    )
    return_type = signature.get("return_type") or "int"
    parameters = signature.get("parameters") or []
    if not parameters:
        parameter_text = "void"
    else:
        parameter_text = ", ".join(c_parameter_declaration(item) for item in parameters if isinstance(item, dict))
    return f"{return_type} {function_name}({parameter_text});"


def c_parameter_declaration(parameter: dict[str, Any]) -> str:
    name = str(parameter.get("name") or "arg")
    c_type = str(parameter.get("c_type") or "int").strip()
    if c_type.endswith("*"):
        return f"{c_type[:-1].rstrip()} *{name}"
    return f"{c_type} {name}"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def artifact_cache_identity(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": artifact.get("status", "unknown"),
        "sha256": sha256_json(artifact),
    }


def resolve_slice_spec(target_id: str, slice_id: str) -> Path:
    spec_dir = REPO_ROOT / "validation" / "slice-specs"
    candidates = [
        spec_dir / f"{target_id}-{slice_id}.json",
        spec_dir / f"{target_id.split('-')[0]}-{slice_id}.json",
    ]
    candidates.extend(spec_dir.glob(f"*-{slice_id}.json"))
    candidates.extend(spec_dir.glob(f"*{slice_id}*.json"))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise SystemExit(
        f"no slice spec found for target_id={target_id!r}, slice_id={slice_id!r}; pass --slice-spec explicitly"
    )


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
