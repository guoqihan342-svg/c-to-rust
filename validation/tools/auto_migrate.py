#!/usr/bin/env python3
"""Run the bounded auto-translation pipeline for a slice spec."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
TRANSLATOR_MANIFEST = REPO_ROOT / "crates" / "c2r-translator" / "Cargo.toml"
TRANSLATOR_LOCK = REPO_ROOT / "crates" / "c2r-translator" / "Cargo.lock"
CACHE_INPUT_FIELDS = [
    "source_commit",
    "source_file_hashes",
    "slice_spec_sha256",
    "fixture_hash",
    "build_profile_hash",
    "cargo_lock_hash",
    "tool_versions",
    "schema_versions",
    "translator_version",
    "translator_manifest_sha256",
    "command_arguments",
    "alias_gate_identity",
    "c2rust_baseline_identity",
    "route_decision_identity",
    "validation_profile_identity",
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
        "--accept-existing-evidence",
        action="store_true",
        help="Bind already accepted oracle/replay/diff/unsafe evidence from the slice spec instead of claiming the generated draft is accepted.",
    )
    args = parser.parse_args()

    spec = read_json(args.slice_spec)
    target_id = required_str(spec, "target_id")
    slice_id = required_str(spec, "slice_id")
    evidence_dir = args.out_root / target_id / "auto-translation" / slice_id
    evidence_dir.mkdir(parents=True, exist_ok=True)

    translator_spec = write_translator_spec(spec, args.slice_spec, evidence_dir)
    translator_summary = run_translator(translator_spec, evidence_dir)
    normalize_translation_artifacts(spec, args.slice_spec, evidence_dir)
    c2rust_baseline = emit_c2rust_baseline_manifest(spec, args.slice_spec, evidence_dir)
    route_decision = emit_route_decision(spec, evidence_dir, translator_summary, c2rust_baseline)
    oracle = generate_oracle_harness_draft(spec, evidence_dir, args.skip_c_oracle)
    replay = generate_rust_replay_test_draft(spec, evidence_dir)
    rust_check, patch = run_rust_check(evidence_dir, args.skip_rust_check, spec)
    accepted = resolve_accepted_evidence(spec) if args.accept_existing_evidence else None
    if accepted is not None:
        oracle = promote_accepted_oracle(spec, evidence_dir, oracle, accepted)
        replay = promote_accepted_test_translation(spec, evidence_dir, replay, accepted)
    validation_profile = emit_validation_profile(spec, evidence_dir, route_decision, oracle, rust_check, accepted)
    if route_decision.get("level") == "L4":
        patch = write_route_refused_patch(spec, evidence_dir, route_decision)
    cache = emit_cache_metadata(
        spec,
        args.slice_spec,
        evidence_dir,
        c2rust_baseline=c2rust_baseline,
        route_decision=route_decision,
        validation_profile=validation_profile,
        accept_existing_evidence=args.accept_existing_evidence,
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
            "target_triple": spec.get("build_profile", {}).get("target_triple") or target.get("triple_or_abi"),
            "abi": spec.get("build_profile", {}).get("abi") or target.get("triple_or_abi"),
            "compiler_command_source": build_profile.get("compiler_command_source", "unknown"),
            "clang_available": bool(build_profile.get("clang_available", clang.get("available", False))),
        },
    }
    path = evidence_dir / f"l3-{spec['slice_id']}-translator-input.json"
    write_json(path, translator_spec)
    return path


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
    callee_names = sorted(
        {
            str(call.get("callee"))
            for call in (call_expressions or [])
            if call.get("callee") and str(call.get("callee")) != entry_name
        }
    )
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


def run_translator(slice_spec: Path, evidence_dir: Path) -> dict[str, Any]:
    cmd = [
        "cargo",
        "run",
        "--quiet",
        "--manifest-path",
        str(TRANSLATOR_MANIFEST),
        "--bin",
        "c2r_translate",
        "--",
        "--slice-spec",
        str(slice_spec),
        "--out-dir",
        str(evidence_dir),
    ]
    result = subprocess.run(cmd, cwd=REPO_ROOT, text=True, capture_output=True)
    write_log_text(evidence_dir / "translator-command.stdout.log", result.stdout)
    write_log_text(evidence_dir / "translator-command.stderr.log", result.stderr)
    if result.returncode != 0:
        raise SystemExit(f"translator failed with exit code {result.returncode}; see {evidence_dir}")
    return json.loads(result.stdout)


def normalize_translation_artifacts(spec: dict[str, Any], slice_spec_path: Path, evidence_dir: Path) -> None:
    """Rewrite raw translator artifacts to the stricter evidence template schemas."""
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
            "cache_invalidation_keys": cache_keys(spec, slice_spec_path),
        },
    )

    raw_cfg = read_json(evidence_dir / f"{prefix}-cfg.json")
    raw_functions = raw_cfg.get("cfg", {}).get("functions", [])
    unsupported_cf = []
    functions = []
    for function in raw_functions:
        unsupported = function.get("unsupported_control_flow", [])
        unsupported_cf.extend(
            {
                "id": f"unsupported-{idx + 1}",
                "kind": "goto" if item == "goto" else "unknown",
                "reason": f"{item} requires CFG/relooper support",
                "source_span": source_span(),
                "translation_effect": "requires_relooper",
            }
            for idx, item in enumerate(unsupported)
        )
        blocks = function.get("blocks", [])
        statements = blocks[0].get("statements", []) if blocks else []
        statement_kinds = blocks[0].get("statement_kinds", []) if blocks else []
        lvalue_kinds = blocks[0].get("lvalue_kinds", []) if blocks else []
        functions.append(
            {
                "name": function.get("name", required_str(spec, "slice_id")),
                "signature": function_signature(spec),
                "source_span": source_span(),
                "entry_block": "entry",
                "exit_blocks": ["return"] if blocks and blocks[0].get("terminator") == "return" else ["exit"],
                "basic_blocks": [
                    {
                        "id": "entry",
                        "kind": "entry",
                        "statements": statements,
                        "statement_kinds": statement_kinds,
                        "lvalue_kinds": lvalue_kinds,
                        "lvalue_decisions": lvalue_decisions(statements, lvalue_kinds),
                        "source_span": source_span(),
                    }
                ],
                "edges": [
                    {"from": "entry", "to": "return", "kind": "return", "source_span": source_span()}
                ],
                "branches": [],
                "returns": [
                    {"block": "entry", "expression": extract_return_expression(statements), "source_span": source_span()}
                ],
                "structured_control_flow": {
                    "if_count": count_token(spec.get("c_source", ""), "if"),
                    "loop_count": count_token(spec.get("c_source", ""), "while") + count_token(spec.get("c_source", ""), "for"),
                    "has_goto": any(item.get("kind") == "goto" for item in unsupported_cf),
                    "has_switch": "switch" in unsupported,
                    "relooper_required": bool(unsupported),
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
    pointer_cache_keys = cache_keys(spec, slice_spec_path) + alias_gate["cache_invalidation_keys"]
    pointer_status = "recorded" if pointer_nodes else "not_applicable"
    pointer_payload = {
        "schema_version": 1,
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


def pointer_node_kind(node: dict[str, Any]) -> str:
    if "bounded_pointer_arithmetic_output_write" in node.get("boundary_decisions", []):
        return "buffer"
    if node.get("role") == "out_param":
        return "struct_pointer"
    if str(node.get("c_type", "")).strip() == "const int*":
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
        for param in signature.get("parameters", []):
            if param.get("name") == pointer_id and param.get("buffer_length_parameter"):
                return str(param["buffer_length_parameter"])
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


def generate_oracle_harness_draft(spec: dict[str, Any], evidence_dir: Path, skip: bool) -> dict[str, Any]:
    slice_id = required_str(spec, "slice_id")
    function_name = required_str(spec, "function_name")
    fixture = spec.get("fixture_contract", {})
    c_path = evidence_dir / f"l3-{slice_id}-c-oracle-harness-draft.c"
    report_path = evidence_dir / f"l3-{slice_id}-c-oracle-status.json"
    source = (
        "/* Auto-generated C oracle harness draft. */\n"
        "/* Review and compile against the pinned L1 source tree before using as oracle evidence. */\n"
        "#include <stdint.h>\n"
        "#include <stdio.h>\n\n"
        f"/* slice: {spec.get('target_id')}/{slice_id} */\n"
        f"/* function: {function_name} */\n"
        "int main(void) {\n"
        f"  puts(\"oracle harness draft for {function_name}\");\n"
        "  return 0;\n"
        "}\n"
    )
    write_text(c_path, source)
    status = "SKIPPED_LOCAL_NO_C_TOOLCHAIN" if skip else "DRAFT_GENERATED"
    payload = {
        "schema_version": 1,
        "target_id": spec.get("target_id"),
        "slice_id": slice_id,
        "status": status,
        "semantic_pass": False,
        "harness_draft": rel(c_path),
        "fixture": fixture.get("input"),
        "required_final_status": "C_ORACLE_GENERATED",
        "boundary": "Draft generation is not oracle success.",
    }
    write_json(report_path, payload)
    return payload


def generate_rust_replay_test_draft(spec: dict[str, Any], evidence_dir: Path) -> dict[str, Any]:
    slice_id = required_str(spec, "slice_id")
    function_name = required_str(spec, "function_name")
    path = evidence_dir / f"l3-{slice_id}-rust-replay-test-draft.rs"
    fixture = spec.get("fixture_contract", {})
    text = (
        "// Auto-generated Rust replay test draft.\n"
        "// Review before promoting into validation/l2_slices/tests.\n\n"
        "#[test]\n"
        f"fn replay_{safe_ident(slice_id)}_fixture_contract() {{\n"
        f"    let _fixture = {fixture.get('input', '')!r};\n"
        f"    let _api = {function_name!r};\n"
        "    // TODO: bind fixture cases to generated Rust API assertions.\n"
        "}\n"
    )
    write_text(path, text)
    fixture_path = fixture.get("path") or fixture.get("input") or "unknown-fixture"
    behavior_fields = fixture.get("observable_outputs") or fixture.get("behavior_fields", [])
    test_name = f"replay_{safe_ident(slice_id)}_fixture_contract"
    payload = {
        "schema_version": 1,
        "target_id": spec.get("target_id"),
        "slice_id": slice_id,
        "level": spec.get("level", "L3"),
        "status": "recorded",
        "test_draft": rel(path),
        "fixture": fixture_path,
        "behavior_fields": list(behavior_fields),
        "source_commit": source_commit(spec),
        "repo_commit": repo_commit(),
        "source_test_inputs": {
            "oracle_strategy": "Generated replay draft from slice fixture contract; accepted semantics still require C_ORACLE_GENERATED.",
            "fixtures": [
                {
                    "path": fixture_path,
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
                "source": fixture_path,
                "rust_test": f"{rel(path)}::{test_name}",
                "behavior_fields": list(behavior_fields),
                "coverage_kind": "oracle_replay",
                "status": "gap",
                "evidence": [
                    {
                        "path": rel(evidence_dir / f"l3-{slice_id}-c-oracle-status.json"),
                        "status": "not_semantic_pass",
                    }
                ],
            }
        ],
        "evidence_links": {
            "rust_draft": {"path": rel(evidence_dir / f"l3-{slice_id}-rust-draft.rs"), "status": "candidate"},
            "c_oracle": {"path": rel(evidence_dir / f"l3-{slice_id}-c-oracle-status.json"), "status": "draft_or_skipped"},
        },
        "known_gaps": [
            "Generated replay test is a draft until accepted C oracle and Rust replay reports are produced."
        ],
        "cache_invalidation_keys": cache_keys(spec, evidence_dir / f"l3-{slice_id}-translator-input.json"),
    }
    write_json(evidence_dir / f"l3-{slice_id}-test-translation-generated.json", payload)
    return payload


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


def emit_cache_metadata(
    spec: dict[str, Any],
    slice_spec: Path,
    evidence_dir: Path,
    c2rust_baseline: dict[str, Any] | None = None,
    route_decision: dict[str, Any] | None = None,
    validation_profile: dict[str, Any] | None = None,
    accept_existing_evidence: bool = False,
) -> dict[str, Any]:
    identity = cache_identity(
        spec,
        slice_spec,
        accept_existing_evidence,
        c2rust_baseline,
        route_decision,
        validation_profile,
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
        "cache_input_fields": CACHE_INPUT_FIELDS,
        "invalidates": CACHE_INVALIDATED_ARTIFACTS,
    }
    write_json(evidence_dir / f"l3-{spec.get('slice_id')}-auto-cache-metadata.json", payload)
    return payload


def artifact_cache_identity(artifact: dict[str, Any] | None) -> dict[str, Any]:
    if artifact is None:
        return {"status": "missing", "sha256": "missing"}
    return {
        "status": artifact.get("status", "unknown"),
        "sha256": sha256_json(artifact),
    }


def emit_c2rust_baseline_manifest(spec: dict[str, Any], slice_spec: Path, evidence_dir: Path) -> dict[str, Any]:
    slice_id = required_str(spec, "slice_id")
    prefix = f"l3-{slice_id}"
    commands = c2rust_command_candidates()
    selected = next((item for item in commands if item.get("path")), None)
    reference_tree = Path("F:/agent/c2rust-master")
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
            "path": str(reference_tree),
            "status": reference_status,
            "cargo_toml": str(reference_tree / "Cargo.toml") if reference_tree.exists() else "",
        },
        "output": None,
        "diagnostics": diagnostics,
        "must_not_claim": [
            "C2Rust output proves semantic equivalence",
            "C2Rust baseline was generated" if status != "generated" else "",
        ],
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


def emit_route_decision(
    spec: dict[str, Any],
    evidence_dir: Path,
    translator_summary: dict[str, Any],
    c2rust_baseline: dict[str, Any],
) -> dict[str, Any]:
    slice_id = required_str(spec, "slice_id")
    prefix = f"l3-{slice_id}"
    type_map = read_json(evidence_dir / f"{prefix}-type-map.json")
    cfg = read_json(evidence_dir / f"{prefix}-cfg.json")
    pointer = read_json(evidence_dir / f"{prefix}-pointer-graph.json")
    plan = read_json(evidence_dir / f"{prefix}-auto-translation-plan.json")
    level, rationale = route_level(spec, translator_summary, type_map, cfg, pointer, plan)
    translator = route_translator(level)
    profile = validation_profile_name(level, "dev")
    decision = {
        "schema_version": 1,
        "target_id": spec.get("target_id"),
        "slice_id": slice_id,
        "status": "refused" if level == "L4" else "recorded",
        "level": level,
        "translator": translator,
        "rationale": rationale,
        "verification_profile": profile,
        "source_artifacts": {
            "type_map": evidence_ref(evidence_dir / f"{prefix}-type-map.json", type_map.get("status", "recorded")),
            "cfg": evidence_ref(evidence_dir / f"{prefix}-cfg.json", cfg.get("status", "recorded")),
            "pointer_graph": evidence_ref(evidence_dir / f"{prefix}-pointer-graph.json", pointer.get("status", "recorded")),
            "translation_plan": evidence_ref(
                evidence_dir / f"{prefix}-auto-translation-plan.json",
                plan.get("status", "recorded"),
            ),
            "c2rust_baseline": c2rust_baseline_ref(spec, evidence_dir, c2rust_baseline),
        },
        "policy": {
            "goal": "dev",
            "fixed_loop_count_required": False,
            "repair_budget_source": "run_policy",
        },
        "misroute": None,
    }
    write_json(evidence_dir / f"{prefix}-route-decision.json", decision)
    return decision


def route_level(
    spec: dict[str, Any],
    translator_summary: dict[str, Any],
    type_map: dict[str, Any],
    cfg: dict[str, Any],
    pointer: dict[str, Any],
    plan: dict[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    rationale: list[dict[str, Any]] = []
    blocked_statuses = {
        "translator": translator_summary.get("status"),
        "type_map": type_map.get("status"),
        "cfg": cfg.get("status"),
        "plan": plan.get("status"),
    }
    if any(value == "blocked" for value in blocked_statuses.values()):
        rationale.append({"feature": "blocked_artifact", "values": blocked_statuses, "weight": "hard_refuse"})
        return "L4", rationale
    if cfg.get("unsupported_control_flow"):
        rationale.append({"feature": "unsupported_control_flow", "weight": "hard_refuse"})
        return "L4", rationale
    pointer_nodes = pointer.get("pointer_nodes", [])
    if not pointer_nodes:
        rationale.append({"feature": "scalar_only", "weight": "low"})
        return "L0", rationale
    alias_contract = pointer.get("alias_contract", {})
    if alias_contract.get("decision") == "blocked":
        rationale.append({"feature": "alias_blocked", "weight": "high"})
        return "L3", rationale
    if any(node.get("ownership_role") == "unknown" for node in pointer_nodes):
        rationale.append({"feature": "unknown_pointer_role", "weight": "medium"})
        return "L2", rationale
    rationale.append({"feature": "bounded_pointer_surface", "weight": "low"})
    return "L1", rationale


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
    slice_id = required_str(spec, "slice_id")
    prefix = f"l3-{slice_id}"
    goal = route_decision.get("policy", {}).get("goal", "dev")
    level = str(route_decision.get("level", "L4"))
    profile = validation_profile_name(level, goal)
    required = required_gates_for_profile(level, goal)
    skipped = []
    if route_decision.get("translator", {}).get("kind") == "refuse":
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
    result = "passed" if not skipped and compile_passed and oracle_passed else "blocked" if level == "L4" else "incomplete"
    payload = {
        "schema_version": 1,
        "target_id": spec.get("target_id"),
        "slice_id": slice_id,
        "status": result,
        "profile": profile,
        "route_level": level,
        "goal": goal,
        "required_gates": required,
        "optional_gates": optional_gates_for_profile(level, goal),
        "skipped_gates": skipped,
        "required_gate_status": {
            "compile": rust_check.get("status"),
            "c_oracle_diff": oracle.get("status"),
        },
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
    if validation_profile.get("route_level") == "L4":
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
        "status": "accepted_evidence_bound" if semantic_pass else "candidate_generated",
        "source_commit": spec.get("source_commit"),
        "fixture": {
            "hash": spec.get("fixture_hash"),
            "path": spec.get("fixture_contract", {}).get("input"),
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
            "scope": "auto-translation candidate evidence only"
            if not semantic_pass
            else "auto-translation run with accepted evidence binding; generated Rust draft remains a candidate unless generated_draft_semantic_pass is true",
            "semantic_pass": semantic_pass,
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
    slice_id = required_str(spec, "slice_id")
    prefix = f"l3-{slice_id}"
    unsafe_count = rust_draft_unsafe_count(evidence_dir / f"{prefix}-rust-draft.rs")
    semantic_pass = semantic_pass_for_run(accepted, rust_check, validation_profile)
    alias_gate = alias_gate_from_pointer_graph(evidence_dir, slice_id)
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
            "status": "incomplete",
            "semantic_pass": False,
            "reason": "Generated Rust replay test is a draft; accepted Rust report has not been produced.",
            "replay": replay,
        },
    )
    write_json(
        evidence_dir / f"{prefix}-diff.json",
        {
            "schema_version": 1,
            "target_id": spec.get("target_id"),
            "slice_id": slice_id,
            "status": "incomplete",
            "semantic_pass": False,
            "first_mismatch": None,
            "reason": "Schema-aware diff requires accepted C oracle and Rust replay reports.",
        },
    )
    write_json(
        evidence_dir / f"{prefix}-negative-diff.json",
        {
            "schema_version": 1,
            "target_id": spec.get("target_id"),
            "slice_id": slice_id,
            "status": "incomplete",
            "expected_failure": True,
            "mutation_detected": False,
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
        "boundary": "C oracle success comes from accepted Linux/WSL/CI evidence, not from the draft harness alone.",
    }
    write_json(path, payload)
    return payload


def promote_accepted_test_translation(
    spec: dict[str, Any],
    evidence_dir: Path,
    replay: dict[str, Any],
    accepted: dict[str, Any],
) -> dict[str, Any]:
    slice_id = required_str(spec, "slice_id")
    path = evidence_dir / f"l3-{slice_id}-test-translation-generated.json"
    payload = read_json(path)
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
                "rust_draft": {"path": rel(evidence_dir / f"l3-{slice_id}-rust-draft.rs"), "status": "candidate"},
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
    slice_id = required_str(spec, "slice_id")
    prefix = f"l3-{slice_id}"
    accepted_paths = accepted["paths"]
    reports = accepted["reports"]
    unsafe_count = unsafe_count_from_report(reports["unsafe_scan"])
    semantic_pass = semantic_pass_for_run(accepted, rust_check, validation_profile)
    alias_gate = alias_gate_from_pointer_graph(evidence_dir, slice_id)
    external_context = external_direct_callee_context(spec, load_plan_call_expressions(evidence_dir, slice_id))
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
            "generated_draft": evidence_ref(evidence_dir / f"{prefix}-rust-draft.rs", "candidate"),
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
            "first_mismatch": reports["diff"].get("first_mismatch"),
            "compared_fields": reports["diff"].get("compared_fields") or behavior_fields(spec),
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
            "expected_failure": True,
            "mutation_detected": mutation_detected(reports["negative_diff"]),
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
            "status": "passed",
            "semantic_pass": True,
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
            "generated_draft_semantic_pass": False,
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
    c2rust_baseline: dict[str, Any] | None = None,
    route_decision: dict[str, Any] | None = None,
    validation_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    command_arguments = ["auto_migrate.py", "--slice-spec", rel(slice_spec_path)]
    if accept_existing_evidence:
        command_arguments.append("--accept-existing-evidence")
    return {
        "source_commit": source_commit(spec),
        "source_file_hashes": source_file_hashes(spec),
        "slice_spec_sha256": sha256(slice_spec_path),
        "fixture_hash": fixture_hash(spec),
        "build_profile_hash": sha256_json(spec.get("build_profile", {})),
        "cargo_lock_hash": sha256(TRANSLATOR_LOCK) if TRANSLATOR_LOCK.exists() else "missing",
        "tool_versions": tool_versions(),
        "schema_versions": {
            "auto_cache_metadata": 1,
            "auto_translation_plan": 1,
            "cfg": 1,
            "evidence_manifest": 1,
            "pointer_graph": 1,
            "type_map": 1,
        },
        "translator_version": "0.1.0",
        "translator_manifest_sha256": sha256(TRANSLATOR_MANIFEST),
        "command_arguments": command_arguments,
        "alias_gate_identity": alias_gate_identity(spec),
        "c2rust_baseline_identity": artifact_cache_identity(c2rust_baseline),
        "route_decision_identity": artifact_cache_identity(route_decision),
        "validation_profile_identity": artifact_cache_identity(validation_profile),
    }


def alias_gate_identity(spec: dict[str, Any]) -> dict[str, Any]:
    pointer_contract = spec.get("c_boundary", {}).get("pointer_contract", {})
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


def cache_drift_report(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    drifted_keys = [
        key for key in CACHE_INPUT_FIELDS if previous.get(key) != current.get(key)
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
    return {
        "files": files,
        "functions": functions,
        "structs": [dep.get("name") for dep in c_boundary.get("direct_dependencies", []) if dep.get("kind") == "type"],
        "globals": [],
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
