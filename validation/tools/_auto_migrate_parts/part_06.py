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


def write_l3_config_profile(spec: dict[str, Any], evidence_dir: Path, slice_spec_path: Path) -> None:
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
            "cache_invalidation_keys": cache_keys(spec, slice_spec_path),
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
        "external_direct_callee_declarations": context["declarations"],
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
            "int_align": target.get("int_align", build.get("int_align", "unknown")),
            "char_width": target.get("char_width", build.get("char_width", "unknown")),
            "char_align": target.get("char_align", build.get("char_align", "unknown")),
            "plain_char_signed": target.get("plain_char_signed", build.get("plain_char_signed", "unknown")),
            "short_width": target.get("short_width", build.get("short_width", "unknown")),
            "short_align": target.get("short_align", build.get("short_align", "unknown")),
            "long_width": target.get("long_width", build.get("long_width", "unknown")),
            "long_align": target.get("long_align", build.get("long_align", "unknown")),
            "long_long_width": target.get("long_long_width", build.get("long_long_width", "unknown")),
            "long_long_align": target.get("long_long_align", build.get("long_long_align", "unknown")),
            "pointer_width": pointer_width,
            "pointer_align": target.get("pointer_align", build.get("pointer_align", "unknown")),
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
    for key in [
        "char_width",
        "short_width",
        "long_long_width",
        "int_align",
        "char_align",
        "short_align",
        "long_align",
        "long_long_align",
        "pointer_align",
    ]:
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


def source_identity(spec: dict[str, Any]) -> dict[str, Any]:
    source = spec.get("source", {})
    if not isinstance(source, dict):
        source = {}
    identity: dict[str, Any] = {"source_commit": source_commit(spec)}
    for key in ["repo_commit", "source_root", "source_repository", "source_branch"]:
        value = source.get(key, spec.get(key))
        if value:
            identity[key] = value
    source_file_hashes = source.get("source_file_hashes", spec.get("source_file_hashes"))
    if isinstance(source_file_hashes, dict) and source_file_hashes:
        identity["source_file_hashes"] = source_file_hashes
    return identity


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
