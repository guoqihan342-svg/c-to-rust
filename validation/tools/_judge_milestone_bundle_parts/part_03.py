def core_translation_quality_source_from_artifact(
    *,
    entrypoint_id: str,
    artifact: dict[str, Any] | None,
    repo_root: Path,
) -> dict[str, Any] | None:
    payload = load_present_json_artifact(artifact, repo_root=repo_root)
    if payload is None:
        return None
    quality = payload.get("core_translation_quality")
    if not isinstance(quality, dict):
        return None
    unsafe_reduction = quality.get("unsafe_reduction", {})
    if not isinstance(unsafe_reduction, dict):
        unsafe_reduction = {}
    final_gate_status = quality.get("final_gate_status")
    translation_before_after = before_after_summary(quality.get("translation_before_after"))
    before_after_units = before_after_unit_summaries(quality.get("before_after_units"))
    overlay_result = before_after_exhibit_unit_overlay_result(
        payload,
        entrypoint_id=entrypoint_id,
        repo_root=repo_root,
    )
    before_after_units = merge_before_after_exhibit_unit_overlays(
        before_after_units,
        overlay_result["overlays"],
    )
    repair_summary = repair_summary_for_bundle(quality.get("repair_summary"))
    return {
        "entrypoint_id": entrypoint_id,
        "artifact": artifact,
        "final_gate_status": final_gate_status if isinstance(final_gate_status, str) else "unknown",
        "semantic_pass_count": int_or_zero(quality.get("semantic_pass_count")),
        "translation_coverage_numerator": int_or_zero(quality.get("translation_coverage_numerator")),
        "generated_draft_semantic_pass": bool(quality.get("generated_draft_semantic_pass")),
        "translation_before_after": translation_before_after,
        "before_after_units": before_after_units,
        "nested_artifact_ref_blockers": overlay_result["blockers"],
        "repair_summary": repair_summary,
        "unsafe_reduction": {
            "status": unsafe_reduction.get("status", "unknown"),
            "baseline_total_unsafe": int_or_none(unsafe_reduction.get("baseline_total_unsafe")),
            "current_total_unsafe": int_or_none(unsafe_reduction.get("current_total_unsafe")),
            "reduced_by": int_or_none(unsafe_reduction.get("reduced_by")),
        },
    }


def before_after_summary(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {
            "status": "not_provided",
            "unit_count": 0,
            "measured_unsafe_unit_count": 0,
            "accepted_patch_unit_count": 0,
        }
    status = value.get("status")
    return {
        "status": status if isinstance(status, str) else "unknown",
        "unit_count": int_or_zero(value.get("unit_count")),
        "measured_unsafe_unit_count": int_or_zero(value.get("measured_unsafe_unit_count")),
        "accepted_patch_unit_count": int_or_zero(value.get("accepted_patch_unit_count")),
    }


def before_after_exhibit_unit_overlay_result(
    payload: dict[str, Any],
    *,
    entrypoint_id: str,
    repo_root: Path,
) -> dict[str, Any]:
    refs = payload.get("evidence_artifact_refs")
    if not isinstance(refs, dict):
        return {"overlays": {}, "blockers": []}
    result: dict[str, dict[str, Any]] = {}
    blockers: list[str] = []
    for ref_name in ["before_after_exhibit", "before_after_exhibit_report"]:
        ref = artifact_ref_from_existing(refs.get(ref_name), repo_root=repo_root)
        if ref is None:
            continue
        status = ref.get("status")
        if status == "sha256_mismatch":
            blockers.append(f"nested_artifact_sha256_mismatch:{entrypoint_id}:{ref_name}")
            continue
        if status == "missing_expected_sha256":
            blockers.append(f"nested_artifact_missing_sha256:{entrypoint_id}:{ref_name}")
            continue
        if status == "status_mismatch":
            blockers.append(f"nested_artifact_status_mismatch:{entrypoint_id}:{ref_name}")
            continue
        if status != "present":
            blockers.append(f"nested_artifact_not_present:{entrypoint_id}:{ref_name}:{status}")
            continue
        exhibit = load_present_json_artifact(ref, repo_root=repo_root)
        if not isinstance(exhibit, dict):
            continue
        units = exhibit.get("units")
        if not isinstance(units, list):
            continue
        for unit in units:
            if not isinstance(unit, dict):
                continue
            unit_id = unit.get("unit_id")
            if not isinstance(unit_id, str) or unit_id in result:
                continue
            overlay: dict[str, Any] = {}
            baseline_verification = baseline_verification_summary(unit.get("baseline_verification"))
            if baseline_verification is not None:
                overlay["baseline_verification"] = baseline_verification
            repair_history = repair_history_summary(unit.get("repair_history"))
            if repair_history is not None:
                overlay["repair_history"] = repair_history
            repair_rounds = int_or_none(unit.get("repair_rounds"))
            if repair_rounds is not None:
                overlay["repair_rounds"] = repair_rounds
            if isinstance(unit.get("auto_recovered"), bool):
                overlay["auto_recovered"] = unit["auto_recovered"]
            root_cause_key = unit.get("root_cause_key")
            if isinstance(root_cause_key, str) and root_cause_key:
                overlay["root_cause_key"] = root_cause_key
            patch_origin = patch_origin_summary(unit.get("patch_origin"))
            if patch_origin is not None:
                overlay["patch_origin"] = patch_origin
            safety_loop_provenance = safety_loop_provenance_summary(unit.get("safety_loop_provenance"))
            if safety_loop_provenance is not None:
                overlay["safety_loop_provenance"] = safety_loop_provenance
            if overlay:
                result[unit_id] = overlay
    return {"overlays": result, "blockers": blockers}


def merge_before_after_exhibit_unit_overlays(
    units: list[dict[str, Any]],
    overlays: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if not overlays:
        return units
    for unit in units:
        unit_id = unit.get("unit_id")
        if not isinstance(unit_id, str) or unit_id not in overlays:
            continue
        for key, value in overlays[unit_id].items():
            if key not in unit:
                unit[key] = deepcopy(value)
    return units


def artifact_binding_summary(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    path = value.get("path")
    sha256 = value.get("sha256")
    if not isinstance(path, str) or not isinstance(sha256, str):
        return None
    return {"path": path, "sha256": sha256}


def baseline_verification_summary(value: object) -> dict[str, Any] | None:
    binding = artifact_binding_summary(value)
    if binding is None or not isinstance(value, dict):
        return None
    status = value.get("status")
    semantic_pass = value.get("semantic_pass")
    semantic_claim_source = value.get("semantic_claim_source")
    generated_draft_semantic_pass = value.get("generated_draft_semantic_pass")
    if isinstance(status, str):
        binding["status"] = status
    if isinstance(semantic_pass, bool):
        binding["semantic_pass"] = semantic_pass
    if isinstance(semantic_claim_source, str):
        binding["semantic_claim_source"] = semantic_claim_source
    if isinstance(generated_draft_semantic_pass, bool):
        binding["generated_draft_semantic_pass"] = generated_draft_semantic_pass
    return binding


def repair_history_summary(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    patch_events_path = value.get("patch_events_path")
    patch_events_sha256 = value.get("patch_events_sha256")
    if not isinstance(patch_events_path, str) or not isinstance(patch_events_sha256, str):
        return None
    result: dict[str, Any] = {
        "patch_events_path": patch_events_path,
        "patch_events_sha256": patch_events_sha256,
    }
    statuses = value.get("statuses")
    if isinstance(statuses, list):
        result["statuses"] = [status for status in statuses if isinstance(status, str)]
    rollback_ids = value.get("rollback_ids")
    if isinstance(rollback_ids, list):
        result["rollback_ids"] = [rollback_id for rollback_id in rollback_ids if isinstance(rollback_id, str)]
    if isinstance(value.get("verified"), bool):
        result["verified"] = value["verified"]
    return result


def patch_origin_summary(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    source = value.get("source")
    if not isinstance(source, str) or not source:
        return None
    result: dict[str, Any] = {"source": source}
    for key in [
        "accepted_patch_bound",
        "opencode_session_bound",
        "repair_history_bound",
        "generated_draft_semantic_pass",
        "semantic_gate",
    ]:
        if isinstance(value.get(key), bool):
            result[key] = value[key]
    semantic_claim_source = value.get("semantic_claim_source")
    if isinstance(semantic_claim_source, str) and semantic_claim_source:
        result["semantic_claim_source"] = semantic_claim_source
    translation_coverage_numerator = int_or_none(value.get("translation_coverage_numerator"))
    if translation_coverage_numerator is not None:
        result["translation_coverage_numerator"] = translation_coverage_numerator
    return result


def safety_loop_provenance_summary(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    status = value.get("status")
    if not isinstance(status, str) or not status:
        return None
    result: dict[str, Any] = {"status": status}
    patch_source = value.get("patch_source")
    if isinstance(patch_source, str) and patch_source:
        result["patch_source"] = patch_source
    baseline_verification_status = value.get("baseline_verification_status")
    if isinstance(baseline_verification_status, str) and baseline_verification_status:
        result["baseline_verification_status"] = baseline_verification_status
    unsafe_delta = unsafe_reduction_summary(value.get("unsafe_delta"))
    if unsafe_delta is not None:
        result["unsafe_delta"] = unsafe_delta
    for key in [
        "opencode_session_bound",
        "repair_history_bound",
        "auto_recovered",
        "semantic_gate",
    ]:
        if isinstance(value.get(key), bool):
            result[key] = value[key]
    repair_rounds = int_or_none(value.get("repair_rounds"))
    if repair_rounds is not None:
        result["repair_rounds"] = repair_rounds
    translation_coverage_numerator = int_or_none(value.get("translation_coverage_numerator"))
    if translation_coverage_numerator is not None:
        result["translation_coverage_numerator"] = translation_coverage_numerator
    return result


def unsafe_reduction_summary(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        "status": value.get("status", "unknown"),
        "baseline_total_unsafe": int_or_none(value.get("baseline_total_unsafe")),
        "current_total_unsafe": int_or_none(value.get("current_total_unsafe")),
        "reduced_by": int_or_none(value.get("reduced_by")),
    }


def before_after_unit_summaries(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        unsafe_reduction = item.get("unsafe_reduction")
        if not isinstance(unsafe_reduction, dict):
            unsafe_reduction = {}
        unit: dict[str, Any] = {
            "unit_id": item.get("unit_id") if isinstance(item.get("unit_id"), str) else "unknown",
            "status": item.get("status") if isinstance(item.get("status"), str) else "unknown",
            "unsafe_reduction": {
                "status": unsafe_reduction.get("status", "unknown"),
                "baseline_total_unsafe": int_or_none(unsafe_reduction.get("baseline_total_unsafe")),
                "current_total_unsafe": int_or_none(unsafe_reduction.get("current_total_unsafe")),
                "reduced_by": int_or_none(unsafe_reduction.get("reduced_by")),
            },
        }
        for key in ["baseline", "final", "accepted_patch", "oracle_evidence"]:
            binding = artifact_binding_summary(item.get(key))
            if binding is not None:
                unit[key] = binding
        baseline_verification = baseline_verification_summary(item.get("baseline_verification"))
        if baseline_verification is not None:
            unit["baseline_verification"] = baseline_verification
        repair_history = repair_history_summary(item.get("repair_history"))
        if repair_history is not None:
            unit["repair_history"] = repair_history
        repair_rounds = int_or_none(item.get("repair_rounds"))
        if repair_rounds is not None:
            unit["repair_rounds"] = repair_rounds
        if isinstance(item.get("auto_recovered"), bool):
            unit["auto_recovered"] = item["auto_recovered"]
        root_cause_key = item.get("root_cause_key")
        if isinstance(root_cause_key, str) and root_cause_key:
            unit["root_cause_key"] = root_cause_key
        patch_origin = patch_origin_summary(item.get("patch_origin"))
        if patch_origin is not None:
            unit["patch_origin"] = patch_origin
        safety_loop_provenance = safety_loop_provenance_summary(item.get("safety_loop_provenance"))
        if safety_loop_provenance is not None:
            unit["safety_loop_provenance"] = safety_loop_provenance
        result.append(unit)
    return result


def workflow_before_after_unit_summaries(value: object) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in object_list(value):
        source = item.get("translation_before_after")
        if not isinstance(source, dict):
            source = item
        unit: dict[str, Any] = {
            "unit_id": item.get("unit_id") if isinstance(item.get("unit_id"), str) else "unknown",
        }
        status = source.get("status")
        if isinstance(status, str):
            unit["status"] = status
        for key in BEFORE_AFTER_ARTIFACT_REF_FIELDS:
            binding = artifact_binding_summary(source.get(key))
            if binding is not None:
                unit[key] = binding
        unsafe_reduction = unsafe_reduction_summary(source.get("unsafe_reduction"))
        if unsafe_reduction is not None:
            unit["unsafe_reduction"] = unsafe_reduction
        if any(key in unit for key in BEFORE_AFTER_ARTIFACT_REF_FIELDS) or "unsafe_reduction" in unit:
            result.append(unit)
    return result


def repair_summary_for_bundle(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {
            "status": "not_provided",
            "repair_round_cap": 0,
            "observed_repair_unit_count": 0,
            "auto_recovered_unit_count": 0,
            "rollback_evidence_count": 0,
        }
    observed = int_or_zero(value.get("observed_repair_unit_count"))
    if observed == 0:
        observed = int_or_zero(value.get("repair_history_unit_count"))
    auto_recovered = int_or_zero(value.get("auto_recovered_unit_count"))
    if auto_recovered == 0:
        auto_recovered = int_or_zero(value.get("auto_recovered_units"))
    rollback_evidence_count = int_or_zero(value.get("rollback_evidence_count"))
    if rollback_evidence_count == 0 and isinstance(value.get("histories"), list):
        rollback_evidence_count = sum(
            len(history.get("repair_history", {}).get("rollback_ids", []))
            for history in value["histories"]
            if isinstance(history, dict) and isinstance(history.get("repair_history"), dict)
        )
    status = value.get("status")
    return {
        "status": status if isinstance(status, str) else "unknown",
        "repair_round_cap": int_or_zero(value.get("repair_round_cap")),
        "observed_repair_unit_count": observed,
        "auto_recovered_unit_count": auto_recovered,
        "rollback_evidence_count": rollback_evidence_count,
        "avg_repair_rounds": number_or_zero(value.get("avg_repair_rounds")),
        "auto_recovery_rate": number_or_zero(value.get("auto_recovery_rate")),
        "human_interventions": int_or_zero(value.get("human_interventions")),
    }


def harness_architecture_source_from_artifact(
    *,
    entrypoint_id: str,
    artifact: dict[str, Any] | None,
    repo_root: Path,
) -> dict[str, Any] | None:
    payload = load_present_json_artifact(artifact, repo_root=repo_root)
    if payload is None:
        return None
    architecture = payload.get("harness_architecture")
    if not isinstance(architecture, dict):
        return None
    retry_policy = architecture.get("retry_policy", {})
    if not isinstance(retry_policy, dict):
        retry_policy = {}
    contracts = architecture.get("architecture_contracts", {})
    if not isinstance(contracts, dict):
        contracts = {}
    agent_contract = contracts.get("agent_coordination", {})
    if not isinstance(agent_contract, dict):
        agent_contract = {}
    graph_runtime = architecture.get("graph_runtime")
    graph_nodes = architecture.get("graph_nodes")
    roles = agent_contract.get("roles")
    repair_checkpoint = retry_policy.get("checkpoint")
    checkpoint_backend = agent_contract.get("checkpoint_backend")
    artifact_refs = payload.get("evidence_artifact_refs")
    evidence_artifact_names = sorted(artifact_refs.keys()) if isinstance(artifact_refs, dict) else []
    opencode_runtime = payload.get("opencode_agent_runtime")
    if not isinstance(opencode_runtime, dict):
        opencode_runtime = {}
    return {
        "entrypoint_id": entrypoint_id,
        "artifact": artifact,
        "graph_runtime": graph_runtime if isinstance(graph_runtime, str) else "unknown",
        "graph_nodes": [value for value in graph_nodes if isinstance(value, str)] if isinstance(graph_nodes, list) else [],
        "worker_count": int_or_zero(architecture.get("worker_count")),
        "repair_round_cap": int_or_zero(retry_policy.get("round_cap")),
        "repair_checkpoint": repair_checkpoint if isinstance(repair_checkpoint, str) else None,
        "roles": [value for value in roles if isinstance(value, str)] if isinstance(roles, list) else [],
        "checkpoint_backend": checkpoint_backend if isinstance(checkpoint_backend, str) else None,
        "evidence_artifact_names": evidence_artifact_names,
        "opencode_runtime_enabled": opencode_runtime.get("runtime") == "opencode"
        or opencode_runtime.get("worker_count") is not None,
        "opencode_worker_count": int_or_zero(opencode_runtime.get("worker_count")),
        "opencode_all_contracts_executed": opencode_runtime.get("all_contracts_executed")
        if isinstance(opencode_runtime.get("all_contracts_executed"), bool)
        else None,
        "chat_output_is_evidence": agent_contract.get("chat_output_is_evidence")
        if isinstance(agent_contract.get("chat_output_is_evidence"), bool)
        else None,
        "semantic_gate": agent_contract.get("semantic_gate")
        if isinstance(agent_contract.get("semantic_gate"), bool)
        else None,
    }


def build_workflow_metrics_rollup(sources: list[dict[str, Any]]) -> dict[str, Any]:
    measured_sources = [source for source in sources if source.get("unsafe_reduction_status") == "measured"]
    baseline_values = [source.get("baseline_total_unsafe") for source in measured_sources]
    current_values = [source.get("current_total_unsafe") for source in measured_sources]
    reduced_values = [source.get("reduced_by") for source in measured_sources]
    measured_complete = all(value is not None for value in baseline_values + current_values + reduced_values)
    return {
        "report_kind": "workflow-metrics-rollup",
        "sources": sources,
        "rollup": {
            "source_count": len(sources),
            "units_total": sum(int_or_zero(source.get("units_total")) for source in sources),
            "units_converged": sum(int_or_zero(source.get("units_converged")) for source in sources),
            "human_interventions": sum(int_or_zero(source.get("human_interventions")) for source in sources),
            "llm_calls": sum(int_or_zero(source.get("llm_calls")) for source in sources),
            "measured_unsafe_reduction_source_count": len(measured_sources),
            "repair_activity": build_repair_activity_rollup(sources),
            "unsafe_reduction": {
                "status": "measured" if measured_sources else "not_measured",
                "baseline_total_unsafe": sum(baseline_values) if measured_complete else None,
                "current_total_unsafe": sum(current_values) if measured_complete else None,
                "reduced_by": sum(reduced_values) if measured_complete else None,
            },
        },
    }


def build_repair_activity_rollup(sources: list[dict[str, Any]]) -> dict[str, Any]:
    units_total = sum(int_or_zero(source.get("units_total")) for source in sources)
    observed_sources = [
        source
        for source in sources
        if number_or_zero(source.get("avg_repair_rounds")) > 0
        or number_or_zero(source.get("auto_recovery_rate")) > 0
        or int_or_zero(source.get("repair_history_unit_count")) > 0
        or int_or_zero(source.get("auto_recovered_unit_count")) > 0
    ]
    return {
        "source_count": len(sources),
        "observed_source_count": len(observed_sources),
        "repair_history_unit_count": sum(int_or_zero(source.get("repair_history_unit_count")) for source in sources),
        "auto_recovered_unit_count": sum(int_or_zero(source.get("auto_recovered_unit_count")) for source in sources),
        "avg_repair_rounds": weighted_source_metric(sources, "avg_repair_rounds", units_total),
        "auto_recovery_rate": weighted_source_metric(sources, "auto_recovery_rate", units_total),
        "human_interventions": sum(int_or_zero(source.get("human_interventions")) for source in sources),
        "boundary": (
            "Repair activity summarizes hash-bound workflow metrics only. It is not a semantic gate, "
            "does not prove unsafe reduction without measured unsafe counts, and does not increase translation coverage."
        ),
    }


def weighted_source_metric(sources: list[dict[str, Any]], key: str, units_total: int) -> float:
    if units_total <= 0:
        return 0.0
    numerator = 0.0
    for source in sources:
        units = int_or_zero(source.get("units_total"))
        value = number_or_zero(source.get(key))
        numerator += float(value) * units
    return numerator / float(units_total)


def build_route_governance_metrics_rollup(sources: list[dict[str, Any]]) -> dict[str, Any]:
    all_retention_present = all(bool(source.get("retention_policy_present")) for source in sources) if sources else True
    all_reproducible = (
        all(
            source.get("target_artifacts_committed") is False
            and source.get("target_artifacts_retention_class") == "reproducible-local-output"
            for source in sources
        )
        if sources
        else True
    )
    return {
        "report_kind": "route-governance-metrics-rollup",
        "sources": sources,
        "rollup": {
            "source_count": len(sources),
            "translation_coverage_numerator": sum(
                int_or_zero(source.get("translation_coverage_numerator")) for source in sources
            ),
            "accepted_evidence_semantic_pass_count": sum(
                int_or_zero(source.get("accepted_evidence_semantic_pass_count")) for source in sources
            ),
            "tracked_route_decision_artifacts": sum(
                int_or_zero(source.get("tracked_route_decision_artifacts")) for source in sources
            ),
            "tracked_slice_gate_contexts": sum(
                int_or_zero(source.get("tracked_slice_gate_contexts")) for source in sources
            ),
            "tracked_capability_delta_ledgers": sum(
                int_or_zero(source.get("tracked_capability_delta_ledgers")) for source in sources
            ),
            "tracked_capability_delta_count": sum(
                int_or_zero(source.get("tracked_capability_delta_count")) for source in sources
            ),
            "capability_vs_governance_delta": build_capability_vs_governance_delta(sources),
            "s2_workflow_run_count": sum(int_or_zero(source.get("s2_workflow_run_count")) for source in sources),
            "s2_unsafe_reduction": {
                "status": "measured"
                if any(source.get("s2_unsafe_reduction_status") == "measured" for source in sources)
                else "not_measured",
                "reduced_by": sum(int_or_zero(source.get("s2_reduced_by")) for source in sources),
            },
            "c2rust_baseline": build_c2rust_baseline_milestone_rollup(sources),
            "blocked_repairs": build_blocked_repairs_route_rollup(sources),
            "all_retention_policies_present": all_retention_present,
            "all_target_artifacts_reproducible": all_reproducible,
        },
        "boundary": (
            "Route governance metrics constrain public claims and artifact retention. They are not a semantic gate "
            "and do not increase translator-generated translation coverage."
        ),
    }


def capability_delta_ledger_source(value: object) -> dict[str, Any]:
    payload = value if isinstance(value, dict) else {}
    return {
        "ledger_count": int_or_zero(payload.get("ledger_count")),
        "delta_count": int_or_zero(payload.get("delta_count")),
        "governance_delta_count": int_or_zero(payload.get("governance_delta_count")),
        "verification_command_count": int_or_zero(payload.get("verification_command_count")),
        "translator_generated_semantic_pass_count": int_or_zero(
            payload.get("translator_generated_semantic_pass_count")
        ),
        "semantic_pass_count": int_or_zero(payload.get("semantic_pass_count")),
        "accepted_evidence_semantic_pass_count": int_or_zero(payload.get("accepted_evidence_semantic_pass_count")),
        "generated_candidate_status": int_count_map(payload.get("generated_candidate_status")),
        "route_levels": int_count_map(payload.get("route_levels")),
        "route_statuses": int_count_map(payload.get("route_statuses")),
        "by_construct": int_count_map(payload.get("by_construct")),
        "blocked_callee_count": int_or_zero(payload.get("blocked_callee_count")),
        "semantic_gate": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
    }


def build_capability_vs_governance_delta(sources: list[dict[str, Any]]) -> dict[str, Any]:
    ledgers = [
        source.get("capability_delta_ledger")
        for source in sources
        if isinstance(source.get("capability_delta_ledger"), dict)
    ]
    return {
        "capability_ledger_count": sum(int_or_zero(ledger.get("ledger_count")) for ledger in ledgers),
        "capability_delta_count": sum(int_or_zero(ledger.get("delta_count")) for ledger in ledgers),
        "governance_delta_count": sum(int_or_zero(ledger.get("governance_delta_count")) for ledger in ledgers),
        "verification_command_count": sum(int_or_zero(ledger.get("verification_command_count")) for ledger in ledgers),
        "translator_generated_semantic_pass_count": sum(
            int_or_zero(ledger.get("translator_generated_semantic_pass_count")) for ledger in ledgers
        ),
        "accepted_evidence_semantic_pass_count": sum(
            int_or_zero(ledger.get("accepted_evidence_semantic_pass_count")) for ledger in ledgers
        ),
        "route_decision_artifacts": sum(int_or_zero(source.get("tracked_route_decision_artifacts")) for source in sources),
        "slice_gate_contexts": sum(int_or_zero(source.get("tracked_slice_gate_contexts")) for source in sources),
        "blocked_callee_count": sum(int_or_zero(ledger.get("blocked_callee_count")) for ledger in ledgers),
        "semantic_gate": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
        "boundary": (
            "Capability and governance deltas are review metrics only. They separate translator capability changes "
            "from evidence, route, and reproduction governance work, and do not create semantic acceptance."
        ),
    }


def build_progress_delta_ledger(
    *,
    route_governance_metrics: dict[str, Any],
    workflow_metrics: dict[str, Any],
    before_after_repair_exhibit: dict[str, Any],
) -> dict[str, Any]:
    route_rollup = (
        route_governance_metrics.get("rollup", {})
        if isinstance(route_governance_metrics.get("rollup"), dict)
        else {}
    )
    delta = (
        route_rollup.get("capability_vs_governance_delta", {})
        if isinstance(route_rollup.get("capability_vs_governance_delta"), dict)
        else {}
    )
    workflow_rollup = (
        workflow_metrics.get("rollup", {}) if isinstance(workflow_metrics.get("rollup"), dict) else {}
    )
    repair_progress = build_workflow_repair_progress_delta(
        workflow_metrics=workflow_metrics,
        before_after_repair_exhibit=before_after_repair_exhibit,
    )
    return {
        "report_kind": "progress-delta-ledger",
        "semantic_gate": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
        "capability_delta": {
            "ledger_count": int_or_zero(delta.get("capability_ledger_count")),
            "delta_count": int_or_zero(delta.get("capability_delta_count")),
            "translator_generated_semantic_pass_count": int_or_zero(
                delta.get("translator_generated_semantic_pass_count")
            ),
            "accepted_evidence_semantic_pass_count": int_or_zero(
                delta.get("accepted_evidence_semantic_pass_count")
            ),
        },
        "governance_delta": {
            "delta_count": int_or_zero(delta.get("governance_delta_count")),
            "verification_command_count": int_or_zero(delta.get("verification_command_count")),
            "route_decision_artifacts": int_or_zero(delta.get("route_decision_artifacts")),
            "slice_gate_contexts": int_or_zero(delta.get("slice_gate_contexts")),
            "blocked_callee_count": int_or_zero(delta.get("blocked_callee_count")),
        },
        "workflow_delta": {
            "workflow_source_count": int_or_zero(workflow_rollup.get("source_count")),
            "workflow_units_total": int_or_zero(workflow_rollup.get("units_total")),
            "workflow_units_converged": int_or_zero(workflow_rollup.get("units_converged")),
            "repair_history_unit_count": repair_progress["repair_history_unit_count"],
            "observed_repair_unit_count": repair_progress["observed_repair_unit_count"],
            "auto_recovered_unit_count": repair_progress["auto_recovered_unit_count"],
            "rollback_evidence_count": repair_progress["rollback_evidence_count"],
            "before_after_repair_source_count": repair_progress["before_after_repair_source_count"],
            "repair_delta_source_count": repair_progress["repair_delta_source_count"],
            "human_interventions": int_or_zero(workflow_rollup.get("human_interventions")),
            "llm_calls": int_or_zero(workflow_rollup.get("llm_calls")),
        },
        "boundary": (
            "Progress deltas distinguish translator capability movement from governance and workflow evidence. "
            "They are reviewer navigation metrics only, not semantic gates or translation coverage numerator."
        ),
    }


def build_workflow_repair_progress_delta(
    *,
    workflow_metrics: dict[str, Any],
    before_after_repair_exhibit: dict[str, Any],
) -> dict[str, int]:
    by_source: dict[str, dict[str, int]] = {}
    workflow_sources = object_list(workflow_metrics.get("sources"))
    before_after_sources = object_list(before_after_repair_exhibit.get("sources"))

    for index, source in enumerate(workflow_sources):
        key = repair_progress_source_key(source, prefix="workflow", index=index)
        entry = by_source.setdefault(key, empty_repair_progress_source())
        repair_history_units = int_or_zero(source.get("repair_history_unit_count"))
        entry["repair_history_unit_count"] = max(entry["repair_history_unit_count"], repair_history_units)
        entry["observed_repair_unit_count"] = max(entry["observed_repair_unit_count"], repair_history_units)
        entry["auto_recovered_unit_count"] = max(
            entry["auto_recovered_unit_count"],
            int_or_zero(source.get("auto_recovered_unit_count")),
        )

    for index, source in enumerate(before_after_sources):
        key = repair_progress_source_key(source, prefix="before_after", index=index)
        entry = by_source.setdefault(key, empty_repair_progress_source())
        repair_summary = source.get("repair_summary") if isinstance(source.get("repair_summary"), dict) else {}
        observed = int_or_zero(repair_summary.get("observed_repair_unit_count"))
        auto_recovered = int_or_zero(repair_summary.get("auto_recovered_unit_count"))
        rollback = int_or_zero(repair_summary.get("rollback_evidence_count"))
        verified_source = 1 if repair_summary.get("status") == "verified" or observed > 0 or rollback > 0 else 0
        entry["repair_history_unit_count"] = max(entry["repair_history_unit_count"], observed)
        entry["observed_repair_unit_count"] = max(entry["observed_repair_unit_count"], observed)
        entry["auto_recovered_unit_count"] = max(entry["auto_recovered_unit_count"], auto_recovered)
        entry["rollback_evidence_count"] = max(entry["rollback_evidence_count"], rollback)
        entry["before_after_repair_source_count"] = max(entry["before_after_repair_source_count"], verified_source)

    if by_source:
        return sum_repair_progress_sources(by_source.values())

    workflow_rollup = (
        workflow_metrics.get("rollup", {}) if isinstance(workflow_metrics.get("rollup"), dict) else {}
    )
    repair_activity = (
        workflow_rollup.get("repair_activity", {}) if isinstance(workflow_rollup.get("repair_activity"), dict) else {}
    )
    before_after_rollup = (
        before_after_repair_exhibit.get("rollup", {})
        if isinstance(before_after_repair_exhibit.get("rollup"), dict)
        else {}
    )
    return {
        "repair_history_unit_count": max(
            int_or_zero(repair_activity.get("repair_history_unit_count")),
            int_or_zero(before_after_rollup.get("observed_repair_unit_count")),
        ),
        "observed_repair_unit_count": max(
            int_or_zero(repair_activity.get("repair_history_unit_count")),
            int_or_zero(before_after_rollup.get("observed_repair_unit_count")),
        ),
        "auto_recovered_unit_count": max(
            int_or_zero(repair_activity.get("auto_recovered_unit_count")),
            int_or_zero(before_after_rollup.get("auto_recovered_unit_count")),
        ),
        "rollback_evidence_count": int_or_zero(before_after_rollup.get("rollback_evidence_count")),
        "before_after_repair_source_count": int_or_zero(before_after_rollup.get("verified_repair_source_count")),
        "repair_delta_source_count": int_or_zero(repair_activity.get("observed_source_count"))
        + int_or_zero(before_after_rollup.get("verified_repair_source_count")),
    }


def empty_repair_progress_source() -> dict[str, int]:
    return {
        "repair_history_unit_count": 0,
        "observed_repair_unit_count": 0,
        "auto_recovered_unit_count": 0,
        "rollback_evidence_count": 0,
        "before_after_repair_source_count": 0,
    }


def repair_progress_source_key(source: dict[str, Any], *, prefix: str, index: int) -> str:
    entrypoint_id = source.get("entrypoint_id")
    if isinstance(entrypoint_id, str) and entrypoint_id:
        return f"entrypoint:{entrypoint_id}"
    artifact = source.get("artifact")
    if isinstance(artifact, dict) and isinstance(artifact.get("path"), str) and artifact["path"]:
        return f"artifact:{artifact['path']}"
    return f"{prefix}:{index}"


def sum_repair_progress_sources(sources: Iterable[dict[str, int]]) -> dict[str, int]:
    result = empty_repair_progress_source()
    repair_delta_source_count = 0
    for source in sources:
        has_repair_delta = False
        for field in result:
            value = int_or_zero(source.get(field))
            result[field] += value
            if value > 0:
                has_repair_delta = True
        if has_repair_delta:
            repair_delta_source_count += 1
    result["repair_delta_source_count"] = repair_delta_source_count
    return result


def c2rust_baseline_source(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return empty_c2rust_baseline_route_source()
    return {
        "report_kind": value.get("report_kind")
        if isinstance(value.get("report_kind"), str)
        else "c2rust-baseline-rollup",
        "status": value.get("status") if isinstance(value.get("status"), str) else "unknown",
        "manifest_count": int_or_zero(value.get("manifest_count")),
        "generated_output_count": int_or_zero(value.get("generated_output_count")),
        "skipped_without_output_count": int_or_zero(value.get("skipped_without_output_count")),
        "compile_attempted_count": int_or_zero(value.get("compile_attempted_count")),
        "compile_passed_count": int_or_zero(value.get("compile_passed_count")),
        "compile_semantic_pass_count": 0,
        "status_counts": int_count_map(value.get("status_counts")),
        "output_status_counts": int_count_map(value.get("output_status_counts")),
        "compile_status_counts": int_count_map(value.get("compile_status_counts")),
        "manifests": object_list(value.get("manifests")),
        "semantic_gate": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
        "boundary": value.get("boundary")
        if isinstance(value.get("boundary"), str)
        else "C2Rust baseline status is candidate context only.",
    }


def empty_c2rust_baseline_route_source() -> dict[str, Any]:
    return {
        "report_kind": "c2rust-baseline-rollup",
        "status": "none",
        "manifest_count": 0,
        "generated_output_count": 0,
        "skipped_without_output_count": 0,
        "compile_attempted_count": 0,
        "compile_passed_count": 0,
        "compile_semantic_pass_count": 0,
        "status_counts": {},
        "output_status_counts": {},
        "compile_status_counts": {},
        "manifests": [],
        "semantic_gate": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
        "boundary": "C2Rust baseline status is candidate context only.",
    }


def build_c2rust_baseline_milestone_rollup(sources: list[dict[str, Any]]) -> dict[str, Any]:
    report_sources = [
        source
        for source in sources
        if isinstance(source.get("c2rust_baseline"), dict)
        and source.get("c2rust_baseline", {}).get("report_kind") == "c2rust-baseline-rollup"
    ]
    by_evidence_root: dict[str, dict[str, Any]] = {}
    conflict_roots: list[str] = []
    for index, source in enumerate(report_sources):
        key = source.get("evidence_root") if isinstance(source.get("evidence_root"), str) else f"entrypoint:{index}"
        baseline = source["c2rust_baseline"]
        if key in by_evidence_root:
            if comparable_c2rust_baseline_payload(by_evidence_root[key]) != comparable_c2rust_baseline_payload(baseline):
                conflict_roots.append(key)
            continue
        by_evidence_root[key] = baseline

    status_counts: Counter[str] = Counter()
    output_status_counts: Counter[str] = Counter()
    compile_status_counts: Counter[str] = Counter()
    manifests_by_key: dict[str, dict[str, Any]] = {}
    generated_output_count = 0
    skipped_without_output_count = 0
    compile_attempted_count = 0
    compile_passed_count = 0

    for baseline in by_evidence_root.values():
        status_counts.update(int_count_map(baseline.get("status_counts")))
        output_status_counts.update(int_count_map(baseline.get("output_status_counts")))
        compile_status_counts.update(int_count_map(baseline.get("compile_status_counts")))
        generated_output_count += int_or_zero(baseline.get("generated_output_count"))
        skipped_without_output_count += int_or_zero(baseline.get("skipped_without_output_count"))
        compile_attempted_count += int_or_zero(baseline.get("compile_attempted_count"))
        compile_passed_count += int_or_zero(baseline.get("compile_passed_count"))
        for manifest in object_list(baseline.get("manifests")):
            manifest_key = manifest_identity(manifest)
            if manifest_key:
                manifests_by_key.setdefault(manifest_key, manifest)

    unique_manifest_count = len(manifests_by_key)
    if unique_manifest_count == 0:
        unique_manifest_count = sum(int_or_zero(baseline.get("manifest_count")) for baseline in by_evidence_root.values())
    return {
        "report_kind": "c2rust-baseline-milestone-rollup",
        "status": "conflict" if conflict_roots else "observed" if report_sources else "none",
        "source_report_count": len(report_sources),
        "unique_evidence_root_count": len(by_evidence_root),
        "unique_manifest_count": unique_manifest_count,
        "generated_output_count": generated_output_count,
        "skipped_without_output_count": skipped_without_output_count,
        "compile_attempted_count": compile_attempted_count,
        "compile_passed_count": compile_passed_count,
        "compile_semantic_pass_count": 0,
        "status_counts": sorted_int_counter(status_counts),
        "output_status_counts": sorted_int_counter(output_status_counts),
        "compile_status_counts": sorted_int_counter(compile_status_counts),
        "manifests": [manifests_by_key[key] for key in sorted(manifests_by_key)],
        "conflict_evidence_roots": sorted(set(conflict_roots)),
        "semantic_gate": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
        "boundary": (
            "C2Rust baseline manifest, output, and compile status are candidate-context observations only; "
            "compile success is not semantic equivalence and does not increase translator-generated coverage."
        ),
    }


def empty_c2rust_baseline_milestone_rollup() -> dict[str, Any]:
    return build_c2rust_baseline_milestone_rollup([])


def comparable_c2rust_baseline_payload(value: dict[str, Any]) -> str:
    comparable = {
        "manifest_count": int_or_zero(value.get("manifest_count")),
        "generated_output_count": int_or_zero(value.get("generated_output_count")),
        "skipped_without_output_count": int_or_zero(value.get("skipped_without_output_count")),
        "compile_attempted_count": int_or_zero(value.get("compile_attempted_count")),
        "compile_passed_count": int_or_zero(value.get("compile_passed_count")),
        "status_counts": int_count_map(value.get("status_counts")),
        "output_status_counts": int_count_map(value.get("output_status_counts")),
        "compile_status_counts": int_count_map(value.get("compile_status_counts")),
        "manifests": object_list(value.get("manifests")),
    }
    return json.dumps(comparable, sort_keys=True)
