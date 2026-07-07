def write_patch_events(events_path: Path, events: list[dict[str, Any]], *, append: bool = False) -> None:
    previous = events_path.read_text(encoding="utf-8") if append and events_path.exists() else ""
    write_text(events_path, previous + "".join(json.dumps(event, sort_keys=True) + "\n" for event in events))


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
    *,
    round_number: int = 1,
    append_events: bool = False,
) -> dict[str, Any]:
    slice_id = required_str(spec, "slice_id")
    events_path = evidence_dir / f"l3-{slice_id}-patch-events.jsonl"
    blocked_path = evidence_dir / f"l3-{slice_id}-self-healing-blocked-repairs.json"
    event = {
        "schema_version": 1,
        "patch_id": f"patch-blocked-{round_number}",
        "target_id": spec.get("target_id"),
        "slice_id": slice_id,
        "round": round_number,
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
        "rollback_id": f"rollback-{slice_id}-blocked-{round_number}",
        "ai_usage": {"used": False},
        "verification_commands": ["rustc --edition=2021 --crate-type=lib --error-format=json <draft>"],
    }
    write_patch_events(events_path, [event], append=append_events)
    blocked = blocked_repairs_payload(
        spec,
        [
            {
                "repair_id": f"repair-blocked-{round_number}",
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
        "self_heal_applied": append_events,
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
    rust_check: dict[str, Any] | None = None,
    replay: dict[str, Any] | None = None,
    c_oracle: dict[str, Any] | None = None,
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
    capability_delta = [
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
    ]
    governance_delta = [
        {
            "delta_id": f"gov-{slice_id}-{construct_id}-evidence",
            "kind": "evidence_contract",
            "construct_id": construct_id,
            "evidence_refs": evidence_refs,
            "bound_to": "P0 capability delta; governance changes only record evidence/repair provenance for this construct.",
        }
    ]
    if (
        isinstance(rust_check, dict)
        and isinstance(replay, dict)
        and rust_check.get("status") == "passed"
        and replay.get("status") == "passed"
        and replay.get("generated_draft_replay_pass") is True
    ):
        replay_construct_id = "rust_replay_fixture_passed"
        replay_refs = list(
            dict.fromkeys(
                [
                    route_ref,
                    profile_ref,
                    rel(evidence_dir / "rust-check.json"),
                    rel(evidence_dir / f"{prefix}-test-translation-generated.json"),
                    rel(evidence_dir / f"{prefix}-final-verification.json"),
                ]
            )
        )
        replay_command = (
            "python -B -m unittest "
            "validation.tools.test_auto_migrate.AutoMigrateTests."
            "test_real_fdb_blob_make_rust_replay_passes_without_semantic_claim"
        )
        capability_delta.append(
            {
                "delta_id": f"cap-{slice_id}-{replay_construct_id}",
                "kind": "candidate_verification",
                "construct_id": replay_construct_id,
                "real_c_slice": slice_id,
                "generated_candidate_status": generated_status,
                "semantic_pass": semantic_pass,
                "blocked_callees": [],
                "evidence_refs": replay_refs,
                "negative_coverage": [
                    {
                        "kind": "rust_replay_regression",
                        "command": replay_command,
                    }
                ],
            }
        )
        governance_delta.append(
            {
                "delta_id": f"gov-{slice_id}-{replay_construct_id}-evidence",
                "kind": "evidence_contract",
                "construct_id": replay_construct_id,
                "evidence_refs": replay_refs,
                "bound_to": "P0 capability delta; governance records that Rust replay passed without semantic acceptance.",
            }
        )
        if replay_command not in verification_commands:
            verification_commands.append(replay_command)
    if c_oracle_harness_matched_not_oracle(c_oracle):
        c_oracle_construct_id = "c_oracle_harness_matched_not_oracle"
        c_oracle_refs = list(
            dict.fromkeys(
                [
                    route_ref,
                    profile_ref,
                    rel(evidence_dir / f"{prefix}-c-oracle-status.json"),
                    rel(evidence_dir / f"{prefix}-c-oracle-harness-draft.c"),
                ]
            )
        )
        c_oracle_command = (
            "python -B -m unittest "
            "validation.tools.test_auto_migrate.AutoMigrateTests."
            "test_capability_ledger_records_c_oracle_matched_not_oracle_without_semantic_claim"
        )
        capability_delta.append(
            {
                "delta_id": f"cap-{slice_id}-{c_oracle_construct_id}",
                "kind": "candidate_verification",
                "construct_id": c_oracle_construct_id,
                "real_c_slice": slice_id,
                "generated_candidate_status": generated_status,
                "semantic_pass": semantic_pass,
                "blocked_callees": [],
                "evidence_refs": c_oracle_refs,
                "negative_coverage": [
                    {
                        "kind": "c_oracle_diagnostic_regression",
                        "command": c_oracle_command,
                    }
                ],
            }
        )
        governance_delta.append(
            {
                "delta_id": f"gov-{slice_id}-{c_oracle_construct_id}-evidence",
                "kind": "evidence_contract",
                "construct_id": c_oracle_construct_id,
                "evidence_refs": c_oracle_refs,
                "bound_to": "P0 capability delta; governance records that the C harness executed and matched fixture markers without semantic acceptance.",
            }
        )
        if c_oracle_command not in verification_commands:
            verification_commands.append(c_oracle_command)
    payload = {
        "schema_version": 1,
        "target_id": target_id,
        "slice_id": slice_id,
        "source_commit": source_commit(spec),
        "source_identity": source_identity(spec),
        "status": "recorded",
        "route_level": route_decision.get("level"),
        "route_status": route_decision.get("status"),
        "capability_delta": capability_delta,
        "governance_delta": governance_delta,
        "verification_commands": verification_commands,
        "boundary": "This ledger records P0 capability/refusal deltas only; it does not accept generated Rust semantics.",
    }
    write_json(evidence_dir / f"{prefix}-capability-delta.json", payload)
    return payload


def c_oracle_harness_matched_not_oracle(c_oracle: dict[str, Any] | None) -> bool:
    if not isinstance(c_oracle, dict):
        return False
    compile_execution = c_oracle.get("compile_execution")
    if not isinstance(compile_execution, dict):
        return False
    harness_execution = compile_execution.get("harness_execution")
    if not isinstance(harness_execution, dict):
        return False
    output_gate = harness_execution.get("output_gate")
    return (
        compile_execution.get("status") == "compile_succeeded_not_oracle"
        and harness_execution.get("status") == "exited_zero_not_oracle"
        and isinstance(output_gate, dict)
        and output_gate.get("status") == "matched_not_oracle"
        and bool(output_gate.get("matched_stdout_fragments"))
        and not output_gate.get("missing_stdout_fragments")
    )


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
    generation_enabled = c2rust_baseline_generation_enabled()
    generation: dict[str, Any] = {
        "enabled": generation_enabled,
        "enabled_by": "C2RUST_BASELINE_GENERATION" if generation_enabled else "",
        "compile_commands": None,
        "command": None,
        "generated_files": [],
    }
    output: dict[str, Any] | None = None
    compile_status: dict[str, Any] | None = None
    status = "skipped"
    diagnostics: list[str] = []
    reason = "blocked_by_missing_tools"
    if selected is None:
        diagnostics.append("no executable c2rust-transpile or c2rust command found on PATH")
    elif not generation_enabled:
        status = "blocked"
        reason = "baseline_generation_not_enabled"
        diagnostics.append("executable C2Rust was detected but baseline generation is not enabled in this bounded MVP")
    else:
        compile_commands = resolve_c2rust_compile_commands(spec, slice_spec)
        if compile_commands is None:
            status = "blocked"
            reason = "missing_compile_commands"
            diagnostics.append(
                "C2Rust baseline generation was enabled, but build_profile.compiler_command_source "
                "does not resolve to compile_commands.json"
            )
        else:
            prepared_compile_commands, compile_commands_metadata = prepare_c2rust_compile_commands(
                compile_commands,
                evidence_dir,
                prefix,
            )
            generation["source_compile_commands"] = compile_commands_metadata["source"]
            generation["compile_commands"] = {
                "path": rel(prepared_compile_commands),
                "sha256": sha256(prepared_compile_commands),
                "normalized_for_c2rust": compile_commands_metadata["normalized_for_c2rust"],
            }
            generation_result = run_c2rust_baseline_generation(
                selected,
                prepared_compile_commands,
                evidence_dir,
                prefix,
            )
            generation.update(generation_result["generation"])
            diagnostics.extend(generation_result["diagnostics"])
            output = generation_result["output"]
            if output is None:
                status = "blocked"
                reason = generation_result["reason"]
            else:
                status = "generated"
                reason = "generated_by_c2rust"
                compile_status = compile_c2rust_baseline_output(
                    c2rust_baseline_output_path(output),
                    evidence_dir,
                    prefix,
                    crate_root=c2rust_baseline_crate_root(output),
                )
                diagnostics.extend(compile_status.get("diagnostics", []))
    toolchain_repair = None if status == "generated" else c2rust_toolchain_repair(reason, slice_spec=slice_spec)
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
        "generation": generation,
        "output": output,
        "compile": compile_status,
        "diagnostics": diagnostics,
        "toolchain_repair": toolchain_repair,
        "must_not_claim": [
            "C2Rust output proves semantic equivalence",
            "C2Rust baseline was generated" if status != "generated" else "",
        ],
        "tool_probe": c2rust_tool_probe(),
    }
    manifest["must_not_claim"] = [item for item in manifest["must_not_claim"] if item]
    write_json(evidence_dir / f"{prefix}-c2rust-baseline-manifest.json", manifest)
    return manifest


def c2rust_baseline_generation_enabled() -> bool:
    value = os.environ.get("C2RUST_BASELINE_GENERATION", "").strip().lower()
    return value in {"1", "true", "yes", "on", "enabled"}


def resolve_c2rust_compile_commands(spec: dict[str, Any], slice_spec: Path) -> Path | None:
    build_profile = spec.get("build_profile", {})
    if not isinstance(build_profile, dict):
        return None
    configured = build_profile.get("compiler_command_source") or build_profile.get("compile_commands")
    if not configured:
        return None
    configured_path = Path(str(configured))
    candidates = [configured_path] if configured_path.is_absolute() else [
        REPO_ROOT / configured_path,
        slice_spec.parent / configured_path,
    ]
    for candidate in candidates:
        if candidate.name != "compile_commands.json":
            continue
        if candidate.exists() and candidate.is_file() and is_compile_commands_database(candidate):
            return candidate.resolve()
    return None


def is_compile_commands_database(path: Path) -> bool:
    try:
        database = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(database, list) or not database:
        return False
    for entry in database:
        if not isinstance(entry, dict):
            return False
        for key in ["directory", "command", "file"]:
            if not isinstance(entry.get(key), str) or not entry[key]:
                return False
    return True


def prepare_c2rust_compile_commands(compile_commands: Path, evidence_dir: Path, prefix: str) -> tuple[Path, dict[str, Any]]:
    database = json.loads(compile_commands.read_text(encoding="utf-8"))
    normalized = [normalize_c2rust_compile_command_entry(entry) for entry in database]
    prepared = evidence_dir / f"{prefix}-c2rust-compile-commands" / "compile_commands.json"
    write_json(prepared, normalized)
    return prepared, {
        "source": {"path": rel(compile_commands), "sha256": sha256(compile_commands)},
        "normalized_for_c2rust": True,
    }


def normalize_c2rust_compile_command_entry(entry: dict[str, Any]) -> dict[str, str]:
    source_directory = Path(str(entry["directory"]))
    if not source_directory.is_absolute():
        source_directory = REPO_ROOT / source_directory
    source_directory = source_directory.resolve()
    source_file = resolve_compile_command_path(str(entry["file"]), source_directory)
    output = entry.get("output")
    output_path = resolve_compile_command_path(str(output), source_directory) if output else None
    command = normalize_c2rust_compile_command(str(entry["command"]), source_directory, source_file, output_path)
    normalized = {
        "directory": source_directory.as_posix(),
        "command": command,
        "file": source_file.as_posix(),
    }
    if output_path is not None:
        normalized["output"] = output_path.as_posix()
    return normalized


def normalize_c2rust_compile_command(
    command: str,
    source_directory: Path,
    source_file: Path,
    output_path: Path | None,
) -> str:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        tokens = command.split()
    normalized: list[str] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token == "-I" and i + 1 < len(tokens):
            normalized.extend([token, resolve_compile_command_path(tokens[i + 1], source_directory).as_posix()])
            i += 2
            continue
        if token.startswith("-I") and len(token) > 2:
            normalized.append("-I" + resolve_compile_command_path(token[2:], source_directory).as_posix())
            i += 1
            continue
        if token == "-c" and i + 1 < len(tokens):
            normalized.extend([token, source_file.as_posix()])
            i += 2
            continue
        if token == "-o" and i + 1 < len(tokens):
            normalized.extend([token, (output_path or resolve_compile_command_path(tokens[i + 1], source_directory)).as_posix()])
            i += 2
            continue
        if token == source_file.name or token.endswith(".c"):
            candidate = resolve_compile_command_path(token, source_directory)
            if candidate == source_file:
                normalized.append(source_file.as_posix())
                i += 1
                continue
        normalized.append(token)
        i += 1
    return shlex.join(normalized)


def resolve_compile_command_path(value: str, source_directory: Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = source_directory / path
    return path.resolve()


def run_c2rust_baseline_generation(
    selected: dict[str, Any],
    compile_commands: Path,
    evidence_dir: Path,
    prefix: str,
) -> dict[str, Any]:
    timeout_seconds = 120
    output_dir = evidence_dir / f"{prefix}-c2rust-baseline-generated"
    stdout_log = evidence_dir / f"{prefix}-c2rust-baseline-stdout.log"
    stderr_log = evidence_dir / f"{prefix}-c2rust-baseline-stderr.log"
    argv = c2rust_generation_argv(selected, compile_commands, output_dir)
    generation: dict[str, Any] = {
        "command": {
            "argv": c2rust_generation_evidence_argv(argv),
            "working_directory": rel(REPO_ROOT),
            "output_dir": rel(output_dir),
            "stdout_log": rel(stdout_log),
            "stderr_log": rel(stderr_log),
            "timeout_seconds": timeout_seconds,
            "exit_status": None,
            "returncode": None,
        },
        "generated_files": [],
    }
    diagnostics: list[str] = []
    try:
        reset_c2rust_output_dir(evidence_dir, output_dir)
        result = subprocess.run(
            argv,
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
    except Exception as exc:
        write_text(stdout_log, "")
        write_text(stderr_log, f"{type(exc).__name__}: {exc}\n")
        generation["command"]["exit_status"] = "error"
        generation["command"]["returncode"] = -1
        diagnostics.append(f"C2Rust baseline generation command failed before completion: {exc}")
        return {
            "reason": "c2rust_generation_failed",
            "diagnostics": diagnostics,
            "generation": generation,
            "output": None,
        }

    write_text(stdout_log, result.stdout or "")
    write_text(stderr_log, result.stderr or "")
    generation["command"]["exit_status"] = "passed" if result.returncode == 0 else "failed"
    generation["command"]["returncode"] = result.returncode
    if result.returncode != 0:
        diagnostics.append(f"C2Rust baseline generation command exited with {result.returncode}")
        return {
            "reason": "c2rust_generation_failed",
            "diagnostics": diagnostics,
            "generation": generation,
            "output": None,
        }

    rust_files = sorted(path for path in output_dir.rglob("*.rs") if path.is_file())
    if not rust_files:
        diagnostics.append("C2Rust baseline generation completed but produced no Rust files")
        return {
            "reason": "c2rust_generation_no_rust_output",
            "diagnostics": diagnostics,
            "generation": generation,
            "output": None,
        }

    generated_refs = [{"path": rel(path), "sha256": sha256(path)} for path in rust_files]
    generation["generated_files"] = generated_refs
    output_path = evidence_dir / f"{prefix}-c2rust-baseline-output.rs"
    write_text(output_path, combined_c2rust_output(rust_files))
    output: dict[str, Any] = {
        "path": rel(output_path),
        "status": "generated",
        "sha256": sha256(output_path),
        "source_files": generated_refs,
    }
    cargo_toml = output_dir / "Cargo.toml"
    if cargo_toml.exists():
        output["crate_root"] = rel(output_dir)
        output["cargo_toml"] = rel(cargo_toml)
    return {
        "reason": "generated_by_c2rust",
        "diagnostics": diagnostics,
        "generation": generation,
        "output": output,
    }


def reset_c2rust_output_dir(evidence_dir: Path, output_dir: Path) -> None:
    evidence_root = evidence_dir.resolve()
    output_root = output_dir.resolve()
    if output_root == evidence_root:
        raise ValueError("refusing to use evidence root itself as C2Rust output directory")
    try:
        output_root.relative_to(evidence_root)
    except ValueError as exc:
        raise ValueError(f"refusing to use C2Rust output directory outside evidence root: {output_dir}") from exc
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def c2rust_generation_argv(selected: dict[str, Any], compile_commands: Path, output_dir: Path) -> list[str]:
    executable = str(selected.get("path", ""))
    name = str(selected.get("name", ""))
    argv_prefix = selected.get("argv_prefix")
    if isinstance(argv_prefix, list) and all(isinstance(item, str) and item for item in argv_prefix):
        base = list(argv_prefix)
    else:
        base = [executable]
    if name == "c2rust":
        base.append("transpile")
    return [
        *base,
        "--emit-build-files",
        "--output-dir",
        str(output_dir),
        str(compile_commands),
    ]


def c2rust_generation_evidence_argv(argv: list[str]) -> list[str]:
    return [repo_relative_absolute_arg(item) for item in argv]


def repo_relative_absolute_arg(value: str) -> str:
    path = Path(value)
    if not path.is_absolute():
        return value
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except (OSError, ValueError):
        return value


def combined_c2rust_output(rust_files: list[Path]) -> str:
    chunks: list[str] = []
    for path in rust_files:
        source = path.read_text(encoding="utf-8", errors="replace")
        if source and not source.endswith("\n"):
            source += "\n"
        chunks.append(f"// c2rust generated source: {rel(path)}\n{source}")
    return "\n".join(chunks)


def c2rust_baseline_output_path(output: dict[str, Any]) -> Path:
    output_path = Path(str(output.get("path", "")))
    if output_path.is_absolute():
        return output_path
    return REPO_ROOT / output_path


def c2rust_baseline_crate_root(output: dict[str, Any]) -> Path | None:
    crate_root_value = str(output.get("crate_root", "") or "")
    if not crate_root_value:
        return None
    crate_root = Path(crate_root_value)
    if crate_root.is_absolute():
        return crate_root
    return REPO_ROOT / crate_root


def c2rust_generated_crate_artifact(crate_root: Path) -> Path | None:
    debug_dir = crate_root / "target" / "debug"
    artifacts = sorted(path for path in debug_dir.glob("lib*.rlib") if path.is_file())
    return artifacts[0] if artifacts else None


def compile_c2rust_generated_crate(
    *,
    output_path: Path,
    evidence_dir: Path,
    prefix: str,
    crate_root: Path,
    candidate_output: dict[str, Any],
    timeout_seconds: int,
) -> dict[str, Any]:
    stdout_log = evidence_dir / f"{prefix}-c2rust-baseline-cargo.stdout.log"
    stderr_log = evidence_dir / f"{prefix}-c2rust-baseline-cargo.stderr.log"
    env_overrides = {"RUSTUP_TOOLCHAIN": "stable", "RUSTC_BOOTSTRAP": "1"}
    command: dict[str, Any] = {
        "argv": [],
        "working_directory": rel(crate_root),
        "stdout_log": rel(stdout_log),
        "stderr_log": rel(stderr_log),
        "timeout_seconds": timeout_seconds,
        "exit_status": "not_executed",
        "returncode": None,
        "compile_strategy": "cargo_generated_crate",
        "env_overrides": env_overrides,
        "crate_root": rel(crate_root),
        "candidate_output_path": rel(output_path),
    }
    cargo = shutil.which("cargo")
    if cargo is None:
        write_text(stdout_log, "")
        write_text(stderr_log, "cargo not found on PATH\n")
        return {
            "status": "rustc_not_found",
            "attempted": False,
            "semantic_pass": False,
            "candidate_output": candidate_output,
            "command": command,
            "artifact": None,
            "diagnostics": ["C2Rust generated crate compile check skipped because cargo was not found on PATH"],
        }

    argv = [cargo, "build"]
    command["argv"] = argv
    env = os.environ.copy()
    env.update(env_overrides)
    try:
        result = subprocess.run(
            argv,
            cwd=str(crate_root),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        write_text(stdout_log, exc.stdout or "")
        write_text(stderr_log, exc.stderr or f"cargo build timed out after {timeout_seconds} seconds\n")
        command["exit_status"] = "timeout"
        command["returncode"] = -1
        return {
            "status": "compile_timeout",
            "attempted": True,
            "semantic_pass": False,
            "candidate_output": candidate_output,
            "command": command,
            "artifact": None,
            "diagnostics": ["C2Rust generated crate cargo compile check timed out"],
        }
    except Exception as exc:
        write_text(stdout_log, "")
        write_text(stderr_log, f"{type(exc).__name__}: {exc}\n")
        command["exit_status"] = "error"
        command["returncode"] = -1
        return {
            "status": "compile_error",
            "attempted": True,
            "semantic_pass": False,
            "candidate_output": candidate_output,
            "command": command,
            "artifact": None,
            "diagnostics": [f"C2Rust generated crate cargo compile check could not start: {exc}"],
        }

    write_text(stdout_log, result.stdout or "")
    write_text(stderr_log, result.stderr or "")
    command["exit_status"] = "passed" if result.returncode == 0 else "failed"
    command["returncode"] = result.returncode
    if result.returncode != 0:
        return {
            "status": "failed",
            "attempted": True,
            "semantic_pass": False,
            "candidate_output": candidate_output,
            "command": command,
            "artifact": None,
            "diagnostics": [f"C2Rust generated crate cargo compile check exited with {result.returncode}"],
        }

    artifact_path = c2rust_generated_crate_artifact(crate_root)
    if artifact_path is None:
        return {
            "status": "failed",
            "attempted": True,
            "semantic_pass": False,
            "candidate_output": candidate_output,
            "command": command,
            "artifact": None,
            "diagnostics": ["C2Rust generated crate cargo compile check passed without producing an rlib artifact"],
        }

    stable_artifact_path = evidence_dir / f"{prefix}-c2rust-baseline-output.rlib"
    shutil.copyfile(artifact_path, stable_artifact_path)
    return {
        "status": "passed",
        "attempted": True,
        "semantic_pass": False,
        "candidate_output": candidate_output,
        "command": command,
        "artifact": {
            "path": rel(stable_artifact_path),
            "status": "compiled",
            "sha256": sha256(stable_artifact_path),
        },
        "diagnostics": [],
    }


def compile_c2rust_baseline_output(
    output_path: Path,
    evidence_dir: Path,
    prefix: str,
    *,
    crate_root: Path | None = None,
) -> dict[str, Any]:
    timeout_seconds = 120
    stdout_log = evidence_dir / f"{prefix}-c2rust-baseline-rustc.stdout.log"
    stderr_log = evidence_dir / f"{prefix}-c2rust-baseline-rustc.stderr.log"
    artifact_path = evidence_dir / f"{prefix}-c2rust-baseline-output.rlib"
    candidate_output = {
        "path": rel(output_path),
        "status": "generated",
        "sha256": sha256(output_path),
    }
    if crate_root is not None and (crate_root / "Cargo.toml").exists():
        return compile_c2rust_generated_crate(
            output_path=output_path,
            evidence_dir=evidence_dir,
            prefix=prefix,
            crate_root=crate_root,
            candidate_output=candidate_output,
            timeout_seconds=timeout_seconds,
        )
    rustc = shutil.which("rustc")
    command: dict[str, Any] = {
        "argv": [],
        "working_directory": rel(evidence_dir),
        "stdout_log": rel(stdout_log),
        "stderr_log": rel(stderr_log),
        "timeout_seconds": timeout_seconds,
        "exit_status": "not_executed",
        "returncode": None,
    }
    if rustc is None:
        write_text(stdout_log, "")
        write_text(stderr_log, "rustc not found on PATH\n")
        return {
            "status": "rustc_not_found",
            "attempted": False,
            "semantic_pass": False,
            "candidate_output": candidate_output,
            "command": command,
            "artifact": None,
            "diagnostics": ["C2Rust baseline output compile check skipped because rustc was not found on PATH"],
        }

    argv = [
        rustc,
        "--crate-type",
        "lib",
        str(output_path),
        "-o",
        str(artifact_path),
    ]
    command["argv"] = argv
    try:
        result = subprocess.run(
            argv,
            cwd=str(evidence_dir),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        write_text(stdout_log, exc.stdout or "")
        write_text(stderr_log, exc.stderr or f"rustc timed out after {timeout_seconds} seconds\n")
        command["exit_status"] = "timeout"
        command["returncode"] = -1
        return {
            "status": "compile_timeout",
            "attempted": True,
            "semantic_pass": False,
            "candidate_output": candidate_output,
            "command": command,
            "artifact": None,
            "diagnostics": ["C2Rust baseline output rustc compile check timed out"],
        }
    except Exception as exc:
        write_text(stdout_log, "")
        write_text(stderr_log, f"{type(exc).__name__}: {exc}\n")
        command["exit_status"] = "error"
        command["returncode"] = -1
        return {
            "status": "compile_error",
            "attempted": True,
            "semantic_pass": False,
            "candidate_output": candidate_output,
            "command": command,
            "artifact": None,
            "diagnostics": [f"C2Rust baseline output rustc compile check could not start: {exc}"],
        }

    write_text(stdout_log, result.stdout or "")
    write_text(stderr_log, result.stderr or "")
    command["exit_status"] = "passed" if result.returncode == 0 else "failed"
    command["returncode"] = result.returncode
    if result.returncode != 0:
        return {
            "status": "failed",
            "attempted": True,
            "semantic_pass": False,
            "candidate_output": candidate_output,
            "command": command,
            "artifact": None,
            "diagnostics": [f"C2Rust baseline output rustc compile check exited with {result.returncode}"],
        }
    if not artifact_path.exists():
        return {
            "status": "failed",
            "attempted": True,
            "semantic_pass": False,
            "candidate_output": candidate_output,
            "command": command,
            "artifact": None,
            "diagnostics": ["C2Rust baseline output rustc compile check passed without producing an artifact"],
        }

    return {
        "status": "passed",
        "attempted": True,
        "semantic_pass": False,
        "candidate_output": candidate_output,
        "command": command,
        "artifact": {
            "path": rel(artifact_path),
            "status": "compiled",
            "sha256": sha256(artifact_path),
        },
        "diagnostics": [],
    }
