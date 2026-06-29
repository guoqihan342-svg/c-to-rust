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
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
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
    replay = generate_rust_replay_test_draft(spec, evidence_dir, route_decision)
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
    emit_capability_delta_ledger(spec, evidence_dir, route_decision, validation_profile)
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
        },
    }
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
    parameters = [
        {
            "name": str(param.get("name") or f"arg{index + 1}"),
            "c_type": str(param.get("c_type") or param.get("type") or ""),
        }
        for index, param in enumerate(signature.get("parameters", []))
    ]
    return_type = str(signature.get("return_type") or signature.get("returns") or "")
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
    return {
        "name": name,
        "signature_ref": signature_ref,
        "source_ref": item.get("source_ref") or signature.get("source_ref") or "",
        "source_files": item.get("source_files") or source_files_for_external_callee(spec, name),
        "header_files": item.get("header_files", []),
        "definition_status": item.get("definition_status") or signature.get("definition_status") or "real_source_bound",
        "stub_kind": "compile_only",
        "stub_boundary": item.get("stub_boundary", "compile_only"),
        "semantics_verified": False,
        "parameters": parameters,
        "return_type": return_type,
        "supported": not unsupported_reasons,
        "unsupported_reasons": sorted(set(unsupported_reasons)),
    }


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
            blocked.append(
                {
                    "name": name,
                    "reason": "unsupported_external_direct_callee_signature",
                    "unsupported_reasons": descriptor.get("unsupported_reasons", []),
                    "stub_kind": "none",
                    "semantics_verified": False,
                }
            )
            continue
        declared.append(descriptor)

    status = "not_applicable"
    if blocked:
        status = "blocked"
    elif declared:
        status = "recorded"
    return {
        "status": status,
        "declared": declared,
        "blocked": blocked,
        "declared_count": len(declared),
        "blocked_count": len(blocked),
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
        bindings.append(
            {
                "callee": callee,
                "signature_ref": descriptor["signature_ref"],
                "source_expression": call.get("source_expression", ""),
                "statement_context": call.get("statement_context", ""),
                "stub_kind": descriptor["stub_kind"],
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
            "allowed_use": "standalone_rust_check_only",
            "semantics_verified": False,
        }
        for callee in context.get("declared", [])
    ]


def external_callee_claim_scope(context: dict[str, Any]) -> dict[str, Any]:
    if context["status"] == "recorded":
        status = "compile_context_only"
    else:
        status = context["status"]
    return {
        "status": status,
        "declared_count": context["declared_count"],
        "blocked_count": context["blocked_count"],
        "stub_kind": "compile_only" if context["declared_count"] else "none",
        "semantics_verified": False,
    }


def rust_check_external_context(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": context["status"],
        "declared_count": context["declared_count"],
        "blocked_count": context["blocked_count"],
        "declared_callees": [
            {
                "name": callee["name"],
                "signature_ref": callee["signature_ref"],
                "stub_kind": callee["stub_kind"],
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


def inject_external_callee_stubs(draft_path: Path, context: dict[str, Any]) -> bool:
    callees = context.get("declared", [])
    if not callees:
        return False
    text = draft_path.read_text(encoding="utf-8")
    stubs = []
    for callee in callees:
        name = rust_identifier(callee["name"])
        params = []
        for index, param in enumerate(callee.get("parameters", [])):
            param_name = rust_identifier(param.get("name") or f"arg{index + 1}")
            rust_type = primitive_rust_type(param.get("c_type", "")) or "i32"
            params.append(f"{param_name}: {rust_type}")
        return_type = primitive_rust_type(callee.get("return_type", "")) or "i32"
        signature = f"fn {name}({', '.join(params)}) -> {return_type}"
        if signature in text:
            continue
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


def mark_route_refused_candidate_artifacts(
    spec: dict[str, Any],
    evidence_dir: Path,
    route_decision: dict[str, Any],
) -> None:
    if not route_refuses_candidate_generation(route_decision):
        return
    slice_id = required_str(spec, "slice_id")
    prefix = f"l3-{slice_id}"
    plan_path = evidence_dir / f"{prefix}-auto-translation-plan.json"
    if plan_path.exists():
        plan = read_json(plan_path)
        for artifact in plan.get("generated_artifacts", []):
            artifact["status"] = "blocked"
        write_json(plan_path, plan)

    events_path = evidence_dir / f"{prefix}-auto-translation-events.jsonl"
    if not events_path.exists():
        return
    events = [
        json.loads(line)
        for line in events_path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    for event in events:
        if event.get("event_kind") not in {"rust_draft_generated", "run_completed"}:
            continue
        event["status"] = "blocked"
        if event.get("event_kind") == "rust_draft_generated":
            event["message"] = "Route refused candidate generation; Rust draft is blocked diagnostic output."
        else:
            event["message"] = "Route refused candidate generation; semantic acceptance gates remain blocked."
        for ref in event.get("artifact_refs", []):
            ref["status"] = "blocked"
    write_text(events_path, "".join(json.dumps(event, sort_keys=True) + "\n" for event in events))


def pointer_node_kind(node: dict[str, Any]) -> str:
    boundary_decisions = node.get("boundary_decisions", [])
    c_type = str(node.get("c_type", "")).replace(" ", "")
    if "byte_cursor_post_increment_read" in boundary_decisions:
        return "buffer"
    if "bounded_pointer_arithmetic_output_write" in node.get("boundary_decisions", []):
        return "buffer"
    if node.get("role") == "out_param":
        return "struct_pointer"
    if str(node.get("c_type", "")).strip() == "const int*":
        return "buffer"
    if c_type in {"constvoid*", "constuint8_t*"}:
        return "buffer"
    return "raw_pointer"


def pointer_buffer_role(node: dict[str, Any]) -> str:
    if node.get("role") == "out_param":
        return "output"
    return "input"


def pointer_ownership_role(node: dict[str, Any]) -> str:
    role = str(node.get("role") or "borrowed")
    return {
        "borrowed_input": "borrowed",
        "out_param": "out_param",
        "inout_param": "inout_param",
        "global": "global",
        "owner": "owner",
        "observer": "observer",
    }.get(role, "borrowed")


def input_buffer_length_companion(spec: dict[str, Any], pointer_id: str) -> str:
    pointer_contract = spec.get("c_boundary", {}).get("pointer_contract", {})
    for item in pointer_contract.get("input_buffers", []):
        if item.get("name") == pointer_id and item.get("length_companion"):
            return str(item["length_companion"])
    for signature in spec.get("c_boundary", {}).get("signatures", []):
        parameters = signature.get("parameters", [])
        for param in parameters:
            if param.get("name") == pointer_id and param.get("buffer_length_parameter"):
                return str(param["buffer_length_parameter"])
            c_type = str(param.get("c_type", "")).replace(" ", "")
            if param.get("name") == pointer_id and c_type in {"constvoid*", "constuint8_t*"}:
                for companion in parameters:
                    if companion.get("name") == "size" and str(companion.get("c_type", "")).strip() == "size_t":
                        return "size"
    return "len"


def alias_gate_evidence(spec: dict[str, Any], pointer_nodes: list[dict[str, Any]]) -> dict[str, Any]:
    read_nodes = [node for node in pointer_nodes if node.get("read_effects")]
    write_nodes = [node for node in pointer_nodes if node.get("write_effects")]
    alias_pairs = [
        (read_node, write_node)
        for read_node in read_nodes
        for write_node in write_nodes
        if read_node.get("id") != write_node.get("id")
    ]
    if not alias_pairs:
        summary = {
            "decision": "not_applicable",
            "risk_level": "none",
            "requires_noalias": False,
            "complete_alias_safety": False,
            "reason": "slice has no input/output pointer alias surface",
        }
        return {
            "is_alias_sensitive": False,
            "alias_sets": [],
            "alias_risks": [],
            "alias_contract": {
                "decision": "not_applicable",
                "proven": False,
                "requires_noalias": False,
                "source": "no read/write pointer pair",
                "evidence_refs": [],
                "complete_alias_safety": False,
            },
            "safe_boundary_preconditions": [],
            "blocked_reasons": [],
            "summary": summary,
            "cache_invalidation_keys": ["alias_gate=not_applicable"],
        }

    aliasing_proven = bool(
        spec.get("c_boundary", {}).get("pointer_contract", {}).get("aliasing_proven", False)
    )
    decision = "allow" if aliasing_proven else "requires_noalias_contract"
    risk_level = "proven_noalias" if aliasing_proven else "unknown_alias"
    evidence_source = (
        "c_boundary.pointer_contract.aliasing_proven=true"
        if aliasing_proven
        else "c_boundary.pointer_contract.aliasing_proven=false"
    )
    alias_sets = []
    alias_risks = []
    safe_boundary_preconditions = []
    for index, (read_node, write_node) in enumerate(alias_pairs, start=1):
        members = [str(read_node.get("id")), str(write_node.get("id"))]
        alias_sets.append(
            {
                "id": f"alias-set-{index}",
                "members": members,
                "relationship": "proven_disjoint" if aliasing_proven else "unknown_overlap",
                "risk": risk_level,
                "evidence": evidence_source,
            }
        )
        alias_risks.append(
            {
                "id": f"alias-risk-{index}",
                "pointer_nodes": members,
                "read_effects": read_node.get("read_effects", []),
                "write_effects": write_node.get("write_effects", []),
                "risk_level": risk_level,
                "evidence_source": evidence_source,
                "gate_decision": decision,
                "requires_noalias": not aliasing_proven,
            }
        )
        safe_boundary_preconditions.append(
            {
                "id": f"alias-precondition-{index}",
                "kind": "noalias",
                "applies_to": members,
                "required": not aliasing_proven,
                "reason": "safe Rust input/output slice boundary cannot express overlapping C input/output buffers",
            }
        )
    summary = {
        "decision": decision,
        "risk_level": risk_level,
        "requires_noalias": not aliasing_proven,
        "complete_alias_safety": False,
        "risk_count": len(alias_risks),
        "evidence_source": evidence_source,
    }
    return {
        "is_alias_sensitive": True,
        "alias_sets": alias_sets,
        "alias_risks": alias_risks,
        "alias_contract": {
            "decision": decision,
            "proven": aliasing_proven,
            "requires_noalias": not aliasing_proven,
            "source": evidence_source,
            "evidence_refs": [],
            "complete_alias_safety": False,
        },
        "safe_boundary_preconditions": safe_boundary_preconditions,
        "blocked_reasons": [] if aliasing_proven else ["input/output alias requires explicit noalias contract"],
        "summary": summary,
        "cache_invalidation_keys": [
            f"alias_gate={decision}",
            f"alias_risk_count={len(alias_risks)}",
            f"aliasing_proven={str(aliasing_proven).lower()}",
        ],
    }


def scalar_ub_contract(spec: dict[str, Any]) -> dict[str, Any]:
    c_contract = spec.get("c_boundary", {}).get("scalar_arithmetic_contract", {})
    if not isinstance(c_contract, dict):
        c_contract = {}
    fixture_domain = spec.get("fixture_contract", {}).get("scalar_input_domain", {})
    if not isinstance(fixture_domain, dict):
        fixture_domain = {}
    must_not_claim = spec.get("claim_boundary", {}).get("must_not_claim", [])
    if not isinstance(must_not_claim, list):
        must_not_claim = []
    status = "recorded" if c_contract or fixture_domain or must_not_claim else "not_declared"
    parameters = fixture_domain.get("parameters", [])
    if not isinstance(parameters, list):
        parameters = []
    return {
        "status": status,
        "c_boundary": {
            "wrapping_profile": str(c_contract.get("wrapping_profile", "not_declared")),
            "signed_overflow": str(c_contract.get("signed_overflow", "not_declared")),
            "division_by_zero": str(c_contract.get("division_by_zero", "not_declared")),
            "signed_division_overflow": str(
                c_contract.get("signed_division_overflow", "not_declared")
            ),
            "shift_count": str(c_contract.get("shift_count", "not_declared")),
            "signed_right_shift": str(c_contract.get("signed_right_shift", "not_declared")),
        },
        "fixture_contract": {
            "case_source": str(fixture_domain.get("case_source", "not_declared")),
            "parameters": parameters,
            "covers_overflow_boundaries": bool(
                fixture_domain.get("covers_overflow_boundaries", False)
            ),
        },
        "claim_boundary": {
            "must_not_claim": [str(item) for item in must_not_claim],
        },
    }


def scalar_ub_contract_identity(spec: dict[str, Any]) -> dict[str, Any]:
    contract = scalar_ub_contract(spec)
    return {
        "status": contract["status"],
        "sha256": sha256_json(contract),
    }


def scalar_admission_from_runtime_preconditions(
    spec: dict[str, Any],
    runtime_preconditions: Any,
) -> dict[str, Any]:
    preconditions = runtime_preconditions if isinstance(runtime_preconditions, list) else []
    contract = scalar_ub_contract(spec)
    if not preconditions:
        return {
            "status": "not_applicable",
            "precondition_count": 0,
            "covered": [],
            "unresolved": [],
            "contract_status": contract["status"],
        }
    covered = []
    unresolved = []
    for item in preconditions:
        code = str(item.get("code", "unknown")) if isinstance(item, dict) else "unknown"
        admission = scalar_precondition_admission(code, contract)
        if admission["status"] == "covered":
            covered.append(admission)
        else:
            unresolved.append(admission)
    return {
        "status": "covered" if not unresolved else "unresolved",
        "precondition_count": len(preconditions),
        "covered": covered,
        "unresolved": unresolved,
        "contract_status": contract["status"],
        "source_fields": [
            "c_boundary.scalar_arithmetic_contract",
            "fixture_contract.scalar_input_domain",
            "claim_boundary.must_not_claim",
        ],
    }


def scalar_precondition_admission(code: str, contract: dict[str, Any]) -> dict[str, Any]:
    required_field, required_value = scalar_precondition_required_contract(code)
    c_contract = contract.get("c_boundary", {})
    fixture_contract = contract.get("fixture_contract", {})
    parameters = fixture_contract.get("parameters", [])
    has_input_domain = isinstance(parameters, list) and bool(parameters)
    if required_field and c_contract.get(required_field) == required_value and has_input_domain:
        return {
            "code": code,
            "status": "covered",
            "covered_by": [
                f"c_boundary.scalar_arithmetic_contract.{required_field}",
                "fixture_contract.scalar_input_domain",
            ],
        }
    missing = []
    if not required_field or c_contract.get(required_field) != required_value:
        missing.append(f"c_boundary.scalar_arithmetic_contract.{required_field or 'unknown'}")
    if not has_input_domain:
        missing.append("fixture_contract.scalar_input_domain")
    return {
        "code": code,
        "status": "unresolved",
        "missing": missing,
    }


def scalar_precondition_required_contract(code: str) -> tuple[str | None, str | None]:
    if code in {
        "signed_add_no_overflow",
        "signed_sub_no_overflow",
        "signed_mul_no_overflow",
    }:
        return "signed_overflow", "runtime_precondition_no_overflow"
    if code in {"division_divisor_nonzero", "modulo_divisor_nonzero"}:
        return "division_by_zero", "runtime_precondition_nonzero_divisor"
    if code in {"signed_division_no_overflow", "signed_modulo_no_overflow"}:
        return "signed_division_overflow", "runtime_precondition_excludes_min_div_minus_one"
    if code == "shift_count_in_range":
        return "shift_count", "runtime_precondition_in_range"
    if code == "signed_right_shift_implementation_defined":
        return "signed_right_shift", "explicit_implementation_defined_contract"
    return None, None


def emit_scalar_refusal_evidence(
    spec: dict[str, Any],
    evidence_dir: Path,
    route_decision: dict[str, Any],
    validation_profile: dict[str, Any],
) -> dict[str, Any] | None:
    slice_id = required_str(spec, "slice_id")
    typed_ir = route_decision.get("candidate_generation", {}).get("typed_ir", {})
    runtime_preconditions = typed_ir.get("runtime_preconditions", [])
    if not isinstance(runtime_preconditions, list):
        runtime_preconditions = []
    codes = {
        str(item.get("code", ""))
        for item in runtime_preconditions
        if isinstance(item, dict)
    }
    if "signed_right_shift_implementation_defined" not in codes:
        return None

    prefix = f"l3-{slice_id}"
    path = evidence_dir / f"{prefix}-refusal-evidence.json"
    payload = {
        "schema_version": 1,
        "target_id": spec.get("target_id"),
        "slice_id": slice_id,
        "source_commit": source_commit(spec),
        "status": "recorded",
        "route_level": route_decision.get("level"),
        "runtime_preconditions": runtime_preconditions,
        "scalar_admission": typed_ir.get("scalar_admission"),
        "scalar_ub_contract": scalar_ub_contract(spec),
        "refusals": [
            {
                "code": "missing_explicit_signed_right_shift_contract",
                "decision": "fail_closed",
                "reason": "C signed right shift is implementation-defined and the typed-IR emitter must reject it without an explicit slice/platform contract.",
                "required_contract": {
                    "field": "c_boundary.scalar_arithmetic_contract.signed_right_shift",
                    "value": "explicit_implementation_defined_contract",
                },
                "evidence_refs": [
                    "crates/c2r-translator/tests/bounded_translation.rs::typed_ir_rejects_signed_right_shift_without_contract"
                ],
            },
            {
                "code": "wrong_explicit_signed_right_shift_contract",
                "decision": "fail_closed",
                "reason": "The scalar admission gate treats any non-matching signed_right_shift contract as unresolved.",
                "required_contract": {
                    "field": "c_boundary.scalar_arithmetic_contract.signed_right_shift",
                    "value": "explicit_implementation_defined_contract",
                },
                "evidence_refs": [
                    "validation/tools/test_auto_migrate.py::test_scalar_admission_requires_matching_contract_and_input_domain"
                ],
            },
            {
                "code": "missing_scalar_input_domain",
                "decision": "fail_closed",
                "reason": "Runtime scalar preconditions cannot be admitted without a fixture input domain binding.",
                "required_contract": {
                    "field": "fixture_contract.scalar_input_domain",
                    "value": "nonempty parameters",
                },
                "evidence_refs": [
                    "validation/tools/test_auto_migrate.py::test_scalar_admission_requires_matching_contract_and_input_domain"
                ],
            },
        ],
        "artifact_refs": {
            "route_decision": {
                "path": rel(evidence_dir / f"{prefix}-route-decision.json"),
                "status": route_decision.get("status", "recorded"),
            },
            "validation_profile": {
                "path": rel(evidence_dir / f"{prefix}-validation-profile.json"),
                "status": validation_profile.get("status", "recorded"),
            },
            "clang_lowering_report": {
                "path": rel(evidence_dir / f"{prefix}-clang-lowering-report.json"),
                "status": typed_ir.get("source_artifact", {}).get("status", "recorded"),
            },
        },
        "boundary": "This artifact records refusal conditions for signed right shift contracts; it does not accept the generated Rust draft as semantic proof.",
    }
    write_json(path, payload)
    return payload


def generate_oracle_harness_draft(spec: dict[str, Any], evidence_dir: Path, skip: bool) -> dict[str, Any]:
    slice_id = required_str(spec, "slice_id")
    function_name = required_str(spec, "function_name")
    fixture = spec.get("fixture_contract", {})
    c_path = evidence_dir / f"l3-{slice_id}-c-oracle-harness-draft.c"
    report_path = evidence_dir / f"l3-{slice_id}-c-oracle-status.json"
    global_requirements = global_dependency_requirements(spec)
    global_comments = "".join(
        f"/* global dependency: {item['name']} ({item['definition_status']}) from {item.get('source_span', {}).get('file', 'unknown')} */\n"
        for item in global_requirements
    )
    source_files = spec.get("c_boundary", {}).get("files", [])
    source_comments = "".join(
        f"/* source file: {item.get('path', 'unknown')} (sha256: {item.get('sha256', 'unknown')}) */\n"
        for item in source_files
        if isinstance(item, dict)
    )
    prototype = c_function_prototype(spec)
    fixture_path_text = fixture_path(spec)
    fixture_binding = oracle_fixture_binding(spec)
    fixture_comments = oracle_fixture_comments(fixture_binding)
    fixture_execution = oracle_fixture_execution_source(spec, fixture_binding)
    compile_command = c_oracle_compile_command(spec, c_path, evidence_dir)
    fixture_execution_statements = fixture_execution["statements"]
    if not fixture_execution_statements:
        fixture_execution_statements = (
            "  /* TODO: load fixture values, call the target function, and compare observable outputs. */\n"
        )
    source = (
        "/* Auto-generated C oracle harness draft. */\n"
        "/* Review and compile against the pinned L1 source tree before using as oracle evidence. */\n"
        "/* Draft only: fixture values and oracle assertions must be reviewed before acceptance. */\n"
        "#include <stdint.h>\n"
        "#include <stddef.h>\n"
        "#include <stdio.h>\n\n"
        f"/* slice: {spec.get('target_id')}/{slice_id} */\n"
        f"/* function: {function_name} */\n"
        f"/* fixture input: {fixture_path_text} */\n"
        f"{fixture_comments}"
        f"{source_comments}"
        f"{global_comments}"
        f"{prototype}\n\n"
        f"{fixture_execution['declarations']}"
        "int main(void) {\n"
        f"  puts(\"oracle harness draft for {function_name}\");\n"
        f"  puts(\"fixture input: {fixture_path_text}\");\n"
        f"{fixture_execution_statements}"
        "  return 0;\n"
        "}\n"
    )
    write_text(c_path, source)
    harness_draft_ref = evidence_ref(c_path, "draft")
    compile_execution = c_oracle_compile_execution(compile_command, evidence_dir, skip, spec, fixture_binding)
    status = "SKIPPED_LOCAL_NO_C_TOOLCHAIN" if skip else "DRAFT_GENERATED"
    payload = {
        "schema_version": 1,
        "target_id": spec.get("target_id"),
        "slice_id": slice_id,
        "status": status,
        "toolchain_status": compile_execution["toolchain_status_after_attempt"],
        "semantic_pass": False,
        "harness_draft": rel(c_path),
        "harness_draft_ref": harness_draft_ref,
        "fixture": fixture_path_text,
        "fixture_binding": fixture_binding,
        "harness_contract": {
            "function_prototype": prototype,
            "fixture": fixture_binding,
            "source_files": source_files,
            "global_dependencies": global_requirements,
            "status": "draft_requires_review",
        },
        "compile_command_draft": compile_command,
        "compile_execution": compile_execution,
        "global_linkage_requirements": global_requirements,
        "required_final_status": "C_ORACLE_GENERATED",
        "boundary": "Draft generation is not oracle success.",
    }
    write_json(report_path, payload)
    return payload


def oracle_fixture_binding(spec: dict[str, Any]) -> dict[str, Any]:
    fixture = spec.get("fixture_contract", {})
    cases = fixture.get("cases") or []
    path = fixture_path(spec)
    case_bindings = oracle_fixture_case_bindings(spec)
    if not cases:
        binding_status = "missing_or_empty"
    else:
        binding_status = "declared_not_executed"
    return {
        "path": path,
        "case_count": len(cases),
        "binding_status": binding_status,
        "behavior_fields": behavior_fields(spec),
        "observable_outputs": behavior_fields(spec),
        "case_bindings": case_bindings,
        "expected_output_status": fixture_expected_output_status(case_bindings),
    }


def oracle_fixture_case_bindings(spec: dict[str, Any]) -> list[dict[str, Any]]:
    fixture = spec.get("fixture_contract", {})
    fields = behavior_fields(spec)
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
    fields = behavior_fields(spec)
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
    return read_json(path)


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


def oracle_fixture_comments(fixture_binding: dict[str, Any]) -> str:
    outputs = ", ".join(str(item) for item in fixture_binding.get("observable_outputs", [])) or "none"
    lines = [
        f"/* fixture cases: {fixture_binding.get('case_count', 0)} */\n",
        f"/* observable outputs: {outputs} */\n",
    ]
    for case in fixture_binding.get("case_bindings", []):
        expected_outputs = json.dumps(case.get("expected_outputs", {}), sort_keys=True)
        lines.append(
            "/* fixture case: "
            f"{case.get('id')} input_ref={case.get('input_ref')} "
            f"expected_ref={case.get('expected_ref')} expected_outputs={expected_outputs} */\n"
        )
    return "".join(lines)


def oracle_fixture_execution_source(
    spec: dict[str, Any],
    fixture_binding: dict[str, Any],
) -> dict[str, str]:
    signature = c_function_signature(spec)
    if not c_oracle_signature_supports_return_code_call(spec, signature):
        return {"declarations": "", "statements": ""}

    declarations: list[str] = []
    statements: list[str] = []
    for case_binding in fixture_binding.get("case_bindings", []):
        if not isinstance(case_binding, dict):
            continue
        case_source = c_oracle_case_execution_source(spec, signature, case_binding)
        if case_source is None:
            case_id = str(case_binding.get("id") or "unknown-case")
            statements.append(
                f"  /* TODO: fixture case {case_id} is not supported by this draft call generator. */\n"
            )
            continue
        declarations.append(case_source["declarations"])
        statements.append(case_source["statements"])
    return {"declarations": "".join(declarations), "statements": "".join(statements)}


def c_oracle_signature_supports_return_code_call(
    spec: dict[str, Any],
    signature: dict[str, Any],
) -> bool:
    if signature.get("return_type") != "uint32_t":
        return False
    if behavior_fields(spec) != ["return_code"]:
        return False
    parameters = [item for item in signature.get("parameters", []) if isinstance(item, dict)]
    if len(parameters) != 3:
        return False
    expected = [
        ("crc", "uint32_t"),
        ("buf", "const void *"),
        ("size", "size_t"),
    ]
    actual = [
        (str(item.get("name") or ""), normalize_c_type(str(item.get("c_type") or "")))
        for item in parameters
    ]
    return actual == expected


def c_oracle_case_execution_source(
    spec: dict[str, Any],
    signature: dict[str, Any],
    case_binding: dict[str, Any],
) -> dict[str, str] | None:
    case_payload = oracle_fixture_input_payload(spec, case_binding)
    if not isinstance(case_payload, dict):
        return None
    expected_outputs = case_binding.get("expected_outputs")
    if not isinstance(expected_outputs, dict):
        return None
    expected_return = expected_outputs.get("return_code")
    if not is_uint32_value(expected_return):
        return None

    crc = case_payload.get("crc")
    buf = case_payload.get("buf")
    size = case_payload.get("size")
    if not is_uint32_value(crc) or not is_size_value(size) or not is_byte_list(buf):
        return None
    if int(size) != len(buf):
        return None

    function_name = required_str(spec, "function_name")
    case_id = str(case_binding.get("id") or "case")
    case_ident = c_safe_ident(case_id)
    buffer_name = f"{case_ident}_buf"
    actual_name = f"actual_{case_ident}_return_code"
    buffer_values = c_byte_array_initializer(buf)
    expected_literal = c_integer_literal("uint32_t", int(expected_return))
    parameters = [item for item in signature.get("parameters", []) if isinstance(item, dict)]
    argument_expressions = [
        c_integer_literal(str(parameters[0].get("c_type") or "uint32_t"), int(crc)),
        buffer_name,
        c_integer_literal(str(parameters[2].get("c_type") or "size_t"), int(size)),
    ]
    declarations = f"static const uint8_t {buffer_name}[] = {{ {buffer_values} }};\n\n"
    statements = (
        f"  uint32_t {actual_name} = {function_name}({', '.join(argument_expressions)});\n"
        f"  if ({actual_name} != {expected_literal}) {{\n"
        "    fprintf(stderr, "
        f"{c_string_literal(case_id + ' return_code mismatch: expected ' + str(int(expected_return)) + ' got %llu\n')}, "
        f"(unsigned long long){actual_name});\n"
        "    return 1;\n"
        "  }\n"
        f"  puts({c_string_literal('fixture case ' + case_id + ' return_code matched')});\n"
    )
    return {"declarations": declarations, "statements": statements}


def oracle_fixture_input_payload(spec: dict[str, Any], case_binding: dict[str, Any]) -> Any | None:
    fixture = spec.get("fixture_contract", {})
    input_ref = str(case_binding.get("input_ref") or "")
    candidate_refs = [fixture.get("path") or fixture.get("input"), case_binding.get("expected_ref")]
    for candidate_ref in candidate_refs:
        payload = load_fixture_ref_payload(candidate_ref)
        if payload is None:
            continue
        case_payload = fixture_case_payload(payload, input_ref)
        if isinstance(case_payload, dict):
            return case_payload
    inline_case = fixture_case_payload({"cases": fixture.get("cases", [])}, input_ref)
    if isinstance(inline_case, dict):
        return inline_case
    return None


def c_function_signature(spec: dict[str, Any]) -> dict[str, Any]:
    function_name = required_str(spec, "function_name")
    signatures = spec.get("c_boundary", {}).get("signatures", [])
    return next(
        (item for item in signatures if isinstance(item, dict) and item.get("function") == function_name),
        {},
    )


def c_function_prototype(spec: dict[str, Any]) -> str:
    function_name = required_str(spec, "function_name")
    signature = c_function_signature(spec)
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


def normalize_c_type(c_type: str) -> str:
    text = str(c_type).strip()
    text = text.replace("*", " * ")
    return " ".join(text.split())


def c_safe_ident(text: str) -> str:
    identifier = "".join(ch if (ch.isascii() and (ch.isalnum() or ch == "_")) else "_" for ch in str(text))
    if not identifier:
        return "case"
    if identifier[0].isdigit():
        return f"case_{identifier}"
    return identifier


def is_uint32_value(value: Any) -> bool:
    return type(value) is int and 0 <= value <= 0xFFFFFFFF


def is_size_value(value: Any) -> bool:
    return type(value) is int and value >= 0


def is_byte_list(value: Any) -> bool:
    return isinstance(value, list) and all(type(item) is int and 0 <= item <= 0xFF for item in value)


def c_byte_array_initializer(values: list[int]) -> str:
    if not values:
        return "0"
    return ", ".join(f"{item}u" for item in values)


def c_integer_literal(c_type: str, value: int) -> str:
    normalized = normalize_c_type(c_type)
    suffix = "u" if value >= 0 else ""
    return f"({normalized}){value}{suffix}"


def c_string_literal(value: str) -> str:
    return json.dumps(str(value))


def c_oracle_compile_command(spec: dict[str, Any], harness_path: Path, evidence_dir: Path) -> dict[str, Any]:
    source_root = compile_source_root(spec)
    resolved_include_paths = [
        resolve_source_root_path(source_root, path)
        for path in spec.get("build_profile", {}).get("include_paths", [])
    ]
    defines = [str(item) for item in spec.get("build_profile", {}).get("defines", [])]
    link_source_files = compile_link_source_files(spec, source_root)
    define_args = [f"-D{item}" for item in defines]
    include_args = [f"-I{path}" for path in resolved_include_paths]
    link_args = [item["resolved_path"] for item in link_source_files]
    output_name = harness_path.with_suffix(".exe").name
    return {
        "working_directory": rel(evidence_dir),
        "source_root": source_root,
        "defines": defines,
        "resolved_include_paths": resolved_include_paths,
        "link_source_files": link_source_files,
        "link_strategy": c_oracle_link_strategy(spec),
        "argv": [
            "cc",
            "-std=c99",
            *define_args,
            *include_args,
            harness_path.name,
            *link_args,
            "-o",
            output_name,
        ],
        "status": "draft_not_executed",
    }


def c_oracle_compile_execution(
    compile_command: dict[str, Any],
    evidence_dir: Path,
    skip: bool,
    spec: dict[str, Any] | None = None,
    fixture_binding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = {
        "argv": compile_command.get("argv", []),
        "working_directory": rel(evidence_dir),
        "semantic_pass": False,
    }
    if skip:
        return {
            **base,
            "status": "skipped_by_flag",
            "attempted": False,
            "toolchain_adapter": "not_executed",
            "toolchain_status_after_attempt": "DRAFT_NOT_EXECUTED",
            "diagnostics": ["C oracle compile execution skipped by --skip-c-oracle."],
        }

    argv = [str(item) for item in compile_command.get("argv", [])]
    if not argv:
        return {
            **base,
            "status": "missing_argv",
            "attempted": False,
            "toolchain_status_after_attempt": "COMPILE_NOT_EXECUTED",
            "diagnostics": ["C oracle compile command argv is missing."],
        }

    compiler_resolution = resolve_c_compiler(argv[0])
    compiler_path = compiler_resolution["path"]
    if compiler_path is None:
        return {
            **base,
            "status": "compiler_not_found",
            "attempted": False,
            "toolchain_status_after_attempt": "COMPILE_NOT_EXECUTED",
            "requested_compiler": argv[0],
            "compiler_candidates": compiler_resolution["candidates"],
            "diagnostics": [
                f"C compiler not found on PATH: {argv[0]}",
                f"Fallback C compilers checked: {', '.join(compiler_resolution['candidates'])}",
            ],
        }

    resolved_argv: list[str] = []
    try:
        resolved_argv = c_oracle_compile_execution_argv(argv, evidence_dir, compiler_resolution)
        result = subprocess.run(
            resolved_argv,
            cwd=None if compiler_resolution.get("adapter") == "wsl" else evidence_dir,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            **base,
            "status": "compile_timeout",
            "attempted": True,
            "compiler_path": compiler_path,
            "compiler_name": compiler_resolution["name"],
            "requested_compiler": argv[0],
            "compiler_candidates": compiler_resolution["candidates"],
            "toolchain_adapter": compiler_resolution["adapter"],
            "execution_argv": resolved_argv,
            "toolchain_status_after_attempt": "COMPILE_FAILED",
            "returncode": None,
            "stdout": truncate_text(exc.stdout or ""),
            "stderr": truncate_text(exc.stderr or "compile timed out after 30 seconds"),
            "diagnostics": ["C oracle compile command timed out; no oracle evidence accepted."],
        }
    except (OSError, RuntimeError) as exc:
        return {
            **base,
            "status": "compile_failed",
            "attempted": True,
            "compiler_path": compiler_path,
            "compiler_name": compiler_resolution["name"],
            "requested_compiler": argv[0],
            "compiler_candidates": compiler_resolution["candidates"],
            "toolchain_adapter": compiler_resolution["adapter"],
            "execution_argv": resolved_argv,
            "toolchain_status_after_attempt": "COMPILE_FAILED",
            "returncode": None,
            "stdout": "",
            "stderr": truncate_text(str(exc)),
            "diagnostics": ["C oracle compile command could not start; no oracle evidence accepted."],
        }

    succeeded = result.returncode == 0
    payload = {
        **base,
        "status": "compile_succeeded_not_oracle" if succeeded else "compile_failed",
        "attempted": True,
        "compiler_path": compiler_path,
        "compiler_name": compiler_resolution["name"],
        "requested_compiler": argv[0],
        "compiler_candidates": compiler_resolution["candidates"],
        "toolchain_adapter": compiler_resolution["adapter"],
        "execution_argv": resolved_argv,
        "toolchain_status_after_attempt": "COMPILE_SUCCEEDED_NOT_ORACLE" if succeeded else "COMPILE_FAILED",
        "returncode": result.returncode,
        "stdout": truncate_text(result.stdout),
        "stderr": truncate_text(result.stderr),
        "diagnostics": [
            "C oracle compile command succeeded, but execution/diff gates are still required."
            if succeeded
            else "C oracle compile command failed; no oracle evidence accepted."
        ],
    }
    if succeeded:
        payload["harness_execution"] = c_oracle_harness_execution(
            argv, evidence_dir, spec, fixture_binding, compiler_resolution
        )
    return payload


def resolve_c_compiler(requested: str) -> dict[str, Any]:
    candidates = [requested]
    requested_name = Path(requested).name.lower()
    if requested_name in {"cc", "cc.exe"}:
        candidates.extend(["gcc", "clang"])

    seen: set[str] = set()
    ordered_candidates = []
    for candidate in candidates:
        if candidate not in seen:
            ordered_candidates.append(candidate)
            seen.add(candidate)

    for candidate in ordered_candidates:
        path = shutil.which(candidate)
        if path is not None:
            return {
                "path": path,
                "name": candidate,
                "candidates": ordered_candidates,
                "adapter": "local",
                "launcher": None,
            }

    wsl = shutil.which("wsl.exe") or shutil.which("wsl")
    if wsl is not None:
        for candidate in ordered_candidates:
            path = wsl_command_output(wsl, f"command -v {shlex.quote(candidate)}")
            if path:
                return {
                    "path": path,
                    "name": candidate,
                    "candidates": ordered_candidates,
                    "adapter": "wsl",
                    "launcher": wsl,
                }
    return {
        "path": None,
        "name": None,
        "candidates": ordered_candidates,
        "adapter": "local",
        "launcher": None,
    }


def c_oracle_compile_execution_argv(
    argv: list[str],
    evidence_dir: Path,
    compiler_resolution: dict[str, Any],
) -> list[str]:
    compiler_path = str(compiler_resolution["path"])
    if compiler_resolution.get("adapter") != "wsl":
        return [compiler_path, *argv[1:]]

    launcher = str(compiler_resolution["launcher"])
    wsl_cwd = wsl_path(evidence_dir, launcher)
    converted_args = [compiler_path]
    for arg in argv[1:]:
        converted_args.append(wsl_compile_arg(arg, launcher))
    shell_command = f"cd {shlex.quote(wsl_cwd)} && {' '.join(shlex.quote(item) for item in converted_args)}"
    return [launcher, "-e", "sh", "-lc", shell_command]


def wsl_compile_arg(arg: str, launcher: str) -> str:
    if arg.startswith("-I") and len(arg) > 2:
        return "-I" + wsl_maybe_path(arg[2:], launcher)
    return wsl_maybe_path(arg, launcher)


def wsl_maybe_path(value: str, launcher: str) -> str:
    if path_is_absolute(value):
        return wsl_path(Path(value), launcher)
    return value


def wsl_path(path: Path, launcher: str) -> str:
    result = subprocess.run(
        [launcher, "-e", "wslpath", "-a", str(path)],
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(truncate_text(result.stderr or result.stdout or f"wslpath failed for {path}"))
    converted = result.stdout.strip()
    if not converted:
        raise RuntimeError(f"wslpath returned no path for {path}")
    return converted


def wsl_command_output(launcher: str, command: str) -> str | None:
    try:
        result = subprocess.run(
            [launcher, "-e", "sh", "-lc", command],
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    first_line = result.stdout.strip().splitlines()
    return first_line[0] if first_line else None


def c_oracle_harness_execution(
    argv: list[str],
    evidence_dir: Path,
    spec: dict[str, Any] | None = None,
    fixture_binding: dict[str, Any] | None = None,
    compiler_resolution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    timeout_seconds = 30
    executable_path = c_oracle_output_executable(argv, evidence_dir)
    base = {
        "argv": [rel(executable_path)] if executable_path is not None else [],
        "working_directory": rel(evidence_dir),
        "executable_path": rel(executable_path) if executable_path is not None else "missing",
        "timeout_seconds": timeout_seconds,
        "semantic_pass": False,
    }
    if executable_path is None:
        payload = {
            **base,
            "status": "executable_missing_not_oracle",
            "attempted": False,
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "diagnostics": ["C oracle harness output path is missing; no oracle evidence accepted."],
        }
        payload["output_gate"] = c_oracle_harness_output_gate(spec, fixture_binding, payload)
        return payload
    if not executable_path.exists():
        payload = {
            **base,
            "status": "executable_missing_not_oracle",
            "attempted": False,
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "diagnostics": [
                "C oracle harness executable is missing after compile success; no oracle evidence accepted."
            ],
        }
        payload["output_gate"] = c_oracle_harness_output_gate(spec, fixture_binding, payload)
        return payload

    execution_argv = [str(executable_path)]
    execution_cwd: Path | None = evidence_dir
    adapter = None
    if compiler_resolution and compiler_resolution.get("adapter") == "wsl":
        adapter = "wsl"
        launcher = str(compiler_resolution["launcher"])
        try:
            wsl_cwd = wsl_path(evidence_dir, launcher)
            wsl_executable = wsl_path(executable_path, launcher)
            execution_argv = [
                launcher,
                "-e",
                "sh",
                "-lc",
                f"cd {shlex.quote(wsl_cwd)} && {shlex.quote(wsl_executable)}",
            ]
            execution_cwd = None
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            payload = {
                **base,
                "status": "execution_error_not_oracle",
                "attempted": False,
                "returncode": None,
                "stdout": "",
                "stderr": truncate_text(str(exc)),
                "diagnostics": ["C oracle harness execution could not start; no oracle evidence accepted."],
                "toolchain_adapter": adapter,
            }
            payload["output_gate"] = c_oracle_harness_output_gate(spec, fixture_binding, payload)
            return payload

    try:
        result = subprocess.run(
            execution_argv,
            cwd=execution_cwd,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        payload = {
            **base,
            "status": "execution_timeout_not_oracle",
            "attempted": True,
            "returncode": None,
            "stdout": truncate_text(exc.stdout or ""),
            "stderr": truncate_text(exc.stderr or f"harness execution timed out after {timeout_seconds} seconds"),
            "diagnostics": ["C oracle harness execution timed out; no oracle evidence accepted."],
        }
        if adapter:
            payload["toolchain_adapter"] = adapter
            payload["execution_argv"] = execution_argv
        payload["output_gate"] = c_oracle_harness_output_gate(spec, fixture_binding, payload)
        return payload
    except OSError as exc:
        payload = {
            **base,
            "status": "execution_error_not_oracle",
            "attempted": False,
            "returncode": None,
            "stdout": "",
            "stderr": truncate_text(str(exc)),
            "diagnostics": ["C oracle harness execution could not start; no oracle evidence accepted."],
        }
        if adapter:
            payload["toolchain_adapter"] = adapter
            payload["execution_argv"] = execution_argv
        payload["output_gate"] = c_oracle_harness_output_gate(spec, fixture_binding, payload)
        return payload

    exited_zero = result.returncode == 0
    raw_payload = {
        **base,
        "status": "exited_zero_not_oracle" if exited_zero else "exited_nonzero_not_oracle",
        "attempted": True,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "diagnostics": [
            "C oracle harness executed, but execution output has not passed oracle diff gates."
        ],
    }
    if adapter:
        raw_payload["toolchain_adapter"] = adapter
        raw_payload["execution_argv"] = execution_argv
    payload = {
        **raw_payload,
        "stdout": truncate_text(result.stdout),
        "stderr": truncate_text(result.stderr),
    }
    payload["output_gate"] = c_oracle_harness_output_gate(spec, fixture_binding, raw_payload)
    return payload


def c_oracle_harness_output_gate(
    spec: dict[str, Any] | None,
    fixture_binding: dict[str, Any] | None,
    harness_execution: dict[str, Any],
) -> dict[str, Any]:
    expected_fragments = c_oracle_expected_stdout_fragments(spec, fixture_binding)
    base = {
        "schema_version": 1,
        "gate": "c_oracle_harness_output",
        "semantic_pass": False,
        "compared_fields": behavior_fields(spec) if spec is not None else [],
        "fixture_expected_output_status": str(
            fixture_binding.get("expected_output_status", "missing_or_empty")
            if isinstance(fixture_binding, dict)
            else "missing_or_empty"
        ),
        "expected_stdout_fragments": expected_fragments,
        "matched_stdout_fragments": [],
        "missing_stdout_fragments": expected_fragments,
        "boundary": "Harness stdout markers are diagnostic only until accepted oracle diff gates pass.",
    }
    if harness_execution.get("status") != "exited_zero_not_oracle" or harness_execution.get("returncode") != 0:
        return {
            **base,
            "status": "not_run_not_oracle",
            "diagnostics": ["C oracle harness output gate did not run because harness execution did not exit zero."],
        }
    if not expected_fragments:
        return {
            **base,
            "status": "unsupported_not_oracle",
            "diagnostics": ["C oracle harness output gate has no supported fixture stdout markers to compare."],
        }

    stdout = str(harness_execution.get("stdout") or "")
    matched = [fragment for fragment in expected_fragments if fragment in stdout]
    missing = [fragment for fragment in expected_fragments if fragment not in stdout]
    if not missing:
        return {
            **base,
            "status": "matched_not_oracle",
            "matched_stdout_fragments": matched,
            "missing_stdout_fragments": [],
            "diagnostics": [
                "C oracle harness stdout matched draft fixture markers, but oracle diff gates are still required."
            ],
        }
    return {
        **base,
        "status": "mismatch_not_oracle",
        "matched_stdout_fragments": matched,
        "missing_stdout_fragments": missing,
        "diagnostics": ["C oracle harness stdout did not match all draft fixture markers; no oracle evidence accepted."],
    }


def c_oracle_expected_stdout_fragments(
    spec: dict[str, Any] | None,
    fixture_binding: dict[str, Any] | None,
) -> list[str]:
    if spec is None or fixture_binding is None:
        return []
    fields = behavior_fields(spec)
    fragments: list[str] = []
    for case in fixture_binding.get("case_bindings", []):
        if not isinstance(case, dict):
            continue
        expected_outputs = case.get("expected_outputs")
        if not isinstance(expected_outputs, dict):
            continue
        case_id = str(case.get("id") or "case")
        for field in fields:
            if field in expected_outputs:
                fragments.append(f"fixture case {case_id} {field} matched")
    return fragments


def c_oracle_output_executable(argv: list[str], evidence_dir: Path) -> Path | None:
    try:
        output_index = argv.index("-o") + 1
    except ValueError:
        return None
    if output_index >= len(argv):
        return None
    output_path = Path(argv[output_index])
    if not output_path.is_absolute():
        output_path = evidence_dir / output_path
    return output_path


def truncate_text(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]"


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


def generate_rust_replay_test_draft(
    spec: dict[str, Any],
    evidence_dir: Path,
    route_decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    slice_id = required_str(spec, "slice_id")
    function_name = required_str(spec, "function_name")
    path = evidence_dir / f"l3-{slice_id}-rust-replay-test-draft.rs"
    fixture = spec.get("fixture_contract", {})
    fixture_path_text = fixture_path(spec)
    fixture_binding = oracle_fixture_binding(spec)
    fixture_cases_source = rust_replay_fixture_cases_source(spec, fixture_binding)
    text = (
        "// Auto-generated Rust replay test draft.\n"
        "// Review before promoting into validation/l2_slices/tests.\n\n"
        "#[test]\n"
        f"fn replay_{safe_ident(slice_id)}_fixture_contract() {{\n"
        f"    let _fixture = {rust_string_literal(fixture_path_text)};\n"
        f"    let _api = {rust_string_literal(function_name)};\n"
        "    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;\n"
        f"{fixture_cases_source}"
        "}\n"
    )
    write_text(path, text)
    behavior_fields = fixture.get("observable_outputs") or fixture.get("behavior_fields", [])
    test_name = f"replay_{safe_ident(slice_id)}_fixture_contract"
    payload = {
        "schema_version": 1,
        "target_id": spec.get("target_id"),
        "slice_id": slice_id,
        "level": spec.get("level", "L3"),
        "status": "recorded",
        "generated_draft_semantic_pass": False,
        "test_draft": rel(path),
        "fixture": fixture_path_text,
        "behavior_fields": list(behavior_fields),
        "source_commit": source_commit(spec),
        "repo_commit": repo_commit(),
        "source_test_inputs": {
            "oracle_strategy": "Generated replay draft from slice fixture contract; accepted semantics still require C_ORACLE_GENERATED.",
            "fixtures": [
                {
                    "path": fixture_path_text,
                    "hash": fixture_hash(spec),
                    "operation_count": len(fixture.get("cases", [])),
                    "source_kind": "fixture",
                }
            ],
            "oracle_reports": [
                {
                    "path": rel(evidence_dir / f"l3-{slice_id}-c-oracle-status.json"),
                    "status": "draft_or_skipped",
                }
            ],
        },
        "rust_tests": [
            {
                "file": rel(path),
                "test_names": [test_name],
                "cargo_command": f"cargo test {test_name}",
                "framework": "cargo test",
                "file_hash": sha256(path),
            }
        ],
        "coverage": {
            "main_paths": list(behavior_fields),
            "error_paths": [],
            "negative_cases": ["negative diff must be generated before acceptance"],
        },
        "translation_mappings": [
            {
                "source": fixture_path_text,
                "rust_test": f"{rel(path)}::{test_name}",
                "behavior_fields": list(behavior_fields),
                "coverage_kind": "oracle_replay",
                "status": "mapped",
                "evidence": [
                    {
                        "path": rel(evidence_dir / f"l3-{slice_id}-c-oracle-status.json"),
                        "status": "not_semantic_pass",
                    }
                ],
            }
        ],
        "evidence_links": {
            "rust_draft": {
                "path": rel(evidence_dir / f"l3-{slice_id}-rust-draft.rs"),
                "status": generated_rust_draft_status(route_decision),
            },
            "c_oracle": {"path": rel(evidence_dir / f"l3-{slice_id}-c-oracle-status.json"), "status": "draft_or_skipped"},
        },
        "known_gaps": [
            "Generated replay test is a draft until accepted C oracle and Rust replay reports are produced."
        ],
        "cache_invalidation_keys": cache_keys(spec, evidence_dir / f"l3-{slice_id}-translator-input.json"),
    }
    write_json(evidence_dir / f"l3-{slice_id}-test-translation-generated.json", payload)
    return payload


def rust_replay_fixture_cases_source(spec: dict[str, Any], fixture_binding: dict[str, Any]) -> str:
    if behavior_fields(spec) != ["return_code"]:
        return "    // TODO: bind fixture cases to generated Rust API assertions.\n"

    function_name = safe_ident(required_str(spec, "function_name"))
    case_literals: list[str] = []
    unsupported_comments: list[str] = []
    for case_binding in fixture_binding.get("case_bindings", []):
        if not isinstance(case_binding, dict):
            continue
        case_literal = rust_replay_fixture_case_literal(spec, case_binding)
        if case_literal is None:
            case_id = str(case_binding.get("id") or "unknown-case")
            unsupported_comments.append(
                f"    // TODO: fixture case {case_id} is not supported by this replay draft generator.\n"
            )
            continue
        case_literals.append(case_literal)

    if not case_literals and not unsupported_comments:
        return "    // TODO: bind fixture cases to generated Rust API assertions.\n"

    expected_case_count = fixture_binding.get("case_count", len(case_literals))
    lines = [
        "    struct FixtureCase {\n",
        "        id: &'static str,\n",
        "        crc: u32,\n",
        "        buf: &'static [u8],\n",
        "        size: usize,\n",
        "        return_code: u32,\n",
        "    }\n",
        "\n",
        "    let fixture_cases: &[FixtureCase] = &[\n",
    ]
    lines.extend(case_literals)
    lines.extend(
        [
            "    ];\n",
            f"    assert_eq!(fixture_cases.len(), {expected_case_count}usize, \"fixture case count drifted\");\n",
            "    for case in fixture_cases {\n",
            '        assert_eq!(case.buf.len(), case.size, "{} fixture size must match byte buffer length", case.id);\n',
            f"        let actual = {function_name}(case.crc, case.buf, case.size);\n",
            '        assert_eq!(actual, case.return_code, "{} return_code drifted", case.id);\n',
            "    }\n",
        ]
    )
    lines.extend(unsupported_comments)
    return "".join(lines)


def rust_replay_fixture_case_literal(spec: dict[str, Any], case_binding: dict[str, Any]) -> str | None:
    case_payload = oracle_fixture_input_payload(spec, case_binding)
    if not isinstance(case_payload, dict):
        return None
    expected_outputs = case_binding.get("expected_outputs")
    if not isinstance(expected_outputs, dict):
        return None
    expected_return = expected_outputs.get("return_code")
    crc = case_payload.get("crc")
    buf = case_payload.get("buf")
    size = case_payload.get("size")
    if not is_uint32_value(expected_return) or not is_uint32_value(crc):
        return None
    if not is_size_value(size) or not is_byte_list(buf):
        return None
    if int(size) != len(buf):
        return None

    return (
        "        FixtureCase { "
        f"id: {rust_string_literal(case_binding.get('id') or 'case')}, "
        f"crc: {int(crc)}u32, "
        f"buf: {rust_byte_slice_literal(buf)}, "
        f"size: {int(size)}usize, "
        f"return_code: {int(expected_return)}u32 "
        "},\n"
    )


def rust_byte_slice_literal(values: list[int]) -> str:
    if not values:
        return "&[]"
    return "&[" + ", ".join(f"{item}u8" for item in values) + "]"


def rust_string_literal(value: Any) -> str:
    return json.dumps(str(value))


def run_generated_rust_replay(
    spec: dict[str, Any],
    evidence_dir: Path,
    replay: dict[str, Any],
    rust_check: dict[str, Any],
) -> dict[str, Any]:
    slice_id = required_str(spec, "slice_id")
    replay_path = evidence_dir / f"l3-{slice_id}-rust-replay-test-draft.rs"
    draft_path = evidence_dir / f"l3-{slice_id}-rust-draft.rs"
    if rust_check.get("status") != "passed":
        return replay
    if not generated_rust_replay_supported(spec, evidence_dir):
        return replay
    result = run_generated_rust_replay_once(draft_path, replay_path)
    write_log_text(evidence_dir / "generated-rust-replay-compile.stdout.log", result["compile_stdout"])
    write_log_text(evidence_dir / "generated-rust-replay-compile.stderr.jsonl", result["compile_stderr"])
    write_log_text(evidence_dir / "generated-rust-replay.stdout.log", result["run_stdout"])
    write_log_text(evidence_dir / "generated-rust-replay.stderr.log", result["run_stderr"])
    passed = result["status"] == "passed"
    replay["status"] = "passed" if passed else "failed"
    replay["generated_draft_replay_pass"] = passed
    replay["generated_draft_semantic_pass"] = False
    replay["replay_execution"] = {
        "status": result["status"],
        "phase": result["phase"],
        "compile_command": result["compile_command"],
        "compile_returncode": result["compile_returncode"],
        "run_command": result["run_command"],
        "run_returncode": result["run_returncode"],
        "stdout_log": rel(evidence_dir / "generated-rust-replay.stdout.log"),
        "stderr_log": rel(evidence_dir / "generated-rust-replay.stderr.log"),
    }
    replay["known_gaps"] = [
        "Generated Rust replay passed committed fixture cases; C oracle, schema diff, negative diff, unsafe, and final verification gates are still required."
    ]
    for mapping in replay.get("translation_mappings", []):
        if isinstance(mapping, dict):
            mapping["status"] = "passed" if passed else "failed"
    write_json(evidence_dir / f"l3-{slice_id}-test-translation-generated.json", replay)
    return replay


def generated_rust_replay_supported(spec: dict[str, Any], evidence_dir: Path) -> bool:
    if behavior_fields(spec) != ["return_code"]:
        return False
    slice_id = required_str(spec, "slice_id")
    plan_path = evidence_dir / f"l3-{slice_id}-auto-translation-plan.json"
    draft_path = evidence_dir / f"l3-{slice_id}-rust-draft.rs"
    replay_path = evidence_dir / f"l3-{slice_id}-rust-replay-test-draft.rs"
    if not plan_path.exists() or not draft_path.exists() or not replay_path.exists():
        return False
    plan = read_json(plan_path)
    rule_ids = plan.get("translation_summary", {}).get("translation_rule_ids", [])
    return "clang-lowered-typed-ir" in rule_ids


def run_generated_rust_replay_once(draft_path: Path, replay_path: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="c2r-generated-replay-") as build_dir_text:
        build_dir = Path(build_dir_text)
        combined_path = build_dir / "generated_replay.rs"
        exe_path = build_dir / "generated_replay.exe"
        combined_path.write_text(
            draft_path.read_text(encoding="utf-8-sig")
            + "\n"
            + replay_path.read_text(encoding="utf-8-sig"),
            encoding="utf-8",
        )
        compile_cmd = [
            "rustc",
            "--edition=2021",
            "--test",
            "--error-format=json",
            str(combined_path),
            "-o",
            str(exe_path),
        ]
        compile_result = subprocess.run(compile_cmd, cwd=REPO_ROOT, text=True, capture_output=True)
        if compile_result.returncode != 0:
            return {
                "status": "failed",
                "phase": "compile",
                "compile_command": shlex.join(compile_cmd),
                "compile_returncode": compile_result.returncode,
                "compile_stdout": compile_result.stdout,
                "compile_stderr": compile_result.stderr,
                "run_command": None,
                "run_returncode": None,
                "run_stdout": "",
                "run_stderr": "",
            }
        run_cmd = [str(exe_path), "--nocapture"]
        run_result = subprocess.run(run_cmd, cwd=REPO_ROOT, text=True, capture_output=True)
        return {
            "status": "passed" if run_result.returncode == 0 else "failed",
            "phase": "run",
            "compile_command": shlex.join(compile_cmd),
            "compile_returncode": compile_result.returncode,
            "compile_stdout": compile_result.stdout,
            "compile_stderr": compile_result.stderr,
            "run_command": shlex.join(run_cmd),
            "run_returncode": run_result.returncode,
            "run_stdout": run_result.stdout,
            "run_stderr": run_result.stderr,
        }


def generated_rust_report_cases(spec: dict[str, Any]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    fixture_binding = oracle_fixture_binding(spec)
    for case_binding in fixture_binding.get("case_bindings", []):
        if not isinstance(case_binding, dict):
            continue
        case_payload = oracle_fixture_input_payload(spec, case_binding)
        expected_outputs = case_binding.get("expected_outputs")
        if not isinstance(case_payload, dict) or not isinstance(expected_outputs, dict):
            continue
        case = {
            "id": case_binding.get("id"),
            "crc": case_payload.get("crc"),
            "buf": case_payload.get("buf"),
            "size": case_payload.get("size"),
            "return_code": expected_outputs.get("return_code"),
        }
        for optional_key in ["coverage_kind", "status"]:
            if optional_key in case_payload:
                case[optional_key] = case_payload[optional_key]
        cases.append(case)
    return cases


def run_rust_check(evidence_dir: Path, skip: bool, spec: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    path = next(evidence_dir.glob("l3-*-rust-draft.rs"), None)
    slice_id = required_str(spec, "slice_id")
    external_context = external_direct_callee_context(spec, load_plan_call_expressions(evidence_dir, slice_id))
    if skip or path is None:
        payload = {
            "schema_version": 1,
            "status": "skipped",
            "errors": [],
            "command": None,
            "external_callee_context": rust_check_external_context(external_context),
        }
        patch = write_no_patch_required(spec, evidence_dir, path)
    else:
        if external_context["status"] == "recorded":
            inject_external_callee_stubs(path, external_context)
        first = rust_check_once(path)
        write_log_text(evidence_dir / "rust-check-initial.stdout.log", first["stdout"])
        write_log_text(evidence_dir / "rust-check-initial.stderr.jsonl", first["stderr"])
        patch = write_no_patch_required(spec, evidence_dir, path)
        final = first
        if first["returncode"] != 0:
            patch = try_safe_self_heal(spec, evidence_dir, path, first)
            if patch.get("self_heal_applied"):
                final = rust_check_once(path)
        write_log_text(evidence_dir / "rust-check.stdout.log", final["stdout"])
        write_log_text(evidence_dir / "rust-check.stderr.jsonl", final["stderr"])
        payload = {
            "schema_version": 1,
            "status": "passed" if final["returncode"] == 0 else "failed",
            "command": final["command"],
            "error_count": len(final["errors"]),
            "errors": final["errors"],
            "external_callee_context": rust_check_external_context(external_context),
            "self_healing": {
                "status": patch["status"],
                "patch_events": patch["patch_events"],
                "blocked_repairs": patch["blocked_repairs"],
            },
        }
        if final["returncode"] != 0 and patch["status"] != "recorded":
            patch = write_blocked_patch(spec, evidence_dir, path, final["errors"])
    write_json(evidence_dir / "rust-check.json", payload)
    return payload, patch


def rust_check_once(path: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="c2r-rust-check-") as build_dir:
        cmd = [
            "rustc",
            "--edition=2021",
            "--crate-type=lib",
            "--error-format=json",
            "--out-dir",
            build_dir,
            str(path),
        ]
        result = subprocess.run(cmd, cwd=REPO_ROOT, text=True, capture_output=True)
    errors = [
        json.loads(line)
        for line in result.stderr.splitlines()
        if line.startswith("{") and '"level":"error"' in line.replace(" ", "")
    ]
    return {
        "command": " ".join(cmd),
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "errors": errors,
    }


RUST_KEYWORDS = {
    "as",
    "async",
    "await",
    "break",
    "const",
    "continue",
    "crate",
    "dyn",
    "else",
    "enum",
    "extern",
    "false",
    "fn",
    "for",
    "if",
    "impl",
    "in",
    "let",
    "loop",
    "match",
    "mod",
    "move",
    "mut",
    "pub",
    "ref",
    "return",
    "self",
    "Self",
    "static",
    "struct",
    "super",
    "trait",
    "true",
    "type",
    "unsafe",
    "use",
    "where",
    "while",
}


def try_safe_self_heal(
    spec: dict[str, Any],
    evidence_dir: Path,
    draft_path: Path,
    first: dict[str, Any],
) -> dict[str, Any]:
    text = draft_path.read_text(encoding="utf-8")
    params = set(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*:", text))
    keyword_params = sorted(params & RUST_KEYWORDS)
    if not keyword_params:
        return write_blocked_patch(spec, evidence_dir, draft_path, first["errors"])

    patched = text
    for name in keyword_params:
        patched = re.sub(rf"(?<!#)\b{re.escape(name)}\b", f"r#{name}", patched)
    if patched == text:
        return write_blocked_patch(spec, evidence_dir, draft_path, first["errors"])

    draft_path.write_text(patched, encoding="utf-8")
    slice_id = required_str(spec, "slice_id")
    events_path = evidence_dir / f"l3-{slice_id}-patch-events.jsonl"
    blocked_path = evidence_dir / f"l3-{slice_id}-self-healing-blocked-repairs.json"
    base_event = {
        "schema_version": 1,
        "patch_id": "patch-rust-keyword-identifiers-1",
        "target_id": spec.get("target_id"),
        "slice_id": slice_id,
        "round": 1,
        "files": [{"path": rel(draft_path), "spans": [{"line_start": 1, "line_end": max(1, len(text.splitlines()))}]}],
        "reason": "Rust keyword used as generated identifier; convert to raw identifier without changing C oracle or fixture semantics.",
        "expected_error_delta": {
            "before": [rustc_error_code(error) for error in first["errors"]],
            "after_expected": [],
        },
        "forbidden_changes": [
            "c_oracle_contract",
            "fixture_expected_behavior",
            "accepted_metadata_differences",
            "public_api_outside_impact_set",
            "source_slice_boundary",
            "unsafe_budget_policy",
        ],
        "rollback_id": f"rollback-{slice_id}-keyword-identifiers-1",
        "ai_usage": {"used": False},
        "verification_commands": ["rustc --edition=2021 --crate-type=lib --error-format=json <draft>"],
    }
    events = [
        {**base_event, "status": "applied"},
        {**base_event, "status": "verified"},
    ]
    write_text(events_path, "".join(json.dumps(event, sort_keys=True) + "\n" for event in events))
    blocked = blocked_repairs_payload(spec, [])
    write_json(blocked_path, blocked)
    return {
        "patch_events": rel(events_path),
        "blocked_repairs": rel(blocked_path),
        "blocked_repairs_status": blocked["status"],
        "blocked_repairs_items": blocked["blocked_repairs"],
        "status": "recorded",
        "self_heal_applied": True,
    }


def write_no_patch_required(spec: dict[str, Any], evidence_dir: Path, draft_path: Path | None) -> dict[str, Any]:
    slice_id = required_str(spec, "slice_id")
    events_path = evidence_dir / f"l3-{slice_id}-patch-events.jsonl"
    blocked_path = evidence_dir / f"l3-{slice_id}-self-healing-blocked-repairs.json"
    write_text(events_path, "")
    blocked = blocked_repairs_payload(spec, [])
    write_json(blocked_path, blocked)
    return {
        "patch_events": rel(events_path),
        "blocked_repairs": rel(blocked_path),
        "blocked_repairs_status": blocked["status"],
        "blocked_repairs_items": blocked["blocked_repairs"],
        "status": "none",
        "self_heal_applied": False,
    }


def write_route_refused_patch(
    spec: dict[str, Any],
    evidence_dir: Path,
    route_decision: dict[str, Any],
) -> dict[str, Any]:
    slice_id = required_str(spec, "slice_id")
    events_path = evidence_dir / f"l3-{slice_id}-patch-events.jsonl"
    blocked_path = evidence_dir / f"l3-{slice_id}-self-healing-blocked-repairs.json"
    draft_path = next(evidence_dir.glob("l3-*-rust-draft.rs"), None)
    reason = "Route decision refused candidate generation for unsupported C semantics."
    event = {
        "schema_version": 1,
        "patch_id": "patch-route-refused-1",
        "target_id": spec.get("target_id"),
        "slice_id": slice_id,
        "round": 1,
        "status": "blocked",
        "files": [{"path": rel(draft_path) if draft_path else "", "spans": [{"line_start": 1, "line_end": 1}]}],
        "reason": reason,
        "expected_error_delta": {"before": [], "after_expected": []},
        "forbidden_changes": [
            "c_oracle_contract",
            "fixture_expected_behavior",
            "accepted_metadata_differences",
            "public_api_outside_impact_set",
            "source_slice_boundary",
            "unsafe_budget_policy",
        ],
        "rollback_id": f"rollback-{slice_id}-route-refused-1",
        "ai_usage": {"used": False},
        "verification_commands": ["route-decision validation"],
    }
    write_text(events_path, json.dumps(event, sort_keys=True) + "\n")
    blocked = blocked_repairs_payload(
        spec,
        [
            {
                "repair_id": "repair-route-refused-1",
                "blocked_reason": reason,
                "forbidden_change": "unsupported_control_flow",
                "candidate_patch_id": event["patch_id"],
                "source_span": {"file": rel(draft_path) if draft_path else "", "line_start": 1, "line_end": 1},
                "human_action_required": True,
                "route_decision": route_decision.get("level"),
                **route_refused_repair_playbook(spec, evidence_dir, route_decision),
            }
        ],
    )
    write_json(blocked_path, blocked)
    return {
        "patch_events": rel(events_path),
        "blocked_repairs": rel(blocked_path),
        "blocked_repairs_status": blocked["status"],
        "blocked_repairs_items": blocked["blocked_repairs"],
        "status": "blocked",
        "self_heal_applied": False,
    }


def write_blocked_patch(
    spec: dict[str, Any],
    evidence_dir: Path,
    draft_path: Path | None,
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    slice_id = required_str(spec, "slice_id")
    events_path = evidence_dir / f"l3-{slice_id}-patch-events.jsonl"
    blocked_path = evidence_dir / f"l3-{slice_id}-self-healing-blocked-repairs.json"
    event = {
        "schema_version": 1,
        "patch_id": "patch-blocked-1",
        "target_id": spec.get("target_id"),
        "slice_id": slice_id,
        "round": 1,
        "status": "blocked",
        "files": [{"path": rel(draft_path) if draft_path else "", "spans": [{"line_start": 1, "line_end": 1}]}],
        "reason": "No safe local compile self-healing rule matched this rustc error stack.",
        "expected_error_delta": {
            "before": [rustc_error_code(error) for error in errors],
            "after_expected": [],
        },
        "forbidden_changes": [
            "c_oracle_contract",
            "fixture_expected_behavior",
            "accepted_metadata_differences",
            "public_api_outside_impact_set",
            "source_slice_boundary",
            "unsafe_budget_policy",
        ],
        "rollback_id": f"rollback-{slice_id}-blocked-1",
        "ai_usage": {"used": False},
        "verification_commands": ["rustc --edition=2021 --crate-type=lib --error-format=json <draft>"],
    }
    write_text(events_path, json.dumps(event, sort_keys=True) + "\n")
    blocked = blocked_repairs_payload(
        spec,
        [
            {
                "repair_id": "repair-blocked-1",
                "blocked_reason": event["reason"],
                "forbidden_change": "type_uncertainty",
                "candidate_patch_id": event["patch_id"],
                "source_span": {"file": rel(draft_path) if draft_path else "", "line_start": 1, "line_end": 1},
                "human_action_required": True,
                **compile_blocked_repair_playbook(spec, draft_path, errors),
            }
        ],
    )
    write_json(blocked_path, blocked)
    return {
        "patch_events": rel(events_path),
        "blocked_repairs": rel(blocked_path),
        "blocked_repairs_status": blocked["status"],
        "blocked_repairs_items": blocked["blocked_repairs"],
        "status": "blocked",
        "self_heal_applied": False,
    }


def route_refused_repair_playbook(
    spec: dict[str, Any],
    evidence_dir: Path,
    route_decision: dict[str, Any],
) -> dict[str, Any]:
    gap = route_refused_ir_feature_gap(spec, evidence_dir, route_decision)
    smallest_next_test = {
        "kind": "route_refusal_regression",
        "command": (
            "python -B -m unittest "
            "validation.tools.test_auto_migrate.AutoMigrateTests."
            "test_unsupported_lvalue_blocks_auto_migrate_candidate_generation"
        ),
        "expected_gate": "self-healing-blocked-repairs records repair playbook fields",
    }
    if gap["kind"] == "external_direct_callee_context":
        smallest_next_test = {
            "kind": "external_callee_context_regression",
            "command": (
                "python -B -m unittest "
                "validation.tools.test_auto_migrate.AutoMigrateTests."
                "test_real_fdb_kv_set_records_fail_closed_callee_provenance_without_semantic_claim"
            ),
            "expected_gate": "external direct callees are declared, stubbed, or kept blocked before candidate acceptance",
        }
    return {
        "ir_feature_gap": gap,
        "oracle_fixture_gap": {
            "status": "not_blocking",
            "reason": "The route refused candidate generation before semantic acceptance; oracle evidence still gates any later candidate.",
        },
        "candidate_routes": repair_candidate_routes(gap["kind"]),
        "smallest_next_test": smallest_next_test,
        "human_intervention_point": (
            "Add the missing typed-IR lowering/emitter support or provide an explicit slice contract, "
            "then rerun auto_migrate before promoting any candidate."
        ),
    }


def route_refused_ir_feature_gap(
    spec: dict[str, Any],
    evidence_dir: Path,
    route_decision: dict[str, Any],
) -> dict[str, Any]:
    slice_id = required_str(spec, "slice_id")
    prefix = f"l3-{slice_id}"
    plan_path = evidence_dir / f"{prefix}-auto-translation-plan.json"
    cfg_path = evidence_dir / f"{prefix}-cfg.json"
    plan = read_json(plan_path) if plan_path.exists() else {}
    cfg = read_json(cfg_path) if cfg_path.exists() else {}
    summary = plan.get("translation_summary", {})
    if isinstance(summary, dict) and int(summary.get("unsupported_lvalue_count", 0) or 0) > 0:
        return {
            "kind": "unsupported_lvalue",
            "source": "auto_translation_plan.translation_summary.unsupported_lvalue_count",
            "evidence_refs": [rel(plan_path), rel(cfg_path)],
        }
    if cfg.get("unsupported_control_flow"):
        return {
            "kind": "unsupported_control_flow",
            "source": "cfg.unsupported_control_flow",
            "evidence_refs": [rel(cfg_path)],
        }
    external_blocks = summary.get("external_direct_callee_blocks")
    if isinstance(external_blocks, list) and external_blocks:
        return {
            "kind": "external_direct_callee_context",
            "source": "auto_translation_plan.translation_summary.external_direct_callee_blocks",
            "blocked_callees": [
                str(item.get("name"))
                for item in external_blocks
                if isinstance(item, dict) and item.get("name")
            ],
            "evidence_refs": [rel(plan_path), rel(evidence_dir / f"{prefix}-context-pack.json")],
        }
    rationale = route_decision.get("rationale", [])
    feature = "route_refused"
    if isinstance(rationale, list) and rationale and isinstance(rationale[0], dict):
        feature = str(rationale[0].get("feature", feature))
    return {
        "kind": feature,
        "source": "route_decision.rationale",
        "evidence_refs": [rel(evidence_dir / f"{prefix}-route-decision.json")],
    }


def emit_capability_delta_ledger(
    spec: dict[str, Any],
    evidence_dir: Path,
    route_decision: dict[str, Any],
    validation_profile: dict[str, Any],
) -> dict[str, Any]:
    slice_id = required_str(spec, "slice_id")
    target_id = required_str(spec, "target_id")
    prefix = f"l3-{slice_id}"
    route_ref = rel(evidence_dir / f"{prefix}-route-decision.json")
    profile_ref = rel(evidence_dir / f"{prefix}-validation-profile.json")
    gap = route_refused_ir_feature_gap(spec, evidence_dir, route_decision)
    construct_id = str(gap.get("kind", "route_status"))
    evidence_refs = list(dict.fromkeys([*gap.get("evidence_refs", []), route_ref, profile_ref]))
    repair = route_refused_repair_summary(evidence_dir, slice_id)
    verification_commands = []
    if repair.get("smallest_next_test", {}).get("command"):
        verification_commands.append(str(repair["smallest_next_test"]["command"]))
    if not verification_commands:
        verification_commands.append("python -B validation/tools/validate_auto_translation_evidence.py")
    generated_status = "refused" if route_refuses_candidate_generation(route_decision) else generated_rust_draft_status(route_decision)
    semantic_pass = bool(validation_profile.get("generated_draft_semantic_pass") is True)
    payload = {
        "schema_version": 1,
        "target_id": target_id,
        "slice_id": slice_id,
        "status": "recorded",
        "route_level": route_decision.get("level"),
        "route_status": route_decision.get("status"),
        "capability_delta": [
            {
                "delta_id": f"cap-{slice_id}-{construct_id}",
                "kind": "refusal_classification" if generated_status == "refused" else "candidate_status",
                "construct_id": construct_id,
                "real_c_slice": slice_id,
                "generated_candidate_status": generated_status,
                "semantic_pass": semantic_pass,
                "blocked_callees": gap.get("blocked_callees", []),
                "evidence_refs": evidence_refs,
                "negative_coverage": [
                    {
                        "kind": repair.get("smallest_next_test", {}).get("kind", "validation_regression"),
                        "command": command,
                    }
                    for command in verification_commands
                ],
            }
        ],
        "governance_delta": [
            {
                "delta_id": f"gov-{slice_id}-{construct_id}-evidence",
                "kind": "evidence_contract",
                "construct_id": construct_id,
                "evidence_refs": evidence_refs,
                "bound_to": "P0 capability delta; governance changes only record evidence/repair provenance for this construct.",
            }
        ],
        "verification_commands": verification_commands,
        "boundary": "This ledger records P0 capability/refusal deltas only; it does not accept generated Rust semantics.",
    }
    write_json(evidence_dir / f"{prefix}-capability-delta.json", payload)
    return payload


def route_refused_repair_summary(evidence_dir: Path, slice_id: str) -> dict[str, Any]:
    path = evidence_dir / f"l3-{slice_id}-self-healing-blocked-repairs.json"
    if not path.exists():
        return {}
    repairs = read_json(path).get("blocked_repairs", [])
    if not repairs or not isinstance(repairs[0], dict):
        return {}
    return repairs[0]


def compile_blocked_repair_playbook(
    spec: dict[str, Any],
    draft_path: Path | None,
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "ir_feature_gap": {
            "kind": "rust_compile_failure",
            "source": "rustc_diagnostics",
            "error_codes": [rustc_error_code(error) for error in errors],
            "evidence_refs": [rel(draft_path)] if draft_path else [],
        },
        "oracle_fixture_gap": {
            "status": "unknown_until_compile_passes",
            "reason": "The generated Rust draft must compile before C/Rust behavior can be compared.",
        },
        "candidate_routes": repair_candidate_routes("rust_compile_failure"),
        "smallest_next_test": {
            "kind": "rust_compile_replay",
            "command": "rustc --edition=2021 --crate-type=lib --error-format=json <draft>",
            "expected_gate": "compile diagnostics either self-heal or remain blocked with playbook fields",
        },
        "human_intervention_point": (
            "Repair the typed-IR emitter output without changing the C oracle, fixture expected behavior, "
            "source slice boundary, or unsafe policy."
        ),
    }


def repair_candidate_routes(gap_kind: str) -> list[dict[str, Any]]:
    typed_ir_action = "extend_typed_ir_lowering_or_emitter"
    if gap_kind == "rust_compile_failure":
        typed_ir_action = "repair_typed_ir_emitted_rust"
    return [
        {
            "route": "typed_ir",
            "status": "blocked",
            "next_action": typed_ir_action,
        },
        {
            "route": "c2rust",
            "status": "candidate_context_only",
            "next_action": "generate_or_attach_baseline_output_then_run_common_validation",
        },
        {
            "route": "llm",
            "status": "candidate_only",
            "next_action": "generate_candidate_from_bound_inputs_then_run_common_validation",
        },
        {
            "route": "manual",
            "status": "allowed_with_review",
            "next_action": "write_reviewed_candidate_and_bind_it_to_oracle_diff_gates",
        },
    ]


def emit_cache_metadata(
    spec: dict[str, Any],
    slice_spec: Path,
    evidence_dir: Path,
    c2rust_baseline: dict[str, Any] | None = None,
    route_decision: dict[str, Any] | None = None,
    validation_profile: dict[str, Any] | None = None,
    oracle: dict[str, Any] | None = None,
    accept_existing_evidence: bool = False,
    emit_clang_dry_run: bool = False,
    emit_clang_lowering_report: bool = False,
    competition_clang_lane: bool = False,
) -> dict[str, Any]:
    effective_emit_clang_lowering_report = emit_clang_lowering_report or competition_clang_lane
    identity = cache_identity(
        spec,
        slice_spec,
        accept_existing_evidence=accept_existing_evidence,
        emit_clang_dry_run=emit_clang_dry_run,
        emit_clang_lowering_report=effective_emit_clang_lowering_report,
        competition_clang_lane=competition_clang_lane,
        c2rust_baseline=c2rust_baseline,
        route_decision=route_decision,
        validation_profile=validation_profile,
        oracle=oracle,
    )
    dependent_artifacts = {
        "c2rust_baseline": c2rust_baseline_ref(spec, evidence_dir, c2rust_baseline),
        "route_decision": route_decision_ref(spec, evidence_dir, route_decision),
        "validation_profile": validation_profile_ref(spec, evidence_dir, validation_profile),
    }
    payload = {
        "schema_version": 1,
        "target_id": spec.get("target_id"),
        "slice_id": spec.get("slice_id"),
        **identity,
        "dependent_artifacts": dependent_artifacts,
        "cache_input_fields": cache_input_fields(
            emit_clang_lowering_report=effective_emit_clang_lowering_report
        ),
        "invalidates": CACHE_INVALIDATED_ARTIFACTS,
    }
    write_json(evidence_dir / f"l3-{spec.get('slice_id')}-auto-cache-metadata.json", payload)
    return payload


def cache_input_fields(*, emit_clang_lowering_report: bool = False) -> list[str]:
    fields = list(CACHE_INPUT_FIELDS)
    if emit_clang_lowering_report:
        fields.extend(CLANG_LOWERING_CACHE_INPUT_FIELDS)
    return fields


def artifact_cache_identity(artifact: dict[str, Any] | None) -> dict[str, Any]:
    if artifact is None:
        return {"status": "missing", "sha256": "missing"}
    return {
        "status": artifact.get("status", "unknown"),
        "sha256": sha256_json(artifact),
    }


def oracle_boundary_contract_identity(validation_profile: dict[str, Any] | None) -> dict[str, Any]:
    if validation_profile is None:
        return {"status": "missing", "sha256": "missing"}
    contract = validation_profile.get("oracle_boundary_contract")
    if not isinstance(contract, dict):
        return {"status": "missing", "sha256": "missing"}
    return {
        "status": contract.get("status", "unknown"),
        "sha256": sha256_json(contract),
    }


def oracle_harness_identity(oracle: dict[str, Any] | None) -> dict[str, Any]:
    if oracle is None:
        return {"path": "missing", "status": "missing", "sha256": "missing"}
    ref = oracle.get("harness_draft_ref")
    if isinstance(ref, dict):
        return {
            "path": ref.get("path", "missing"),
            "status": ref.get("status", "missing"),
            "sha256": ref.get("sha256", "missing"),
        }
    return {"path": oracle.get("harness_draft", "missing"), "status": "missing", "sha256": "missing"}


def emit_c2rust_baseline_manifest(spec: dict[str, Any], slice_spec: Path, evidence_dir: Path) -> dict[str, Any]:
    slice_id = required_str(spec, "slice_id")
    prefix = f"l3-{slice_id}"
    commands = c2rust_command_candidates()
    selected = next((item for item in commands if item.get("path")), None)
    reference_tree, reference_tree_configured = resolve_c2rust_reference_tree()
    reference_status = "present" if reference_tree.exists() else "missing"
    status = "skipped"
    diagnostics: list[str] = []
    reason = "blocked_by_missing_tools"
    if selected is None:
        diagnostics.append("no executable c2rust-transpile or c2rust command found on PATH")
    else:
        status = "blocked"
        reason = "baseline_generation_not_enabled"
        diagnostics.append("executable C2Rust was detected but baseline generation is not enabled in this bounded MVP")
    manifest = {
        "schema_version": 1,
        "target_id": spec.get("target_id"),
        "slice_id": slice_id,
        "status": status,
        "reason": reason,
        "correctness_role": "candidate_context_only",
        "fallback_oracle": "original_c_oracle_required",
        "validation_impact": "baseline_unavailable_does_not_accept_or_reject_candidate; selected validation profile still owns acceptance",
        "source_commit": source_commit(spec),
        "slice_spec": {"path": rel(slice_spec), "sha256": sha256(slice_spec)},
        "build_profile_hash": sha256_json(spec.get("build_profile", {})),
        "commands": commands,
        "selected_command": selected,
        "reference_tree": {
            "path": rel(reference_tree),
            "status": reference_status,
            "cargo_toml": rel(reference_tree / "Cargo.toml") if reference_tree.exists() else "",
            "diagnostic_only": not reference_tree_configured,
        },
        "output": None,
        "diagnostics": diagnostics,
        "must_not_claim": [
            "C2Rust output proves semantic equivalence",
            "C2Rust baseline was generated" if status != "generated" else "",
        ],
        "tool_probe": c2rust_tool_probe(),
    }
    manifest["must_not_claim"] = [item for item in manifest["must_not_claim"] if item]
    write_json(evidence_dir / f"{prefix}-c2rust-baseline-manifest.json", manifest)
    return manifest


def c2rust_command_candidates() -> list[dict[str, Any]]:
    names = ["c2rust-transpile", "c2rust"]
    candidates = []
    for name in names:
        path = shutil.which(name)
        version = c2rust_command_version(path) if path else {"version_status": "NOT_FOUND", "version": ""}
        candidates.append({"name": name, "path": path or "", "available": bool(path), **version})
    return candidates


def c2rust_command_version(path: str | None) -> dict[str, str]:
    if not path:
        return {"version_status": "NOT_FOUND", "version": ""}
    try:
        result = subprocess.run(
            [path, "--version"],
            text=True,
            capture_output=True,
            timeout=5,
        )
    except Exception as exc:
        return {"version_status": "ERROR", "version": "", "version_error": str(exc)}
    version = (result.stdout or result.stderr).strip()
    return {
        "version_status": "OK" if result.returncode == 0 and version else "UNKNOWN",
        "version": version,
    }


def resolve_c2rust_reference_tree() -> tuple[Path, bool]:
    configured = os.environ.get("C2RUST_REFERENCE_TREE", "").strip()
    if configured:
        path = Path(configured)
        if not path.is_absolute():
            path = REPO_ROOT / path
        return path, True
    return REPO_ROOT / "tools" / "c2rust-reference", False


def c2rust_tool_probe() -> dict[str, Any]:
    return {
        "os_name": os.name,
        "path_search": ["c2rust-transpile", "c2rust"],
        "probed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "diagnostic_only": True,
        "environment_profile_hash": sha256(COMPETITION_ENVIRONMENT_PROFILE)
        if COMPETITION_ENVIRONMENT_PROFILE.exists()
        else "missing",
        "competition_environment_identity": competition_environment_identity()
        if COMPETITION_ENVIRONMENT_PROFILE.exists()
        else {"status": "missing"},
    }


def emit_route_decision(
    spec: dict[str, Any],
    evidence_dir: Path,
    translator_summary: dict[str, Any],
    c2rust_baseline: dict[str, Any],
) -> dict[str, Any]:
    """Emit the route/profile decision and candidate provenance bundle.

    The route chooses which verification profile must later pass; it does not
    accept a generated draft. The candidate set records primary, typed-IR, and
    C2Rust-baseline inputs with semantic flags pinned false so downstream
    validators can reject candidate evidence that tries to act like accepted
    evidence.
    """
    slice_id = required_str(spec, "slice_id")
    prefix = f"l3-{slice_id}"
    type_map = read_json(evidence_dir / f"{prefix}-type-map.json")
    cfg = read_json(evidence_dir / f"{prefix}-cfg.json")
    pointer = read_json(evidence_dir / f"{prefix}-pointer-graph.json")
    plan = read_json(evidence_dir / f"{prefix}-auto-translation-plan.json")
    c2rust_baseline_artifact = c2rust_baseline_ref(spec, evidence_dir, c2rust_baseline)
    candidate_generation = candidate_generation_evidence(
        spec,
        evidence_dir,
        c2rust_baseline,
        baseline_manifest_ref=c2rust_baseline_artifact,
    )
    level, rationale = route_level(spec, translator_summary, type_map, cfg, pointer, plan, candidate_generation)
    translator = route_translator(level)
    profile = validation_profile_name(level, "dev")
    source_artifacts = {
        "type_map": evidence_ref(evidence_dir / f"{prefix}-type-map.json", type_map.get("status", "recorded")),
        "cfg": evidence_ref(evidence_dir / f"{prefix}-cfg.json", cfg.get("status", "recorded")),
        "pointer_graph": evidence_ref(evidence_dir / f"{prefix}-pointer-graph.json", pointer.get("status", "recorded")),
        "c2rust_baseline": c2rust_baseline_artifact,
    }
    typed_ir_source_artifact = candidate_generation.get("typed_ir", {}).get("source_artifact")
    if isinstance(typed_ir_source_artifact, dict) and typed_ir_source_artifact.get("status") != "missing":
        source_artifacts["clang_lowering_report"] = typed_ir_source_artifact
    translation_plan_ref = evidence_ref(
        evidence_dir / f"{prefix}-auto-translation-plan.json",
        plan.get("status", "recorded"),
    )
    # The plan is later bound back to this route decision, so its content hash is not stable here.
    translation_plan_ref.pop("sha256", None)
    source_artifacts["translation_plan"] = translation_plan_ref
    decision = {
        "schema_version": 1,
        "target_id": spec.get("target_id"),
        "slice_id": slice_id,
        "status": "refused" if level == "L4" else "recorded",
        "level": level,
        "translator": translator,
        "rationale": rationale,
        "verification_profile": profile,
        "source_artifacts": source_artifacts,
        "candidate_generation": candidate_generation,
        "scalar_ub_contract": scalar_ub_contract(spec),
        "policy": {
            "goal": "dev",
            "fixed_loop_count_required": False,
            "repair_budget_source": "run_policy",
        },
        "misroute": None,
    }
    write_json(evidence_dir / f"{prefix}-route-decision.json", decision)
    return decision


def candidate_generation_evidence(
    spec: dict[str, Any],
    evidence_dir: Path,
    c2rust_baseline: dict[str, Any] | None = None,
    *,
    baseline_manifest_ref: dict[str, Any] | None = None,
) -> dict[str, Any]:
    slice_id = required_str(spec, "slice_id")
    prefix = f"l3-{slice_id}"
    if baseline_manifest_ref is None:
        baseline_manifest_ref = c2rust_baseline_ref(spec, evidence_dir, c2rust_baseline)
    report_path = evidence_dir / f"{prefix}-clang-lowering-report.json"
    plan_path = evidence_dir / f"{prefix}-auto-translation-plan.json"
    plan = read_json(plan_path) if plan_path.exists() else {}
    primary_candidate = primary_candidate_binding(plan)
    compatibility_sources = compatibility_source_bindings(plan)
    typed_ir_candidate = typed_ir_candidate_binding(report_path)
    typed_ir_candidate["scalar_admission"] = scalar_admission_from_runtime_preconditions(
        spec,
        typed_ir_candidate.get("runtime_preconditions", []),
    )
    c2rust_candidate = c2rust_baseline_candidate_binding(
        c2rust_baseline,
        baseline_manifest_ref=baseline_manifest_ref,
    )
    return {
        "selection_policy": candidate_selection_policy(),
        "selected_candidate_id": selected_candidate_id(primary_candidate),
        "candidate_set": candidate_set_binding(
            primary_candidate,
            compatibility_sources,
            typed_ir_candidate,
            c2rust_candidate,
        ),
        "compatibility_sources": compatibility_sources,
        "primary_candidate": primary_candidate,
        "typed_ir": typed_ir_candidate,
        "c2rust_baseline": c2rust_candidate,
        "generated_draft_semantic_pass": False,
    }


def primary_candidate_binding(plan: dict[str, Any]) -> dict[str, Any]:
    source = translation_source_from_plan(plan)
    if source["selected"] == "legacy-string-translator":
        return {
            "candidate_id": "primary:unknown",
            "selected": "unknown",
            "fallback": False,
            "semantic_pass": False,
        }
    candidate_prefix = "primary"
    binding: dict[str, Any] = {
        "candidate_id": f"{candidate_prefix}:{source['selected']}",
        "selected": source["selected"],
        "fallback": bool(source.get("fallback_from")),
        "semantic_pass": False,
    }
    if source.get("fallback_from"):
        binding["fallback_from"] = source["fallback_from"]
    if source.get("fallback_reason"):
        binding["fallback_reason"] = source["fallback_reason"]
    return binding


def compatibility_source_bindings(plan: dict[str, Any]) -> list[dict[str, Any]]:
    source = translation_source_from_plan(plan)
    if source["selected"] != "legacy-string-translator":
        return []
    binding: dict[str, Any] = {
        "candidate_id": "compat:legacy-string-translator",
        "selected": "legacy-string-translator",
        "fallback": bool(source.get("fallback_from")),
        "semantic_pass": False,
        "compatibility_only": True,
        "correctness_role": "compatibility_only",
    }
    if source.get("fallback_from"):
        binding["fallback_from"] = source["fallback_from"]
    if source.get("fallback_reason"):
        binding["fallback_reason"] = source["fallback_reason"]
    return [binding]


def candidate_selection_policy() -> dict[str, Any]:
    return {
        "stage": "post_generation_provenance",
        "selection_basis": "translator_artifact_primary_candidate",
        "semantic_acceptance": False,
        "full_router": False,
    }


def selected_candidate_id(primary_candidate: dict[str, Any]) -> str | None:
    if primary_candidate.get("selected") == "unknown":
        return None
    if primary_candidate.get("compatibility_only") is True:
        return None
    return str(primary_candidate.get("candidate_id"))


def candidate_set_binding(
    primary_candidate: dict[str, Any],
    compatibility_sources: list[dict[str, Any]],
    typed_ir_candidate: dict[str, Any],
    c2rust_candidate: dict[str, Any],
) -> list[dict[str, Any]]:
    selected = str(primary_candidate.get("selected", "unknown"))
    primary_status = "missing" if selected == "unknown" else "generated"
    primary = {
        "candidate_id": primary_candidate.get("candidate_id", "primary:unknown"),
        "kind": selected,
        "status": primary_status,
        "role": "compatibility_rust_draft"
        if primary_candidate.get("compatibility_only") is True
        else "primary_rust_draft",
        "semantic_pass": False,
    }
    if primary_candidate.get("compatibility_only") is True:
        primary["compatibility_only"] = True
        primary["correctness_role"] = "compatibility_only"
    if primary_candidate.get("fallback"):
        primary["fallback"] = True
    if primary_candidate.get("fallback_from"):
        primary["fallback_from"] = primary_candidate["fallback_from"]
    if primary_candidate.get("fallback_reason"):
        primary["fallback_reason"] = primary_candidate["fallback_reason"]
    candidates = []
    if selected != "unknown":
        candidates.append(primary)
    candidates.extend(compatibility_candidate_set_items(compatibility_sources))
    candidates.extend(
        [
            {
            "candidate_id": "typed-ir:clang-lowered",
            "kind": "typed-ir",
            "status": typed_ir_candidate.get("status", "missing"),
            "role": "typed_ir_candidate_signal",
            "rust_draft_generated": bool(typed_ir_candidate.get("rust_draft_generated", False)),
            "semantic_pass": False,
        },
            c2rust_candidate,
        ]
    )
    return candidates


def compatibility_candidate_set_items(compatibility_sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    for source in compatibility_sources:
        selected = str(source.get("selected", "unknown"))
        item = {
            "candidate_id": source.get("candidate_id", f"compat:{selected}"),
            "kind": selected,
            "status": "generated" if selected != "unknown" else "missing",
            "role": "compatibility_rust_draft",
            "semantic_pass": False,
            "compatibility_only": True,
            "correctness_role": "compatibility_only",
        }
        if source.get("fallback"):
            item["fallback"] = True
        if source.get("fallback_from"):
            item["fallback_from"] = source["fallback_from"]
        if source.get("fallback_reason"):
            item["fallback_reason"] = source["fallback_reason"]
        items.append(item)
    return items


def c2rust_baseline_candidate_binding(
    c2rust_baseline: dict[str, Any] | None,
    *,
    baseline_manifest_ref: dict[str, Any] | None = None,
) -> dict[str, Any]:
    baseline = c2rust_baseline or {}
    status = str(baseline.get("status", "missing"))
    binding = {
        "candidate_id": "c2rust-baseline",
        "kind": "c2rust-baseline",
        "status": status,
        "role": "baseline_or_repair_candidate_context",
        "correctness_role": str(baseline.get("correctness_role", "candidate_context_only")),
        "reason": str(baseline.get("reason", "missing")),
        "output_ref": c2rust_baseline_output_ref(baseline, status),
        "generated_draft_semantic_pass": False,
        "semantic_pass": False,
    }
    if baseline_manifest_ref is not None:
        binding["baseline_manifest"] = baseline_manifest_ref
    return binding


def c2rust_baseline_output_ref(baseline: dict[str, Any], status: str) -> dict[str, Any] | None:
    output = baseline.get("output")
    if not isinstance(output, dict):
        return None
    path = output.get("path")
    output_sha = output.get("sha256")
    if not path or not output_sha:
        return None
    return {
        "path": str(path),
        "status": status,
        "sha256": str(output_sha),
    }


def translation_source_from_plan(plan: dict[str, Any]) -> dict[str, Any]:
    source = plan.get("translation_source")
    if not isinstance(source, dict):
        return {"selected": "unknown"}
    selected = str(source.get("selected") or "unknown")
    normalized = {"selected": selected}
    fallback_from = source.get("fallback_from")
    fallback_reason = source.get("fallback_reason")
    if fallback_from:
        normalized["fallback_from"] = str(fallback_from)
    if fallback_reason:
        normalized["fallback_reason"] = str(fallback_reason)
    return normalized


def typed_ir_candidate_binding(report_path: Path) -> dict[str, Any]:
    source_artifact = evidence_ref(report_path, "missing")
    if not report_path.exists():
        return {
            "status": "missing",
            "source_artifact": source_artifact,
            "candidate_route": None,
            "readonly_globals": [],
            "readonly_globals_identity": readonly_globals_identity([]),
            "runtime_preconditions": [],
            "rust_draft_generated": False,
            "semantic_pass": False,
        }

    report = read_json(report_path)
    candidate = report.get("typed_ir_candidate")
    if not isinstance(candidate, dict):
        return {
            "status": "missing",
            "source_artifact": evidence_ref(report_path, str(report.get("status", "recorded"))),
            "candidate_route": None,
            "readonly_globals": [],
            "readonly_globals_identity": readonly_globals_identity([]),
            "runtime_preconditions": [],
            "rust_draft_generated": False,
            "semantic_pass": False,
            "reason": "typed_ir_candidate_missing",
        }

    readonly_globals = candidate.get("readonly_globals", [])
    if not isinstance(readonly_globals, list):
        readonly_globals = []
    runtime_preconditions = candidate.get("runtime_preconditions", [])
    if not isinstance(runtime_preconditions, list):
        runtime_preconditions = []
    binding = {
        "status": str(candidate.get("status", "unknown")),
        "source_artifact": evidence_ref(report_path, str(report.get("status", "recorded"))),
        "candidate_route": candidate.get("candidate_route"),
        "readonly_globals": readonly_globals,
        "readonly_globals_identity": readonly_globals_identity(readonly_globals),
        "runtime_preconditions": runtime_preconditions,
        "rust_draft_generated": bool(candidate.get("rust_draft_generated", False)),
        "semantic_pass": False,
    }
    if candidate.get("reason"):
        binding["reason"] = str(candidate["reason"])
    if candidate.get("unsupported_reason"):
        binding["unsupported_reason"] = str(candidate["unsupported_reason"])
    if candidate.get("typed_ir_sha256"):
        binding["typed_ir_sha256"] = str(candidate["typed_ir_sha256"])
    if candidate.get("rust_draft_sha256"):
        binding["rust_draft_sha256"] = str(candidate["rust_draft_sha256"])
    return binding


def readonly_globals_identity(readonly_globals: list[Any]) -> dict[str, Any]:
    names = [
        str(item.get("name", ""))
        for item in readonly_globals
        if isinstance(item, dict) and item.get("name")
    ]
    return {
        "count": len(readonly_globals),
        "names": names,
        "sha256": sha256_json(readonly_globals),
    }


def route_level(
    spec: dict[str, Any],
    translator_summary: dict[str, Any],
    type_map: dict[str, Any],
    cfg: dict[str, Any],
    pointer: dict[str, Any],
    plan: dict[str, Any],
    candidate_generation: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Classify the slice route from fail-closed artifact and alias risk.

    Typed-IR candidate signals may select a cheaper route for generated drafts,
    but they never override blocked artifacts, unsupported control flow, alias
    floors, or the later requirement that a validation profile produce the
    semantic-pass claim.
    """
    rationale: list[dict[str, Any]] = []
    blocked_statuses = {
        "translator": translator_summary.get("status"),
        "type_map": type_map.get("status"),
        "cfg": cfg.get("status"),
        "plan": plan.get("status"),
    }
    if cfg.get("unsupported_control_flow"):
        rationale.append({"feature": "unsupported_control_flow", "weight": "hard_refuse"})
        return "L4", rationale
    if any(value == "blocked" for value in blocked_statuses.values()):
        rationale.append({"feature": "blocked_artifact", "values": blocked_statuses, "weight": "hard_refuse"})
        return "L4", rationale
    pointer_nodes = pointer.get("pointer_nodes", [])
    typed_ir_signal = typed_ir_candidate_route_signal(candidate_generation or {}, scalar_only=not pointer_nodes)
    alias_floor = alias_route_floor(pointer)
    if alias_floor is not None:
        level, alias_rationale = alias_floor
        rationale.append(alias_rationale)
        if typed_ir_signal is not None:
            rationale.append(typed_ir_signal[1])
        return level, rationale
    if any(node.get("ownership_role") == "unknown" for node in pointer_nodes):
        rationale.append({"feature": "unknown_pointer_role", "weight": "medium"})
        if typed_ir_signal is not None:
            rationale.append(typed_ir_signal[1])
        return "L2", rationale
    if typed_ir_signal is not None:
        level, typed_ir_rationale = typed_ir_signal
        rationale.append(typed_ir_rationale)
        return level, rationale
    if not pointer_nodes:
        rationale.append({"feature": "scalar_only", "weight": "low"})
        return "L0", rationale
    rationale.append({"feature": "bounded_pointer_surface", "weight": "low"})
    return "L1", rationale


def alias_route_floor(pointer: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    alias_contract = pointer.get("alias_contract", {})
    if not isinstance(alias_contract, dict):
        alias_contract = {}
    alias_risks = pointer.get("alias_risks", [])
    if not isinstance(alias_risks, list):
        alias_risks = []
    if alias_contract.get("decision") == "blocked":
        return "L3", {"feature": "alias_blocked", "weight": "high"}
    if alias_contract.get("decision") == "requires_noalias_contract" or any(
        isinstance(risk, dict)
        and (
            risk.get("risk_level") == "unknown_alias"
            or risk.get("gate_decision") == "requires_noalias_contract"
            or risk.get("requires_noalias") is True
        )
        for risk in alias_risks
    ):
        return (
            "L2",
            {
                "feature": "alias_requires_noalias_contract",
                "risk_count": len(alias_risks),
                "weight": "medium",
            },
        )
    return None


def typed_ir_candidate_route_signal(
    candidate_generation: dict[str, Any], *, scalar_only: bool = False
) -> tuple[str, dict[str, Any]] | None:
    typed_ir = candidate_generation.get("typed_ir")
    if not isinstance(typed_ir, dict):
        return None
    status = str(typed_ir.get("status", ""))
    candidate_route = typed_ir.get("candidate_route")
    route = candidate_route.get("route") if isinstance(candidate_route, dict) else None
    token_cost = candidate_route.get("token_cost") if isinstance(candidate_route, dict) else None
    if status == "generated" and route == "GenericTypedIr" and typed_ir.get("rust_draft_generated") is True:
        scalar_admission = typed_ir.get("scalar_admission", {})
        if isinstance(scalar_admission, dict) and scalar_admission.get("status") == "unresolved":
            unresolved = scalar_admission.get("unresolved", [])
            return (
                "L1",
                {
                    "feature": "typed_ir_scalar_admission_unresolved",
                    "route": "GenericTypedIr",
                    "unresolved_count": len(unresolved) if isinstance(unresolved, list) else 0,
                    "weight": "requires_contract_or_domain_evidence",
                },
            )
        if scalar_only and token_cost == 0:
            return (
                "L0",
                {
                    "feature": "typed_ir_zero_token_deterministic",
                    "route": "GenericTypedIr",
                    "token_cost": 0,
                    "weight": "deterministic_typed_ir",
                },
            )
        return (
            "L1",
            {
                "feature": "typed_ir_candidate_generated",
                "route": "GenericTypedIr",
                "weight": "generic_typed_ir",
            },
        )
    if status == "unsupported":
        reason = str(typed_ir.get("unsupported_reason") or typed_ir.get("reason") or "typed_ir_candidate_unsupported")
        return (
            "L2",
            {
                "feature": "typed_ir_candidate_unsupported",
                "reason": reason,
                "weight": "repair_queue",
            },
        )
    return None


def route_translator(level: str) -> dict[str, Any]:
    if level == "L4":
        return {"kind": "refuse", "candidate_generation_allowed": False}
    if level in {"L0", "L1", "L2"}:
        return {"kind": "tier1", "candidate_generation_allowed": True}
    return {"kind": "agent", "candidate_generation_allowed": True}


def emit_validation_profile(
    spec: dict[str, Any],
    evidence_dir: Path,
    route_decision: dict[str, Any],
    oracle: dict[str, Any],
    rust_check: dict[str, Any],
    accepted: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write the profile that owns required gates for this route.

    Route status selects the profile; profile status records whether every
    required gate is present and passed. Generated candidate replay or diff
    evidence remains diagnostic unless accepted evidence is explicitly
    authoritative for the route and all profile gates are satisfied.
    """
    slice_id = required_str(spec, "slice_id")
    prefix = f"l3-{slice_id}"
    goal = route_decision.get("policy", {}).get("goal", "dev")
    level = str(route_decision.get("level", "L4"))
    profile = route_decision.get("verification_profile") or validation_profile_name(level, goal)
    required = required_gates_for_profile(level, goal)
    skipped = []
    accepted_authoritative = accepted_evidence_authoritative_route(route_decision)
    if route_decision.get("translator", {}).get("kind") == "refuse" and not accepted_authoritative:
        skipped.append({"gate": "candidate_generation", "reason": "route_refused"})
    if "compile" in required and rust_check.get("status") not in {"passed", "failed"}:
        skipped.append({"gate": "compile", "reason": rust_check.get("status", "unknown")})
    if "c_oracle_diff" in required and oracle.get("status") != "C_ORACLE_GENERATED":
        skipped.append({"gate": "c_oracle_diff", "reason": oracle.get("status", "missing")})
    for gate in required:
        if gate in {"compile", "c_oracle_diff"}:
            continue
        if gate == "rust_tests":
            test_translation = read_json(evidence_dir / f"{prefix}-test-translation-generated.json")
            if test_translation.get("status") not in {"recorded", "passed"}:
                skipped.append({"gate": gate, "reason": test_translation.get("status", "missing")})
            continue
        if gate == "unsafe_ledger":
            accepted_ledger = accepted is not None and accepted.get("reports", {}).get("unsafe_ledger", {}).get("status") == "passed"
            unsafe_ledger = evidence_dir / f"{prefix}-unsafe-ledger.json"
            generated_ledger = unsafe_ledger.exists() and read_json(unsafe_ledger).get("status") == "passed"
            if not accepted_ledger and not generated_ledger:
                skipped.append({"gate": gate, "reason": "unsafe_ledger_not_passed"})
            continue
        skipped.append({"gate": gate, "reason": "required_gate_not_available_in_dev_evidence"})
    compile_passed = rust_check.get("status") == "passed"
    oracle_passed = oracle.get("status") == "C_ORACLE_GENERATED"
    oracle_contract = oracle_boundary_contract(spec, accepted=accepted, oracle=oracle)
    if accepted is not None and oracle_contract.get("status") != "sufficient_for_semantic_pass":
        skipped.append(
            {
                "gate": "oracle_boundary_contract",
                "reason": oracle_contract.get("status", "missing"),
                "insufficient": oracle_contract.get("insufficient_reasons", []),
            }
        )
    result = "passed" if not skipped and compile_passed and oracle_passed else "blocked" if level == "L4" else "incomplete"
    payload = {
        "schema_version": 1,
        "target_id": spec.get("target_id"),
        "slice_id": slice_id,
        "status": result,
        "profile": profile,
        "route_level": level,
        "goal": goal,
        "competition_environment": competition_environment_identity(),
        "required_gates": required,
        "optional_gates": optional_gates_for_profile(level, goal),
        "skipped_gates": skipped,
        "required_gate_status": {
            "compile": rust_check.get("status"),
            "c_oracle_diff": oracle.get("status"),
        },
        "candidate_generation": route_decision.get("candidate_generation", {}),
        "scalar_ub_contract": route_decision.get("scalar_ub_contract", scalar_ub_contract(spec)),
        "oracle_boundary_contract": oracle_contract,
        "accepted_evidence_authoritative": accepted_authoritative,
        "generated_draft_semantic_pass": False,
        "loop_policy": {
            "source": "run_policy",
            "fixed_project_loop_count_required": False,
            "stress_loops": spec.get("verification_profile", {}).get("stress_loops"),
        },
        "tool_boundaries": {
            "c_ub": ["clang_diagnostics", "sanitizer_oracle", "unsupported_evidence"],
            "rust_ub": ["miri", "unsafe_ledger", "rust_verification_tools"],
        },
    }
    write_json(evidence_dir / f"{prefix}-validation-profile.json", payload)
    return payload


def validation_profile_name(level: str, goal: str) -> str:
    return f"{level}-{goal}"


def required_gates_for_profile(level: str, goal: str) -> list[str]:
    gates = ["compile", "c_oracle_diff"]
    if level in {"L1", "L2", "L3"}:
        gates.extend(["unsafe_ledger", "rust_tests"])
    if level in {"L2", "L3"}:
        gates.extend(["fuzz_property", "miri"])
    if level == "L3" and goal in {"ci-merge", "release"}:
        gates.append("kani")
    if goal == "release":
        gates.extend(["negative_diff", "evidence_cleanliness"])
    return gates


def optional_gates_for_profile(level: str, goal: str) -> list[str]:
    optional = ["negative_diff", "evidence_cleanliness"]
    if level in {"L0", "L1"}:
        optional.extend(["fuzz_property", "miri"])
    if goal != "release":
        optional.append("kani")
    return optional


def c2rust_baseline_ref(
    spec: dict[str, Any], evidence_dir: Path, c2rust_baseline: dict[str, Any] | None
) -> dict[str, Any]:
    slice_id = required_str(spec, "slice_id")
    path = evidence_dir / f"l3-{slice_id}-c2rust-baseline-manifest.json"
    status = c2rust_baseline.get("status", "missing") if c2rust_baseline else "missing"
    return evidence_ref(path, status)


def route_decision_ref(
    spec: dict[str, Any], evidence_dir: Path, route_decision: dict[str, Any] | None
) -> dict[str, Any]:
    slice_id = required_str(spec, "slice_id")
    path = evidence_dir / f"l3-{slice_id}-route-decision.json"
    status = route_decision.get("status", "missing") if route_decision else "missing"
    ref = evidence_ref(path, status)
    if route_decision:
        ref["level"] = route_decision.get("level")
    return ref


def validation_profile_ref(
    spec: dict[str, Any], evidence_dir: Path, validation_profile: dict[str, Any] | None
) -> dict[str, Any]:
    slice_id = required_str(spec, "slice_id")
    path = evidence_dir / f"l3-{slice_id}-validation-profile.json"
    status = validation_profile.get("status", "missing") if validation_profile else "missing"
    ref = evidence_ref(path, status)
    if validation_profile:
        ref["profile"] = validation_profile.get("profile")
    return ref


def semantic_pass_for_run(
    accepted: dict[str, Any] | None,
    rust_check: dict[str, Any],
    validation_profile: dict[str, Any],
) -> bool:
    if accepted is None:
        return False
    if rust_check.get("status") != "passed":
        return False
    if validation_profile.get("status") != "passed":
        return False
    if validation_profile.get("route_level") == "L4" and not (
        validation_profile.get("accepted_evidence_authoritative") is True
        and validation_profile.get("generated_draft_semantic_pass") is False
    ):
        return False
    if not oracle_boundary_contract_sufficient(validation_profile.get("oracle_boundary_contract")):
        return False
    return not validation_profile.get("skipped_gates")


def emit_manifest(
    spec: dict[str, Any],
    evidence_dir: Path,
    translator_summary: dict[str, Any],
    oracle: dict[str, Any],
    replay: dict[str, Any],
    rust_check: dict[str, Any],
    patch: dict[str, Any],
    cache: dict[str, Any],
    c2rust_baseline: dict[str, Any],
    route_decision: dict[str, Any],
    validation_profile: dict[str, Any],
    accepted: dict[str, Any] | None = None,
) -> dict[str, Any]:
    slice_id = required_str(spec, "slice_id")
    l3_manifest = emit_l3_evidence_manifest(
        spec,
        evidence_dir,
        oracle,
        replay,
        rust_check,
        cache,
        c2rust_baseline,
        route_decision,
        validation_profile,
        accepted,
    )
    semantic_pass = semantic_pass_for_run(accepted, rust_check, validation_profile)
    alias_gate = alias_gate_from_pointer_graph(evidence_dir, slice_id)
    external_context = external_direct_callee_context(spec, load_plan_call_expressions(evidence_dir, slice_id))
    payload = {
        "schema_version": 1,
        "level": "L3",
        "target_id": spec.get("target_id"),
        "slice_id": slice_id,
        "status": auto_manifest_status(semantic_pass, route_decision),
        "semantic_pass": semantic_pass,
        "source_commit": spec.get("source_commit"),
        "fixture": {
            "hash": fixture_hash(spec),
            "path": fixture_path(spec),
        },
        "translator": translator_summary,
        "oracle": oracle,
        "replay": replay,
        "rust_check": rust_check,
        "patch": patch,
        "cache": cache,
        "c2rust_baseline": c2rust_baseline_ref(spec, evidence_dir, c2rust_baseline),
        "route_decision": route_decision_ref(spec, evidence_dir, route_decision),
        "validation_profile": validation_profile_ref(spec, evidence_dir, validation_profile),
        "l3_evidence_manifest": {
            "path": rel(l3_manifest),
            "status": "passed" if semantic_pass else "incomplete",
            "semantic_pass": semantic_pass,
        },
        "accepted_evidence_binding": accepted_binding_summary(accepted) if accepted else None,
        "claim_boundary": {
            "scope": auto_manifest_claim_scope(semantic_pass, route_decision),
            "semantic_pass": semantic_pass,
            "accepted_evidence_authoritative": accepted_evidence_authoritative_route(route_decision),
            "generated_draft_semantic_pass": False,
            "must_still_pass": []
            if semantic_pass
            else [
                "C_ORACLE_GENERATED",
                "Rust replay",
                "schema-aware diff",
                "negative diff",
                "unsafe scan",
                "version/config binding",
                "OpenSpec validation",
            ],
            "non_goals": spec.get("non_goals", []),
            "alias_gate": alias_gate,
            "external_callee_scope": external_callee_claim_scope(external_context),
        },
    }
    write_json(evidence_dir / f"l3-{slice_id}-auto-translation-manifest.json", payload)
    return payload


def route_refuses_candidate_generation(route_decision: dict[str, Any]) -> bool:
    translator = route_decision.get("translator", {})
    return (
        route_decision.get("level") == "L4"
        or translator.get("kind") == "refuse"
        or translator.get("candidate_generation_allowed") is False
    )


def generated_rust_draft_status(route_decision: dict[str, Any] | None) -> str:
    if route_decision and route_refuses_candidate_generation(route_decision):
        return "blocked"
    return "candidate"


def auto_manifest_status(semantic_pass: bool, route_decision: dict[str, Any]) -> str:
    if semantic_pass:
        return "accepted_evidence_bound"
    if route_refuses_candidate_generation(route_decision):
        return "candidate_refused"
    return "candidate_generated"


def auto_manifest_claim_scope(semantic_pass: bool, route_decision: dict[str, Any]) -> str:
    if semantic_pass:
        return "auto-translation run bound to accepted_evidence_binding; final_verification.semantic_pass=true is sourced from accepted/named-slice evidence; generated_draft_semantic_pass remains false; generated Rust draft remains candidate/provenance"
    if route_refuses_candidate_generation(route_decision):
        return "refused translation route; no generated candidate can claim semantics"
    return "generated Rust candidate only; semantic acceptance requires independent L3 gates"


def accepted_evidence_authoritative_requested(spec: dict[str, Any], accepted: dict[str, Any] | None) -> bool:
    if accepted is None or accepted.get("status") != "accepted":
        return False
    return spec.get("claim_boundary", {}).get("accepted_evidence_authoritative") is True


def accepted_evidence_authoritative_route(route_decision: dict[str, Any]) -> bool:
    policy = route_decision.get("policy", {})
    return (
        route_decision.get("level") == "L4"
        and route_decision.get("status") == "refused"
        and policy.get("accepted_evidence_authoritative") is True
        and policy.get("generated_draft_semantic_pass") is False
    )


def mark_accepted_evidence_authoritative_route(
    spec: dict[str, Any],
    evidence_dir: Path,
    route_decision: dict[str, Any],
    accepted: dict[str, Any] | None,
) -> dict[str, Any]:
    if not accepted_evidence_authoritative_requested(spec, accepted):
        return route_decision
    route_decision["level"] = "L4"
    route_decision["status"] = "refused"
    route_decision["translator"] = {"kind": "refuse", "candidate_generation_allowed": False}
    policy = route_decision.setdefault("policy", {})
    policy["accepted_evidence_authoritative"] = True
    policy["generated_draft_semantic_pass"] = False
    route_decision["verification_profile"] = "L4-accepted-evidence"
    rationale = route_decision.setdefault("rationale", [])
    if not any(item.get("feature") == "accepted_evidence_authoritative" for item in rationale):
        rationale.append({"feature": "accepted_evidence_authoritative", "weight": "override"})
    write_json(evidence_dir / f"l3-{required_str(spec, 'slice_id')}-route-decision.json", route_decision)
    return route_decision


def emit_l3_evidence_manifest(
    spec: dict[str, Any],
    evidence_dir: Path,
    oracle: dict[str, Any],
    replay: dict[str, Any],
    rust_check: dict[str, Any],
    cache: dict[str, Any],
    c2rust_baseline: dict[str, Any],
    route_decision: dict[str, Any],
    validation_profile: dict[str, Any],
    accepted: dict[str, Any] | None = None,
) -> Path:
    slice_id = required_str(spec, "slice_id")
    prefix = f"l3-{slice_id}"
    semantic_pass = semantic_pass_for_run(accepted, rust_check, validation_profile)
    write_l3_candidate_supporting_evidence(
        spec,
        evidence_dir,
        oracle,
        replay,
        rust_check,
        cache,
        c2rust_baseline,
        route_decision,
        validation_profile,
        accepted,
    )
    bind_route_decision_to_generated_artifacts(spec, evidence_dir, c2rust_baseline, route_decision, validation_profile)
    alias_gate = alias_gate_from_pointer_graph(evidence_dir, slice_id)
    external_context = external_direct_callee_context(spec, load_plan_call_expressions(evidence_dir, slice_id))
    pointer_ref = evidence_ref(evidence_dir / f"{prefix}-pointer-graph.json", pointer_status_for_manifest(spec, evidence_dir))
    if pointer_ref["status"] == "not_applicable":
        pointer_ref["not_applicable_reason"] = "slice has no pointer surface"
    test_ref = evidence_ref(evidence_dir / f"{prefix}-test-translation-generated.json", "recorded")
    negative = read_json(evidence_dir / f"{prefix}-negative-diff.json")
    manifest = {
        "schema_version": 1,
        "level": "L3",
        "target_id": spec.get("target_id"),
        "slice_id": slice_id,
        "status": "passed" if semantic_pass else "incomplete",
        "source_commit": source_commit(spec),
        "repo_commit": repo_commit(),
        "fixture": {
            "path": fixture_path(spec),
            "hash": fixture_hash(spec),
            "operation_count": len(spec.get("fixture_contract", {}).get("cases", [])),
        },
        "evidence": {
            "slice_contract": evidence_ref(evidence_dir / f"{prefix}-slice-contract.json", "recorded"),
            "context_pack": evidence_ref(evidence_dir / f"{prefix}-context-pack.json", "recorded"),
            "c2rust_baseline": c2rust_baseline_ref(spec, evidence_dir, c2rust_baseline),
            "route_decision": route_decision_ref(spec, evidence_dir, route_decision),
            "validation_profile": validation_profile_ref(spec, evidence_dir, validation_profile),
            "cache_metadata": evidence_ref(evidence_dir / f"{prefix}-auto-cache-metadata.json", "recorded"),
            "config_profile": {
                **evidence_ref(evidence_dir / f"{prefix}-config-profile.json", "recorded" if semantic_pass else "incomplete"),
                "profile_id": build_profile_id(spec),
            },
            "pointer_dependency_graph": pointer_ref,
            "test_translation": test_ref,
            "c_oracle": evidence_ref(evidence_dir / f"{prefix}-c-oracle-status.json", oracle.get("status", "draft")),
            "rust_report": evidence_ref(evidence_dir / f"{prefix}-rust-report.json", "passed" if semantic_pass else "incomplete"),
            "schema_diff": evidence_ref(evidence_dir / f"{prefix}-diff.json", "passed" if semantic_pass else "incomplete"),
            "negative_diff": {
                **evidence_ref(evidence_dir / f"{prefix}-negative-diff.json", negative.get("status", "incomplete")),
                "expected_failure": True,
                "mutation_detected": bool(negative.get("mutation_detected") or negative.get("detected")),
            },
            "rust_check": evidence_ref(evidence_dir / "rust-check.json", rust_check.get("status", "unknown")),
            "unsafe_scan": evidence_ref(evidence_dir / f"{prefix}-unsafe-scan.json", "passed" if semantic_pass else "incomplete"),
            "unsafe_ledger": evidence_ref(evidence_dir / f"{prefix}-unsafe-ledger.json", "passed" if semantic_pass else "incomplete"),
            "performance_smoke": {
                **evidence_ref(evidence_dir / f"{prefix}-performance-smoke.json", "recorded"),
                "secondary_only": True,
            },
            "final_verification": evidence_ref(evidence_dir / f"{prefix}-final-verification.json", "passed" if semantic_pass else "incomplete"),
            "summary": evidence_ref(evidence_dir / f"{prefix}-summary.json", "passed" if semantic_pass else "incomplete"),
            "version_or_config_binding": evidence_ref(evidence_dir / f"{prefix}-version-manifest.json", "recorded"),
        },
        "claim_boundary": {
            "scope": "Automatic translation candidate only; semantic acceptance is blocked until the C oracle, Rust replay, diff, negative diff, unsafe, version/cache, and OpenSpec gates pass."
            if not semantic_pass
            else "Automatic translation run completed with accepted evidence binding; the generated Rust draft is provenance evidence and remains a candidate unless a later gate explicitly accepts that exact draft.",
            "accepted_evidence_authoritative": accepted_evidence_authoritative_route(route_decision),
            "generated_draft_semantic_pass": False,
            "behavior_fields_checked": behavior_fields(spec),
            "accepted_metadata_differences": accepted_metadata_differences(spec),
            "known_gaps": non_goals(spec)
            + (
                [
                    "Auto-generated Rust draft remains a candidate; accepted semantics are bound to the referenced Rust replay evidence.",
                ]
                if semantic_pass
                else [
                    "C oracle has not produced an accepted semantic pass for this auto-translation candidate.",
                    "Schema diff and negative diff are placeholders until accepted oracle/replay evidence exists.",
                ]
            ),
            "must_not_claim": must_not_claim(spec)
            + [
                "semantic equivalence for this auto-generated Rust draft",
                "full C99/C11 automatic translation",
            ],
            "alias_gate": alias_gate,
            "external_callee_scope": external_callee_claim_scope(external_context),
        },
    }
    clang_report = evidence_dir / f"{prefix}-clang-lowering-report.json"
    if clang_report.exists():
        manifest["evidence"]["clang_lowering_report"] = evidence_ref(clang_report, "recorded")
    path = evidence_dir / f"{prefix}-evidence-manifest.json"
    write_json(path, manifest)
    return path


def bind_route_decision_to_generated_artifacts(
    spec: dict[str, Any],
    evidence_dir: Path,
    c2rust_baseline: dict[str, Any],
    route_decision: dict[str, Any],
    validation_profile: dict[str, Any],
) -> None:
    slice_id = required_str(spec, "slice_id")
    prefix = f"l3-{slice_id}"
    refs = {
        "c2rust_baseline": c2rust_baseline_ref(spec, evidence_dir, c2rust_baseline),
        "route_decision": route_decision_ref(spec, evidence_dir, route_decision),
        "validation_profile": validation_profile_ref(spec, evidence_dir, validation_profile),
    }
    for file_name in [
        f"{prefix}-auto-translation-plan.json",
        f"{prefix}-ai-candidate-manifest.json",
        "rust-check.json",
        f"{prefix}-diff.json",
        f"{prefix}-negative-diff.json",
        f"{prefix}-unsafe-scan.json",
        f"{prefix}-unsafe-ledger.json",
    ]:
        path = evidence_dir / file_name
        if not path.exists():
            continue
        payload = read_json(path)
        payload.update(refs)
        write_json(path, payload)


def c_oracle_output_gate_status(oracle: dict[str, Any]) -> str:
    output_gate = c_oracle_output_gate_from_oracle(oracle)
    return str(output_gate.get("status", "missing"))


def c_oracle_output_gate_from_oracle(oracle: dict[str, Any]) -> dict[str, Any]:
    compile_execution = oracle.get("compile_execution")
    if not isinstance(compile_execution, dict):
        return {}
    harness_execution = compile_execution.get("harness_execution")
    if not isinstance(harness_execution, dict):
        return {}
    output_gate = harness_execution.get("output_gate")
    return output_gate if isinstance(output_gate, dict) else {}


def generated_candidate_diff_from_diagnostics(
    spec: dict[str, Any],
    oracle: dict[str, Any],
    replay: dict[str, Any],
    rust_report_status: str,
) -> dict[str, Any] | None:
    compile_execution = oracle.get("compile_execution")
    if not isinstance(compile_execution, dict):
        return None
    harness_execution = compile_execution.get("harness_execution")
    if not isinstance(harness_execution, dict):
        return None
    output_gate = c_oracle_output_gate_from_oracle(oracle)
    if not (
        oracle.get("status") == "DRAFT_GENERATED"
        and oracle.get("toolchain_status") == "COMPILE_SUCCEEDED_NOT_ORACLE"
        and oracle.get("semantic_pass") is not True
        and compile_execution.get("status") == "compile_succeeded_not_oracle"
        and harness_execution.get("status") == "exited_zero_not_oracle"
        and output_gate.get("status") == "matched_not_oracle"
        and output_gate.get("semantic_pass") is not True
        and replay.get("status") == "passed"
        and replay.get("generated_draft_replay_pass") is True
        and replay.get("generated_draft_semantic_pass") is not True
        and rust_report_status == "passed"
    ):
        return None
    return {
        "schema_version": 1,
        "status": "matched_not_oracle",
        "semantic_pass": False,
        "compared_fields": output_gate.get("compared_fields") or behavior_fields(spec),
        "c_oracle_output_gate_status": output_gate.get("status"),
        "rust_replay_status": replay.get("status"),
        "matched_stdout_fragments": output_gate.get("matched_stdout_fragments", []),
        "missing_stdout_fragments": output_gate.get("missing_stdout_fragments", []),
        "boundary": "Generated candidate diff is diagnostic only until accepted oracle diff gates pass.",
    }


def write_l3_candidate_supporting_evidence(
    spec: dict[str, Any],
    evidence_dir: Path,
    oracle: dict[str, Any],
    replay: dict[str, Any],
    rust_check: dict[str, Any],
    cache: dict[str, Any],
    c2rust_baseline: dict[str, Any],
    route_decision: dict[str, Any],
    validation_profile: dict[str, Any],
    accepted: dict[str, Any] | None = None,
) -> None:
    """Write supporting evidence for a generated L3 candidate.

    Without accepted evidence, this function deliberately emits diagnostic
    draft reports: replay and candidate diff may show useful agreement, but
    generated_draft_semantic_pass and semantic_pass remain false. If accepted
    evidence is provided, control moves to the accepted writer below.
    """
    slice_id = required_str(spec, "slice_id")
    prefix = f"l3-{slice_id}"
    unsafe_count = rust_draft_unsafe_count(evidence_dir / f"{prefix}-rust-draft.rs")
    semantic_pass = semantic_pass_for_run(accepted, rust_check, validation_profile)
    generated_replay_pass = replay.get("status") == "passed" and replay.get("generated_draft_replay_pass") is True
    generated_replay_failed = replay.get("status") == "failed"
    rust_report_status = "passed" if generated_replay_pass else "failed" if generated_replay_failed else "incomplete"
    rust_report_cases = generated_rust_report_cases(spec)
    alias_gate = alias_gate_from_pointer_graph(evidence_dir, slice_id)
    candidate_diff = generated_candidate_diff_from_diagnostics(spec, oracle, replay, rust_report_status)
    candidate_diff_pass = candidate_diff is not None and candidate_diff.get("status") == "matched_not_oracle"
    write_json(
        evidence_dir / f"{prefix}-slice-contract.json",
        {
            "schema_version": 1,
            "target_id": spec.get("target_id"),
            "slice_id": slice_id,
            "status": "recorded",
            "source_commit": source_commit(spec),
            "fixture": {"path": fixture_path(spec), "hash": fixture_hash(spec)},
            "c_boundary": spec.get("c_boundary", {}),
            "rust_boundary": spec.get("rust_boundary", {}),
            "claim_boundary": spec.get("claim_boundary", {}),
        },
    )
    write_l3_config_profile(spec, evidence_dir)
    if accepted is not None:
        write_accepted_supporting_evidence(
            spec,
            evidence_dir,
            oracle,
            replay,
            rust_check,
            cache,
            c2rust_baseline,
            route_decision,
            validation_profile,
            accepted,
        )
        return
    write_json(
        evidence_dir / f"{prefix}-rust-report.json",
        {
            "schema_version": 1,
            "target_id": spec.get("target_id"),
            "slice_id": slice_id,
            "status": rust_report_status,
            "semantic_pass": False,
            "reason": "Generated Rust replay passed fixture cases; semantic acceptance still requires C oracle, diff, negative diff, unsafe, and final verification gates."
            if generated_replay_pass
            else "Generated Rust replay failed fixture cases; semantic acceptance remains blocked."
            if generated_replay_failed
            else "Generated Rust replay test is a draft; accepted Rust report has not been produced.",
            "case_count": len(rust_report_cases),
            "cases": rust_report_cases,
            "generated_draft": evidence_ref(evidence_dir / f"{prefix}-rust-draft.rs", generated_rust_draft_status(route_decision)),
            "generated_draft_replay_pass": generated_replay_pass,
            "generated_draft_semantic_pass": False,
            "replay": replay,
        },
    )
    write_json(
        evidence_dir / f"{prefix}-diff.json",
        {
            "schema_version": 1,
            "target_id": spec.get("target_id"),
            "slice_id": slice_id,
            "diff_gate": "schema_aware_c_rust_diff",
            "status": "incomplete",
            "semantic_pass": False,
            "first_mismatch": None,
            "compared_fields": behavior_fields(spec),
            "accepted_diff_required": True,
            "blocked_by": ["accepted_c_oracle"] if candidate_diff_pass else ["c_oracle", "rust_replay"],
            "required_inputs": {
                "c_oracle_required_status": "C_ORACLE_GENERATED",
                "rust_report_required_status": "passed",
                "c_oracle_actual_status": oracle.get("status", "unknown"),
                "c_oracle_actual_toolchain_status": oracle.get("toolchain_status", "unknown"),
                "c_oracle_output_gate_actual_status": c_oracle_output_gate_status(oracle),
                "rust_replay_actual_status": replay.get("status", "unknown"),
                "rust_report_actual_status": rust_report_status,
            },
            "generated_candidate_diff_pass": candidate_diff_pass,
            **({"candidate_diff": candidate_diff} if candidate_diff_pass else {}),
            "reason_code": "candidate_matched_accepted_oracle_required"
            if candidate_diff_pass
            else "missing_accepted_c_oracle"
            if generated_replay_pass
            else "missing_accepted_c_oracle_and_rust_replay",
            "reason": "Generated candidate matched diagnostic C harness output and Rust replay fixtures; accepted C oracle diff remains required before semantic acceptance."
            if candidate_diff_pass
            else "Schema-aware diff requires accepted C oracle evidence before semantic acceptance."
            if generated_replay_pass
            else "Schema-aware diff requires accepted C oracle and Rust replay reports.",
        },
    )
    write_json(
        evidence_dir / f"{prefix}-negative-diff.json",
        {
            "schema_version": 1,
            "target_id": spec.get("target_id"),
            "slice_id": slice_id,
            "negative_diff_gate": "schema_aware_negative_diff",
            "status": "incomplete",
            "expected_failure": True,
            "mutation_detected": False,
            "accepted_negative_diff_required": True,
            "blocked_by": ["schema_diff"],
            "root_blocked_by": ["c_oracle", "rust_replay"],
            "required_inputs": {
                "schema_diff_required_status": "passed",
                "schema_diff_required_first_mismatch": None,
                "schema_diff_actual_status": "incomplete",
                "c_oracle_required_status": "C_ORACLE_GENERATED",
                "rust_report_required_status": "passed",
            },
            "reason_code": "missing_passed_schema_diff",
            "reason": "Negative diff is not run for draft-only auto-translation candidates.",
        },
    )
    write_json(
        evidence_dir / f"{prefix}-unsafe-scan.json",
        {
            "schema_version": 1,
            "target_id": spec.get("target_id"),
            "slice_id": slice_id,
            "status": "passed" if unsafe_count == 0 else "incomplete",
            "first_party_non_test_unsafe_count": unsafe_count,
            "first_party_non_test_unsafe_ratio": 0.0 if unsafe_count == 0 else None,
            "semantic_pass": False,
        },
    )
    write_json(
        evidence_dir / f"{prefix}-unsafe-ledger.json",
        {
            "schema_version": 1,
            "target_id": spec.get("target_id"),
            "slice_id": slice_id,
            "status": "passed" if unsafe_count == 0 else "incomplete",
            "entries": [],
            "policy": "Every first-party non-test unsafe use must be ledgered before acceptance.",
        },
    )
    write_json(
        evidence_dir / f"{prefix}-performance-smoke.json",
        {
            "schema_version": 1,
            "target_id": spec.get("target_id"),
            "slice_id": slice_id,
            "status": "recorded",
            "secondary_only": True,
            "semantic_pass": False,
            "reason": "Performance is not evaluated for draft-only auto-translation candidates.",
        },
    )
    write_json(
        evidence_dir / f"{prefix}-final-verification.json",
        {
            "schema_version": 1,
            "target_id": spec.get("target_id"),
            "slice_id": slice_id,
            "status": "incomplete",
            "semantic_pass": False,
            "rust_check_status": rust_check.get("status"),
            "c_oracle_status": oracle.get("status"),
            "c2rust_baseline": c2rust_baseline_ref(spec, evidence_dir, c2rust_baseline),
            "route_decision": route_decision_ref(spec, evidence_dir, route_decision),
            "validation_profile": validation_profile_ref(spec, evidence_dir, validation_profile),
            "skipped_gates": validation_profile.get("skipped_gates", []),
            "validation_profile_status": validation_profile.get("status"),
            "alias_gate": alias_gate,
            "required_before_acceptance": [
                "C_ORACLE_GENERATED",
                "Rust replay",
                "schema-aware diff",
                "negative diff",
                "unsafe scan",
                "version/config binding",
                "OpenSpec validation",
            ],
        },
    )
    write_json(
        evidence_dir / f"{prefix}-summary.json",
        {
            "schema_version": 1,
            "target_id": spec.get("target_id"),
            "slice_id": slice_id,
            "status": "incomplete",
            "semantic_pass": False,
            "summary": "Auto-translation candidate generated with schema-bound evidence; acceptance gates remain open.",
        },
    )
    write_json(
        evidence_dir / f"{prefix}-version-manifest.json",
        {
            "schema_version": 1,
            "target_id": spec.get("target_id"),
            "slice_id": slice_id,
            "status": "recorded",
            "source_commit": source_commit(spec),
            "repo_commit": repo_commit(),
            "cache": cache,
            "translator_version": "0.1.0",
            "semantic_pass": semantic_pass,
        },
    )


def resolve_accepted_evidence(spec: dict[str, Any]) -> dict[str, Any]:
    fixture = spec.get("fixture_contract", {})
    c_oracle_path = required_repo_path(fixture.get("c_oracle"), "fixture_contract.c_oracle")
    rust_report_path = required_repo_path(fixture.get("rust_report"), "fixture_contract.rust_report")
    diff_path = optional_repo_path(fixture.get("diff")) or derive_evidence_path(c_oracle_path, "-oracle.json", "-diff.json")
    negative_diff_path = optional_repo_path(fixture.get("negative_diff")) or derive_evidence_path(
        c_oracle_path, "-oracle.json", "-negative-diff.json"
    )
    unsafe_scan_path = optional_repo_path(fixture.get("unsafe_scan")) or default_unsafe_scan_path(spec, c_oracle_path)
    unsafe_ledger_path = optional_repo_path(fixture.get("unsafe_ledger")) or default_unsafe_ledger_path(spec, c_oracle_path)
    performance_path = optional_repo_path(fixture.get("performance_smoke"))
    final_path = optional_repo_path(fixture.get("final_verification")) or optional_default_evidence(
        spec, "final-verification"
    )
    version_path = optional_repo_path(fixture.get("version_manifest")) or optional_default_evidence(
        spec, "version-manifest"
    )

    paths = {
        "c_oracle": c_oracle_path,
        "rust_report": rust_report_path,
        "diff": diff_path,
        "negative_diff": negative_diff_path,
        "unsafe_scan": unsafe_scan_path,
        "unsafe_ledger": unsafe_ledger_path,
        "performance_smoke": performance_path,
        "final_verification": final_path,
        "version_manifest": version_path,
    }
    for key in ["c_oracle", "rust_report", "diff", "negative_diff", "unsafe_scan", "unsafe_ledger"]:
        if paths[key] is None or not paths[key].exists():
            raise SystemExit(f"--accept-existing-evidence requires {key} evidence at {paths[key]}")

    reports = {key: read_json(path) for key, path in paths.items() if path is not None and path.exists()}
    require_accepted_report(spec, "c_oracle", reports["c_oracle"], require_toolchain=True)
    require_accepted_report(spec, "rust_report", reports["rust_report"])
    require_accepted_report(spec, "diff", reports["diff"])
    require_accepted_report(spec, "unsafe_scan", reports["unsafe_scan"])
    if reports["diff"].get("first_mismatch") is not None:
        raise SystemExit("--accept-existing-evidence requires schema diff with first_mismatch=null")
    if not mutation_detected(reports["negative_diff"]):
        raise SystemExit("--accept-existing-evidence requires negative diff mutation_detected/detected=true")

    fixture_path_text = fixture_path(spec)
    fixture_file = REPO_ROOT / fixture_path_text
    fixture_sha = sha256(fixture_file) if fixture_file.exists() and fixture_file.is_file() else fixture_hash(spec)
    return {
        "schema_version": 1,
        "status": "accepted",
        "target_id": spec.get("target_id"),
        "slice_id": spec.get("slice_id"),
        "source_commit": source_commit(spec),
        "fixture_path": fixture_path_text,
        "fixture_sha256": fixture_sha,
        "paths": {key: rel(path) for key, path in paths.items() if path is not None and path.exists()},
        "path_sha256": {key: sha256(path) for key, path in paths.items() if path is not None and path.exists()},
        "reports": reports,
        "toolchain_status": "C_ORACLE_GENERATED",
        "generated_draft_semantic_pass": False,
        "binding_boundary": "Accepted semantics are bound to referenced oracle/replay/diff/unsafe evidence; the generated Rust draft remains candidate evidence.",
    }


def promote_accepted_oracle(
    spec: dict[str, Any],
    evidence_dir: Path,
    draft_oracle: dict[str, Any],
    accepted: dict[str, Any],
) -> dict[str, Any]:
    slice_id = required_str(spec, "slice_id")
    report = accepted["reports"]["c_oracle"]
    path = evidence_dir / f"l3-{slice_id}-c-oracle-status.json"
    payload = {
        "schema_version": 1,
        "target_id": spec.get("target_id"),
        "slice_id": slice_id,
        "status": "C_ORACLE_GENERATED",
        "semantic_pass": True,
        "toolchain_status": "C_ORACLE_GENERATED",
        "source_commit": source_commit(spec),
        "fixture": fixture_path(spec),
        "fixture_sha256": accepted["fixture_sha256"],
        "case_count": report.get("case_count"),
        "source_status": report.get("status"),
        "source_slice_id": report.get("slice_id"),
        "accepted_oracle": evidence_ref(REPO_ROOT / accepted["paths"]["c_oracle"], "passed"),
        "harness_draft": draft_oracle.get("harness_draft"),
        "harness_draft_ref": draft_oracle.get("harness_draft_ref"),
        "boundary": "C oracle success comes from accepted Linux/WSL/CI evidence, not from the draft harness alone.",
    }
    if global_dependency_requirements(spec):
        for key in [
            "fixture_binding",
            "harness_contract",
            "global_linkage_requirements",
            "compile_command_draft",
            "compile_execution",
        ]:
            if key in draft_oracle:
                payload[key] = draft_oracle[key]
        payload.setdefault("global_linkage_requirements", global_dependency_requirements(spec))
    write_json(path, payload)
    return payload


def promote_accepted_test_translation(
    spec: dict[str, Any],
    evidence_dir: Path,
    replay: dict[str, Any],
    accepted: dict[str, Any],
    route_decision: dict[str, Any],
) -> dict[str, Any]:
    slice_id = required_str(spec, "slice_id")
    path = evidence_dir / f"l3-{slice_id}-test-translation-generated.json"
    payload = read_json(path)
    draft_status = generated_rust_draft_status(route_decision)
    test_file = spec.get("rust_boundary", {}).get("test_file") or replay.get("test_draft")
    test_name = f"accepted_{safe_ident(slice_id)}_replay"
    payload.update(
        {
            "status": "recorded",
            "source_commit": source_commit(spec),
            "source_test_inputs": {
                "oracle_strategy": "Accepted C oracle and Rust replay evidence are bound from the slice spec; generated replay draft remains provenance.",
                "fixtures": [
                    {
                        "path": fixture_path(spec),
                        "hash": accepted["fixture_sha256"],
                        "operation_count": len(spec.get("fixture_contract", {}).get("cases", [])),
                        "source_kind": "fixture",
                    }
                ],
                "oracle_reports": [
                    evidence_ref(REPO_ROOT / accepted["paths"]["c_oracle"], "passed"),
                    evidence_ref(REPO_ROOT / accepted["paths"]["rust_report"], "passed"),
                ],
            },
            "rust_tests": [
                {
                    "file": test_file,
                    "test_names": [test_name],
                    "cargo_command": f"cargo test --manifest-path validation/l2_slices/Cargo.toml {safe_ident(slice_id)}",
                    "framework": "cargo test",
                    "source": "accepted replay evidence",
                },
                {
                    "file": replay.get("test_draft"),
                    "test_names": [f"replay_{safe_ident(slice_id)}_fixture_contract"],
                    "cargo_command": f"cargo test replay_{safe_ident(slice_id)}_fixture_contract",
                    "framework": "cargo test",
                    "status": "generated_draft",
                },
            ],
            "translation_mappings": [
                {
                    "source": fixture_path(spec),
                    "rust_test": f"{test_file}::{test_name}",
                    "behavior_fields": behavior_fields(spec),
                    "coverage_kind": "main_path",
                    "status": "mapped",
                    "evidence": [
                        evidence_ref(REPO_ROOT / accepted["paths"]["c_oracle"], "passed"),
                        evidence_ref(REPO_ROOT / accepted["paths"]["rust_report"], "passed"),
                        evidence_ref(REPO_ROOT / accepted["paths"]["diff"], "passed"),
                    ],
                },
                {
                    "source": accepted["paths"]["negative_diff"],
                    "rust_test": f"validation/l2_slices/src/bin/emit_reports.rs::emit_{safe_ident(slice_id)}_negative_diff",
                    "behavior_fields": behavior_fields(spec),
                    "coverage_kind": "negative_case",
                    "status": "mapped",
                    "evidence": [
                        evidence_ref(REPO_ROOT / accepted["paths"]["negative_diff"], "passed"),
                    ],
                }
            ],
            "evidence_links": {
                "rust_draft": {"path": rel(evidence_dir / f"l3-{slice_id}-rust-draft.rs"), "status": draft_status},
                "c_oracle": evidence_ref(REPO_ROOT / accepted["paths"]["c_oracle"], "passed"),
                "rust_report": evidence_ref(REPO_ROOT / accepted["paths"]["rust_report"], "passed"),
                "schema_diff": evidence_ref(REPO_ROOT / accepted["paths"]["diff"], "passed"),
                "negative_diff": evidence_ref(REPO_ROOT / accepted["paths"]["negative_diff"], "passed"),
            },
            "known_gaps": [
                "Generated replay draft is not itself the accepted replay implementation.",
                "Generated Rust draft remains a candidate until that exact draft is promoted by later gates.",
            ],
        }
    )
    write_json(path, payload)
    return payload


def write_accepted_supporting_evidence(
    spec: dict[str, Any],
    evidence_dir: Path,
    oracle: dict[str, Any],
    replay: dict[str, Any],
    rust_check: dict[str, Any],
    cache: dict[str, Any],
    c2rust_baseline: dict[str, Any],
    route_decision: dict[str, Any],
    validation_profile: dict[str, Any],
    accepted: dict[str, Any],
) -> None:
    """Bind accepted evidence into semantic-pass supporting artifacts.

    This path is the boundary where C oracle, Rust report, schema diff,
    negative diff, unsafe checks, route decision, and validation profile agree.
    The generated draft is still tracked as a draft, while semantic_pass comes
    from the accepted evidence binding and final verification artifacts.
    """
    slice_id = required_str(spec, "slice_id")
    prefix = f"l3-{slice_id}"
    accepted_paths = accepted["paths"]
    reports = accepted["reports"]
    unsafe_count = unsafe_count_from_report(reports["unsafe_scan"])
    semantic_pass = semantic_pass_for_run(accepted, rust_check, validation_profile)
    alias_gate = alias_gate_from_pointer_graph(evidence_dir, slice_id)
    external_context = external_direct_callee_context(spec, load_plan_call_expressions(evidence_dir, slice_id))
    draft_status = generated_rust_draft_status(route_decision)
    mark_config_profile_recorded(spec, evidence_dir, accepted)
    write_json(
        evidence_dir / f"{prefix}-rust-report.json",
        {
            "schema_version": 1,
            "target_id": spec.get("target_id"),
            "slice_id": slice_id,
            "status": "passed" if semantic_pass else "blocked",
            "semantic_pass": semantic_pass,
            "source_commit": source_commit(spec),
            "fixture": {"path": fixture_path(spec), "sha256": accepted["fixture_sha256"]},
            "source_slice_id": reports["rust_report"].get("slice_id"),
            "case_count": reports["rust_report"].get("case_count"),
            "accepted_rust_report": evidence_ref(REPO_ROOT / accepted_paths["rust_report"], "passed"),
            "generated_draft": evidence_ref(evidence_dir / f"{prefix}-rust-draft.rs", draft_status),
            "generated_draft_semantic_pass": False,
            "replay": replay,
        },
    )
    write_json(
        evidence_dir / f"{prefix}-diff.json",
        {
            "schema_version": 1,
            "target_id": spec.get("target_id"),
            "slice_id": slice_id,
            "status": "passed",
            "semantic_pass": True,
            "diff_gate": "schema_aware_c_rust_diff",
            "first_mismatch": reports["diff"].get("first_mismatch"),
            "compared_fields": reports["diff"].get("compared_fields") or behavior_fields(spec),
            "accepted_diff_required": True,
            "blocked_by": [],
            "required_inputs": {
                "c_oracle_required_status": "C_ORACLE_GENERATED",
                "rust_report_required_status": "passed",
                "c_oracle_actual_status": oracle.get("status", "unknown"),
                "c_oracle_actual_toolchain_status": oracle.get("toolchain_status", "unknown"),
                "rust_replay_actual_status": replay.get("status", "unknown"),
                "rust_report_actual_status": reports["rust_report"].get("status", "unknown"),
                "schema_diff_actual_status": reports["diff"].get("status", "unknown"),
            },
            "accepted_diff": evidence_ref(REPO_ROOT / accepted_paths["diff"], "passed"),
        },
    )
    write_json(
        evidence_dir / f"{prefix}-negative-diff.json",
        {
            "schema_version": 1,
            "target_id": spec.get("target_id"),
            "slice_id": slice_id,
            "status": reports["negative_diff"].get("status", "passed"),
            "negative_diff_gate": "schema_aware_negative_diff",
            "expected_failure": True,
            "mutation_detected": mutation_detected(reports["negative_diff"]),
            "accepted_negative_diff_required": True,
            "blocked_by": [],
            "root_blocked_by": [],
            "required_inputs": {
                "schema_diff_required_status": "passed",
                "schema_diff_required_first_mismatch": None,
                "schema_diff_actual_status": reports["diff"].get("status", "unknown"),
                "c_oracle_required_status": "C_ORACLE_GENERATED",
                "rust_replay_actual_status": replay.get("status", "unknown"),
                "rust_report_required_status": "passed",
                "negative_diff_actual_status": reports["negative_diff"].get("status", "unknown"),
            },
            "first_mismatch": reports["negative_diff"].get("first_mismatch"),
            "accepted_negative_diff": evidence_ref(REPO_ROOT / accepted_paths["negative_diff"], "passed"),
        },
    )
    write_json(
        evidence_dir / f"{prefix}-unsafe-scan.json",
        {
            "schema_version": 1,
            "target_id": spec.get("target_id"),
            "slice_id": slice_id,
            "status": "passed",
            "semantic_pass": True,
            "first_party_non_test_unsafe_count": unsafe_count,
            "first_party_non_test_unsafe_ratio": 0.0,
            "generated_draft_unsafe_count": rust_draft_unsafe_count(evidence_dir / f"{prefix}-rust-draft.rs"),
            "accepted_unsafe_scan": evidence_ref(REPO_ROOT / accepted_paths["unsafe_scan"], "passed"),
        },
    )
    write_json(
        evidence_dir / f"{prefix}-unsafe-ledger.json",
        {
            "schema_version": 1,
            "target_id": spec.get("target_id"),
            "slice_id": slice_id,
            "status": "passed",
            "first_party_non_test_unsafe_count": unsafe_count,
            "entries": [],
            "accepted_unsafe_ledger": evidence_ref(REPO_ROOT / accepted_paths["unsafe_ledger"], "passed"),
            "policy": "Every first-party non-test unsafe use must be ledgered before acceptance.",
        },
    )
    write_json(
        evidence_dir / f"{prefix}-performance-smoke.json",
        {
            "schema_version": 1,
            "target_id": spec.get("target_id"),
            "slice_id": slice_id,
            "status": "recorded",
            "secondary_only": True,
            "semantic_pass": True,
            "accepted_performance_smoke": optional_evidence_ref(accepted_paths.get("performance_smoke"), "recorded"),
        },
    )
    write_json(
        evidence_dir / f"{prefix}-final-verification.json",
        {
            "schema_version": 1,
            "target_id": spec.get("target_id"),
            "slice_id": slice_id,
            "status": "passed" if semantic_pass else "incomplete",
            "semantic_pass": semantic_pass,
            "source_commit": source_commit(spec),
            "fixture": {"path": fixture_path(spec), "sha256": accepted["fixture_sha256"]},
            "rust_check_status": rust_check.get("status"),
            "c_oracle_status": oracle.get("status"),
            "c2rust_baseline": c2rust_baseline_ref(spec, evidence_dir, c2rust_baseline),
            "route_decision": route_decision_ref(spec, evidence_dir, route_decision),
            "validation_profile": validation_profile_ref(spec, evidence_dir, validation_profile),
            "skipped_gates": validation_profile.get("skipped_gates", []),
            "validation_profile_status": validation_profile.get("status"),
            "toolchain_status": "C_ORACLE_GENERATED",
            "rust_report_status": reports["rust_report"].get("status"),
            "schema_diff_status": reports["diff"].get("status"),
            "negative_diff_mutation_detected": mutation_detected(reports["negative_diff"]),
            "unsafe_status": reports["unsafe_scan"].get("status"),
            "version_config_status": "recorded",
            "accepted_evidence_authoritative": accepted_evidence_authoritative_route(route_decision),
            "generated_draft_semantic_pass": False,
            "oracle_boundary_contract": validation_profile.get("oracle_boundary_contract"),
            "alias_gate": alias_gate,
            "external_callee_scope": external_callee_claim_scope(external_context),
            "accepted_evidence_binding": accepted_binding_summary(accepted),
        },
    )
    write_json(
        evidence_dir / f"{prefix}-summary.json",
        {
            "schema_version": 1,
            "target_id": spec.get("target_id"),
            "slice_id": slice_id,
            "status": "passed" if semantic_pass else "blocked",
            "semantic_pass": semantic_pass,
            "summary": "Auto-translation run completed with accepted C oracle, Rust replay, diff, negative diff, unsafe, version/cache, and final-verification evidence binding.",
            "generated_draft_semantic_pass": False,
            "accepted_evidence_binding": accepted_binding_summary(accepted),
        },
    )
    write_json(
        evidence_dir / f"{prefix}-version-manifest.json",
        {
            "schema_version": 1,
            "target_id": spec.get("target_id"),
            "slice_id": slice_id,
            "status": "recorded",
            "semantic_pass": semantic_pass,
            "source_commit": source_commit(spec),
            "repo_commit": repo_commit(),
            "cache": cache,
            "translator_version": "0.1.0",
            "accepted_evidence_binding": accepted_binding_summary(accepted),
            "repo_commit_note": "Accepted source reports may have been generated at an earlier repo commit; this manifest binds their file hashes for drift review.",
        },
    )


def mark_config_profile_recorded(spec: dict[str, Any], evidence_dir: Path, accepted: dict[str, Any]) -> None:
    path = evidence_dir / f"l3-{required_str(spec, 'slice_id')}-config-profile.json"
    payload = read_json(path)
    payload["status"] = "recorded"
    payload["accepted_evidence_binding"] = accepted_binding_summary(accepted)
    write_json(path, payload)


def required_repo_path(value: Any, field: str) -> Path:
    path = optional_repo_path(value)
    if path is None:
        raise SystemExit(f"--accept-existing-evidence requires {field}")
    if not path.exists():
        raise SystemExit(f"--accept-existing-evidence requires existing {field}: {path}")
    return path


def optional_repo_path(value: Any) -> Path | None:
    if not value:
        return None
    path = Path(str(value))
    return path if path.is_absolute() else REPO_ROOT / path


def derive_evidence_path(c_oracle_path: Path, old_suffix: str, new_suffix: str) -> Path:
    name = c_oracle_path.name
    if name.endswith("-c-oracle.json"):
        return c_oracle_path.with_name(name[: -len("-c-oracle.json")] + new_suffix)
    if name.endswith(old_suffix):
        return c_oracle_path.with_name(name[: -len(old_suffix)] + new_suffix)
    return c_oracle_path.with_name(c_oracle_path.stem + new_suffix)


def default_unsafe_scan_path(spec: dict[str, Any], c_oracle_path: Path) -> Path:
    target_id = str(spec.get("target_id", ""))
    slice_id = required_str(spec, "slice_id")
    if target_id == "zlib-ng":
        return REPO_ROOT / "validation" / "evidence" / "l2-slices" / "unsafe-scan.json"
    return c_oracle_path.parent / f"l3-{slice_id}-unsafe-scan.json"


def default_unsafe_ledger_path(spec: dict[str, Any], c_oracle_path: Path) -> Path:
    target_id = str(spec.get("target_id", ""))
    slice_id = required_str(spec, "slice_id")
    if target_id == "zlib-ng":
        return REPO_ROOT / "validation" / "evidence" / "l2-slices" / "unsafe-ledger.json"
    return c_oracle_path.parent / f"l3-{slice_id}-unsafe-ledger.json"


def optional_default_evidence(spec: dict[str, Any], name: str) -> Path | None:
    target_id = str(spec.get("target_id", ""))
    slice_id = required_str(spec, "slice_id")
    candidate = REPO_ROOT / "validation" / "evidence" / target_id / f"l3-{slice_id}-{name}.json"
    return candidate if candidate.exists() else None


def require_accepted_report(
    spec: dict[str, Any],
    label: str,
    report: dict[str, Any],
    require_toolchain: bool = False,
) -> None:
    status = str(report.get("status", ""))
    if status not in {"passed", "expected_failed"}:
        raise SystemExit(f"--accept-existing-evidence requires {label}.status passed/expected_failed, got {status!r}")
    report_commit = report.get("source_commit")
    if report_commit and report_commit != source_commit(spec):
        raise SystemExit(
            f"--accept-existing-evidence source_commit mismatch for {label}: {report_commit} != {source_commit(spec)}"
        )
    if require_toolchain and report.get("toolchain_status") != "C_ORACLE_GENERATED":
        raise SystemExit(f"--accept-existing-evidence requires {label}.toolchain_status=C_ORACLE_GENERATED")


def mutation_detected(report: dict[str, Any]) -> bool:
    return bool(report.get("mutation_detected") or report.get("detected"))


def unsafe_count_from_report(report: dict[str, Any]) -> int:
    for key in ["first_party_non_test_unsafe_count", "unsafe_count"]:
        value = report.get(key)
        if isinstance(value, int):
            return value
    hits = report.get("hits")
    return len(hits) if isinstance(hits, list) else 0


def optional_evidence_ref(path_text: str | None, status: str) -> dict[str, Any]:
    if not path_text:
        return {"status": "not_applicable"}
    return evidence_ref(REPO_ROOT / path_text, status)


def accepted_binding_summary(accepted: dict[str, Any] | None) -> dict[str, Any] | None:
    if accepted is None:
        return None
    return {
        "status": accepted.get("status"),
        "target_id": accepted.get("target_id"),
        "slice_id": accepted.get("slice_id"),
        "source_commit": accepted.get("source_commit"),
        "fixture_path": accepted.get("fixture_path"),
        "fixture_sha256": accepted.get("fixture_sha256"),
        "toolchain_status": accepted.get("toolchain_status"),
        "generated_draft_semantic_pass": accepted.get("generated_draft_semantic_pass"),
        "paths": accepted.get("paths", {}),
        "path_sha256": accepted.get("path_sha256", {}),
        "binding_boundary": accepted.get("binding_boundary"),
    }


def write_l3_config_profile(spec: dict[str, Any], evidence_dir: Path) -> None:
    slice_id = required_str(spec, "slice_id")
    build = spec.get("build_profile", {})
    target = build.get("target", {})
    translator_input = evidence_dir / f"l3-{slice_id}-translator-input.json"
    write_json(
        evidence_dir / f"l3-{slice_id}-config-profile.json",
        {
            "schema_version": 1,
            "level": "L3",
            "target_id": spec.get("target_id"),
            "slice_id": slice_id,
            "profile_id": build_profile_id(spec),
            "status": "incomplete",
            "source_commit": source_commit(spec),
            "repo_commit": repo_commit(),
            "fixture": {
                "path": fixture_path(spec),
                "hash": fixture_hash(spec),
                "operation_count": len(spec.get("fixture_contract", {}).get("cases", [])),
            },
            "config_header": {
                "path": rel(translator_input),
                "sha256": sha256(translator_input) if translator_input.exists() else "missing",
                "role": "normalized translator input and build profile",
            },
            "c_defines": defines_to_object(build.get("defines", [])),
            "feature_matrix": {"auto_translation_candidate": True},
            "compile_profile": {
                "c_oracle_command": "review and compile generated C oracle harness in WSL/Linux/CI",
                "include_paths": build.get("include_paths", []),
                "config_header_included": True,
                "command_args": [build.get("compiler_command_source", "unknown")],
            },
            "rust_profile": {
                "package": spec.get("rust_boundary", {}).get("crate", "c2r-translator"),
                "cargo_features": [],
                "feature_env": "none",
                "backend": "generated-draft",
            },
            "toolchain": {
                "rustc_version": "captured_by_rust_check",
                "cargo_version": "captured_by_validation",
                "openspec_version": "captured_by_validation",
                "target_triple_or_abi": target.get("triple_or_abi") or build.get("target_triple") or "unknown",
            },
            "cache_invalidation_keys": cache_keys(spec, translator_input),
            "non_goals": non_goals(spec),
        },
    )


def write_context_pack(
    spec: dict[str, Any],
    slice_spec_path: Path,
    evidence_dir: Path,
    call_expressions: list[dict[str, Any]] | None = None,
    external_callee_context: dict[str, Any] | None = None,
) -> None:
    slice_id = required_str(spec, "slice_id")
    context = external_callee_context or external_direct_callee_context(spec, call_expressions)
    payload = {
        "schema_version": 1,
        "level": "L3",
        "target_id": spec.get("target_id"),
        "slice_id": slice_id,
        "status": "recorded",
        "source_commit": source_commit(spec),
        "repo_commit": repo_commit(),
        "slice_spec": {"path": rel(slice_spec_path), "sha256": sha256(slice_spec_path)},
        "direct_c_files": [item["path"] for item in spec.get("c_boundary", {}).get("files", [])]
        or spec.get("source_files", []),
        "direct_rust_files": [spec.get("rust_boundary", {}).get("module") or spec.get("rust_boundary", {}).get("module_path", "")],
        "call_edges": spec.get("c_boundary", {}).get("direct_dependencies", []),
        "global_dependencies": global_dependency_requirements(spec),
        "source_boundary": source_boundary(spec),
        "direct_call_edges": call_expressions or [],
        "external_direct_callees": context["declared"],
        "external_direct_callee_blocks": context["blocked"],
        "callee_sources": external_callee_sources(context),
        "signature_bindings": external_signature_bindings(context),
        "stub_boundaries": external_stub_boundaries(context),
        "call_edge_to_callee_binding": call_edge_to_callee_binding(call_expressions or [], context),
        "fixture": spec.get("fixture_contract", {}).get("path") or spec.get("fixture_contract", {}).get("input"),
        "cache_invalidation_keys": cache_keys(spec, slice_spec_path),
    }
    write_json(evidence_dir / f"l3-{slice_id}-context-pack.json", payload)


def write_auto_translation_events(spec: dict[str, Any], slice_spec_path: Path, evidence_dir: Path) -> None:
    slice_id = required_str(spec, "slice_id")
    target_id = required_str(spec, "target_id")
    prefix = f"l3-{slice_id}"
    timestamp = "2026-06-24T00:00:00Z"
    plan_path = evidence_dir / f"{prefix}-auto-translation-plan.json"
    plan = read_json(plan_path) if plan_path.exists() else {}
    translation_source = translation_source_from_plan(plan)
    event_defs = [
        ("input-normalized", "input_normalized", "recorded", slice_spec_path),
        ("context-extracted", "context_extracted", "recorded", evidence_dir / f"{prefix}-context-pack.json"),
        ("type-map-emitted", "type_map_emitted", "recorded", evidence_dir / f"{prefix}-type-map.json"),
        ("cfg-emitted", "cfg_emitted", "recorded", evidence_dir / f"{prefix}-cfg.json"),
        ("pointer-graph-emitted", "pointer_graph_emitted", "recorded", evidence_dir / f"{prefix}-pointer-graph.json"),
        ("rust-draft-generated", "rust_draft_generated", "recorded", evidence_dir / f"{prefix}-rust-draft.rs"),
        ("run-completed", "run_completed", "skipped", evidence_dir / f"{prefix}-evidence-manifest.json"),
    ]
    events = []
    for suffix, kind, status, artifact in event_defs:
        events.append(
            {
                "schema_version": 1,
                "event_id": f"{target_id}-{slice_id}-{suffix}",
                "timestamp_utc": timestamp,
                "target_id": target_id,
                "slice_id": slice_id,
                "event_kind": kind,
                "status": status,
                "message": event_message(kind),
                "artifact_refs": [evidence_ref(artifact, status)],
            }
        )
    if translation_source.get("fallback_from"):
        events.insert(
            -1,
            {
                "schema_version": 1,
                "event_id": f"{target_id}-{slice_id}-translation-fallback",
                "timestamp_utc": timestamp,
                "target_id": target_id,
                "slice_id": slice_id,
                "event_kind": "translation_fallback",
                "status": "recorded",
                "message": "Rust draft provenance recorded a compatibility fallback translator path.",
                "selected": translation_source["selected"],
                "fallback_from": translation_source["fallback_from"],
                "fallback_reason": translation_source.get("fallback_reason", "unspecified"),
                "artifact_refs": [evidence_ref(plan_path, "recorded")],
            },
        )
    write_text(
        evidence_dir / f"{prefix}-auto-translation-events.jsonl",
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
    )


def event_message(kind: str) -> str:
    messages = {
        "input_normalized": "Slice spec normalized for bounded auto translation.",
        "context_extracted": "Context pack evidence emitted before accepting Rust draft.",
        "type_map_emitted": "Type map evidence emitted before accepting Rust draft.",
        "cfg_emitted": "CFG evidence emitted before accepting Rust draft.",
        "pointer_graph_emitted": "Pointer graph evidence emitted before accepting safe public boundary.",
        "rust_draft_generated": "Rust draft candidate generated.",
        "run_completed": "Candidate generation completed; semantic acceptance gates remain incomplete.",
    }
    return messages.get(kind, kind)


def evidence_ref(path: Path, status: str) -> dict[str, Any]:
    payload: dict[str, Any] = {"path": rel(path), "status": status}
    if path.exists() and path.is_file():
        payload["sha256"] = sha256(path)
    return payload


def pointer_status_for_manifest(spec: dict[str, Any], evidence_dir: Path) -> str:
    slice_id = required_str(spec, "slice_id")
    path = evidence_dir / f"l3-{slice_id}-pointer-graph.json"
    if not path.exists():
        return "incomplete"
    try:
        return str(read_json(path).get("status", "recorded"))
    except json.JSONDecodeError:
        return "incomplete"


def alias_gate_from_pointer_graph(evidence_dir: Path, slice_id: str) -> dict[str, Any]:
    path = evidence_dir / f"l3-{slice_id}-pointer-graph.json"
    if not path.exists():
        return {
            "decision": "missing",
            "risk_level": "unknown",
            "requires_noalias": True,
            "complete_alias_safety": False,
        }
    pointer_graph = read_json(path)
    contract = pointer_graph.get("alias_contract", {})
    if contract:
        return {
            "decision": contract.get("decision", "unknown"),
            "risk_level": (pointer_graph.get("alias_risks") or [{}])[0].get("risk_level", "none"),
            "requires_noalias": bool(contract.get("requires_noalias", False)),
            "complete_alias_safety": bool(contract.get("complete_alias_safety", False)),
            "risk_count": len(pointer_graph.get("alias_risks", [])),
            "preconditions": pointer_graph.get("safe_boundary_preconditions", []),
        }
    return {
        "decision": "not_applicable" if pointer_graph.get("status") == "not_applicable" else "missing",
        "risk_level": "none" if pointer_graph.get("status") == "not_applicable" else "unknown",
        "requires_noalias": False,
        "complete_alias_safety": False,
        "risk_count": 0,
        "preconditions": [],
    }


def effect_graph_from_pointer_nodes(
    pointer_nodes: list[dict[str, Any]],
    alias_gate: dict[str, Any],
) -> dict[str, Any]:
    effects: list[dict[str, Any]] = []
    read_effect_ids_by_node: dict[str, list[str]] = {}
    write_effect_ids_by_node: dict[str, list[str]] = {}

    for node in pointer_nodes:
        node_id = str(node.get("id", ""))
        if not node_id:
            continue
        for raw_effect in node.get("read_effects", []):
            expression = pointer_effect_expression(raw_effect)
            if not expression:
                continue
            effect_id = f"effect-{len(effects) + 1}"
            effects.append(
                {
                    "id": effect_id,
                    "pointer_node": node_id,
                    "kind": "read",
                    "expression": expression,
                    "source": "pointer_nodes.read_effects",
                }
            )
            read_effect_ids_by_node.setdefault(node_id, []).append(effect_id)
        for raw_effect in node.get("write_effects", []):
            expression = pointer_effect_expression(raw_effect)
            if not expression:
                continue
            effect_id = f"effect-{len(effects) + 1}"
            effects.append(
                {
                    "id": effect_id,
                    "pointer_node": node_id,
                    "kind": "write",
                    "expression": expression,
                    "source": "pointer_nodes.write_effects",
                }
            )
            write_effect_ids_by_node.setdefault(node_id, []).append(effect_id)

    edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str]] = set()
    for risk in alias_gate.get("alias_risks", []):
        members = [str(item) for item in risk.get("pointer_nodes", []) if item]
        relationship = "requires_noalias" if risk.get("requires_noalias") else "may_alias"
        for read_node in members:
            for write_node in members:
                if read_node == write_node:
                    continue
                for read_effect_id in read_effect_ids_by_node.get(read_node, []):
                    for write_effect_id in write_effect_ids_by_node.get(write_node, []):
                        key = (read_effect_id, write_effect_id, relationship)
                        if key in seen_edges:
                            continue
                        seen_edges.add(key)
                        edges.append(
                            {
                                "from_effect": read_effect_id,
                                "to_effect": write_effect_id,
                                "relationship": relationship,
                                "evidence": f"{risk.get('id', 'alias-risk')} covers {read_node}/{write_node}",
                            }
                        )

    return {
        "effects": effects,
        "edges": edges,
        "summary": {
            "reads": sorted(read_effect_ids_by_node),
            "writes": sorted(write_effect_ids_by_node),
            "read_count": sum(len(values) for values in read_effect_ids_by_node.values()),
            "write_count": sum(len(values) for values in write_effect_ids_by_node.values()),
            "external_state": [],
            "alias_sensitive": bool(alias_gate.get("is_alias_sensitive", False)),
            "alias_gate_decision": alias_gate.get("summary", {}).get("decision", "unknown"),
        },
    }


def pointer_effect_expression(raw_effect: Any) -> str:
    if isinstance(raw_effect, dict):
        return str(raw_effect.get("expression", "")).strip()
    return str(raw_effect).strip()


def fixture_path(spec: dict[str, Any]) -> str:
    fixture = spec.get("fixture_contract", {})
    return fixture.get("path") or fixture.get("input") or "unknown-fixture"


def build_profile_id(spec: dict[str, Any]) -> str:
    build = spec.get("build_profile", {})
    return build.get("profile_id") or f"{spec.get('target_id', 'target')}-{spec.get('slice_id', 'slice')}-auto-profile"


def behavior_fields(spec: dict[str, Any]) -> list[str]:
    fixture = spec.get("fixture_contract", {})
    fields = fixture.get("observable_outputs") or fixture.get("behavior_fields") or []
    return [str(item) for item in fields]


def oracle_boundary_contract(
    spec: dict[str, Any],
    accepted: dict[str, Any] | None = None,
    oracle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fixture = spec.get("fixture_contract", {})
    build = spec.get("build_profile", {})
    c_boundary = spec.get("c_boundary", {})
    target = build.get("target", {})
    if not isinstance(target, dict):
        target = {}
    accepted_reports = accepted.get("reports", {}) if isinstance(accepted, dict) else {}
    accepted_oracle = accepted_reports.get("c_oracle", {}) if isinstance(accepted_reports, dict) else {}
    if not isinstance(accepted_oracle, dict):
        accepted_oracle = {}
    oracle_report = oracle if isinstance(oracle, dict) else {}
    platform = c_boundary.get("platform_contract", {})
    if not isinstance(platform, dict):
        platform = {}

    declared_case_count = len(fixture.get("cases") or [])
    accepted_case_count = accepted_oracle.get("case_count") or oracle_report.get("case_count")
    diagnostics = list_of_strings(build.get("diagnostics"))
    clang_type = build.get("clang_type_extraction", {})
    if isinstance(clang_type, dict):
        diagnostics.extend(list_of_strings(clang_type.get("diagnostics")))
    diagnostics.extend(list_of_strings(c_boundary.get("diagnostics")))

    hardware_dependencies = list_of_strings(
        c_boundary.get("hardware_dependencies") or platform.get("hardware_dependencies")
    )
    rtos_dependencies = list_of_strings(c_boundary.get("rtos_dependencies") or platform.get("rtos_dependencies"))
    volatile_dependencies = list_of_strings(
        c_boundary.get("volatile_dependencies") or platform.get("volatile_dependencies")
    )
    pointer_width = target.get("pointer_width", build.get("pointer_width", build.get("word_size_bits", "unknown")))
    compiler_command_source = (
        build.get("compiler_command_source")
        or build.get("compile_commands")
        or build.get("compile_commands_path")
        or "unknown"
    )
    contract = {
        "schema_version": 1,
        "observable_outputs": behavior_fields(spec),
        "fixture_representativeness": {
            "fixture_path": fixture_path(spec),
            "fixture_hash": fixture_hash(spec),
            "declared_case_count": declared_case_count,
            "case_source": fixture.get("case_source", "fixture_contract"),
            "representativeness": fixture.get("representativeness", "bounded_fixture_contract"),
            "limitations": list_of_strings(fixture.get("limitations")),
        },
        "compiler": {
            "command_source": compiler_command_source,
            "compile_commands": build.get("compile_commands") or build.get("compile_commands_path"),
            "include_paths": list_of_strings(build.get("include_paths")),
            "defines": list_of_strings(build.get("defines")),
            "flags": list_of_strings(build.get("flags") or build.get("cflags")),
            "tool_versions": build.get("tool_versions", {}),
        },
        "target": {
            "triple_or_abi": target.get("triple_or_abi") or build.get("target_triple") or build.get("abi") or "unknown",
            "endianness": target.get("endianness", build.get("endianness", "unknown")),
            "int_width": target.get("int_width", build.get("int_width", "unknown")),
            "char_width": target.get("char_width", build.get("char_width", "unknown")),
            "plain_char_signed": target.get("plain_char_signed", build.get("plain_char_signed", "unknown")),
            "short_width": target.get("short_width", build.get("short_width", "unknown")),
            "long_width": target.get("long_width", build.get("long_width", "unknown")),
            "long_long_width": target.get("long_long_width", build.get("long_long_width", "unknown")),
            "pointer_width": pointer_width,
            "word_size_bits": pointer_width,
        },
        "sanitizer_diagnostics": {
            "sanitizer_status": c_boundary.get("sanitizer_status", build.get("sanitizer_status", "not_run")),
            "diagnostic_status": "recorded" if diagnostics else "none_recorded",
            "diagnostics": diagnostics,
            "clang_type_extraction_available": clang_type.get("available") if isinstance(clang_type, dict) else None,
        },
        "ub_and_implementation_defined": {
            "known_ub": list_of_strings(c_boundary.get("known_ub")),
            "implementation_defined_behavior": list_of_strings(c_boundary.get("implementation_defined_behavior")),
            "scalar_arithmetic_contract": c_boundary.get("scalar_arithmetic_contract", {}),
        },
        "platform_model": {
            "hardware_dependencies": hardware_dependencies,
            "rtos_dependencies": rtos_dependencies,
            "volatile_dependencies": volatile_dependencies,
            "hardware_dependency_status": dependency_status(platform, "hardware_dependency_status", hardware_dependencies),
            "rtos_dependency_status": dependency_status(platform, "rtos_dependency_status", rtos_dependencies),
            "volatile_dependency_status": dependency_status(platform, "volatile_dependency_status", volatile_dependencies),
        },
    }
    if isinstance(accepted_case_count, int):
        contract["fixture_representativeness"]["accepted_oracle_case_count"] = accepted_case_count
    insufficient = oracle_boundary_insufficient_reasons(contract)
    contract["status"] = "insufficient" if insufficient else "sufficient_for_semantic_pass"
    contract["insufficient_reasons"] = insufficient
    return contract


def oracle_boundary_contract_sufficient(contract: Any) -> bool:
    return isinstance(contract, dict) and contract.get("status") == "sufficient_for_semantic_pass"


def dependency_status(platform: dict[str, Any], key: str, dependencies: list[str]) -> str:
    status = platform.get(key)
    if isinstance(status, str) and status:
        return status
    return "unmodeled" if dependencies else "not_applicable"


def list_of_strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def oracle_boundary_insufficient_reasons(contract: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not contract.get("observable_outputs"):
        reasons.append("observable_outputs_missing")
    fixture = contract.get("fixture_representativeness", {})
    declared_case_count = fixture.get("declared_case_count")
    accepted_case_count = fixture.get("accepted_oracle_case_count")
    if not positive_int_like(declared_case_count):
        reasons.append("fixture_declared_case_count_missing")
    if not positive_int_like(accepted_case_count):
        reasons.append("fixture_accepted_oracle_case_count_missing")
    if positive_int_like(declared_case_count) and positive_int_like(accepted_case_count):
        if accepted_case_count < declared_case_count:
            reasons.append("fixture_accepted_oracle_case_count_below_declared")
    compiler = contract.get("compiler", {})
    if missing_boundary_value(compiler.get("command_source")):
        reasons.append("compiler_command_source_missing")
    target = contract.get("target", {})
    if missing_boundary_value(target.get("triple_or_abi")):
        reasons.append("target_triple_or_abi_missing")
    if missing_boundary_value(target.get("endianness")) or target.get("endianness") not in {"little", "big"}:
        reasons.append("target_endianness_missing")
    for key in ["int_width", "long_width", "pointer_width", "word_size_bits"]:
        if missing_boundary_value(target.get(key)):
            reasons.append(f"target_{key}_missing")
        elif not positive_int_like(target.get(key)):
            reasons.append(f"target_{key}_invalid")
    for key in ["char_width", "short_width", "long_long_width"]:
        if not missing_boundary_value(target.get(key)) and not positive_int_like(target.get(key)):
            reasons.append(f"target_{key}_invalid")
    if (
        not missing_boundary_value(target.get("plain_char_signed"))
        and not isinstance(target.get("plain_char_signed"), bool)
    ):
        reasons.append("target_plain_char_signed_invalid")
    sanitizer = contract.get("sanitizer_diagnostics", {})
    if missing_boundary_value(sanitizer.get("sanitizer_status"), allow_not_run=True):
        reasons.append("sanitizer_status_missing")
    ub = contract.get("ub_and_implementation_defined", {})
    if not isinstance(ub.get("known_ub"), list):
        reasons.append("known_ub_boundary_missing")
    if not isinstance(ub.get("implementation_defined_behavior"), list):
        reasons.append("implementation_defined_boundary_missing")
    platform = contract.get("platform_model", {})
    for key in ["hardware_dependency_status", "rtos_dependency_status", "volatile_dependency_status"]:
        if missing_boundary_value(platform.get(key)) or platform.get(key) == "unmodeled":
            reasons.append(f"platform_{key}_missing")
    return reasons


def missing_boundary_value(value: Any, allow_not_run: bool = False) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        if allow_not_run and value == "not_run":
            return False
        return value.strip() in {"", "unknown", "not_recorded", "missing"}
    return False


def positive_int_like(value: Any) -> bool:
    return isinstance(value, int) and value > 0


def accepted_metadata_differences(spec: dict[str, Any]) -> list[str]:
    boundary = spec.get("claim_boundary", {})
    values = spec.get("accepted_metadata_differences") or boundary.get("accepted_metadata_differences") or []
    return [str(item) for item in values]


def non_goals(spec: dict[str, Any]) -> list[str]:
    boundary = spec.get("claim_boundary", {})
    values = spec.get("non_goals") or boundary.get("non_goals") or []
    return [str(item) for item in values]


def must_not_claim(spec: dict[str, Any]) -> list[str]:
    boundary = spec.get("claim_boundary", {})
    values = boundary.get("must_not_claim") or []
    return [str(item) for item in values]


def defines_to_object(defines: list[Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in defines:
        text = str(item)
        if "=" in text:
            key, value = text.split("=", 1)
            result[key] = value
        else:
            result[text] = True
    if not result:
        result["none"] = True
    return result


def lvalue_decisions(statements: list[str], lvalue_kinds: list[str]) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    for index, kind in enumerate(lvalue_kinds):
        if kind == "none":
            continue
        decision = lvalue_decision_for_kind(kind)
        decisions.append(
            {
                "statement_index": index,
                "source_statement": statements[index] if index < len(statements) else "",
                "lvalue_kind": kind,
                "decision": decision,
                "translation_rule_id": lvalue_translation_rule(kind),
                "source_span": source_span(),
            }
        )
    return decisions


def cfg_basic_blocks(raw_blocks: list[Any]) -> list[dict[str, Any]]:
    if not raw_blocks:
        return [
            {
                "id": "entry",
                "kind": "entry",
                "statements": [],
                "statement_kinds": [],
                "lvalue_kinds": [],
                "lvalue_decisions": [],
                "source_span": source_span(),
            }
        ]
    blocks: list[dict[str, Any]] = []
    for index, raw_block in enumerate(raw_blocks):
        if not isinstance(raw_block, dict):
            continue
        block_id = str(raw_block.get("id") or ("entry" if index == 0 else f"block-{index}"))
        statements = [str(item) for item in raw_block.get("statements", [])]
        statement_kinds = [str(item) for item in raw_block.get("statement_kinds", [])]
        lvalue_kinds = [str(item) for item in raw_block.get("lvalue_kinds", [])]
        blocks.append(
            {
                "id": block_id,
                "kind": cfg_block_kind(block_id, str(raw_block.get("terminator", "")), index),
                "statements": statements,
                "statement_kinds": statement_kinds,
                "lvalue_kinds": lvalue_kinds,
                "lvalue_decisions": lvalue_decisions(statements, lvalue_kinds),
                "terminator": str(raw_block.get("terminator", "")),
                "source_span": source_span(),
            }
        )
    return blocks


def cfg_block_kind(block_id: str, terminator: str, index: int) -> str:
    if block_id == "entry" or index == 0:
        return "entry"
    if terminator.startswith("unsupported_"):
        return "unsupported"
    if terminator == "return":
        return "return"
    if terminator in {"if", "switch"}:
        return "branch"
    if terminator in {"while", "for"}:
        return "loop_header"
    return "body"


def cfg_edges(raw_blocks: list[Any]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for raw_block in raw_blocks:
        if not isinstance(raw_block, dict):
            continue
        for raw_edge in raw_block.get("edges", []):
            edge = cfg_edge_from_raw(str(raw_edge))
            if edge is None:
                continue
            key = (edge["from"], edge["to"], edge["kind"])
            if key in seen:
                continue
            seen.add(key)
            edges.append(edge)
    if not edges:
        edges.append({"from": "entry", "to": "return", "kind": "return", "source_span": source_span()})
    return edges


def cfg_edge_from_raw(raw_edge: str) -> dict[str, Any] | None:
    if "->" not in raw_edge:
        return None
    from_block, to_block = [part.strip() for part in raw_edge.split("->", 1)]
    if not from_block or not to_block:
        return None
    return {
        "from": from_block,
        "to": to_block,
        "kind": cfg_edge_kind(from_block, to_block),
        "source_span": source_span(),
    }


def cfg_edge_kind(from_block: str, to_block: str) -> str:
    if to_block.startswith("return"):
        return "return"
    if from_block.startswith("goto-") or to_block.startswith(("goto-", "label-", "switch-", "case-", "default")):
        return "unsupported"
    return "unsupported"


def lvalue_decision_for_kind(kind: str) -> str:
    return {
        "simple_identifier": "value_assignment",
        "pointer_field": "safe_wrapper",
        "deref_identifier": "safe_wrapper",
        "bounded_pointer_index": "bounded_pointer_index",
        "bounded_input_buffer": "bounded_input_buffer",
        "bounded_pointer_arithmetic_input_buffer": "bounded_pointer_arithmetic_input_read",
        "bounded_pointer_arithmetic_output_buffer": "bounded_pointer_arithmetic_output_write",
        "unsupported_lvalue": "unsupported_lvalue",
    }.get(kind, "unknown")


def lvalue_translation_rule(kind: str) -> str:
    return {
        "simple_identifier": "assignment",
        "pointer_field": "pointer-field-write",
        "deref_identifier": "pointer-deref-write",
        "bounded_pointer_index": "bounded-pointer-index-write",
        "bounded_input_buffer": "bounded-input-buffer-read",
        "bounded_pointer_arithmetic_input_buffer": "bounded-pointer-arithmetic-input-read",
        "bounded_pointer_arithmetic_output_buffer": "bounded-pointer-arithmetic-output-write",
        "unsupported_lvalue": "unsupported-lvalue-block",
    }.get(kind, "unknown-lvalue")


def pointer_decisions(pointer_nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    for node in pointer_nodes:
        for decision in node.get("boundary_decisions", []):
            decisions.append(
                {
                    "id": f"pointer-decision-{len(decisions) + 1}",
                    "pointer_node": node.get("id", ""),
                    "source_statement": pointer_decision_source_statement(node),
                    "lvalue_kind": pointer_decision_lvalue_kind(decision),
                    "decision": decision,
                    "reason": "bounded translator pointer/lvalue decision",
                    "translation_rule_id": pointer_decision_translation_rule(decision),
                    "unsafe_expected": False,
                    "source_span": source_span(),
                }
            )
    return decisions


def pointer_decision_source_statement(node: dict[str, Any]) -> str:
    if node.get("write_effects"):
        return str(node["write_effects"][0])
    if node.get("read_effects"):
        return str(node["read_effects"][0])
    return ""


def pointer_decision_lvalue_kind(decision: str) -> str:
    if decision == "bounded_pointer_index":
        return "bounded_pointer_index"
    if decision == "bounded_input_buffer":
        return "bounded_input_buffer"
    if decision == "byte_cursor_post_increment_read":
        return "bounded_input_buffer"
    if decision == "bounded_pointer_arithmetic_input_read":
        return "bounded_pointer_arithmetic_input_buffer"
    if decision == "bounded_pointer_arithmetic_output_write":
        return "bounded_pointer_arithmetic_output_buffer"
    return "pointer_write"


def pointer_decision_translation_rule(decision: str) -> str:
    if decision == "bounded_pointer_index":
        return "bounded-pointer-index-write"
    if decision == "bounded_input_buffer":
        return "bounded-input-buffer-read"
    if decision == "byte_cursor_post_increment_read":
        return "byte-cursor-post-increment-read"
    if decision == "bounded_pointer_arithmetic_input_read":
        return "bounded-pointer-arithmetic-input-read"
    if decision == "bounded_pointer_arithmetic_output_write":
        return "bounded-pointer-arithmetic-output-write"
    return "pointer-field-write"


def count_occurrences(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        text = str(value)
        counts[text] = counts.get(text, 0) + 1
    return counts


def rust_draft_unsafe_count(path: Path) -> int:
    if not path.exists():
        return 0
    return len(re.findall(r"\bunsafe\b", path.read_text(encoding="utf-8")))


def generated_artifact(path: Path, kind: str) -> dict[str, Any]:
    return {
        "path": rel(path),
        "kind": kind,
        "generator": {"name": "c2r-translator", "version": "0.1.0"},
        "source_spans": [source_span()],
        "generated_spans": [source_span(file=rel(path))],
        "status": "candidate",
    }


def source_span(file: str = "slice-spec") -> dict[str, Any]:
    return {"file": file, "line_start": 1, "line_end": 1}


def global_dependency_requirements(spec: dict[str, Any]) -> list[dict[str, Any]]:
    requirements: list[dict[str, Any]] = []
    seen: set[str] = set()
    for dependency in spec.get("c_boundary", {}).get("direct_dependencies", []):
        if dependency.get("kind") != "global":
            continue
        name = str(dependency.get("name") or "")
        if not name or name in seen:
            continue
        seen.add(name)
        span = dependency.get("source_span") if isinstance(dependency.get("source_span"), dict) else source_span()
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


def source_commit(spec: dict[str, Any]) -> str:
    return spec.get("source_commit") or spec.get("source", {}).get("source_commit") or "UNKNOWN0"


def fixture_hash(spec: dict[str, Any]) -> str:
    fixture = spec.get("fixture_contract", {})
    return spec.get("fixture_hash") or fixture.get("hash") or "UNKNOWN_FIXTURE"


def repo_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    except Exception:
        return "UNKNOWN0"


def cache_keys(spec: dict[str, Any], slice_spec_path: Path) -> list[str]:
    return [
        f"source_commit={source_commit(spec)}",
        f"slice_spec_sha256={sha256(slice_spec_path)}",
        f"fixture_hash={fixture_hash(spec)}",
        f"build_profile_hash={sha256_json(spec.get('build_profile', {}))}",
        "translator_version=0.1.0",
        "schema_version=1",
    ]


def cache_identity(
    spec: dict[str, Any],
    slice_spec_path: Path,
    accept_existing_evidence: bool = False,
    emit_clang_dry_run: bool = False,
    emit_clang_lowering_report: bool = False,
    competition_clang_lane: bool = False,
    c2rust_baseline: dict[str, Any] | None = None,
    route_decision: dict[str, Any] | None = None,
    validation_profile: dict[str, Any] | None = None,
    oracle: dict[str, Any] | None = None,
    environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build the cache key material for drift-sensitive evidence reuse.

    The identity includes route decision, validation profile, C2Rust baseline,
    global dependencies, clang-lowering options, and oracle-harness inputs so a
    reused run cannot silently cross route/profile/cache boundaries after any
    semantically relevant artifact changes.
    """
    effective_emit_clang_lowering_report = emit_clang_lowering_report or competition_clang_lane
    command_arguments = ["auto_migrate.py", "--slice-spec", rel(slice_spec_path)]
    if accept_existing_evidence:
        command_arguments.append("--accept-existing-evidence")
    if emit_clang_dry_run:
        command_arguments.append("--emit-clang-dry-run")
    if effective_emit_clang_lowering_report:
        command_arguments.append("--emit-clang-lowering-report")
    if competition_clang_lane:
        command_arguments.append("--competition-clang-lane")
    identity = {
        "source_commit": source_commit(spec),
        "source_file_hashes": source_file_hashes(spec),
        "slice_spec_sha256": sha256(slice_spec_path),
        "fixture_hash": fixture_hash(spec),
        "build_profile_hash": sha256_json(spec.get("build_profile", {})),
        "competition_environment_identity": competition_environment_identity(),
        "cargo_lock_hash": sha256(TRANSLATOR_LOCK) if TRANSLATOR_LOCK.exists() else "missing",
        "tool_versions": tool_versions(),
        "schema_versions": {
            "auto_cache_metadata": 1,
            "auto_translation_plan": 1,
            "cfg": 1,
            "evidence_manifest": 1,
            "pointer_graph": POINTER_GRAPH_SCHEMA_VERSION,
            "type_map": 1,
        },
        "translator_version": "0.1.0",
        "translator_manifest_sha256": sha256(TRANSLATOR_MANIFEST),
        "command_arguments": command_arguments,
        "alias_gate_identity": alias_gate_identity(spec),
        "effect_graph_identity": effect_graph_identity(spec),
        "scalar_ub_contract_identity": scalar_ub_contract_identity(spec),
        "oracle_boundary_contract_identity": oracle_boundary_contract_identity(validation_profile),
        "c2rust_baseline_identity": artifact_cache_identity(c2rust_baseline),
        "route_decision_identity": artifact_cache_identity(route_decision),
        "validation_profile_identity": artifact_cache_identity(validation_profile),
        "global_dependency_identity": {
            "sha256": sha256_json(global_dependency_requirements(spec)),
            "count": len(global_dependency_requirements(spec)),
            "names": [item["name"] for item in global_dependency_requirements(spec)],
        },
        "c_oracle_harness_identity": oracle_harness_identity(oracle),
    }
    if effective_emit_clang_lowering_report:
        identity["translator_feature_set"] = translator_feature_set(
            emit_clang_dry_run=emit_clang_dry_run,
            emit_clang_lowering_report=effective_emit_clang_lowering_report,
        )
        identity["clang_lowering_identity"] = clang_lowering_identity(
            environment=environment,
            competition_clang_lane=competition_clang_lane,
        )
    return identity


def competition_environment_identity() -> dict[str, str]:
    profile = read_json(COMPETITION_ENVIRONMENT_PROFILE)
    return {
        "profile_id": str(profile.get("profile_id", "unknown")),
        "path": rel(COMPETITION_ENVIRONMENT_PROFILE),
        "sha256": sha256(COMPETITION_ENVIRONMENT_PROFILE),
    }


LOCAL_CLANG_CANDIDATES = (
    "tools/llvm/bin/clang",
    "tools/llvm/bin/clang-18",
    "tools/clang/bin/clang",
    "tools/llvm/bin/clang.exe",
    "tools/llvm/bin/clang-18.exe",
    "tools/clang/bin/clang.exe",
)


def resolve_competition_clang_path(
    *, environment: dict[str, str] | None = None, repo_root: Path = REPO_ROOT
) -> tuple[str, str] | None:
    env = os.environ if environment is None else environment
    clang_path = str(env.get("CLANG_PATH", "")).strip()
    if clang_path:
        return clang_path, "CLANG_PATH"
    for candidate in LOCAL_CLANG_CANDIDATES:
        path = repo_root / candidate
        if path.exists():
            return rel(path) if repo_root == REPO_ROOT else candidate, f"vendored:{candidate}"
    return None


def require_competition_clang_lane(*, environment: dict[str, str] | None = None) -> None:
    if resolve_competition_clang_path(environment=environment) is not None:
        return
    raise SystemExit(
        "competition clang lane requires CLANG_PATH or a project-local clang binary under "
        "tools/llvm/bin/ or tools/clang/bin/; omit --competition-clang-lane to keep the "
        "diagnostic/fail-closed non-clang lane."
    )


def clang_lowering_identity(
    *, environment: dict[str, str] | None = None, competition_clang_lane: bool = False
) -> dict[str, Any]:
    env = os.environ if environment is None else environment
    resolved_clang = resolve_competition_clang_path(environment=env)
    clang_path = resolved_clang[0] if resolved_clang else ""
    libclang_path = str(env.get("LIBCLANG_PATH", "")).strip()
    clang_path_status = "configured" if clang_path else "not_configured"
    libclang_path_status = "configured" if libclang_path else "not_configured"
    if clang_path:
        clang_version = command_version([clang_path, "--version"])
    else:
        clang_version = "not_configured"
    identity = {
        "enabled": True,
        "frontend": "clang_ast_dump_json",
        "command": "clang -Xclang -ast-dump=json -fsyntax-only",
        "features": ["clang-lowering-report"],
        "requires_env": ["CLANG_PATH"],
        "clang_path_status": clang_path_status,
        "clang_path": clang_path,
        "ignored_env_for_ast_dump": {
            "LIBCLANG_PATH": {
                "status": libclang_path_status,
                "value": libclang_path,
                "reason": "ignored_for_ast_dump",
            }
        },
        "clang_version": clang_version,
    }
    if competition_clang_lane:
        identity.update(
            {
                "lane": "competition-clang-lane",
                "required": True,
                "requires_env": ["CLANG_PATH"],
                "ignored_env_for_ast_dump": identity["ignored_env_for_ast_dump"],
            }
        )
    return identity


def alias_gate_identity(spec: dict[str, Any]) -> dict[str, Any]:
    pointer_contract = spec.get("c_boundary", {}).get("pointer_contract", {})
    pointer_nodes = pointer_nodes_from_pointer_contract(pointer_contract)
    gate = alias_gate_evidence(spec, [node for node in pointer_nodes if node["id"]])
    return {
        "decision": gate["summary"]["decision"],
        "risk_count": gate["summary"].get("risk_count", 0),
        "risk_level": gate["summary"]["risk_level"],
        "aliasing_proven": bool(pointer_contract.get("aliasing_proven", False)),
        "requires_noalias": bool(gate["summary"]["requires_noalias"]),
        "precondition_count": len(gate["safe_boundary_preconditions"]),
        "alias_set_count": len(gate["alias_sets"]),
    }


def effect_graph_identity(spec: dict[str, Any]) -> dict[str, Any]:
    pointer_contract = spec.get("c_boundary", {}).get("pointer_contract", {})
    pointer_nodes = pointer_nodes_from_pointer_contract(pointer_contract)
    gate = alias_gate_evidence(spec, [node for node in pointer_nodes if node["id"]])
    graph = effect_graph_from_pointer_nodes(pointer_nodes, gate)
    summary = graph["summary"]
    return {
        "schema_version": POINTER_GRAPH_SCHEMA_VERSION,
        "sha256": sha256_json(graph),
        "read_effect_count": summary["read_count"],
        "write_effect_count": summary["write_count"],
        "read_nodes": summary["reads"],
        "write_nodes": summary["writes"],
        "alias_sensitive": summary["alias_sensitive"],
        "alias_gate_decision": summary["alias_gate_decision"],
    }


def pointer_nodes_from_pointer_contract(pointer_contract: dict[str, Any]) -> list[dict[str, Any]]:
    pointer_nodes = []
    for item in pointer_contract.get("input_buffers", []):
        pointer_nodes.append(
            {
                "id": str(item.get("name", "")),
                "read_effects": item.get("read_effects", []),
                "write_effects": item.get("write_effects", []),
            }
        )
    for item in pointer_contract.get("output_pointers", []):
        pointer_nodes.append(
            {
                "id": str(item.get("name", "")),
                "read_effects": item.get("read_effects", []),
                "write_effects": item.get("write_effects", []),
            }
        )
    for item in pointer_contract.get("inout_pointers", []):
        pointer_nodes.append(
            {
                "id": str(item.get("name", "")),
                "read_effects": item.get("read_effects", []),
                "write_effects": item.get("write_effects", []),
            }
        )
    return pointer_nodes


def cache_drift_report(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    fields = cache_drift_input_fields(previous, current)
    drifted_keys = [
        key for key in fields if previous.get(key) != current.get(key)
    ]
    if not drifted_keys:
        return {
            "schema_version": 1,
            "status": "reusable",
            "reuse_allowed": True,
            "drifted_keys": [],
            "invalidated_artifacts": [],
        }
    return {
        "schema_version": 1,
        "status": "drift_detected",
        "reuse_allowed": False,
        "drifted_keys": drifted_keys,
        "invalidated_artifacts": CACHE_INVALIDATED_ARTIFACTS,
        "required_action": "regenerate artifacts or attach explicit evidence review before reuse",
    }


def cache_drift_input_fields(previous: dict[str, Any], current: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    for source in (
        CACHE_INPUT_FIELDS,
        previous.get("cache_input_fields", []),
        current.get("cache_input_fields", []),
    ):
        if not isinstance(source, list):
            continue
        for field in source:
            if isinstance(field, str) and field not in fields:
                fields.append(field)
    return fields


def source_file_hashes(spec: dict[str, Any]) -> dict[str, str]:
    declared_hashes = {
        str(path): str(value)
        for path, value in spec.get("source", {}).get("source_file_hashes", {}).items()
        if value
    }
    file_entries = [item for item in spec.get("c_boundary", {}).get("files", []) if item.get("path")]
    files = [item["path"] for item in file_entries]
    files.extend(str(item) for item in spec.get("source_files", []))
    result: dict[str, str] = {}
    source_root = spec.get("source", {}).get("source_root")
    for file_name in sorted(set(files)):
        matching_entry = next((item for item in file_entries if item.get("path") == file_name), {})
        explicit_hash = declared_hashes.get(file_name) or matching_entry.get("sha256")
        path = REPO_ROOT / file_name
        if path.exists() and path.is_file():
            result[file_name] = sha256(path)
            continue
        if source_root:
            source_path = Path(str(source_root)) / file_name
            if source_path.exists() and source_path.is_file():
                result[file_name] = sha256(source_path)
                continue
        result[file_name] = str(explicit_hash) if explicit_hash else "missing"
    return result


def tool_versions() -> dict[str, str]:
    return {
        "python": command_version(["python", "--version"]),
        "rustc": command_version(["rustc", "--version"]),
        "cargo": command_version(["cargo", "--version"]),
        "openspec": command_version(
            ["openspec", "--version"],
            fallback=["powershell", "-NoProfile", "-Command", "openspec --version"],
        ),
    }


def command_version(cmd: list[str], fallback: list[str] | None = None) -> str:
    try:
        result = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        if fallback is None:
            return "unavailable"
        return command_version(fallback)
    text = (result.stdout or result.stderr).strip()
    if result.returncode != 0 and not text:
        return f"unavailable:{result.returncode}"
    return text.splitlines()[0] if text else "unknown"


def type_mapping_kind(c_type: str) -> str:
    if "*" in c_type:
        return "pointer"
    if c_type in {"int", "unsigned int", "uint32_t", "char", "unsigned char"}:
        return "primitive"
    if c_type.startswith("struct "):
        return "struct"
    return "unsupported"


def function_signature(spec: dict[str, Any]) -> str:
    signatures = spec.get("c_boundary", {}).get("signatures", [])
    if signatures:
        signature = signatures[0]
        params = ", ".join(
            f"{param.get('c_type')} {param.get('name')}" for param in signature.get("parameters", [])
        )
        return f"{signature.get('return_type')} {signature.get('function')}({params})"
    return spec.get("c_source", "").split("{", 1)[0].strip()


def extract_return_expression(statements: list[str]) -> str:
    for statement in statements:
        if statement.strip().startswith("return"):
            return statement.strip()[len("return") :].strip()
    return ""


def count_token(text: str, token: str) -> int:
    return len(re.findall(rf"\b{re.escape(token)}\b", text))


def source_boundary(spec: dict[str, Any]) -> dict[str, Any]:
    c_boundary = spec.get("c_boundary", {})
    files = [item["path"] for item in c_boundary.get("files", [])] or spec.get("source_files", [])
    functions = c_boundary.get("functions") or [spec.get("function_name", "unknown")]
    global_dependencies = global_dependency_requirements(spec)
    return {
        "files": files,
        "functions": functions,
        "structs": [dep.get("name") for dep in c_boundary.get("direct_dependencies", []) if dep.get("kind") == "type"],
        "globals": [item["name"] for item in global_dependencies],
        "direct_call_edges": [],
    }


def blocked_repairs_payload(spec: dict[str, Any], repairs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "target_id": spec.get("target_id"),
        "slice_id": spec.get("slice_id"),
        "status": "recorded" if repairs else "none",
        "blocked_repairs": repairs,
        "cache_invalidation_keys": [
            f"source_commit={source_commit(spec)}",
            f"fixture_hash={fixture_hash(spec)}",
            "patch_plan_schema=1",
        ],
    }


def rustc_error_code(error: dict[str, Any]) -> str:
    code = error.get("code")
    if isinstance(code, dict) and code.get("code"):
        return str(code["code"])
    return "rustc_error"


def required_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise SystemExit(f"slice spec must include non-empty string `{key}`")
    return value


def safe_ident(text: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in text)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    write_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_log_text(path: Path, text: str) -> None:
    if text:
        write_text(path, text)
    elif path.exists():
        path.unlink()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
