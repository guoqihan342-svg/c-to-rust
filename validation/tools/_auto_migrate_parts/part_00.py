#!/usr/bin/env python3
"""Run the bounded auto-translation pipeline for a slice spec.

This module emits candidate evidence and, separately, accepted semantic-pass
evidence. Generated Rust drafts, typed-IR candidates, and C2Rust baselines are
provenance inputs until the validation profile and accepted evidence gates bind
them to a final verification report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from validation.tools import validate_judge_entrypoints as judge_validator
TRANSLATOR_MANIFEST = REPO_ROOT / "crates" / "c2r-translator" / "Cargo.toml"
TRANSLATOR_LOCK = REPO_ROOT / "crates" / "c2r-translator" / "Cargo.lock"
COMPETITION_ENVIRONMENT_PROFILE = REPO_ROOT / "config" / "competition-env" / "environment.json"
POINTER_GRAPH_SCHEMA_VERSION = 2
CACHE_INPUT_FIELDS = [
    "source_commit",
    "source_file_hashes",
    "slice_spec_sha256",
    "fixture_hash",
    "build_profile_hash",
    "competition_environment_identity",
    "cargo_lock_hash",
    "tool_versions",
    "schema_versions",
    "translator_version",
    "translator_manifest_sha256",
    "command_arguments",
    "alias_gate_identity",
    "effect_graph_identity",
    "scalar_ub_contract_identity",
    "oracle_boundary_contract_identity",
    "c2rust_baseline_identity",
    "route_decision_identity",
    "validation_profile_identity",
    "global_dependency_identity",
    "c_oracle_harness_identity",
]
CLANG_LOWERING_CACHE_INPUT_FIELDS = [
    "translator_feature_set",
    "clang_lowering_identity",
]
CACHE_INVALIDATED_ARTIFACTS = [
    "context_pack",
    "type_map",
    "cfg",
    "pointer_graph",
    "c2rust_baseline",
    "route_decision",
    "validation_profile",
    "rust_draft",
    "patch_plan",
    "ai_candidate",
    "c_oracle",
    "rust_replay",
    "diff",
    "negative_diff",
    "unsafe_ledger",
    "final_verification",
    "auto_translation_manifest",
    "summary",
]
REPAIR_ROUND_LIMIT = 5


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slice-spec", required=True, type=Path)
    parser.add_argument("--out-root", default=REPO_ROOT / "validation" / "evidence", type=Path)
    parser.add_argument("--skip-c-oracle", action="store_true")
    parser.add_argument("--skip-rust-check", action="store_true")
    parser.add_argument(
        "--emit-clang-dry-run",
        action="store_true",
        help="Opt in to the translator clang-frontend dry-run artifact under a temporary or explicit out-root.",
    )
    parser.add_argument(
        "--emit-clang-lowering-report",
        action="store_true",
        help="Opt in to the translator clang lowering report artifact under a temporary or explicit out-root.",
    )
    parser.add_argument(
        "--competition-clang-lane",
        action="store_true",
        help="Require the competition clang typed-IR lane: enables clang lowering report and fails clearly when neither CLANG_PATH nor a project-local clang binary is available.",
    )
    parser.add_argument(
        "--accept-existing-evidence",
        action="store_true",
        help="Bind already accepted oracle/replay/diff/unsafe evidence from the slice spec instead of claiming the generated draft is accepted.",
    )
    args = parser.parse_args()
    if args.competition_clang_lane:
        args.emit_clang_lowering_report = True
        require_competition_clang_lane()

    spec = read_json(args.slice_spec)
    target_id = required_str(spec, "target_id")
    slice_id = required_str(spec, "slice_id")
    evidence_dir = args.out_root / target_id / "auto-translation" / slice_id
    evidence_dir.mkdir(parents=True, exist_ok=True)

    translator_spec = write_translator_spec(spec, args.slice_spec, evidence_dir)
    translator_summary = run_translator(
        translator_spec,
        evidence_dir,
        emit_clang_dry_run=args.emit_clang_dry_run,
        emit_clang_lowering_report=args.emit_clang_lowering_report,
    )
    normalize_translation_artifacts(spec, args.slice_spec, evidence_dir)
    if args.emit_clang_lowering_report:
        enrich_clang_lowering_report(
            evidence_dir,
            f"l3-{slice_id}",
            clang_lowering_identity(
                environment=os.environ,
                competition_clang_lane=args.competition_clang_lane,
            ),
        )
    c2rust_baseline = emit_c2rust_baseline_manifest(spec, args.slice_spec, evidence_dir)
    route_decision = emit_route_decision(spec, evidence_dir, translator_summary, c2rust_baseline)
    mark_route_refused_candidate_artifacts(spec, evidence_dir, route_decision)
    oracle = generate_oracle_harness_draft(spec, evidence_dir, args.skip_c_oracle)
    replay = generate_rust_replay_test_draft(spec, evidence_dir, args.slice_spec, route_decision)
    rust_check, patch = run_rust_check(evidence_dir, args.skip_rust_check, spec)
    accepted = resolve_accepted_evidence(spec) if args.accept_existing_evidence else None
    if accepted is not None:
        oracle = promote_accepted_oracle(spec, evidence_dir, oracle, accepted)
        replay = promote_accepted_test_translation(spec, evidence_dir, replay, accepted, route_decision)
        mark_accepted_evidence_authoritative_route(spec, evidence_dir, route_decision, accepted)
    else:
        replay = run_generated_rust_replay(spec, evidence_dir, replay, rust_check)
    validation_profile = emit_validation_profile(spec, evidence_dir, route_decision, oracle, rust_check, accepted)
    emit_scalar_refusal_evidence(spec, evidence_dir, route_decision, validation_profile)
    if route_decision.get("level") == "L4":
        patch = write_route_refused_patch(spec, evidence_dir, route_decision)
    emit_capability_delta_ledger(spec, evidence_dir, route_decision, validation_profile, rust_check, replay, oracle)
    cache = emit_cache_metadata(
        spec,
        args.slice_spec,
        evidence_dir,
        c2rust_baseline=c2rust_baseline,
        route_decision=route_decision,
        validation_profile=validation_profile,
        oracle=oracle,
        accept_existing_evidence=args.accept_existing_evidence,
        emit_clang_dry_run=args.emit_clang_dry_run,
        emit_clang_lowering_report=args.emit_clang_lowering_report,
        competition_clang_lane=args.competition_clang_lane,
    )
    manifest = emit_manifest(
        spec,
        evidence_dir,
        args.slice_spec,
        translator_summary,
        oracle,
        replay,
        rust_check,
        patch,
        cache,
        c2rust_baseline,
        route_decision,
        validation_profile,
        accepted,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


def write_translator_spec(spec: dict[str, Any], original_spec: Path, evidence_dir: Path) -> Path:
    build_profile = spec.get("build_profile", {})
    target = build_profile.get("target", {})
    clang = build_profile.get("clang_type_extraction", {})
    signatures = spec.get("c_boundary", {}).get("signatures", [])
    function_name = spec.get("function_name")
    c_source = spec.get("c_source")
    if not function_name and signatures:
        function_name = signatures[0].get("function")
    if not c_source and signatures:
        c_source = signatures[0].get("c_source")
    if not c_source:
        c_source = spec.get("c_boundary", {}).get("c_source")
    if not function_name or not c_source:
        raise SystemExit(f"{original_spec} must include function_name/c_source or c_boundary.signatures[].function/c_source")
    translator_spec = {
        "target_id": required_str(spec, "target_id"),
        "slice_id": required_str(spec, "slice_id"),
        "source_commit": source_commit(spec),
        "function_name": function_name,
        "c_source": c_source,
        "fixture_hash": fixture_hash(spec),
        "build_profile": {
            "include_paths": build_profile.get("include_paths", []),
            "defines": build_profile.get("defines", []),
            "target": target if target else None,
            "target_triple": spec.get("build_profile", {}).get("target_triple") or target.get("triple_or_abi"),
            "abi": spec.get("build_profile", {}).get("abi") or target.get("triple_or_abi"),
            "compiler_command_source": build_profile.get("compiler_command_source", "unknown"),
            "clang_available": bool(build_profile.get("clang_available", clang.get("available", False))),
            "clang_ast_fixture": build_profile.get("clang_ast_fixture"),
        },
    }
    if translator_spec["build_profile"]["clang_ast_fixture"] is None:
        del translator_spec["build_profile"]["clang_ast_fixture"]
    if translator_spec["build_profile"]["target"] is None:
        del translator_spec["build_profile"]["target"]
    source_root = spec.get("source", {}).get("source_root")
    if source_root:
        translator_spec["source_root"] = source_root
    source_files = c_boundary_source_files(spec)
    source_span = function_source_span(signatures, function_name)
    if source_files:
        translator_spec["source_files"] = source_files
        primary_source = primary_source_file(source_files, source_span)
        if primary_source.get("path"):
            translator_spec["source_file"] = primary_source["path"]
    resolved_source_file_hashes = source_file_hashes(spec)
    if resolved_source_file_hashes:
        translator_spec["source_file_hashes"] = resolved_source_file_hashes
    if source_span:
        translator_spec["function_source_span"] = source_span
    scalar_contract = spec.get("c_boundary", {}).get("scalar_arithmetic_contract", {})
    if scalar_contract:
        translator_spec["c_boundary"] = {
            "scalar_arithmetic_contract": scalar_contract,
        }
    compile_commands = build_profile.get("compile_commands") or build_profile.get("compile_commands_path")
    if compile_commands:
        translator_spec["compile_commands"] = compile_commands
    path = evidence_dir / f"l3-{spec['slice_id']}-translator-input.json"
    write_json(path, translator_spec)
    return path


def c_boundary_source_files(spec: dict[str, Any]) -> list[dict[str, Any]]:
    files = spec.get("c_boundary", {}).get("files", [])
    source_files: list[dict[str, Any]] = []
    for item in files:
        if not isinstance(item, dict) or not item.get("path"):
            continue
        source_file = {
            "path": item.get("path"),
            "role": item.get("role", "source"),
        }
        if item.get("sha256"):
            source_file["sha256"] = item["sha256"]
        source_files.append(source_file)
    return source_files


def primary_source_file(
    source_files: list[dict[str, Any]], source_span: dict[str, Any] | None
) -> dict[str, Any]:
    if source_span and source_span.get("file"):
        span_file = normalized_metadata_path(source_span["file"])
        for item in source_files:
            if normalized_metadata_path(item.get("path")) == span_file:
                return item
    return next((item for item in source_files if item.get("role") == "source"), source_files[0])


def normalized_metadata_path(value: Any) -> str:
    return str(value or "").strip().replace("\\", "/")


def function_source_span(signatures: list[dict[str, Any]], function_name: str) -> dict[str, Any] | None:
    for signature in signatures:
        if signature.get("function") != function_name:
            continue
        source_span = signature.get("source_span")
        if isinstance(source_span, dict):
            return source_span
    return None


def entry_function_name(spec: dict[str, Any]) -> str:
    function_name = spec.get("function_name")
    signatures = spec.get("c_boundary", {}).get("signatures", [])
    if not function_name and signatures:
        function_name = signatures[0].get("function")
    return str(function_name or "")


def rust_identifier(name: str) -> str:
    return f"r#{name}" if name in RUST_KEYWORDS else name


def primitive_rust_type(c_type: str) -> str | None:
    normalized = " ".join(str(c_type).strip().split())
    return {
        "int": "i32",
        "signed int": "i32",
        "unsigned int": "u32",
        "short": "i16",
        "short int": "i16",
        "unsigned short": "u16",
        "unsigned short int": "u16",
        "long": "i64",
        "long int": "i64",
        "unsigned long": "u64",
        "unsigned long int": "u64",
    }.get(normalized)


def compact_c_type(c_type: str) -> str:
    return "".join(str(c_type).strip().split())


def is_modeled_strlen_contract(
    name: str,
    return_type: str,
    parameters: list[dict[str, str]],
) -> bool:
    if name != "strlen":
        return False
    if compact_c_type(return_type) != "size_t":
        return False
    if len(parameters) != 1:
        return False
    return compact_c_type(parameters[0]["c_type"]) in {"constchar*", "charconst*"}


def is_flashdb_kv_external_context_callee(spec: dict[str, Any], name: str) -> bool:
    return (
        spec.get("target_id") == "flashdb"
        and spec.get("slice_id") == "real-fdb-kv-set"
        and name in {"fdb_kv_del", "fdb_kv_set_blob"}
    )


def is_const_char_pointer_type(c_type: str) -> bool:
    return compact_c_type(c_type) in {"constchar*", "charconst*"}


def is_flashdb_kv_external_context_signature(
    spec: dict[str, Any],
    item: dict[str, Any],
    signature: dict[str, Any],
    name: str,
    return_type: str,
    parameters: list[dict[str, str]],
) -> bool:
    if not is_flashdb_kv_external_context_callee(spec, name):
        return False
    definition_status = item.get("definition_status") or signature.get("definition_status")
    if definition_status != "real_source_bound":
        return False
    source_ref = str(item.get("source_ref") or signature.get("source_ref") or "")
    if source_ref != f"src/fdb_kvdb.c#{name}":
        return False
    if compact_c_type(return_type) != "fdb_err_t":
        return False
    if name == "fdb_kv_del":
        return (
            len(parameters) == 2
            and parameters[0]["name"] == "db"
            and compact_c_type(parameters[0]["c_type"]) == "fdb_kvdb_t"
            and parameters[1]["name"] == "key"
            and is_const_char_pointer_type(parameters[1]["c_type"])
        )
    return (
        len(parameters) == 3
        and parameters[0]["name"] == "db"
        and compact_c_type(parameters[0]["c_type"]) == "fdb_kvdb_t"
        and parameters[1]["name"] == "key"
        and is_const_char_pointer_type(parameters[1]["c_type"])
        and parameters[2]["name"] == "blob"
        and compact_c_type(parameters[2]["c_type"]) == "fdb_blob_t"
    )


def flashdb_kv_external_context_rust_type(
    spec: dict[str, Any],
    name: str,
    c_type: str,
) -> str | None:
    primitive = primitive_rust_type(c_type)
    if primitive is not None:
        return primitive
    if not is_flashdb_kv_external_context_callee(spec, name):
        return None
    return {
        "fdb_err_t": "i32",
        "fdb_kvdb_t": "*mut core::ffi::c_void",
        "constchar*": "*const core::ffi::c_char",
        "charconst*": "*const core::ffi::c_char",
        "fdb_blob_t": "*mut core::ffi::c_void",
    }.get(compact_c_type(c_type))


def accepted_named_slice_evidence_for_callee(spec: dict[str, Any], name: str) -> dict[str, Any] | None:
    if spec.get("target_id") != "flashdb" or name != "fdb_blob_make":
        return None
    final_verification = (
        REPO_ROOT
        / "validation"
        / "evidence"
        / "flashdb"
        / "auto-translation"
        / "real-fdb-blob-make"
        / "l3-real-fdb-blob-make-final-verification.json"
    )
    if not final_verification.exists():
        return None
    try:
        final = json.loads(final_verification.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if final.get("target_id") != "flashdb" or final.get("slice_id") != "real-fdb-blob-make":
        return None
    if final.get("semantic_pass") is not True:
        return None
    if final.get("accepted_evidence_authoritative") is not True:
        return None
    return {
        "kind": "accepted_named_slice_evidence",
        "target_id": "flashdb",
        "slice_id": "real-fdb-blob-make",
        "final_verification_path": rel(final_verification),
        "final_verification_sha256": sha256(final_verification),
        "semantic_pass": True,
        "accepted_evidence_authoritative": True,
        "generated_draft_semantic_pass": bool(final.get("generated_draft_semantic_pass") is True),
        "boundary": (
            "This validates the named fdb_blob_make slice through accepted evidence only; "
            "it does not validate the fdb_kv_set caller or its generated Rust draft."
        ),
    }


def declared_external_direct_callee_map(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    c_boundary = spec.get("c_boundary", {})
    signatures = c_boundary.get("signatures", [])
    signatures_by_name = {str(item.get("function")): item for item in signatures if item.get("function")}
    signatures_by_id = {str(item.get("id")): item for item in signatures if item.get("id")}
    declared: dict[str, dict[str, Any]] = {}

    for item in c_boundary.get("external_direct_callees", []):
        name = str(item.get("name") or "")
        if not name:
            continue
        signature = signatures_by_id.get(str(item.get("signature_ref") or "")) or signatures_by_name.get(name) or {}
        declared[name] = external_callee_descriptor(spec, item, signature)

    for signature in signatures:
        if signature.get("role") != "external_direct_callee":
            continue
        name = str(signature.get("function") or "")
        if not name or name in declared:
            continue
        declared[name] = external_callee_descriptor(
            spec,
            {
                "name": name,
                "signature_ref": signature.get("id") or name,
                "source_files": source_files_for_external_callee(spec, name),
                "definition_status": signature.get("definition_status", "real_source_bound"),
                "stub_boundary": "compile_only",
            },
            signature,
        )
    return declared


def external_callee_descriptor(
    spec: dict[str, Any],
    item: dict[str, Any],
    signature: dict[str, Any],
) -> dict[str, Any]:
    name = str(item.get("name") or signature.get("function") or "")
    signature_ref = str(item.get("signature_ref") or signature.get("id") or name)
    parameters = []
    for index, param in enumerate(signature.get("parameters", [])):
        c_type = str(param.get("c_type") or param.get("type") or "")
        parameters.append(
            {
                "name": str(param.get("name") or f"arg{index + 1}"),
                "c_type": c_type,
            }
        )
    return_type = str(signature.get("return_type") or signature.get("returns") or "")
    return_rust_type = None
    unsupported_reasons: list[str] = []
    if not signature:
        unsupported_reasons.append("missing_signature")
    if primitive_rust_type(return_type) is None:
        unsupported_reasons.append("unsupported_return_type")
    for param in parameters:
        if primitive_rust_type(param["c_type"]) is None:
            unsupported_reasons.append(f"unsupported_parameter_type:{param['name']}")
    if not parameters:
        unsupported_reasons.append("missing_parameters")
    modeled_strlen = is_modeled_strlen_contract(name, return_type, parameters)
    if modeled_strlen:
        unsupported_reasons = []
    accepted_named_slice = accepted_named_slice_evidence_for_callee(spec, name)
    if accepted_named_slice:
        unsupported_reasons = []
    flashdb_external_compile_context = is_flashdb_kv_external_context_signature(
        spec,
        item,
        signature,
        name,
        return_type,
        parameters,
    )
    if flashdb_external_compile_context:
        unsupported_reasons = []
        return_rust_type = flashdb_kv_external_context_rust_type(spec, name, return_type)
        for param in parameters:
            rust_type = flashdb_kv_external_context_rust_type(spec, name, param["c_type"])
            if rust_type is not None:
                param["rust_type"] = rust_type
    stub_kind = "compile_only"
    stub_boundary = item.get("stub_boundary", "compile_only")
    stub_generation = "generated_compile_only"
    model_contract = ""
    if modeled_strlen:
        stub_boundary = "stdlib_readonly_string_model"
        stub_generation = "not_emitted_modeled_stdlib"
        model_contract = "strlen_readonly_nul_terminated"
    if flashdb_external_compile_context:
        stub_boundary = "flashdb_external_direct_callee_context_only"
        stub_generation = "not_emitted_flashdb_signature_context"
        model_contract = "flashdb_external_direct_callee_signature_context"
    if accepted_named_slice:
        stub_kind = "accepted_named_slice_evidence"
        stub_boundary = "accepted_named_slice_context_only"
        stub_generation = "not_emitted_named_slice_evidence"
        model_contract = "fdb_blob_make_named_slice_accepted_evidence"
    descriptor = {
        "name": name,
        "signature_ref": signature_ref,
        "source_ref": item.get("source_ref") or signature.get("source_ref") or "",
        "source_files": item.get("source_files") or source_files_for_external_callee(spec, name),
        "header_files": item.get("header_files", []),
        "definition_status": item.get("definition_status") or signature.get("definition_status") or "real_source_bound",
        "stub_kind": stub_kind,
        "stub_boundary": stub_boundary,
        "stub_generation": stub_generation,
        "model_contract": model_contract,
        "semantics_verified": False,
        "parameters": parameters,
        "return_type": return_type,
        "supported": not unsupported_reasons,
        "unsupported_reasons": sorted(set(unsupported_reasons)),
    }
    if return_rust_type is not None:
        descriptor["return_rust_type"] = return_rust_type
    if accepted_named_slice:
        descriptor["accepted_named_slice_evidence"] = accepted_named_slice
    return descriptor


def source_files_for_external_callee(spec: dict[str, Any], name: str) -> list[dict[str, Any]]:
    files = []
    for item in spec.get("c_boundary", {}).get("files", []):
        role = str(item.get("role") or "")
        path = item.get("path")
        if path and (role == "external_direct_callee" or name in str(path)):
            files.append({"path": path, "sha256": item.get("sha256", "")})
    return files


def external_direct_callee_context(
    spec: dict[str, Any],
    call_expressions: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    entry_name = entry_function_name(spec)
    declared_map = declared_external_direct_callee_map(spec)
    callee_names = sorted(external_direct_callee_names(spec, call_expressions, entry_name))
    declared = []
    blocked = []
    for name in callee_names:
        descriptor = declared_map.get(name)
        if descriptor is None:
            blocked.append(
                {
                    "name": name,
                    "reason": "missing_declared_external_direct_callee",
                    "stub_kind": "none",
                    "semantics_verified": False,
                }
            )
            continue
        if not descriptor.get("supported"):
            blocked.append(external_callee_block_from_descriptor(name, descriptor))
            continue
        declared.append(descriptor)

    status = "not_applicable"
    if blocked:
        status = "blocked"
    elif declared:
        status = "recorded"
    return {
        "status": status,
        "declarations": [declared_map[name] for name in sorted(declared_map)],
        "declared": declared,
        "blocked": blocked,
        "declared_spec_count": len(declared_map),
        "declared_spec_names": sorted(declared_map),
        "declared_count": len(declared),
        "blocked_count": len(blocked),
    }


def external_callee_block_from_descriptor(name: str, descriptor: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "reason": "unsupported_external_direct_callee_signature",
        "signature_ref": descriptor.get("signature_ref", ""),
        "source_ref": descriptor.get("source_ref", ""),
        "definition_status": descriptor.get("definition_status", ""),
        "unsupported_reasons": descriptor.get("unsupported_reasons", []),
        "stub_kind": "none",
        "semantics_verified": False,
    }


def external_direct_callee_names(
    spec: dict[str, Any],
    call_expressions: list[dict[str, Any]] | None,
    entry_name: str,
) -> set[str]:
    names = {
        str(call.get("callee"))
        for call in (call_expressions or [])
        if call.get("callee") and str(call.get("callee")) != entry_name
    }
    for dependency in spec.get("c_boundary", {}).get("direct_dependencies", []):
        if dependency.get("kind") != "callee":
            continue
        name = str(dependency.get("name") or "")
        if name and name != entry_name:
            names.add(name)
    return names


def external_context_input_ref(evidence_dir: Path, slice_id: str, context: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": rel(evidence_dir / f"l3-{slice_id}-context-pack.json"),
        "status": context["status"],
        "declared_count": context["declared_count"],
        "declared_spec_count": context["declared_spec_count"],
        "declared_spec_names": context["declared_spec_names"],
        "blocked_count": context["blocked_count"],
    }


def bind_external_callee_context(
    call_expressions: list[dict[str, Any]],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    declared = {item["name"]: item for item in context.get("declared", [])}
    blocked = {item["name"]: item for item in context.get("blocked", [])}
    bound = []
    for call in call_expressions:
        enriched = dict(call)
        callee = str(call.get("callee") or "")
        if callee in declared:
            descriptor = declared[callee]
            enriched.update(
                {
                    "callee_scope": "external_direct_callee",
                    "callee_signature_id": descriptor["signature_ref"],
                    "callee_source_ref": descriptor.get("source_ref", ""),
                    "definition_status": descriptor.get("definition_status", ""),
                    "stub_status": "compile_only",
                }
            )
        elif callee in blocked:
            enriched.update(
                {
                    "callee_scope": "external_direct_callee",
                    "stub_status": "blocked",
                    "blocked_reason": blocked[callee].get("reason", ""),
                }
            )
        bound.append(enriched)
    return bound


def call_edge_to_callee_binding(
    call_expressions: list[dict[str, Any]],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    bindings = []
    declared = {item["name"]: item for item in context.get("declared", [])}
    for call in call_expressions:
        callee = str(call.get("callee") or "")
        if callee not in declared:
            continue
        descriptor = declared[callee]
        stub_kind = str(descriptor.get("stub_kind") or "compile_only")
        if stub_kind not in {"compile_only", "accepted_named_slice_evidence"}:
            continue
        bindings.append(
            {
                "callee": callee,
                "signature_ref": descriptor["signature_ref"],
                "source_expression": call.get("source_expression", ""),
                "statement_context": call.get("statement_context", ""),
                "stub_kind": stub_kind,
                "semantics_verified": False,
            }
        )
    return bindings


def external_callee_sources(context: dict[str, Any]) -> list[dict[str, Any]]:
    sources = []
    for callee in context.get("declared", []):
        for source in callee.get("source_files", []):
            sources.append(
                {
                    "callee": callee["name"],
                    "path": source.get("path", ""),
                    "sha256": source.get("sha256", ""),
                }
            )
    return sources


def external_signature_bindings(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "callee": callee["name"],
            "signature_ref": callee["signature_ref"],
            "definition_status": callee.get("definition_status", ""),
            "stub_kind": callee["stub_kind"],
            "semantics_verified": False,
        }
        for callee in context.get("declared", [])
    ]


def external_stub_boundaries(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "callee": callee["name"],
            "stub_kind": callee["stub_kind"],
            "allowed_use": (
                "named_slice_evidence_reference_only"
                if callee.get("stub_kind") == "accepted_named_slice_evidence"
                else "standalone_rust_check_only"
            ),
            "semantics_verified": False,
        }
        for callee in context.get("declared", [])
    ]


def external_scope_stub_kind(context: dict[str, Any]) -> str:
    kinds = {
        str(callee.get("stub_kind") or "compile_only")
        for callee in context.get("declared", [])
    }
    if not kinds:
        return "none"
    if len(kinds) == 1:
        return next(iter(kinds))
    return "mixed_context"


def external_callee_claim_scope(context: dict[str, Any]) -> dict[str, Any]:
    if context["status"] == "recorded":
        status = "compile_context_only"
    else:
        status = context["status"]
    return {
        "status": status,
        "declared_spec_count": context["declared_spec_count"],
        "declared_spec_names": context["declared_spec_names"],
        "declared_count": context["declared_count"],
        "blocked_count": context["blocked_count"],
        "stub_kind": external_scope_stub_kind(context),
        "semantics_verified": False,
    }


def rust_check_external_context(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": context["status"],
        "declared_spec_count": context["declared_spec_count"],
        "declared_spec_names": context["declared_spec_names"],
        "declared_count": context["declared_count"],
        "blocked_count": context["blocked_count"],
        "declared_callees": [
            {
                "name": callee["name"],
                "signature_ref": callee["signature_ref"],
                "stub_kind": callee["stub_kind"],
                "binding_status": rust_check_binding_status(callee),
                "semantics_verified": False,
            }
            for callee in context.get("declared", [])
        ],
        "blocked_callees": context.get("blocked", []),
    }


def load_plan_call_expressions(evidence_dir: Path, slice_id: str) -> list[dict[str, Any]]:
    plan_path = evidence_dir / f"l3-{slice_id}-auto-translation-plan.json"
    if not plan_path.exists():
        return []
    plan = read_json(plan_path)
    return plan.get("translation_summary", {}).get("call_expressions", [])


def rust_check_binding_status(callee: dict[str, Any]) -> str:
    binding = callee.get("rust_check_binding")
    if isinstance(binding, dict) and binding.get("status"):
        return str(binding["status"])
    if callee.get("stub_generation") == "generated_compile_only":
        return "generated_compile_only"
    if str(callee.get("stub_generation") or "").startswith("not_emitted_"):
        return "not_emitted"
    return "unknown"


def mark_rust_check_binding(callee: dict[str, Any], status: str, signature: str) -> None:
    callee["rust_check_binding"] = {
        "status": status,
        "allowed_use": "rustc_compile_only",
        "signature": signature,
        "semantics_verified": False,
    }


def rust_check_harness_only_external_stub(callee: dict[str, Any], text: str) -> str | None:
    name = rust_identifier(callee["name"])
    if "FdbBlob" not in text:
        return None
    signatures = {
        "fdb_blob_make": (
            "pub fn fdb_blob_make("
            "blob: &mut FdbBlob, "
            "value_buf: *const core::ffi::c_void, "
            "buf_len: usize"
            ") -> &mut FdbBlob"
        ),
        "fdb_kv_set_blob": (
            "pub fn fdb_kv_set_blob("
            "db: *mut core::ffi::c_void, "
            "key: *const core::ffi::c_void, "
            "blob: &mut FdbBlob"
            ") -> i32"
        ),
        "fdb_kv_del": (
            "pub fn fdb_kv_del("
            "db: *mut core::ffi::c_void, "
            "key: *const core::ffi::c_void"
            ") -> i32"
        ),
    }
    signature = signatures.get(name)
    if signature is None:
        return None
    if f"fn {name}(" in text:
        mark_rust_check_binding(callee, "already_present", signature)
        return None
    body_lines = {
        "fdb_blob_make": [
            "    let _ = (value_buf, buf_len);",
            '    unimplemented!("rust-check harness-only external callee binding: fdb_blob_make")',
        ],
        "fdb_kv_set_blob": [
            "    let _ = (db, key, blob);",
            '    unimplemented!("rust-check harness-only external callee binding: fdb_kv_set_blob")',
        ],
        "fdb_kv_del": [
            "    let _ = (db, key);",
            '    unimplemented!("rust-check harness-only external callee binding: fdb_kv_del")',
        ],
    }[name]
    mark_rust_check_binding(callee, "harness_only", signature)
    return signature + " {\n" + "\n".join(body_lines) + "\n}"


def rust_check_external_binding_report(context: dict[str, Any]) -> dict[str, Any]:
    bindings = [
        {
            "name": callee["name"],
            "status": callee["rust_check_binding"]["status"],
            "allowed_use": callee["rust_check_binding"]["allowed_use"],
            "signature": callee["rust_check_binding"]["signature"],
            "semantics_verified": False,
        }
        for callee in context.get("declared", [])
        if isinstance(callee.get("rust_check_binding"), dict)
    ]
    return {
        "status": "emitted" if any(item["status"] == "harness_only" for item in bindings) else "none",
        "allowed_use": "rustc_compile_only",
        "semantics_verified": False,
        "bindings": bindings,
    }


def inject_external_callee_stubs(draft_path: Path, context: dict[str, Any]) -> bool:
    callees = context.get("declared", [])
    if not callees:
        return False
    text = draft_path.read_text(encoding="utf-8")
    stubs = []
    for callee in callees:
        if callee.get("stub_generation") == "not_emitted_modeled_stdlib":
            continue
        if callee.get("stub_generation") in {
            "not_emitted_named_slice_evidence",
            "not_emitted_flashdb_signature_context",
        }:
            stub = rust_check_harness_only_external_stub(callee, text)
            if stub is not None:
                stubs.append(stub)
            continue
        name = rust_identifier(callee["name"])
        params = []
        for index, param in enumerate(callee.get("parameters", [])):
            param_name = rust_identifier(param.get("name") or f"arg{index + 1}")
            rust_type = (
                param.get("rust_type")
                or primitive_rust_type(param.get("c_type", ""))
                or "i32"
            )
            params.append(f"{param_name}: {rust_type}")
        return_type = (
            callee.get("return_rust_type")
            or primitive_rust_type(callee.get("return_type", ""))
            or "i32"
        )
        signature = f"fn {name}({', '.join(params)}) -> {return_type}"
        if signature in text:
            continue
        mark_rust_check_binding(callee, "generated_compile_only", signature)
        stubs.append(
            f'{signature} {{ unimplemented!("external callee context stub: {callee["name"]}") }}'
        )
    if not stubs:
        return False
    draft_path.write_text("\n".join(stubs) + "\n\n" + text, encoding="utf-8")
    return True


def translator_feature_set(
    *, emit_clang_dry_run: bool = False, emit_clang_lowering_report: bool = False
) -> list[str]:
    features: list[str] = []
    if emit_clang_dry_run:
        features.append("clang-frontend")
    if emit_clang_lowering_report:
        features.append("clang-lowering-report")
    return features


def run_translator(
    slice_spec: Path,
    evidence_dir: Path,
    *,
    emit_clang_dry_run: bool = False,
    emit_clang_lowering_report: bool = False,
) -> dict[str, Any]:
    cmd = [
        "cargo",
        "run",
        "--quiet",
        "--manifest-path",
        str(TRANSLATOR_MANIFEST),
    ]
    features = translator_feature_set(
        emit_clang_dry_run=emit_clang_dry_run,
        emit_clang_lowering_report=emit_clang_lowering_report,
    )
    if features:
        cmd.extend(["--features", ",".join(features)])
    cmd.extend(
        [
            "--bin",
            "c2r_translate",
            "--",
            "--slice-spec",
            str(slice_spec),
            "--out-dir",
            str(evidence_dir),
        ]
    )
    result = subprocess.run(cmd, cwd=REPO_ROOT, text=True, capture_output=True)
    write_log_text(evidence_dir / "translator-command.stdout.log", result.stdout)
    write_log_text(evidence_dir / "translator-command.stderr.log", result.stderr)
    if result.returncode != 0:
        raise SystemExit(f"translator failed with exit code {result.returncode}; see {evidence_dir}")
    return json.loads(result.stdout)


def enrich_clang_lowering_report(
    evidence_dir: Path,
    prefix: str,
    clang_identity: dict[str, Any],
) -> None:
    report_path = evidence_dir / f"{prefix}-clang-lowering-report.json"
    if not report_path.exists():
        return
    report = read_json(report_path)
    typed_ir_candidate = report.get("typed_ir_candidate")
    if not isinstance(typed_ir_candidate, dict):
        return
    lowering_report = report.get("lowering_report")
    function_ir = lowering_report.get("function_ir") if isinstance(lowering_report, dict) else None
    if function_ir is None:
        return

    rust_draft_path = evidence_dir / f"{prefix}-rust-draft.rs"
    typed_ir_sha256 = sha256_json(function_ir)
    rust_draft_sha256 = sha256(rust_draft_path) if rust_draft_path.exists() else "missing"
    typed_ir_candidate["typed_ir_sha256"] = typed_ir_sha256
    typed_ir_candidate["rust_draft_sha256"] = rust_draft_sha256
    report["durable_evidence"] = {
        "hash_algorithm": "sha256",
        "typed_ir_sha256": typed_ir_sha256,
        "rust_draft_sha256": rust_draft_sha256,
        "clang_path": str(clang_identity.get("clang_path", "")),
        "clang_version": str(clang_identity.get("clang_version", "")),
        "frontend": str(clang_identity.get("frontend", "clang_ast_dump_json")),
        "competition_environment": competition_environment_identity(),
    }
    write_json(report_path, report)


def unsupported_control_flow_kind(label: str) -> str:
    prefix = str(label).split(":", 1)[0]
    if prefix in {
        "goto",
        "switch",
        "label",
        "case",
        "default",
        "setjmp",
        "longjmp",
        "inline_assembly",
        "relooper_refusal",
    }:
        return prefix
    return "unknown"


def structured_control_flow_recovery_evidence(
    unsupported_labels: list[str], unsupported_items: list[dict[str, Any]]
) -> dict[str, Any]:
    kinds = {item.get("kind") for item in unsupported_items}
    labels = [str(label) for label in unsupported_labels]
    label_targets = {label.split(":", 1)[1] for label in labels if label.startswith("label:")}
    goto_targets = {label.split(":", 1)[1] for label in labels if label.startswith("goto:")}
    preconditions: list[str] = []
    if "goto" in kinds and goto_targets and goto_targets.issubset(label_targets):
        preconditions.append("goto_target_resolved")
    if "switch" in kinds and ({"case", "default"} & kinds):
        preconditions.append("switch_cases_enumerated")

    refusals: list[str] = []
    if "goto" in kinds:
        refusals.append("goto_requires_structured_recovery")
    if "switch" in kinds:
        refusals.append("switch_requires_structured_recovery")

    return {
        "recovery_status": "refused" if unsupported_items else "structured",
        "relooper_preconditions": preconditions,
        "relooper_refusals": refusals,
        "scope_note": (
            "minimal structured-recovery evidence only; no Rust candidate lowering "
            "or C/Rust semantic pass is claimed"
        )
        if unsupported_items
        else "structured control flow does not require relooper recovery",
    }


def normalize_translation_artifacts(spec: dict[str, Any], slice_spec_path: Path, evidence_dir: Path) -> None:
    """Rewrite raw translator output into schema-bound candidate evidence.

    Normalization records what the translator observed and generated, but it is
    still before route selection, validation-profile gating, and any accepted
    evidence binding. Artifacts written here must therefore remain provenance
    for candidates, not semantic-pass proof.
    """
    target_id = required_str(spec, "target_id")
    slice_id = required_str(spec, "slice_id")
    source = source_commit(spec)
    repo = repo_commit()
    prefix = f"l3-{slice_id}"
    slice_ref = {"path": rel(slice_spec_path), "status": "ready", "sha256": sha256(slice_spec_path)}
    build_profile_ref = {
        "path": rel(evidence_dir / f"{prefix}-translator-input.json"),
        "status": "recorded",
        "sha256": sha256(evidence_dir / f"{prefix}-translator-input.json"),
    }

    raw_type = read_json(evidence_dir / f"{prefix}-type-map.json")
    mappings = [
        {
            "id": f"type-{idx + 1}",
            "kind": type_mapping_kind(item.get("c_type", "")),
            "c_name": item.get("symbol", ""),
            "c_type": item.get("c_type", ""),
            "rust_type": item.get("rust_type", ""),
            "confidence": "proven",
            "source": "translator_rule",
            "translation_rule_id": item.get("reason", "supported MVP C subset mapping"),
        }
        for idx, item in enumerate(raw_type.get("type_map", {}).get("mappings", []))
    ]
    uncertainties = [
        {
            "id": f"uncertainty-{idx + 1}",
            "kind": "declaration_resolution",
            "reason": item.get("reason", ""),
            "affected_mapping_ids": [],
            "resolution": "block_translation",
        }
        for idx, item in enumerate(raw_type.get("type_map", {}).get("uncertainties", []))
    ]
    write_json(
        evidence_dir / f"{prefix}-type-map.json",
        {
            "schema_version": 1,
            "target_id": target_id,
            "slice_id": slice_id,
            "level": "L3",
            "status": "recorded" if not uncertainties else "blocked",
            "source_commit": source,
            "repo_commit": repo,
            "slice_spec_ref": slice_ref,
            "build_profile_ref": build_profile_ref,
            "mappings": mappings,
            "uncertainties": uncertainties,
            "unsupported_nodes": [],
            "global_dependencies": global_dependency_requirements(spec),
            "cache_invalidation_keys": cache_keys(spec, slice_spec_path),
        },
    )

    raw_cfg = read_json(evidence_dir / f"{prefix}-cfg.json")
    raw_functions = raw_cfg.get("cfg", {}).get("functions", [])
    unsupported_cf = []
    functions = []
    for function in raw_functions:
        unsupported = function.get("unsupported_control_flow", [])
        function_unsupported_cf = [
            {
                "id": f"unsupported-{idx + 1}",
                "kind": unsupported_control_flow_kind(item),
                "reason": f"{item} requires CFG/relooper support",
                "source_span": source_span(),
                "translation_effect": "requires_relooper",
            }
            for idx, item in enumerate(unsupported)
        ]
        unsupported_cf.extend(function_unsupported_cf)
        blocks = function.get("blocks", [])
        statements = blocks[0].get("statements", []) if blocks else []
        functions.append(
            {
                "name": function.get("name", required_str(spec, "slice_id")),
                "signature": function_signature(spec),
                "source_span": source_span(),
                "entry_block": "entry",
                "exit_blocks": ["return"] if blocks and blocks[0].get("terminator") == "return" else ["exit"],
                "basic_blocks": cfg_basic_blocks(blocks),
                "edges": cfg_edges(blocks),
                "branches": [],
                "returns": [
                    {"block": "entry", "expression": extract_return_expression(statements), "source_span": source_span()}
                ],
                "structured_control_flow": {
                    "if_count": count_token(spec.get("c_source", ""), "if"),
                    "loop_count": count_token(spec.get("c_source", ""), "while") + count_token(spec.get("c_source", ""), "for"),
                    "has_goto": any(item.get("kind") == "goto" for item in function_unsupported_cf),
                    "has_switch": any(item.get("kind") == "switch" for item in function_unsupported_cf),
                    "relooper_required": bool(unsupported),
                    **structured_control_flow_recovery_evidence(unsupported, function_unsupported_cf),
                },
            }
        )
    write_json(
        evidence_dir / f"{prefix}-cfg.json",
        {
            "schema_version": 1,
            "target_id": target_id,
            "slice_id": slice_id,
            "level": "L3",
            "status": "recorded" if not unsupported_cf else "blocked",
            "source_commit": source,
            "repo_commit": repo,
            "slice_spec_ref": slice_ref,
            "functions": functions,
            "unsupported_control_flow": unsupported_cf,
            "cache_invalidation_keys": cache_keys(spec, slice_spec_path),
        },
    )

    raw_pointer = read_json(evidence_dir / f"{prefix}-pointer-graph.json")
    raw_nodes = raw_pointer.get("pointer_graph", {}).get("nodes", [])
    pointer_nodes = []
    for idx, node in enumerate(raw_nodes):
        kind = pointer_node_kind(node)
        pointer_node = {
            "id": node.get("id", f"ptr-{idx + 1}"),
            "symbol": node.get("id", f"ptr-{idx + 1}"),
            "kind": kind,
            "c_type": node.get("c_type", ""),
            "mutability": "write_only" if node.get("role") == "out_param" else "read_only",
            "nullability": "unknown",
            "ownership_role": pointer_ownership_role(node),
            "read_effects": node.get("read_effects", []),
            "write_effects": node.get("write_effects", []),
            "boundary_decisions": node.get("boundary_decisions", []),
        }
        if kind == "buffer":
            pointer_node["buffer_role"] = pointer_buffer_role(node)
            pointer_node["length_companion"] = input_buffer_length_companion(spec, str(pointer_node["id"]))
        pointer_nodes.append(pointer_node)
    dependency_edges = [
        {
            "from": edge.get("from", ""),
            "to": edge.get("to", ""),
            "relationship": "writes_through",
            "evidence": edge.get("relationship", "translator pointer dependency"),
        }
        for edge in raw_pointer.get("pointer_graph", {}).get("edges", [])
    ]
    alias_gate = alias_gate_evidence(spec, pointer_nodes)
    pointer_triggers = ["pointer_parameter"] if pointer_nodes else ["none"]
    if alias_gate["is_alias_sensitive"]:
        pointer_triggers.append("alias_sensitive_state")
    effect_graph = effect_graph_from_pointer_nodes(pointer_nodes, alias_gate)
    pointer_cache_keys = (
        cache_keys(spec, slice_spec_path)
        + alias_gate["cache_invalidation_keys"]
        + ["effect_graph", f"effect_graph_sha256={sha256_json(effect_graph)}"]
    )
    pointer_status = "recorded" if pointer_nodes else "not_applicable"
    pointer_payload = {
        "schema_version": POINTER_GRAPH_SCHEMA_VERSION,
        "target_id": target_id,
        "slice_id": slice_id,
        "level": "L3",
        "status": pointer_status,
        "source_commit": source,
        "repo_commit": repo,
        "context_pack_ref": rel(evidence_dir / f"{prefix}-context-pack.json"),
        "applicability": {
            "has_pointer_surface": bool(pointer_nodes),
            "triggers": pointer_triggers,
        },
        "source_boundary": source_boundary(spec),
        "cache_invalidation_keys": pointer_cache_keys,
    }
    if pointer_nodes:
        pointer_payload.update(
            {
                "pointer_nodes": pointer_nodes,
                "dependency_edges": dependency_edges,
                "alias_sets": alias_gate["alias_sets"],
                "alias_risks": alias_gate["alias_risks"],
                "alias_contract": alias_gate["alias_contract"],
                "safe_boundary_preconditions": alias_gate["safe_boundary_preconditions"],
                "effect_graph": effect_graph,
                "pointer_decisions": pointer_decisions(pointer_nodes),
                "rust_mapping": [
                    {
                        "pointer_node": node["id"],
                        "strategy": "safe public API boundary generated by bounded translator",
                        "boundary_kind": "safe_wrapper",
                        "unsafe_expected": False,
                    }
                    for node in pointer_nodes
                ],
                "risk_summary": {
                    "unsafe_expected": False,
                    "blocked_reasons": alias_gate["blocked_reasons"],
                    "known_gaps": spec.get("non_goals", []),
                    "alias_gate": alias_gate["summary"],
                },
            }
        )
    else:
        pointer_payload["not_applicable_reason"] = "slice has no pointer surface"
    write_json(evidence_dir / f"{prefix}-pointer-graph.json", pointer_payload)

    raw_plan = read_json(evidence_dir / f"{prefix}-auto-translation-plan.json")
    translation_source = translation_source_from_plan(raw_plan)
    raw_call_expressions = raw_plan.get("plan", {}).get("call_expressions", [])
    external_callee_context = external_direct_callee_context(spec, raw_call_expressions)
    call_expressions = bind_external_callee_context(raw_call_expressions, external_callee_context)
    lvalue_decision_counts = count_occurrences(
        lvalue_decision_for_kind(kind)
        for function in functions
        for block in function.get("basic_blocks", [])
        for kind in block.get("lvalue_kinds", [])
        if kind != "none"
    )
    pointer_boundary_decision_counts = count_occurrences(
        decision
        for node in pointer_nodes
        for decision in node.get("boundary_decisions", [])
    )
    unsupported_lvalue_count = sum(
        1 for error in raw_plan.get("errors", []) if error.get("kind") == "unsupported_lvalue"
    )
    write_json(
        evidence_dir / f"{prefix}-auto-translation-plan.json",
        {
            "schema_version": 1,
            "target_id": target_id,
            "slice_id": slice_id,
            "level": "L3",
            "status": "draft_generated" if raw_plan.get("status") == "generated" else "blocked",
            "source_commit": source,
            "repo_commit": repo,
            "translation_source": translation_source,
            "inputs": {
                "slice_spec": slice_ref,
                "type_map": {"path": rel(evidence_dir / f"{prefix}-type-map.json"), "status": "recorded"},
                "cfg": {"path": rel(evidence_dir / f"{prefix}-cfg.json"), "status": "recorded"},
                "pointer_graph": {"path": rel(evidence_dir / f"{prefix}-pointer-graph.json"), "status": pointer_status},
                "external_callee_context": external_context_input_ref(
                    evidence_dir,
                    slice_id,
                    external_callee_context,
                ),
            },
            "generated_artifacts": [
                generated_artifact(evidence_dir / f"{prefix}-rust-draft.rs", "rust_draft"),
                generated_artifact(evidence_dir / f"{prefix}-c-oracle-harness-draft.c", "c_oracle_harness"),
                generated_artifact(evidence_dir / f"{prefix}-rust-replay-test-draft.rs", "rust_replay_test"),
            ],
            "translation_summary": {
                "translation_rule_ids": raw_plan.get("plan", {}).get("translation_rule_ids", []),
                "unsupported_node_count": raw_plan.get("plan", {}).get("unsupported_node_count", 0),
                "unsafe_candidate_count": raw_plan.get("plan", {}).get("unsafe_candidate_count", 0),
                "safe_public_api": True,
                "lvalue_decision_counts": lvalue_decision_counts,
                "unsupported_lvalue_count": unsupported_lvalue_count,
                "pointer_boundary_decision_counts": pointer_boundary_decision_counts,
                "alias_gate": alias_gate["summary"],
                "call_expressions": call_expressions,
                "external_direct_callee_declarations": external_callee_context["declarations"],
                "external_direct_callees": external_callee_context["declared"],
                "external_direct_callee_blocks": external_callee_context["blocked"],
            },
            "verification_plan": [
                {"gate": "rust_check", "command": "rustc --error-format=json <draft>", "required_before_acceptance": True},
                {"gate": "c_oracle", "command": "generate accepted C oracle", "required_before_acceptance": True},
                {"gate": "l3_manifest", "command": "emit L3 evidence manifest", "required_before_acceptance": True},
            ],
            "cache_invalidation_keys": pointer_cache_keys,
        },
    )

    write_json(
        evidence_dir / f"{prefix}-ai-candidate-manifest.json",
        {
            "schema_version": 1,
            "target_id": target_id,
            "slice_id": slice_id,
            "status": "not_used",
            "skipped_reason": "AI_SKIPPED: default local pipeline does not require an online provider",
            "ai_required_for_default_pipeline": False,
            "candidates": [],
            "cache_invalidation_keys": cache_keys(spec, slice_spec_path),
        },
    )

    write_auto_translation_events(spec, slice_spec_path, evidence_dir)
    write_context_pack(spec, slice_spec_path, evidence_dir, call_expressions, external_callee_context)
