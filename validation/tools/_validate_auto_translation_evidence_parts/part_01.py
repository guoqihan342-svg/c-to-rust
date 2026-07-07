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
    if c_oracle_embeds_slice_source(spec):
        return "compile_harness_with_embedded_slice_source"
    if spec.get("build_profile", {}).get("link_source_files"):
        return "compile_harness_with_declared_c_boundary_and_build_profile_sources"
    return "compile_harness_with_declared_c_boundary_sources"


def c_oracle_source_mode(spec: dict[str, Any]) -> str:
    return str(spec.get("c_boundary", {}).get("oracle_source_mode") or "declared_c_boundary_sources")


def c_oracle_embeds_slice_source(spec: dict[str, Any]) -> bool:
    return c_oracle_source_mode(spec) == "embedded_slice_c_source"


def c_oracle_embedded_slice_source(spec: dict[str, Any]) -> str | None:
    if not c_oracle_embeds_slice_source(spec):
        return None
    c_source = spec.get("c_source")
    if isinstance(c_source, str) and c_source.strip():
        return c_source
    function_name = required_str(spec, "function_name")
    for signature in spec.get("c_boundary", {}).get("signatures", []):
        if not isinstance(signature, dict) or signature.get("function") != function_name:
            continue
        c_source = signature.get("c_source")
        if isinstance(c_source, str) and c_source.strip():
            return c_source
    return None


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
    """Ensure generated candidate diffs remain diagnostic, not semantic proof.

    A generated draft may replay and match the draft oracle output, but the
    report must remain blocked on accepted oracle evidence and must not set
    semantic_pass or generated_draft_semantic_pass. Accepted schema-diff checks
    are validated elsewhere.
    """
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


def validate_unsupported_control_flow_cfg_contract(cfg: dict[str, Any], label: str) -> None:
    unsupported = cfg.get("unsupported_control_flow")
    if not isinstance(unsupported, list) or not unsupported:
        return
    unsupported_kinds = {
        str(item.get("kind"))
        for item in unsupported
        if isinstance(item, dict) and item.get("kind")
    }
    functions = cfg.get("functions")
    if not isinstance(functions, list) or not functions:
        raise SystemExit(f"unsupported control-flow CFG contract missing functions in {label}")

    block_ids: set[str] = set()
    edge_pairs: set[tuple[str, str]] = set()
    saw_relooper_required = False
    saw_relooper_refusal = False
    for function in functions:
        if not isinstance(function, dict):
            continue
        structured = function.get("structured_control_flow")
        if not isinstance(structured, dict):
            raise SystemExit(f"unsupported control-flow CFG contract missing structured_control_flow in {label}")
        saw_relooper_required = saw_relooper_required or bool(structured.get("relooper_required"))
        refusals = structured.get("relooper_refusals")
        saw_relooper_refusal = saw_relooper_refusal or (isinstance(refusals, list) and bool(refusals))
        for block in function.get("basic_blocks", []):
            if isinstance(block, dict) and block.get("id"):
                block_ids.add(str(block["id"]))
        for edge in function.get("edges", []):
            if isinstance(edge, dict) and edge.get("from") and edge.get("to"):
                edge_pairs.add((str(edge["from"]), str(edge["to"])))

    if not saw_relooper_required or not saw_relooper_refusal:
        raise SystemExit(f"unsupported control-flow CFG contract missing relooper refusal evidence in {label}")
    if "goto" in unsupported_kinds:
        has_goto_block = any(block_id.startswith("goto-") for block_id in block_ids)
        has_label_block = any(block_id.startswith("label-") for block_id in block_ids)
        has_goto_to_label_edge = any(
            source.startswith("goto-") and target.startswith("label-")
            for source, target in edge_pairs
        )
        if not (has_goto_block and has_label_block and has_goto_to_label_edge):
            raise SystemExit(f"unsupported control-flow CFG contract missing goto/label block-edge evidence in {label}")
    if "switch" in unsupported_kinds:
        has_switch_block = any(block_id.startswith("switch-") for block_id in block_ids)
        has_case_or_default_block = any(
            block_id.startswith("case-") or block_id == "default"
            for block_id in block_ids
        )
        has_switch_edge = any(
            source.startswith("switch-")
            and (target.startswith("case-") or target == "default")
            for source, target in edge_pairs
        )
        if not (has_switch_block and has_case_or_default_block and has_switch_edge):
            raise SystemExit(f"unsupported control-flow CFG contract missing switch/case/default edge evidence in {label}")


def validate_typed_ir_candidate_binding(
    evidence_dir: Path,
    prefix: str,
    route: dict[str, Any],
    profile: dict[str, Any],
) -> None:
    """Bind typed-IR candidate metadata across route, profile, and clang report.

    Typed-IR can influence candidate routing and draft generation, but the same
    candidate_generation object must appear in route and profile evidence, and
    readonly-global identity must match the lowering report. The binding never
    upgrades typed-IR output to semantic-pass evidence.
    """
    route_candidate_generation = route.get("candidate_generation")
    if not isinstance(route_candidate_generation, dict):
        if profile.get("candidate_generation") is not None:
            raise SystemExit("validation_profile.candidate_generation must match route_decision.candidate_generation")
        return
    profile_candidate_generation = profile.get("candidate_generation")
    if profile_candidate_generation != route_candidate_generation:
        raise SystemExit("validation_profile.candidate_generation must match route_decision.candidate_generation")
    validate_candidate_selection_record(
        route_candidate_generation,
        evidence_dir=evidence_dir,
        prefix=prefix,
        route_level=route.get("level"),
        route_status=route.get("status"),
    )

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
    runtime_preconditions = report_candidate.get("runtime_preconditions", [])
    if not isinstance(runtime_preconditions, list):
        runtime_preconditions = []
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
        "runtime_preconditions": runtime_preconditions,
        "rust_draft_generated": bool(report_candidate.get("rust_draft_generated", False)),
        "semantic_pass": False,
    }
    if report_candidate.get("reason"):
        expected["reason"] = report_candidate.get("reason")
    if report_candidate.get("unsupported_reason"):
        expected["unsupported_reason"] = report_candidate.get("unsupported_reason")
    if report_candidate.get("typed_ir_sha256"):
        expected["typed_ir_sha256"] = report_candidate.get("typed_ir_sha256")
    if report_candidate.get("rust_draft_sha256"):
        expected["rust_draft_sha256"] = report_candidate.get("rust_draft_sha256")
    actual = {
        "status": typed_ir.get("status"),
        "candidate_route": typed_ir.get("candidate_route"),
        "readonly_globals": typed_ir.get("readonly_globals", []),
        "readonly_globals_identity": typed_ir.get("readonly_globals_identity"),
        "runtime_preconditions": typed_ir.get("runtime_preconditions", []),
        "rust_draft_generated": bool(typed_ir.get("rust_draft_generated", False)),
        "semantic_pass": typed_ir.get("semantic_pass"),
    }
    if typed_ir.get("reason"):
        actual["reason"] = typed_ir.get("reason")
    if typed_ir.get("unsupported_reason"):
        actual["unsupported_reason"] = typed_ir.get("unsupported_reason")
    if typed_ir.get("typed_ir_sha256"):
        actual["typed_ir_sha256"] = typed_ir.get("typed_ir_sha256")
    if typed_ir.get("rust_draft_sha256"):
        actual["rust_draft_sha256"] = typed_ir.get("rust_draft_sha256")
    if actual != expected:
        raise SystemExit("route_decision.candidate_generation.typed_ir drifted from clang-lowering-report")
    if runtime_preconditions and "scalar_admission" not in typed_ir:
        raise SystemExit("route_decision.candidate_generation.typed_ir.scalar_admission missing")
    if "scalar_admission" in typed_ir:
        expected_admission = scalar_admission_from_runtime_preconditions(
            route.get("scalar_ub_contract", {}),
            runtime_preconditions,
        )
        if typed_ir.get("scalar_admission") != expected_admission:
            raise SystemExit("route_decision.candidate_generation.typed_ir.scalar_admission drift")


def scalar_admission_from_runtime_preconditions(
    scalar_contract: Any,
    runtime_preconditions: Any,
) -> dict[str, Any]:
    preconditions = runtime_preconditions if isinstance(runtime_preconditions, list) else []
    contract = scalar_contract if isinstance(scalar_contract, dict) else {}
    if not preconditions:
        return {
            "status": "not_applicable",
            "precondition_count": 0,
            "covered": [],
            "unresolved": [],
            "contract_status": str(contract.get("status", "not_declared")),
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
        "contract_status": str(contract.get("status", "not_declared")),
        "source_fields": [
            "c_boundary.scalar_arithmetic_contract",
            "fixture_contract.scalar_input_domain",
            "claim_boundary.must_not_claim",
        ],
    }


def scalar_precondition_admission(code: str, contract: dict[str, Any]) -> dict[str, Any]:
    required_field, required_value = scalar_precondition_required_contract(code)
    c_contract = contract.get("c_boundary", {})
    if not isinstance(c_contract, dict):
        c_contract = {}
    fixture_contract = contract.get("fixture_contract", {})
    if not isinstance(fixture_contract, dict):
        fixture_contract = {}
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
    if code == "signed_left_shift_no_overflow":
        return "signed_left_shift", "runtime_precondition_no_overflow"
    if code == "signed_negation_no_overflow":
        return "signed_negation", "runtime_precondition_no_overflow"
    return None, None


def validate_candidate_selection_record(
    candidate_generation: dict[str, Any],
    *,
    evidence_dir: Path | None = None,
    prefix: str | None = None,
    route_level: Any | None = None,
    route_status: Any | None = None,
) -> None:
    """Validate candidate selection provenance without accepting a candidate.

    The selected id must refer to the candidate set, the policy must not claim a
    full router or semantic acceptance, and each candidate must keep semantic
    flags false. The C2Rust candidate is additionally constrained to
    candidate_context_only.
    """
    candidate_set = candidate_generation.get("candidate_set")
    selected_candidate_id = candidate_generation.get("selected_candidate_id")
    selection_policy = candidate_generation.get("selection_policy")
    c2rust_baseline = candidate_generation.get("c2rust_baseline")
    primary_candidate = candidate_generation.get("primary_candidate")
    compatibility_sources = candidate_generation.get("compatibility_sources")
    strict_generated_record = candidate_generation.get("generated_draft_semantic_pass") is False
    if candidate_generation.get("generated_draft_semantic_pass") is True:
        raise SystemExit("route_decision.candidate_generation cannot claim generated_draft_semantic_pass")
    if (
        candidate_set is None
        and selected_candidate_id is None
        and selection_policy is None
        and c2rust_baseline is None
    ):
        return

    if selection_policy is not None:
        if not isinstance(selection_policy, dict):
            raise SystemExit("route_decision.candidate_generation.selection_policy must be an object")
        if selection_policy.get("semantic_acceptance") is not False:
            raise SystemExit("route_decision.candidate_generation.selection_policy cannot claim semantic_acceptance")
        if selection_policy.get("full_router") is not False:
            raise SystemExit("route_decision.candidate_generation.selection_policy cannot claim full_router")
        if selection_policy.get("stage") == "p0_route_governance":
            governance_stage = True
        else:
            governance_stage = False
    else:
        governance_stage = False

    if primary_candidate is not None:
        if not isinstance(primary_candidate, dict):
            raise SystemExit("route_decision.candidate_generation.primary_candidate must be an object")
        if primary_candidate.get("selected") == "legacy-string-translator":
            raise SystemExit(
                "route_decision.candidate_generation.primary_candidate cannot be legacy-string-translator; "
                "use compatibility_sources"
            )

    if candidate_set is None:
        if governance_stage or candidate_generation.get("governance_summary") is not None:
            validate_p0_route_governance_summary(
                candidate_generation,
                {},
                route_level=route_level,
                route_status=route_status,
            )
        if selected_candidate_id is not None or c2rust_baseline is not None:
            raise SystemExit("route_decision.candidate_generation.candidate_set missing for candidate selection record")
        return
    if not isinstance(candidate_set, list):
        raise SystemExit("route_decision.candidate_generation.candidate_set must be a list")

    candidates_by_id: dict[str, dict[str, Any]] = {}
    for index, candidate in enumerate(candidate_set):
        if not isinstance(candidate, dict):
            raise SystemExit(f"route_decision.candidate_generation.candidate_set[{index}] must be an object")
        candidate_id = candidate.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise SystemExit(f"route_decision.candidate_generation.candidate_set[{index}].candidate_id missing")
        if candidate_id in candidates_by_id:
            raise SystemExit(f"route_decision.candidate_generation.candidate_set duplicate candidate_id {candidate_id}")
        if candidate.get("semantic_pass") is not False:
            raise SystemExit(
                f"route_decision.candidate_generation.candidate_set[{candidate_id}] cannot claim semantic_pass"
            )
        if candidate.get("generated_draft_semantic_pass") is True:
            raise SystemExit(
                "route_decision.candidate_generation.candidate_set"
                f"[{candidate_id}] cannot claim generated_draft_semantic_pass"
            )
        candidates_by_id[candidate_id] = candidate

    if selected_candidate_id is not None:
        if not isinstance(selected_candidate_id, str) or selected_candidate_id not in candidates_by_id:
            raise SystemExit(
                "route_decision.candidate_generation.selected_candidate_id must reference candidate_set"
            )

    validate_legacy_string_translator_candidate_binding(candidates_by_id, selected_candidate_id)
    validate_compatibility_sources_binding(compatibility_sources, candidates_by_id)
    if governance_stage or candidate_generation.get("governance_summary") is not None:
        validate_p0_route_governance_summary(
            candidate_generation,
            candidates_by_id,
            route_level=route_level,
            route_status=route_status,
        )

    c2rust_candidate = candidates_by_id.get("c2rust-baseline")
    if c2rust_candidate is not None and c2rust_candidate.get("correctness_role") != "candidate_context_only":
        raise SystemExit(
            "route_decision.candidate_generation.candidate_set[c2rust-baseline].correctness_role "
            "must be candidate_context_only"
        )
    if c2rust_candidate is not None:
        validate_c2rust_baseline_candidate_binding(
            c2rust_candidate,
            evidence_dir=evidence_dir,
            prefix=prefix,
            strict=strict_generated_record,
        )
    if c2rust_baseline is not None:
        if not isinstance(c2rust_baseline, dict):
            raise SystemExit("route_decision.candidate_generation.c2rust_baseline must be an object")
        if c2rust_candidate is None:
            raise SystemExit("route_decision.candidate_generation.c2rust_baseline missing from candidate_set")
        if c2rust_baseline != c2rust_candidate:
            raise SystemExit("route_decision.candidate_generation.c2rust_baseline drifted from candidate_set")


P0_ROUTE_REQUIRED_ACCEPTANCE_GATES = {
    "c_oracle",
    "rust_replay",
    "schema_diff",
    "negative_diff",
    "unsafe_ledger",
    "final_verification",
}

P0_ROUTE_REQUIRED_HARD_GATES = {
    "generated_candidate_semantic_acceptance": "deferred",
    "legacy_string_translator_primary_selection": "forbidden",
    "c2rust_baseline_semantic_source": "forbidden",
}


def validate_p0_route_governance_summary(
    candidate_generation: dict[str, Any],
    candidates_by_id: dict[str, dict[str, Any]],
    *,
    route_level: Any | None,
    route_status: Any | None,
) -> None:
    summary = candidate_generation.get("governance_summary")
    if not isinstance(summary, dict):
        raise SystemExit("route_decision.candidate_generation.governance_summary must be an object")
    if summary.get("stage") != "p0_route_governance":
        raise SystemExit("route_decision.candidate_generation.governance_summary.stage must be p0_route_governance")
    if summary.get("semantic_acceptance") is not False:
        raise SystemExit("route_decision.candidate_generation.governance_summary cannot claim semantic_acceptance")
    if summary.get("full_router") is not False:
        raise SystemExit("route_decision.candidate_generation.governance_summary cannot claim full_router")
    if route_level is not None and summary.get("route_level") != route_level:
        raise SystemExit("route_decision.candidate_generation.governance_summary route_level drift")
    if route_status is not None and summary.get("route_status") != route_status:
        raise SystemExit("route_decision.candidate_generation.governance_summary route_status drift")

    validation_summary = summary.get("validation_gate_summary")
    if not isinstance(validation_summary, dict):
        raise SystemExit(
            "route_decision.candidate_generation.governance_summary.validation_gate_summary must be an object"
        )
    if validation_summary.get("generated_draft_semantic_pass") is not False:
        raise SystemExit(
            "route_decision.candidate_generation.governance_summary.validation_gate_summary "
            "cannot claim generated_draft_semantic_pass"
        )
    required_acceptance_gates = validation_summary.get("required_acceptance_gates")
    if not isinstance(required_acceptance_gates, list):
        raise SystemExit(
            "route_decision.candidate_generation.governance_summary.validation_gate_summary."
            "required_acceptance_gates must be a list"
        )
    missing_gates = P0_ROUTE_REQUIRED_ACCEPTANCE_GATES - {str(gate) for gate in required_acceptance_gates}
    if missing_gates:
        raise SystemExit(
            "route_decision.candidate_generation.governance_summary.validation_gate_summary "
            f"missing required gates: {', '.join(sorted(missing_gates))}"
        )

    hard_gates = summary.get("hard_gates")
    if not isinstance(hard_gates, list):
        raise SystemExit("route_decision.candidate_generation.governance_summary.hard_gates must be a list")
    hard_gate_by_id = {
        gate.get("gate_id"): gate
        for gate in hard_gates
        if isinstance(gate, dict) and isinstance(gate.get("gate_id"), str)
    }
    missing_hard_gates = set(P0_ROUTE_REQUIRED_HARD_GATES) - set(hard_gate_by_id)
    if missing_hard_gates:
        raise SystemExit(
            "route_decision.candidate_generation.governance_summary.hard_gates missing: "
            f"{', '.join(sorted(missing_hard_gates))}"
        )
    for gate_id, expected_status in P0_ROUTE_REQUIRED_HARD_GATES.items():
        if hard_gate_by_id[gate_id].get("status") != expected_status:
            raise SystemExit(
                "route_decision.candidate_generation.governance_summary.hard_gates "
                f"{gate_id} status drift"
            )

    fallback_summary = summary.get("fallback_summary")
    if not isinstance(fallback_summary, dict):
        raise SystemExit("route_decision.candidate_generation.governance_summary.fallback_summary must be an object")
    legacy_summary = fallback_summary.get("legacy_string_translator")
    if not isinstance(legacy_summary, dict):
        raise SystemExit(
            "route_decision.candidate_generation.governance_summary.fallback_summary."
            "legacy_string_translator must be an object"
        )
    if legacy_summary.get("selected_as_primary") is not False:
        raise SystemExit(
            "route_decision.candidate_generation.governance_summary.fallback_summary."
            "legacy_string_translator cannot be selected_as_primary"
        )
    expected_legacy_status = (
        "compatibility_only" if "compat:legacy-string-translator" in candidates_by_id else "not_used"
    )
    if legacy_summary.get("status") != expected_legacy_status:
        raise SystemExit(
            "route_decision.candidate_generation.governance_summary.fallback_summary."
            "legacy_string_translator status drift"
        )


def validate_compatibility_sources_binding(
    compatibility_sources: Any,
    candidates_by_id: dict[str, dict[str, Any]],
) -> None:
    if compatibility_sources is None:
        return
    if not isinstance(compatibility_sources, list):
        raise SystemExit("route_decision.candidate_generation.compatibility_sources must be a list")
    for index, source in enumerate(compatibility_sources):
        if not isinstance(source, dict):
            raise SystemExit(f"route_decision.candidate_generation.compatibility_sources[{index}] must be an object")
        candidate_id = source.get("candidate_id")
        if candidate_id not in candidates_by_id:
            raise SystemExit(
                "route_decision.candidate_generation.compatibility_sources must reference candidate_set"
            )
        if source.get("selected") != "legacy-string-translator":
            raise SystemExit(
                "route_decision.candidate_generation.compatibility_sources only supports legacy-string-translator"
            )
        candidate = candidates_by_id[candidate_id]
        if candidate.get("kind") != source.get("selected"):
            raise SystemExit("route_decision.candidate_generation.compatibility_sources drifted from candidate_set")
        if source.get("compatibility_only") is not True:
            raise SystemExit("route_decision.candidate_generation.compatibility_sources must be compatibility_only")
        if source.get("correctness_role") != "compatibility_only":
            raise SystemExit(
                "route_decision.candidate_generation.compatibility_sources correctness_role must be compatibility_only"
            )


def validate_legacy_string_translator_candidate_binding(
    candidates_by_id: dict[str, dict[str, Any]],
    selected_candidate_id: Any,
) -> None:
    legacy = [
        (candidate_id, candidate)
        for candidate_id, candidate in candidates_by_id.items()
        if candidate.get("kind") == "legacy-string-translator"
    ]
    for candidate_id, candidate in legacy:
        if candidate_id == selected_candidate_id:
            raise SystemExit(
                "legacy-string-translator cannot be selected as the primary candidate; "
                "it is compatibility-only"
            )
        if not candidate_id.startswith("compat:"):
            raise SystemExit("legacy-string-translator candidate_id must use compat: prefix")
        if candidate.get("role") != "compatibility_rust_draft":
            raise SystemExit("legacy-string-translator role must be compatibility_rust_draft")
        if candidate.get("correctness_role") != "compatibility_only":
            raise SystemExit("legacy-string-translator correctness_role must be compatibility_only")
        if candidate.get("compatibility_only") is not True:
            raise SystemExit("legacy-string-translator must set compatibility_only=true")
