def exact_host_revalidation_blockers(revalidation: dict[str, Any]) -> list[str]:
    if revalidation.get("required") is True and revalidation.get("status") != "passed":
        return ["run_report_exact_host_revalidation_failed"]
    return []


def proof_classes_after_exact_host_revalidation(
    proof_classes: dict[str, Any],
    revalidation: dict[str, Any],
) -> dict[str, Any]:
    if revalidation.get("required") is not True or revalidation.get("status") == "passed":
        return proof_classes
    adjusted = deepcopy(proof_classes)
    adjusted["competition_exact_host_verified"] = False
    adjusted["exact_host_revalidation_status"] = revalidation.get("status")
    adjusted["exact_host_revalidation_failed_entrypoints"] = list(revalidation.get("entrypoint_ids", []))
    return adjusted


def entrypoint_competition_host_attested(entry: dict[str, Any]) -> bool:
    if entry.get("competition_exact_host_attested") is True:
        return True
    host_attestation = entry.get("host_attestation")
    if isinstance(host_attestation, dict) and host_attestation.get("competition_exact_host_attested") is True:
        return True
    environment = entry.get("execution_environment")
    return isinstance(environment, dict) and environment.get("competition_exact_host_attested") is True


def build_claim_scope(
    *,
    status: str,
    proof_classes: dict[str, Any],
    semantic_evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "external_review_index_ready": status == "passed",
        "semantic_acceptance_ready": False,
        "competition_exact_ready": bool(proof_classes.get("competition_exact_host_verified")),
        "translator_generated_coverage_ready": int_or_zero(
            semantic_evidence.get("translation_coverage_numerator")
        )
        > 0,
        "boundary": (
            "A passed bundle means the external review index is complete. It is not semantic acceptance, "
            "competition-exact proof, or translator-generated coverage."
        ),
    }


def build_publishability(
    *,
    status: str,
    readiness: dict[str, Any],
    proof_classes: dict[str, Any],
    blockers: list[str],
    opencode_runtime: dict[str, Any],
) -> dict[str, Any]:
    all_entrypoints = bool(readiness.get("all_entrypoints_executed"))
    blocked = status != "passed" or bool(blockers)
    all_entrypoints_run_publishable = not blocked and all_entrypoints
    competition_exact_publishable = all_entrypoints_run_publishable and bool(
        proof_classes.get("all_entrypoints_competition_exact")
    ) and bool(
        proof_classes.get("competition_exact_host_verified")
    )
    scope = "full" if all_entrypoints_run_publishable else "partial" if status == "passed" else "blocked"
    preflight_summary = (
        opencode_runtime.get("preflight_proof_summary", {})
        if isinstance(opencode_runtime.get("preflight_proof_summary"), dict)
        else {}
    )
    opencode_enabled = int_or_zero(opencode_runtime.get("enabled_entrypoint_count")) > 0
    preflight_status = preflight_summary.get("status") if opencode_enabled else "not-required"
    if not isinstance(preflight_status, str) or not preflight_status:
        preflight_status = "missing"
    opencode_glm51_publishable = opencode_enabled and opencode_preflight_summary_publishable(preflight_summary)
    external_ready = competition_exact_publishable and opencode_glm51_publishable
    publication_scope_value = (
        "full"
        if external_ready
        else "internal_preview_full"
        if all_entrypoints_run_publishable
        else scope
    )
    return {
        "status": "blocked"
        if blocked
        else "external_release_ready"
        if external_ready
        else "internal_preview",
        "scope": scope,
        "publication_scope": publication_scope_value,
        "external_milestone_claim_ready": external_ready,
        "external_milestone": external_ready,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "all_entrypoints_run_publishable": all_entrypoints_run_publishable,
        "focused_run": not all_entrypoints,
        "competition_exact_publishable": competition_exact_publishable,
        "required_agent_tool": validator.COMPETITION_OPENCODE_COMMAND,
        "required_agent": validator.COMPETITION_OPENCODE_AGENT,
        "required_model": validator.COMPETITION_OPENCODE_MODEL,
        "required_variant": validator.COMPETITION_OPENCODE_VARIANT,
        "opencode_glm51_required": True,
        "opencode_glm51_preflight_status": preflight_status,
        "opencode_glm51_publishable": opencode_glm51_publishable,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
        "target_artifacts_regenerable": True,
        "committed_release_evidence_refs": "Use validation/evidence manifests and config/competition-env profiles as committed anchors.",
        "boundary": (
            "Publishability is a review-package readiness contract. Competition-facing agent evidence requires "
            "OpenCode with GLM-5.1 and does not convert chat/session output into semantic acceptance."
        ),
    }


def build_competition_host_readiness(
    *,
    proof_classes: dict[str, Any],
    publishability: dict[str, Any],
) -> dict[str, Any]:
    all_entrypoints_run_publishable = publishability.get("all_entrypoints_run_publishable") is True
    all_entrypoints_competition_exact = proof_classes.get("all_entrypoints_competition_exact") is True
    competition_exact_host_verified = proof_classes.get("competition_exact_host_verified") is True
    opencode_glm51_publishable = publishability.get("opencode_glm51_publishable") is True
    external_milestone_claim_ready = publishability.get("external_milestone_claim_ready") is True
    missing_requirements = []
    if not all_entrypoints_run_publishable:
        missing_requirements.append("all_entrypoints_run_publishable")
    if not all_entrypoints_competition_exact:
        missing_requirements.append("all_entrypoints_competition_exact")
    if not competition_exact_host_verified:
        missing_requirements.append("competition_exact_host_verified")
    if not opencode_glm51_publishable:
        missing_requirements.append("opencode_glm51_publishable")
    if not external_milestone_claim_ready:
        missing_requirements.append("external_milestone_claim_ready")
    return {
        "report_kind": "competition-host-readiness",
        "status": "ready" if not missing_requirements else "blocked",
        "required_agent_tool": validator.COMPETITION_OPENCODE_COMMAND,
        "required_agent": validator.COMPETITION_OPENCODE_AGENT,
        "required_model": validator.COMPETITION_OPENCODE_MODEL,
        "required_variant": validator.COMPETITION_OPENCODE_VARIANT,
        "required_proof_class": "competition-exact",
        "actual_highest_proof_class": proof_classes.get("highest_proof_class", "unknown"),
        "all_entrypoints_run_publishable": all_entrypoints_run_publishable,
        "all_entrypoints_competition_exact": all_entrypoints_competition_exact,
        "competition_exact_host_verified": competition_exact_host_verified,
        "opencode_glm51_preflight_status": publishability.get("opencode_glm51_preflight_status", "unknown"),
        "opencode_glm51_publishable": opencode_glm51_publishable,
        "external_milestone_claim_ready": external_milestone_claim_ready,
        "missing_requirements": missing_requirements,
        "blocker_count": len(missing_requirements),
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
        "boundary": (
            "Competition host readiness is the P0-H9 launch contract for OpenCode + GLM-5.1 + c2rust-migrator + max. "
            "It is not semantic acceptance and does not increase translator-generated coverage."
        ),
    }


def opencode_preflight_summary_publishable(summary: dict[str, Any]) -> bool:
    if summary.get("status") != "passed":
        return False
    if summary.get("required_when_opencode_runtime_enabled") is not True:
        return False
    if summary.get("chat_output_is_evidence") is not False:
        return False
    if summary.get("semantic_gate") is not False:
        return False
    if int_or_zero(summary.get("translation_coverage_numerator")) != 0:
        return False
    if summary.get("opencode_command") != validator.COMPETITION_OPENCODE_COMMAND:
        return False
    if summary.get("opencode_agent") != validator.COMPETITION_OPENCODE_AGENT:
        return False
    if summary.get("opencode_model") != validator.COMPETITION_OPENCODE_MODEL:
        return False
    if summary.get("opencode_variant") != validator.COMPETITION_OPENCODE_VARIANT:
        return False
    if summary.get("required_model") != validator.COMPETITION_OPENCODE_MODEL:
        return False
    if summary.get("model_availability_status") != "available":
        return False
    if summary.get("model_listed") is not True:
        return False
    if int_or_zero(summary.get("process_returncode")) != 0:
        return False
    if summary.get("contract_status") != "executed":
        return False
    if summary.get("marker_exists") is not True:
        return False
    if summary.get("opencode_run_launched") is not True:
        return False
    if summary.get("opencode_run_argv_bound") is not True:
        return False
    if not validator.opencode_models_argv_matches(
        summary.get("model_probe_argv"),
        expected_command=validator.COMPETITION_OPENCODE_COMMAND,
    ):
        return False
    runtime_env = summary.get("opencode_runtime_env")
    if not isinstance(runtime_env, dict):
        return False
    if summary.get("opencode_runtime_env_sha256") != runtime_env.get("env_sha256"):
        return False
    return True


def build_semantic_evidence_rollup(run_report: dict[str, Any]) -> dict[str, Any]:
    summary_claim = source_summary_claim(run_report)
    return {
        "semantic_claim_source": summary_claim.get("semantic_claim_source", "validator-owned-artifacts"),
        "accepted_evidence_semantic_pass_count": 0,
        "translator_generated_semantic_pass_count": 0,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
        "source_generated_draft_semantic_pass": bool(summary_claim.get("generated_draft_semantic_pass")),
        "source_translation_coverage_numerator": int_or_zero(summary_claim.get("translation_coverage_numerator")),
        "accepted_evidence_counts_as_translator_coverage": False,
        "boundary": (
            "Accepted-evidence semantic pass counts are context only. The bundle does not increase "
            "translator-generated semantic-pass counts or translation coverage."
        ),
    }


def build_unsafe_reduction_scope(sources: list[dict[str, Any]]) -> dict[str, Any]:
    total_units = sum(int_or_zero(source.get("units_total")) for source in sources)
    measured_sources = [source for source in sources if source.get("unsafe_reduction_status") == "measured"]
    measured_units = sum(int_or_zero(source.get("units_total")) for source in measured_sources)
    unmeasured = [
        source.get("entrypoint_id")
        for source in sources
        if source.get("unsafe_reduction_status") != "measured"
    ]
    all_sources_measured = bool(sources) and len(measured_sources) == len(sources)
    if not measured_sources:
        scope = "none"
    elif all_sources_measured:
        scope = "all"
    else:
        scope = "partial"
    return {
        "scope": scope,
        "all_sources_measured": all_sources_measured,
        "measured_units": measured_units,
        "total_units": total_units,
        "unmeasured_entrypoints": unmeasured,
        "boundary": "Unsafe reduction is only global when every workflow metrics source reports measured data.",
    }


def build_core_translation_quality_rollup(sources: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = sorted(
        {
            str(source.get("final_gate_status"))
            for source in sources
            if isinstance(source.get("final_gate_status"), str)
        }
    )
    measured = [
        source.get("unsafe_reduction", {})
        for source in sources
        if isinstance(source.get("unsafe_reduction"), dict)
        and source.get("unsafe_reduction", {}).get("status") == "measured"
    ]
    baseline_values = [value.get("baseline_total_unsafe") for value in measured]
    current_values = [value.get("current_total_unsafe") for value in measured]
    reduced_values = [value.get("reduced_by") for value in measured]
    measured_complete = all(value is not None for value in baseline_values + current_values + reduced_values)
    return {
        "report_kind": "core-translation-quality-rollup",
        "sources": sources,
        "final_gate_statuses": statuses,
        "semantic_pass_count": sum(int_or_zero(source.get("semantic_pass_count")) for source in sources),
        "translation_coverage_numerator": max(
            [int_or_zero(source.get("translation_coverage_numerator")) for source in sources],
            default=0,
        ),
        "generated_draft_semantic_pass": any(bool(source.get("generated_draft_semantic_pass")) for source in sources),
        "unsafe_reduction": {
            "status": "measured" if measured else "not_measured",
            "baseline_total_unsafe": sum(baseline_values) if measured_complete else None,
            "current_total_unsafe": sum(current_values) if measured_complete else None,
            "reduced_by": sum(reduced_values) if measured_complete else None,
        },
        "boundary": (
            "This rollup exposes judge-facing before/after quality signals from evidence indexes. "
            "It does not convert accepted-evidence context into translator-generated semantic acceptance."
        ),
    }


def build_before_after_repair_exhibit_rollup(sources: list[dict[str, Any]]) -> dict[str, Any]:
    exhibit_sources: list[dict[str, Any]] = []
    for source in sources:
        translation = source.get("translation_before_after", {})
        repair = source.get("repair_summary", {})
        units = source.get("before_after_units", [])
        if not isinstance(translation, dict):
            translation = before_after_summary(None)
        if not isinstance(repair, dict):
            repair = repair_summary_for_bundle(None)
        if not isinstance(units, list):
            units = []
        has_exhibit = (
            bool(units)
            or repair.get("status") == "verified"
            or int_or_zero(repair.get("observed_repair_unit_count")) > 0
            or int_or_zero(repair.get("rollback_evidence_count")) > 0
            or bool(source.get("nested_artifact_ref_blockers"))
        )
        if not has_exhibit:
            continue
        exhibit_sources.append(
            {
                "entrypoint_id": source.get("entrypoint_id"),
                "artifact": source.get("artifact"),
                "final_gate_status": source.get("final_gate_status"),
                "translation_before_after": translation,
                "before_after_units": units,
                "nested_artifact_ref_blockers": [
                    blocker
                    for blocker in source.get("nested_artifact_ref_blockers", [])
                    if isinstance(blocker, str) and blocker
                ],
                "repair_summary": repair,
                "unsafe_reduction": source.get("unsafe_reduction", {}),
                "claim_boundary": {
                    "semantic_gate": False,
                    "generated_draft_semantic_pass": False,
                    "translation_coverage_numerator": 0,
                },
            }
        )

    before_after_units = [
        unit
        for source in exhibit_sources
        for unit in source.get("before_after_units", [])
        if isinstance(unit, dict)
    ]
    verified_baseline_unit_count = sum(
        1
        for unit in before_after_units
        if before_after_unit_has_verified_unsafe_baseline(unit)
    )
    measured = [
        source.get("unsafe_reduction", {})
        for source in exhibit_sources
        if isinstance(source.get("unsafe_reduction"), dict)
        and source.get("unsafe_reduction", {}).get("status") == "measured"
    ]
    baseline_values = [value.get("baseline_total_unsafe") for value in measured]
    current_values = [value.get("current_total_unsafe") for value in measured]
    reduced_values = [value.get("reduced_by") for value in measured]
    measured_complete = bool(measured) and all(value is not None for value in baseline_values + current_values + reduced_values)
    return {
        "report_kind": "before-after-repair-exhibit-rollup",
        "sources": exhibit_sources,
        "rollup": {
            "source_count": len(exhibit_sources),
            "bound_unit_count": sum(
                len(source.get("before_after_units", []))
                for source in exhibit_sources
                if isinstance(source.get("before_after_units"), list)
            ),
            "verified_baseline_unit_count": verified_baseline_unit_count,
            "missing_verified_baseline_unit_count": len(before_after_units) - verified_baseline_unit_count,
            "all_units_verified_baseline_bound": bool(before_after_units)
            and verified_baseline_unit_count == len(before_after_units),
            "measured_unsafe_unit_count": sum(
                sum(
                    1
                    for unit in source.get("before_after_units", [])
                    if isinstance(unit, dict)
                    and isinstance(unit.get("unsafe_reduction"), dict)
                    and unit.get("unsafe_reduction", {}).get("status") == "measured"
                )
                for source in exhibit_sources
                if isinstance(source.get("before_after_units"), list)
            ),
            "accepted_patch_unit_count": sum(
                sum(
                    1
                    for unit in source.get("before_after_units", [])
                    if isinstance(unit, dict) and isinstance(unit.get("accepted_patch"), dict)
                )
                for source in exhibit_sources
                if isinstance(source.get("before_after_units"), list)
            ),
            "verified_repair_source_count": sum(
                1
                for source in exhibit_sources
                if isinstance(source.get("repair_summary"), dict)
                and source.get("repair_summary", {}).get("status") == "verified"
            ),
            "observed_repair_unit_count": sum(
                int_or_zero(source.get("repair_summary", {}).get("observed_repair_unit_count"))
                for source in exhibit_sources
                if isinstance(source.get("repair_summary"), dict)
            ),
            "auto_recovered_unit_count": sum(
                int_or_zero(source.get("repair_summary", {}).get("auto_recovered_unit_count"))
                for source in exhibit_sources
                if isinstance(source.get("repair_summary"), dict)
            ),
            "rollback_evidence_count": sum(
                int_or_zero(source.get("repair_summary", {}).get("rollback_evidence_count"))
                for source in exhibit_sources
                if isinstance(source.get("repair_summary"), dict)
            ),
            "repair_round_cap": max(
                [
                    int_or_zero(source.get("repair_summary", {}).get("repair_round_cap"))
                    for source in exhibit_sources
                    if isinstance(source.get("repair_summary"), dict)
                ],
                default=0,
            ),
            "unsafe_reduced_by": sum(int_or_zero(value) for value in reduced_values),
            "unsafe_reduction": {
                "status": "measured" if measured else "not_measured",
                "baseline_total_unsafe": sum(baseline_values) if measured_complete else None,
                "current_total_unsafe": sum(current_values) if measured_complete else None,
                "reduced_by": sum(reduced_values) if measured_complete else None,
            },
            "semantic_gate": False,
            "generated_draft_semantic_pass": False,
            "translation_coverage_numerator": 0,
        },
        "semantic_gate": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
        "accepted_evidence_counts_as_translator_coverage": False,
        "boundary": (
            "This exhibit binds before/after unsafe-reduction and repair evidence for judge review. "
            "It is not a semantic gate and does not increase translator-generated coverage."
        ),
    }


def build_harness_architecture_summary(sources: list[dict[str, Any]]) -> dict[str, Any]:
    roles = sorted(
        {
            role
            for source in sources
            for role in source.get("roles", [])
            if isinstance(role, str)
        }
    )
    graph_nodes = next(
        (
            source.get("graph_nodes")
            for source in sources
            if isinstance(source.get("graph_nodes"), list) and source.get("graph_nodes")
        ),
        [],
    )
    contract_matrix = build_harness_contract_matrix(sources=sources, graph_nodes=graph_nodes, roles=roles)
    return {
        "report_kind": "harness-architecture-summary",
        "sources": sources,
        "graph_runtime": first_string_value(sources, "graph_runtime"),
        "graph_nodes": graph_nodes,
        "worker_count": max([int_or_zero(source.get("worker_count")) for source in sources], default=0),
        "repair_round_cap": max([int_or_zero(source.get("repair_round_cap")) for source in sources], default=0),
        "repair_checkpoint": first_string_value(sources, "repair_checkpoint"),
        "roles": roles,
        "checkpoint_backend": first_string_value(sources, "checkpoint_backend"),
        "contract_matrix": contract_matrix,
        "chat_output_is_evidence": any(source.get("chat_output_is_evidence") is True for source in sources),
        "semantic_gate": any(source.get("semantic_gate") is True for source in sources),
        "boundary": (
            "This summary documents the harness graph and agent contracts. Chat output and runtime logs "
            "remain diagnostic or command-contract evidence unless a validator-owned semantic gate accepts them."
        ),
    }


def build_harness_contract_matrix(
    *,
    sources: list[dict[str, Any]],
    graph_nodes: list[Any],
    roles: list[str],
) -> list[dict[str, Any]]:
    observed_artifacts = sorted(
        {
            artifact
            for source in sources
            for artifact in source.get("evidence_artifact_names", [])
            if isinstance(artifact, str)
        }
    )
    opencode_enabled = any(source.get("opencode_runtime_enabled") is True for source in sources)
    matrix = [
        contract_matrix_entry(
            stage="plan",
            graph_nodes=matching_graph_nodes(graph_nodes, ["load_plan", "fanout_workers"]),
            roles=matching_roles(roles, ["planner"]),
            artifacts=observed_or_default(
                observed_artifacts,
                ["worker_plan", "context_pack", "agent_index", "batch_profile_report"],
            ),
            validators=["validate_worker_plan_contract", "validate_context_ledger_contract"],
            boundary="Planner artifacts select worker assignments and context indexes only.",
        ),
        contract_matrix_entry(
            stage="translate",
            graph_nodes=matching_graph_nodes(graph_nodes, ["worker"]),
            roles=matching_roles(roles, ["worker"]),
            artifacts=observed_or_default(
                observed_artifacts,
                [
                    "assignment_request",
                    "worker_report",
                    "handoff_contract",
                    "opencode_session_evidence",
                    "opencode_preflight_report",
                ],
                extra=["opencode_contract_verification"] if opencode_enabled else [],
            ),
            validators=[
                "validate_opencode_agent_runtime_contract",
                "opencode_contract_verification",
                "validate_competition_summary_entrypoint_contract",
            ],
            boundary="Worker and OpenCode artifacts are command-contract evidence until validator-owned gates accept outputs.",
        ),
        contract_matrix_entry(
            stage="verify",
            graph_nodes=matching_graph_nodes(graph_nodes, ["merge"]),
            roles=matching_roles(roles, ["verifier"]),
            artifacts=observed_or_default(
                observed_artifacts,
                ["competition_summary", "workflow_metrics", "route_governance_metrics_report", "before_after_exhibit"],
            ),
            validators=[
                "validate_competition_summary_entrypoint_contract",
                "validate_route_governance_metrics_artifact",
            ],
            boundary="Verifier artifacts bind oracle, replay, diff, unsafe, and route metrics without creating a new semantic gate.",
        ),
        contract_matrix_entry(
            stage="repair",
            graph_nodes=matching_graph_nodes(graph_nodes, ["repair_retry"]),
            roles=matching_roles(roles, ["repairer"]),
            artifacts=observed_or_default(
                observed_artifacts,
                ["repair_hints", "rollback_evidence", "resume_manifest"],
            ),
            validators=["validate_repair_self_heal_contract", "validate_resume_manifest_contract"],
            boundary="Repair artifacts explain retries, rollback, and blocked next actions only.",
        ),
        contract_matrix_entry(
            stage="report",
            graph_nodes=matching_graph_nodes(graph_nodes, ["report"]),
            roles=matching_roles(roles, ["reporter"]),
            artifacts=observed_or_default(
                observed_artifacts,
                ["judge_evidence_index", "evaluate_report", "milestone_release_report", "judge_milestone_bundle"],
            ),
            validators=["validate_judge_evidence_index_contract", "validate_public_release_packet"],
            boundary="Reporter artifacts publish hashes, commands, and claim boundaries for judge review.",
        ),
    ]
    return matrix


def contract_matrix_entry(
    *,
    stage: str,
    graph_nodes: list[str],
    roles: list[str],
    artifacts: list[str],
    validators: list[str],
    boundary: str,
) -> dict[str, Any]:
    return {
        "stage": stage,
        "graph_nodes": graph_nodes,
        "roles": roles,
        "artifacts": artifacts,
        "validators": validators,
        "semantic_gate": False,
        "chat_output_is_evidence": False,
        "translation_coverage_numerator": 0,
        "boundary": boundary,
    }


def matching_graph_nodes(graph_nodes: list[Any], candidates: list[str]) -> list[str]:
    observed = [node for node in graph_nodes if isinstance(node, str)]
    return [candidate for candidate in candidates if candidate in observed]


def matching_roles(roles: list[str], candidates: list[str]) -> list[str]:
    return [candidate for candidate in candidates if candidate in roles]


def observed_or_default(observed: list[str], defaults: list[str], *, extra: list[str] | None = None) -> list[str]:
    selected = [artifact for artifact in defaults if artifact in observed or artifact in defaults]
    for artifact in extra or []:
        if artifact not in selected:
            selected.append(artifact)
    return selected


def build_opencode_evidence_policy(sources: list[dict[str, Any]]) -> dict[str, Any]:
    enabled = bool(sources)
    boundary_fields_explicit = all(bool(source.get("boundary_fields_explicit")) for source in sources) if sources else True
    chat_false = all(source.get("chat_output_is_evidence") is False for source in sources)
    semantic_false = all(source.get("semantic_gate") is False for source in sources)
    return {
        "enabled": enabled,
        "boundary_fields_explicit": boundary_fields_explicit,
        "chat_output_is_evidence_false": chat_false,
        "semantic_gate_false": semantic_false,
        "session_evidence_role": "command_contract_audit_only",
        "logs_evidence_role": "diagnostic_only",
        "semantic_gate": False,
        "boundary": "OpenCode session/log artifacts are command-contract and diagnostic evidence only.",
    }


def build_must_not_claim(opencode_runtime: dict[str, Any]) -> list[str]:
    claims = [
        "accepted_evidence_is_not_translator_generated_coverage",
        "blocked_repairs_are_not_translation_success",
        "before_after_exhibit_is_not_new_semantic_gate",
        "bundle_status_passed_is_not_project_level_translation_success",
        "quantitative_scorecard_is_not_semantic_acceptance",
        "local_simulation_is_not_competition_exact",
        "review_checklist_is_not_semantic_acceptance",
    ]
    if opencode_runtime.get("enabled_entrypoint_count", 0):
        claims.append("opencode_chat_output_is_semantic_evidence")
    return claims


def build_blocked_repairs_rollup(sources: list[dict[str, Any]]) -> dict[str, Any]:
    rollup = build_blocked_repairs_route_rollup(sources)
    rollup["source_count"] = len(sources)
    rollup["recorded_source_count"] = sum(
        1
        for source in sources
        if blocked_repairs_source_has_entries(source)
    )
    return {
        "report_kind": "blocked-repairs-rollup",
        "sources": [
            {
                "entrypoint_id": source.get("entrypoint_id"),
                "artifact": source.get("artifact"),
                "blocked_repairs": source.get("blocked_repairs", empty_blocked_repairs_rollup()),
            }
            for source in sources
        ],
        "rollup": rollup,
        "semantic_gate": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
        "accepted_evidence_counts_as_translator_coverage": False,
        "boundary": (
            "This rollup indexes validator-bound blocked-repair playbooks for judge review. It records "
            "fail-closed next steps for refused or blocked repair attempts. It is not a semantic acceptance "
            "gate, does not convert blocked or refused work into translation success, does not increase "
            "translator-generated coverage, and does not prove unsafe reduction."
        ),
    }


def blocked_repairs_source_has_entries(source: dict[str, Any]) -> bool:
    blocked = source.get("blocked_repairs", {})
    if not isinstance(blocked, dict):
        return False
    return int_or_zero(blocked.get("blocked_repair_count")) > 0


def before_after_exhibit_has_verified_unsafe_baseline(before_after_repair_exhibit: dict[str, Any]) -> bool:
    observed_unit = False
    for source in object_list(before_after_repair_exhibit.get("sources")):
        for unit in object_list(source.get("before_after_units")):
            observed_unit = True
            if not before_after_unit_has_verified_unsafe_baseline(unit):
                return False
    return observed_unit


def before_after_unit_has_verified_unsafe_baseline(unit: dict[str, Any]) -> bool:
    baseline = unit.get("baseline_verification")
    if not isinstance(baseline, dict):
        return False
    path = baseline.get("path")
    sha256 = baseline.get("sha256")
    return (
        isinstance(path, str)
        and bool(path)
        and isinstance(sha256, str)
        and len(sha256) == 64
        and baseline.get("status") == "passed"
        and baseline.get("semantic_pass") is True
        and baseline.get("semantic_claim_source") == "verified_unsafe_baseline_gates"
        and baseline.get("generated_draft_semantic_pass") is False
    )


def build_known_gaps(
    *,
    proof_classes: dict[str, Any],
    opencode_runtime: dict[str, Any],
    before_after_repair_exhibit: dict[str, Any],
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = [
        {
            "gap_id": "translator_generated_coverage_not_claimed",
            "boundary": "translation_coverage_numerator remains 0 for this bundle.",
        },
        {
            "gap_id": "accepted_evidence_not_translator_generated",
            "boundary": "Accepted-evidence semantic pass counts remain report context and do not become generated-draft acceptance.",
        },
    ]
    if not before_after_exhibit_has_verified_unsafe_baseline(before_after_repair_exhibit):
        gaps.append(
            {
                "gap_id": "c2rust_baseline_output_still_not_verified_here",
                "boundary": "This bundle does not prove a new C2Rust compile-passed or verified unsafe baseline.",
            }
        )
    if not proof_classes.get("has_competition_exact"):
        gaps.append(
            {
                "gap_id": "local_simulation_not_competition_exact",
                "boundary": "No entrypoint in this bundle has proof_class=competition-exact.",
            }
        )
    if opencode_runtime.get("enabled_entrypoint_count", 0):
        gaps.append(
            {
                "gap_id": "opencode_runtime_is_command_contract_evidence",
                "boundary": "OpenCode runtime/session evidence audits command execution; chat output is not semantic evidence.",
            }
        )
    return gaps


def build_quantitative_evaluation(
    *,
    workflow_metrics: dict[str, Any],
    route_governance_metrics: dict[str, Any],
    before_after_repair_exhibit: dict[str, Any],
    blocked_repairs_rollup: dict[str, Any],
    unsafe_scope: dict[str, Any],
    semantic_evidence: dict[str, Any],
    opencode_runtime: dict[str, Any],
    proof_classes: dict[str, Any],
    publishability: dict[str, Any],
) -> dict[str, Any]:
    workflow_rollup = (
        workflow_metrics.get("rollup", {}) if isinstance(workflow_metrics.get("rollup"), dict) else {}
    )
    route_rollup = (
        route_governance_metrics.get("rollup", {})
        if isinstance(route_governance_metrics.get("rollup"), dict)
        else {}
    )
    before_after_rollup = (
        before_after_repair_exhibit.get("rollup", {})
        if isinstance(before_after_repair_exhibit.get("rollup"), dict)
        else {}
    )
    blocked_rollup = (
        blocked_repairs_rollup.get("rollup", {})
        if isinstance(blocked_repairs_rollup.get("rollup"), dict)
        else {}
    )
    repair_activity = (
        workflow_rollup.get("repair_activity", {}) if isinstance(workflow_rollup.get("repair_activity"), dict) else {}
    )
    unsafe_reduction = (
        workflow_rollup.get("unsafe_reduction", {}) if isinstance(workflow_rollup.get("unsafe_reduction"), dict) else {}
    )
    accepted_evidence_count = int_or_zero(route_rollup.get("accepted_evidence_semantic_pass_count"))
    c2rust_baseline_rollup = (
        route_rollup.get("c2rust_baseline")
        if isinstance(route_rollup.get("c2rust_baseline"), dict)
        else empty_c2rust_baseline_milestone_rollup()
    )
    tracked_route_decisions = int_or_zero(route_rollup.get("tracked_route_decision_artifacts"))
    tracked_slice_contexts = int_or_zero(route_rollup.get("tracked_slice_gate_contexts"))
    opencode_enabled = int_or_zero(opencode_runtime.get("enabled_entrypoint_count")) > 0
    opencode_status = (
        "command_contract_executed"
        if opencode_enabled and bool(opencode_runtime.get("all_contracts_executed"))
        else "command_contract_incomplete"
        if opencode_enabled
        else "not_enabled"
    )
    return {
        "report_kind": "quantitative-evaluation-scorecard",
        "evaluation_scope": "bounded-mvp",
        "semantic_gate": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
        "project_slice_counts": {
            "entrypoint_count": len(
                [
                    entry
                    for entry in proof_classes.get("entrypoints", [])
                    if isinstance(entry, dict)
                ]
            ),
            "workflow_source_count": int_or_zero(workflow_rollup.get("source_count")),
            "workflow_units_total": int_or_zero(workflow_rollup.get("units_total")),
            "workflow_units_converged": int_or_zero(workflow_rollup.get("units_converged")),
            "before_after_bound_unit_count": int_or_zero(before_after_rollup.get("bound_unit_count")),
            "tracked_route_decision_artifacts": tracked_route_decisions,
            "tracked_slice_gate_contexts": tracked_slice_contexts,
        },
        "outcome_counts": {
            "accepted_evidence_semantic_pass_count": accepted_evidence_count,
            "translator_generated_semantic_pass_count": int_or_zero(
                semantic_evidence.get("translator_generated_semantic_pass_count")
            ),
            "translation_coverage_numerator": 0,
            "generated_draft_semantic_pass": False,
            "blocked_repair_count": int_or_zero(blocked_rollup.get("blocked_repair_count")),
            "human_action_required_count": int_or_zero(blocked_rollup.get("human_action_required_count")),
            "human_interventions": int_or_zero(workflow_rollup.get("human_interventions")),
            "llm_calls": int_or_zero(workflow_rollup.get("llm_calls")),
            "auto_recovered_unit_count": int_or_zero(before_after_rollup.get("auto_recovered_unit_count")),
            "rollback_evidence_count": int_or_zero(before_after_rollup.get("rollback_evidence_count")),
        },
        "unsafe_reduction": {
            "status": unsafe_reduction.get("status", "unknown"),
            "baseline_total_unsafe": int_or_none(unsafe_reduction.get("baseline_total_unsafe")),
            "current_total_unsafe": int_or_none(unsafe_reduction.get("current_total_unsafe")),
            "reduced_by": int_or_none(unsafe_reduction.get("reduced_by")),
            "scope": unsafe_scope.get("scope", "unknown"),
            "all_sources_measured": bool(unsafe_scope.get("all_sources_measured")),
            "measured_units": int_or_zero(unsafe_scope.get("measured_units")),
            "total_units": int_or_zero(unsafe_scope.get("total_units")),
        },
        "repair_activity": {
            "observed_source_count": int_or_zero(repair_activity.get("observed_source_count")),
            "repair_history_unit_count": int_or_zero(repair_activity.get("repair_history_unit_count")),
            "auto_recovered_unit_count": int_or_zero(repair_activity.get("auto_recovered_unit_count")),
            "avg_repair_rounds": number_or_zero(repair_activity.get("avg_repair_rounds")),
            "auto_recovery_rate": number_or_zero(repair_activity.get("auto_recovery_rate")),
            "human_interventions": int_or_zero(repair_activity.get("human_interventions")),
        },
        "self_heal_classification": build_self_heal_classification(blocked_rollup),
        "baseline_comparison": {
            "raw_c2rust": comparison_row(
                status="manifest_status_observed"
                if int_or_zero(c2rust_baseline_rollup.get("unique_manifest_count")) > 0
                else "not_verified_here",
                evidence_role="baseline_or_candidate_context_only",
                boundary="Raw C2Rust baseline manifests are counted as candidate context only; no output is accepted by this milestone bundle.",
                c2rust_baseline_rollup=c2rust_baseline_rollup,
            ),
            "c2rust_repair": comparison_row(
                status="not_verified_here",
                evidence_role="baseline_or_repair_context_only",
                boundary="C2Rust repair remains subject to the same validators and is not accepted by this scorecard.",
            ),
            "typed_ir_route": comparison_row(
                status="route_governance_tracked",
                evidence_role="candidate_generation_and_refusal_governance",
                boundary="Typed-IR route metrics are governance signals, not semantic acceptance.",
                tracked_route_decision_artifacts=tracked_route_decisions,
                tracked_slice_gate_contexts=tracked_slice_contexts,
            ),
            "opencode_llm_worker": comparison_row(
                status=opencode_status,
                evidence_role="command_contract_and_worker_runtime",
                boundary="OpenCode worker evidence records command-contract execution; chat output is not semantic evidence.",
                worker_count=int_or_zero(opencode_runtime.get("worker_count")),
                chat_output_is_evidence=False,
                chat_output_boundary_ok=bool(opencode_runtime.get("chat_output_is_evidence_false")),
            ),
            "handwritten_reference": comparison_row(
                status="accepted_evidence_context",
                evidence_role="oracle_or_reference_context",
                boundary="Accepted evidence may validate a case but does not become translator-generated coverage.",
                accepted_evidence_semantic_pass_count=accepted_evidence_count,
                counts_as_translator_generated_coverage=False,
            ),
        },
        "proof_class_summary": {
            "highest_proof_class": proof_classes.get("highest_proof_class", "unknown"),
            "competition_exact_publishable": bool(publishability.get("competition_exact_publishable")),
        },
        "claim_boundary": {
            "semantic_gate": False,
            "generated_draft_semantic_pass": False,
            "translation_coverage_numerator": 0,
            "scorecard_is_semantic_gate": False,
            "baseline_comparison_is_semantic_acceptance": False,
        },
        "boundary": (
            "This scorecard summarizes existing validator-owned artifacts for judge review. It is not a new "
            "semantic gate, does not increase translator-generated coverage, and does not claim competition-exact proof."
        ),
    }
