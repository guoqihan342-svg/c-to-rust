def opencode_workflow_metric_units_by_id(workflow_metrics_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    units = workflow_metrics_payload.get("per_unit_statuses")
    if not isinstance(units, list):
        raise ValueError("opencode_safety_transform_attempt.workflow_metrics.per_unit_statuses must be a list")
    result: dict[str, dict[str, Any]] = {}
    for index, unit_value in enumerate(units):
        if not isinstance(unit_value, dict):
            continue
        unit_id = unit_value.get("unit_id")
        if not isinstance(unit_id, str) or not unit_id:
            continue
        if unit_id in result:
            raise ValueError("opencode_safety_transform_attempt.workflow_metrics.per_unit_statuses unit_id values must be unique")
        result[unit_id] = unit_value
    return result


def validate_opencode_safety_transform_unit_matches_workflow_metrics(
    unit: dict[str, Any],
    workflow_metric_units: dict[str, dict[str, Any]],
    *,
    index: int,
    repo_root: Path,
) -> None:
    prefix = f"opencode_safety_transform_attempt.safety_transform_units[{index}]"
    unit_id = require_string(unit.get("unit_id"), f"{prefix}.unit_id")
    workflow_unit = workflow_metric_units.get(unit_id)
    if workflow_unit is None:
        raise ValueError(f"{prefix}.unit_id must match workflow_metrics.per_unit_statuses")
    if workflow_unit.get("status") != unit.get("status"):
        raise ValueError(f"{prefix}.status must match workflow_metrics.per_unit_statuses")

    workflow_evidence = require_object(
        workflow_unit.get("translation_before_after"),
        f"{prefix}.workflow_metrics.per_unit_statuses.translation_before_after",
    )
    patch_evidence = require_object(unit.get("patch_evidence"), f"{prefix}.patch_evidence")
    for field in ("baseline", "final", "accepted_patch", "patch_log"):
        compare_artifact_binding(
            validate_artifact_binding_shape(
                patch_evidence.get(field),
                f"{prefix}.patch_evidence.{field}",
                repo_root=repo_root,
            ),
            validate_artifact_binding_shape(
                workflow_evidence.get(field),
                f"{prefix}.workflow_metrics.per_unit_statuses.translation_before_after.{field}",
                repo_root=repo_root,
            ),
            f"{prefix}.patch_evidence.{field} must match workflow_metrics.per_unit_statuses",
        )

    delta = require_object(unit.get("verification_delta"), f"{prefix}.verification_delta")
    compare_artifact_binding(
        validate_verified_unsafe_baseline_ref(
            delta.get("baseline_verification"),
            f"{prefix}.verification_delta.baseline_verification",
            repo_root=repo_root,
        ),
        validate_verified_unsafe_baseline_ref(
            workflow_evidence.get("baseline_verification"),
            f"{prefix}.workflow_metrics.per_unit_statuses.translation_before_after.baseline_verification",
            repo_root=repo_root,
        ),
        f"{prefix}.verification_delta.baseline_verification must match workflow_metrics.per_unit_statuses",
    )
    for unit_field, workflow_field in (
        ("oracle_evidence", "oracle_evidence"),
        ("unsafe_scan_evidence", "unsafe_scan_evidence"),
    ):
        compare_artifact_binding(
            validate_artifact_binding_shape(
                delta.get(unit_field),
                f"{prefix}.verification_delta.{unit_field}",
                repo_root=repo_root,
            ),
            validate_artifact_binding_shape(
                workflow_evidence.get(workflow_field),
                f"{prefix}.workflow_metrics.per_unit_statuses.translation_before_after.{workflow_field}",
                repo_root=repo_root,
            ),
            f"{prefix}.verification_delta.{unit_field} must match workflow_metrics.per_unit_statuses",
        )
    semantic_evidence = require_object(delta.get("semantic_evidence"), f"{prefix}.verification_delta.semantic_evidence")
    workflow_semantic = require_object(
        workflow_evidence.get("semantic_evidence"),
        f"{prefix}.workflow_metrics.per_unit_statuses.translation_before_after.semantic_evidence",
    )
    compare_artifact_binding(
        validate_artifact_binding_shape(
            semantic_evidence.get("schema_diff"),
            f"{prefix}.verification_delta.semantic_evidence.schema_diff",
            repo_root=repo_root,
        ),
        validate_artifact_binding_shape(
            workflow_semantic.get("schema_diff"),
            f"{prefix}.workflow_metrics.per_unit_statuses.translation_before_after.semantic_evidence.schema_diff",
            repo_root=repo_root,
        ),
        f"{prefix}.verification_delta.semantic_evidence.schema_diff must match workflow_metrics.per_unit_statuses",
    )
    compare_opencode_measured_unsafe_delta(
        require_object(delta.get("unsafe_reduction"), f"{prefix}.verification_delta.unsafe_reduction"),
        require_object(
            workflow_evidence.get("unsafe_reduction"),
            f"{prefix}.workflow_metrics.per_unit_statuses.translation_before_after.unsafe_reduction",
        ),
        f"{prefix}.verification_delta.unsafe_reduction",
    )

    repair_history = unit.get("repair_history")
    workflow_repair_history = workflow_unit.get("repair_history")
    if repair_history is None and workflow_repair_history is None:
        return
    if not isinstance(repair_history, dict) or not isinstance(workflow_repair_history, dict):
        raise ValueError(f"{prefix}.repair_history must match workflow_metrics.per_unit_statuses")
    for field in ("patch_events_path", "patch_events_sha256", "statuses", "verified", "rollback_ids"):
        if repair_history.get(field) != workflow_repair_history.get(field):
            raise ValueError(f"{prefix}.repair_history.{field} must match workflow_metrics.per_unit_statuses")


def validate_opencode_safety_transform_unit_contract(
    unit: dict[str, Any],
    *,
    index: int,
    repo_root: Path,
) -> int:
    prefix = f"opencode_safety_transform_attempt.safety_transform_units[{index}]"
    if unit.get("semantic_gate") is not False:
        raise ValueError(f"{prefix}.semantic_gate must be false")
    if unit.get("translation_coverage_numerator") != 0:
        raise ValueError(f"{prefix}.translation_coverage_numerator must be 0")
    round_contract = require_object(unit.get("round_contract"), f"{prefix}.round_contract")
    if round_contract.get("single_patch_per_round") is not True:
        raise ValueError(f"{prefix}.round_contract.single_patch_per_round must be true")
    if round_contract.get("max_repair_rounds") != 5:
        raise ValueError(f"{prefix}.round_contract.max_repair_rounds must be 5")

    patch_evidence = require_object(unit.get("patch_evidence"), f"{prefix}.patch_evidence")
    validate_artifact_binding_shape(patch_evidence.get("baseline"), f"{prefix}.patch_evidence.baseline", repo_root=repo_root)
    validate_artifact_binding_shape(patch_evidence.get("final"), f"{prefix}.patch_evidence.final", repo_root=repo_root)
    accepted_patch = validate_artifact_binding_shape(
        patch_evidence.get("accepted_patch"),
        f"{prefix}.patch_evidence.accepted_patch",
        repo_root=repo_root,
    )
    accepted_patch_log = validate_artifact_binding_shape(
        patch_evidence.get("patch_log"),
        f"{prefix}.patch_evidence.patch_log",
        repo_root=repo_root,
    )

    delta = require_object(unit.get("verification_delta"), f"{prefix}.verification_delta")
    if delta.get("compiled") is not True:
        raise ValueError(f"{prefix}.verification_delta.compiled must be true")
    accepted_oracle = validate_artifact_binding_shape(
        delta.get("oracle_evidence"),
        f"{prefix}.verification_delta.oracle_evidence",
        repo_root=repo_root,
    )
    accepted_unsafe_scan = validate_artifact_binding_shape(
        delta.get("unsafe_scan_evidence"),
        f"{prefix}.verification_delta.unsafe_scan_evidence",
        repo_root=repo_root,
    )
    semantic_evidence = require_object(delta.get("semantic_evidence"), f"{prefix}.verification_delta.semantic_evidence")
    accepted_schema_diff = validate_artifact_binding_shape(
        semantic_evidence.get("schema_diff"),
        f"{prefix}.verification_delta.semantic_evidence.schema_diff",
        repo_root=repo_root,
    )
    accepted_unsafe_reduction = require_object(
        delta.get("unsafe_reduction"),
        f"{prefix}.verification_delta.unsafe_reduction",
    )
    validate_opencode_measured_unsafe_delta(accepted_unsafe_reduction, f"{prefix}.verification_delta.unsafe_reduction")

    rounds = unit.get("rounds")
    if not isinstance(rounds, list) or not rounds:
        raise ValueError(f"{prefix}.rounds must be a non-empty list")
    if len(rounds) > 5:
        raise ValueError(f"{prefix}.rounds must not exceed 5")
    for round_index, round_value in enumerate(rounds):
        round_payload = require_object(round_value, f"{prefix}.rounds[{round_index}]")
        if round_payload.get("single_patch_per_round") is not True:
            raise ValueError(f"{prefix}.rounds[{round_index}].single_patch_per_round must be true")
        round_patch = validate_artifact_binding_shape(
            round_payload.get("patch"),
            f"{prefix}.rounds[{round_index}].patch",
            repo_root=repo_root,
        )
        round_patch_log = validate_artifact_binding_shape(
            round_payload.get("patch_log"),
            f"{prefix}.rounds[{round_index}].patch_log",
            repo_root=repo_root,
        )
        round_oracle = validate_artifact_binding_shape(
            round_payload.get("oracle_evidence"),
            f"{prefix}.rounds[{round_index}].oracle_evidence",
            repo_root=repo_root,
        )
        round_schema_diff = validate_artifact_binding_shape(
            round_payload.get("schema_diff"),
            f"{prefix}.rounds[{round_index}].schema_diff",
            repo_root=repo_root,
        )
        round_unsafe_scan = validate_artifact_binding_shape(
            round_payload.get("unsafe_scan_evidence"),
            f"{prefix}.rounds[{round_index}].unsafe_scan_evidence",
            repo_root=repo_root,
        )
        round_unsafe_delta = require_object(round_payload.get("unsafe_delta"), f"{prefix}.rounds[{round_index}].unsafe_delta")
        validate_opencode_measured_unsafe_delta(round_unsafe_delta, f"{prefix}.rounds[{round_index}].unsafe_delta")
        if round_index == len(rounds) - 1:
            compare_artifact_binding(
                round_patch,
                accepted_patch,
                f"{prefix}.rounds[{round_index}].patch must match accepted_patch",
            )
            compare_artifact_binding(
                round_patch_log,
                accepted_patch_log,
                f"{prefix}.rounds[{round_index}].patch_log must match patch_evidence.patch_log",
            )
            compare_artifact_binding(
                round_oracle,
                accepted_oracle,
                f"{prefix}.rounds[{round_index}].oracle_evidence must match verification_delta.oracle_evidence",
            )
            compare_artifact_binding(
                round_schema_diff,
                accepted_schema_diff,
                f"{prefix}.rounds[{round_index}].schema_diff must match verification_delta.semantic_evidence.schema_diff",
            )
            compare_artifact_binding(
                round_unsafe_scan,
                accepted_unsafe_scan,
                f"{prefix}.rounds[{round_index}].unsafe_scan_evidence must match verification_delta.unsafe_scan_evidence",
            )
            compare_opencode_measured_unsafe_delta(
                round_unsafe_delta,
                accepted_unsafe_reduction,
                f"{prefix}.rounds[{round_index}].unsafe_delta",
            )
    return len(rounds)


def validate_opencode_accepted_retry_hint_contract(
    retry_hint: dict[str, Any],
    *,
    index: int,
    repo_root: Path,
) -> int:
    prefix = f"opencode_safety_transform_attempt.safety_transform_units[{index}].accepted_retry_hint"
    status = retry_hint.get("status")
    if status == "not_exercised":
        return 0
    if status != "revalidated_passed":
        raise ValueError(f"{prefix}.status must be not_exercised or revalidated_passed")
    if retry_hint.get("auto_recovered") is not True:
        raise ValueError(f"{prefix}.auto_recovered must be true when status is revalidated_passed")
    repair_rounds = retry_hint.get("repair_rounds")
    if not isinstance(repair_rounds, int) or repair_rounds < 1 or repair_rounds > 5:
        raise ValueError(f"{prefix}.repair_rounds must be between 1 and 5")
    rollback_refs = retry_hint.get("rollback_evidence")
    if not isinstance(rollback_refs, list) or not rollback_refs:
        raise ValueError(f"{prefix}.rollback_evidence must be a non-empty list")
    rollback_paths: list[str] = []
    for rollback_index, rollback_ref in enumerate(rollback_refs):
        rollback_binding = validate_artifact_binding_shape(
            rollback_ref,
            f"{prefix}.rollback_evidence[{rollback_index}]",
            repo_root=repo_root,
        )
        rollback_paths.append(str(rollback_binding["path"]))
    rollback_ids = retry_hint.get("rollback_ids")
    if not isinstance(rollback_ids, list) or not all(isinstance(item, str) and item for item in rollback_ids):
        raise ValueError(f"{prefix}.rollback_ids must be a non-empty string list")
    if rollback_ids != rollback_paths:
        raise ValueError(f"{prefix}.rollback_ids must match rollback_evidence paths")
    patch_events_path = retry_hint.get("patch_events_path")
    patch_events_sha256 = retry_hint.get("patch_events_sha256")
    if (patch_events_path is None) != (patch_events_sha256 is None):
        raise ValueError(f"{prefix}.patch_events_path and patch_events_sha256 must be provided together")
    if patch_events_path is not None:
        path_text = require_string(patch_events_path, f"{prefix}.patch_events_path")
        validate_sha256_hex(patch_events_sha256, f"{prefix}.patch_events_sha256")
        artifact_path = repo_path(path_text, repo_root=repo_root)
        if not artifact_path.exists():
            raise ValueError(f"{prefix}.patch_events_path must exist")
        observed_sha = sha256_file(artifact_path)
        if observed_sha != patch_events_sha256:
            raise ValueError(f"{prefix}.patch_events_sha256 does not match artifact")
    return len(rollback_refs)


def validate_opencode_repair_history_contract(
    repair_history_value: Any,
    retry_hint: dict[str, Any],
    *,
    index: int,
    repo_root: Path,
) -> None:
    prefix = f"opencode_safety_transform_attempt.safety_transform_units[{index}].repair_history"
    repair_history = require_object(repair_history_value, prefix)
    if retry_hint.get("status") != "revalidated_passed":
        raise ValueError(f"{prefix} requires accepted_retry_hint.status revalidated_passed")
    patch_events_path = require_string(repair_history.get("patch_events_path"), f"{prefix}.patch_events_path")
    patch_events_sha256 = repair_history.get("patch_events_sha256")
    validate_sha256_hex(patch_events_sha256, f"{prefix}.patch_events_sha256")
    artifact_path = repo_path(patch_events_path, repo_root=repo_root)
    if not artifact_path.exists():
        raise ValueError(f"{prefix}.patch_events_path must exist")
    observed_sha = sha256_file(artifact_path)
    if observed_sha != patch_events_sha256:
        raise ValueError(f"{prefix}.patch_events_sha256 does not match artifact")
    if retry_hint.get("patch_events_path") != patch_events_path:
        raise ValueError(f"{prefix}.patch_events_path must match accepted_retry_hint.patch_events_path")
    if retry_hint.get("patch_events_sha256") != patch_events_sha256:
        raise ValueError(f"{prefix}.patch_events_sha256 must match accepted_retry_hint.patch_events_sha256")
    statuses = repair_history.get("statuses")
    if not isinstance(statuses, list) or not all(isinstance(status, str) for status in statuses):
        raise ValueError(f"{prefix}.statuses must be a string list")
    if repair_history.get("verified") is not True:
        raise ValueError(f"{prefix}.verified must be true")
    rollback_ids = repair_history.get("rollback_ids")
    if not isinstance(rollback_ids, list) or not all(isinstance(item, str) for item in rollback_ids):
        raise ValueError(f"{prefix}.rollback_ids must be a string list")
    if rollback_ids != retry_hint.get("rollback_ids"):
        raise ValueError(f"{prefix}.rollback_ids must match accepted_retry_hint.rollback_ids")


def validate_opencode_measured_unsafe_delta(delta: dict[str, Any], label: str) -> None:
    if delta.get("status") != "measured":
        raise ValueError(f"{label}.status must be measured")
    reduced_by = delta.get("reduced_by")
    baseline = delta.get("baseline_total_unsafe")
    current = delta.get("current_total_unsafe")
    if not isinstance(baseline, int) or not isinstance(current, int):
        raise ValueError(f"{label}.baseline_total_unsafe and current_total_unsafe must be integers")
    if baseline < 0 or current < 0:
        raise ValueError(f"{label}.baseline_total_unsafe and current_total_unsafe must be non-negative")
    if baseline == 0:
        raise ValueError(f"{label}.baseline_total_unsafe must be > 0")
    if not isinstance(reduced_by, int) or reduced_by <= 0:
        raise ValueError(f"{label}.reduced_by must be > 0")
    if reduced_by != baseline - current:
        raise ValueError(f"{label}.reduced_by must equal baseline_total_unsafe - current_total_unsafe")
    ratio = delta.get("ratio")
    if isinstance(ratio, bool) or not isinstance(ratio, (int, float)):
        raise ValueError(f"{label}.ratio must be numeric")
    expected_ratio = current / baseline
    if abs(float(ratio) - expected_ratio) > 1e-9:
        raise ValueError(f"{label}.ratio must equal current_total_unsafe / baseline_total_unsafe")


def compare_opencode_measured_unsafe_delta(actual: dict[str, Any], expected: dict[str, Any], label: str) -> None:
    for field in (
        "status",
        "baseline_total_unsafe",
        "current_total_unsafe",
        "reduced_by",
        "ratio",
    ):
        if actual.get(field) != expected.get(field):
            raise ValueError(f"{label} must match verification_delta.unsafe_reduction")


def compare_artifact_binding(actual: dict[str, Any], expected: dict[str, Any], label: str) -> None:
    if actual.get("path") != expected.get("path") or actual.get("sha256") != expected.get("sha256"):
        raise ValueError(f"{label} must match path and sha256")


def validate_judge_graph_contract(
    architecture: dict[str, Any],
    *,
    opencode_runtime_result: dict[str, Any] | None,
    minimum_worker_count: int = 1,
) -> dict[str, Any]:
    graph_runtime = architecture.get("graph_runtime")
    graph_nodes = architecture.get("graph_nodes")
    if graph_runtime is None and graph_nodes is None and opencode_runtime_result is None:
        return {"status": "skipped", "reason": "graph contract not declared"}
    if graph_runtime != "opencode-harness-langgraph-inspired":
        raise ValueError(
            "judge_evidence_index.harness_architecture.graph_runtime must be opencode-harness-langgraph-inspired"
        )
    if not isinstance(graph_nodes, list):
        raise ValueError("judge_evidence_index.harness_architecture.graph_nodes must be a list")
    missing_nodes = [node for node in REQUIRED_JUDGE_GRAPH_NODES if node not in graph_nodes]
    if missing_nodes:
        raise ValueError(f"judge_evidence_index.harness_architecture.graph_nodes missing required nodes: {missing_nodes}")
    if list(graph_nodes) != list(REQUIRED_JUDGE_GRAPH_NODES):
        raise ValueError(
            "judge_evidence_index.harness_architecture.graph_nodes must be "
            f"{list(REQUIRED_JUDGE_GRAPH_NODES)}"
        )

    retry_policy = require_object(architecture.get("retry_policy"), "judge_evidence_index.harness_architecture.retry_policy")
    if retry_policy.get("checkpoint") != "repair_hints":
        raise ValueError("judge_evidence_index.harness_architecture.retry_policy.checkpoint must be repair_hints")
    if retry_policy.get("round_cap") != 5:
        raise ValueError("judge_evidence_index.harness_architecture.retry_policy.round_cap must be 5")

    parallelism = require_object(architecture.get("parallelism"), "judge_evidence_index.harness_architecture.parallelism")
    worker_count = architecture.get("worker_count")
    if not isinstance(worker_count, int) or worker_count < 1:
        raise ValueError("judge_evidence_index.harness_architecture.worker_count must be a positive integer")
    if worker_count < minimum_worker_count:
        raise ValueError(
            f"judge_evidence_index.harness_architecture.worker_count must be >= {minimum_worker_count} "
            "for multi-worker entrypoint"
        )
    for field in ("max_workers", "effective_workers"):
        value = parallelism.get(field)
        if not isinstance(value, int) or value < worker_count:
            raise ValueError(f"judge_evidence_index.harness_architecture.parallelism.{field} must be >= worker_count")
    if opencode_runtime_result is not None and opencode_runtime_result["worker_count"] != worker_count:
        raise ValueError("judge_evidence_index.harness_architecture.worker_count must match opencode_agent_runtime.worker_count")

    return {
        "status": "passed",
        "graph_runtime": graph_runtime,
        "graph_nodes": list(graph_nodes),
        "worker_count": worker_count,
        "minimum_worker_count": minimum_worker_count,
        "retry_round_cap": 5,
    }


def validate_judge_headline_contract(
    payload: dict[str, Any],
    *,
    boundary: dict[str, Any],
    architecture: dict[str, Any],
    opencode_runtime_result: dict[str, Any] | None,
) -> dict[str, Any]:
    headline = require_object(payload.get("judge_headline"), "judge_evidence_index.judge_headline")
    if headline.get("report_kind") != "judge-headline":
        raise ValueError("judge_evidence_index.judge_headline.report_kind must be judge-headline")
    if headline.get("semantic_gate") is not False:
        raise ValueError("judge_evidence_index.judge_headline.semantic_gate must be false")
    if headline.get("semantic_claim_source") != boundary.get("semantic_claim_source"):
        raise ValueError("judge_evidence_index.judge_headline.semantic_claim_source must match claim_boundary")
    if headline.get("generated_draft_semantic_pass") is not boundary.get("generated_draft_semantic_pass"):
        raise ValueError("judge_evidence_index.judge_headline.generated_draft_semantic_pass must match claim_boundary")
    if headline.get("translation_coverage_numerator") != boundary.get("translation_coverage_numerator"):
        raise ValueError("judge_evidence_index.judge_headline.translation_coverage_numerator must match claim_boundary")

    worker_count = architecture.get("worker_count")
    if isinstance(worker_count, int) and headline.get("worker_count") != worker_count:
        raise ValueError("judge_evidence_index.judge_headline.worker_count must match harness_architecture.worker_count")
    graph_runtime = architecture.get("graph_runtime")
    if graph_runtime is not None and headline.get("graph_runtime") != graph_runtime:
        raise ValueError("judge_evidence_index.judge_headline.graph_runtime must match harness_architecture.graph_runtime")
    parallelism = architecture.get("parallelism")
    if isinstance(parallelism, dict) and headline.get("parallelism") != parallelism:
        raise ValueError("judge_evidence_index.judge_headline.parallelism must match harness_architecture.parallelism")
    retry_policy = architecture.get("retry_policy")
    if isinstance(retry_policy, dict):
        if headline.get("repair_round_cap") != retry_policy.get("round_cap"):
            raise ValueError("judge_evidence_index.judge_headline.repair_round_cap must match harness_architecture.retry_policy.round_cap")
        if headline.get("repair_checkpoint") != retry_policy.get("checkpoint"):
            raise ValueError("judge_evidence_index.judge_headline.repair_checkpoint must match harness_architecture.retry_policy.checkpoint")

    runtime_headline = require_object(headline.get("opencode_runtime"), "judge_evidence_index.judge_headline.opencode_runtime")
    if runtime_headline.get("chat_output_is_evidence") is not False:
        raise ValueError("judge_evidence_index.judge_headline.opencode_runtime.chat_output_is_evidence must be false")
    if runtime_headline.get("semantic_gate") is not False:
        raise ValueError("judge_evidence_index.judge_headline.opencode_runtime.semantic_gate must be false")
    if opencode_runtime_result is not None:
        if runtime_headline.get("enabled") is not True:
            raise ValueError("judge_evidence_index.judge_headline.opencode_runtime.enabled must be true")
        if runtime_headline.get("worker_count") != opencode_runtime_result["worker_count"]:
            raise ValueError("judge_evidence_index.judge_headline.opencode_runtime.worker_count must match opencode_agent_runtime.worker_count")
        if runtime_headline.get("all_contracts_executed") is not True:
            raise ValueError("judge_evidence_index.judge_headline.opencode_runtime.all_contracts_executed must be true")
    else:
        if runtime_headline.get("enabled") is not False:
            raise ValueError("judge_evidence_index.judge_headline.opencode_runtime.enabled must be false without opencode_agent_runtime")

    return {
        "status": "passed",
        "report_kind": "judge-headline",
        "worker_count": headline.get("worker_count"),
        "repair_round_cap": headline.get("repair_round_cap"),
        "opencode_runtime_enabled": runtime_headline.get("enabled"),
    }


def validate_judge_evidence_artifact_refs(
    payload: dict[str, Any],
    *,
    expected_artifacts: dict[str, Any] | None = None,
    repo_root: Path | None = None,
    opencode_runtime_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    refs = payload.get("evidence_artifact_refs")
    if refs is None:
        if expected_artifacts or opencode_runtime_result is not None:
            raise ValueError("judge_evidence_index.evidence_artifact_refs must be an object")
        return {"status": "skipped", "reason": "evidence_artifact_refs not declared"}
    refs_payload = require_object(refs, "judge_evidence_index.evidence_artifact_refs")
    if "judge_evidence_index" in refs_payload:
        raise ValueError("judge_evidence_index.evidence_artifact_refs must not include judge_evidence_index")

    validated_refs = {
        name: validate_artifact_binding_shape(ref, f"judge_evidence_index.evidence_artifact_refs.{name}", repo_root=repo_root)
        for name, ref in sorted(refs_payload.items())
    }
    allowed_ref_keys = set(BASE_JUDGE_EVIDENCE_REF_KEYS)
    if expected_artifacts is not None:
        allowed_ref_keys.update(
            artifact_ref_key_for_expected_artifact(artifact_name)
            for artifact_name in expected_artifacts
            if artifact_name != "judge_evidence_index"
        )
        missing: list[str] = []
        for artifact_name in sorted(expected_artifacts):
            if artifact_name == "judge_evidence_index":
                continue
            ref_name = artifact_ref_key_for_expected_artifact(artifact_name)
            if ref_name not in validated_refs:
                missing.append(artifact_name)
                continue
            expected_path = require_string(expected_artifacts[artifact_name], f"expected_artifacts.{artifact_name}")
            try:
                assert_repo_relative_posix(expected_path)
            except ValueError as error:
                raise ValueError(f"expected_artifacts.{artifact_name}: {error}") from error
            if validated_refs[ref_name]["path"] != expected_path:
                raise ValueError(f"judge_evidence_index.evidence_artifact_refs.{ref_name}.path must match expected_artifacts.{artifact_name}")
        if missing:
            raise ValueError(f"judge_evidence_index.evidence_artifact_refs missing expected artifacts: {missing}")
    unexpected_refs = sorted(
        name for name in set(validated_refs) if not judge_evidence_ref_key_allowed(name, allowed_ref_keys)
    )
    if unexpected_refs:
        raise ValueError(f"judge_evidence_index.evidence_artifact_refs unexpected refs: {unexpected_refs}")
    if opencode_runtime_result is not None:
        if "opencode_preflight_report" not in validated_refs:
            raise ValueError("judge_evidence_index.evidence_artifact_refs missing required OpenCode ref: opencode_preflight_report")
        compare_artifact_binding(
            validated_refs["opencode_preflight_report"],
            opencode_runtime_result["opencode_preflight_report"],
            "judge_evidence_index.evidence_artifact_refs.opencode_preflight_report",
        )

    verified_baseline_contract = None
    if "verified_unsafe_baseline" in refs_payload:
        verified_baseline_contract = validate_verified_unsafe_baseline_ref(
            refs_payload["verified_unsafe_baseline"],
            "judge_evidence_index.evidence_artifact_refs.verified_unsafe_baseline",
            repo_root=repo_root,
        )

    route_metrics_contract = None
    if repo_root is not None and "route_governance_metrics_report" in validated_refs:
        route_metrics_contract = validate_route_governance_metrics_report_contract(
            validated_refs["route_governance_metrics_report"],
            repo_root=repo_root,
        )

    profile_launch_policy = None
    profile_ref = payload.get("profile")
    if "profile" in validated_refs:
        profile_binding = validated_refs["profile"]
        if isinstance(profile_ref, dict):
            profile_payload_binding = validate_artifact_binding_shape(profile_ref, "judge_evidence_index.profile", repo_root=repo_root)
            compare_artifact_binding(
                profile_binding,
                profile_payload_binding,
                "judge_evidence_index.evidence_artifact_refs.profile",
            )
        if repo_root is not None and opencode_runtime_result is not None:
            profile_payload = load_json(repo_path(profile_binding["path"], repo_root=repo_root))
            if profile_payload.get("mode") == "opencode":
                profile_launch_policy = validate_opencode_profile_launch_policy(
                    profile_payload,
                    entry_id="judge_evidence_index.profile",
                )
                compare_opencode_launch_policy(
                    opencode_runtime_result["opencode_preflight_report"]["launch_policy"],
                    profile_launch_policy,
                    "opencode_agent_runtime.opencode_preflight_report",
                    expected_label="profile launch policy",
                )
    architecture = require_object(payload.get("harness_architecture"), "judge_evidence_index.harness_architecture")
    for name in ("context_pack", "agent_index"):
        ref = architecture.get(name)
        if expected_artifacts is not None and name in expected_artifacts and not isinstance(ref, dict):
            raise ValueError(
                f"judge_evidence_index.harness_architecture.{name} is required "
                f"when expected_artifacts.{name} is declared"
            )
        if isinstance(ref, dict) and name in validated_refs:
            architecture_binding = validate_artifact_binding_shape(
                ref,
                f"judge_evidence_index.harness_architecture.{name}",
                repo_root=repo_root,
            )
            compare_artifact_binding(validated_refs[name], architecture_binding, f"judge_evidence_index.evidence_artifact_refs.{name}")

    result: dict[str, Any] = {
        "status": "passed",
        "ref_count": len(validated_refs),
        "refs": sorted(validated_refs),
    }
    if route_metrics_contract is not None:
        result["route_governance_metrics_report"] = route_metrics_contract
    if verified_baseline_contract is not None:
        result["verified_unsafe_baseline"] = verified_baseline_contract
    if profile_launch_policy is not None:
        result["profile_launch_policy"] = profile_launch_policy
    return result


def validate_judge_evidence_index_contract(
    payload: dict[str, Any],
    *,
    path_text: str,
    repo_root: Path | None = None,
    expected_artifacts: dict[str, Any] | None = None,
    minimum_worker_count: int = 1,
) -> dict[str, Any]:
    if payload.get("report_kind") != "judge-evidence-index":
        raise ValueError(f"judge_evidence_index report_kind must be judge-evidence-index: {path_text}")
    boundary = require_object(payload.get("claim_boundary"), "judge_evidence_index.claim_boundary")
    if boundary.get("semantic_claim_source") != "accepted_evidence_binding":
        raise ValueError("judge_evidence_index.claim_boundary.semantic_claim_source must be accepted_evidence_binding")
    if boundary.get("generated_draft_semantic_pass") is not False:
        raise ValueError("judge_evidence_index.claim_boundary.generated_draft_semantic_pass must be false")
    if boundary.get("translation_coverage_numerator") != 0:
        raise ValueError("judge_evidence_index.claim_boundary.translation_coverage_numerator must be 0")
    if boundary.get("index_is_semantic_gate") is not False:
        raise ValueError("judge_evidence_index.claim_boundary.index_is_semantic_gate must be false")

    architecture = require_object(payload.get("harness_architecture"), "judge_evidence_index.harness_architecture")
    contracts = require_object(architecture.get("architecture_contracts"), "judge_evidence_index.architecture_contracts")
    context_contract = require_object(contracts.get("context_management"), "judge_evidence_index.context_management")
    agent_contract = require_object(contracts.get("agent_coordination"), "judge_evidence_index.agent_coordination")
    if context_contract.get("chat_output_is_evidence") is not False or context_contract.get("semantic_gate") is not False:
        raise ValueError("judge_evidence_index.context_management must keep chat_output_is_evidence=false and semantic_gate=false")
    if agent_contract.get("chat_output_is_evidence") is not False or agent_contract.get("semantic_gate") is not False:
        raise ValueError("judge_evidence_index.agent_coordination must keep chat_output_is_evidence=false and semantic_gate=false")
    roles = agent_contract.get("roles")
    if not isinstance(roles, list) or set(roles) != set(REQUIRED_AGENT_ROLES):
        raise ValueError("judge_evidence_index.agent_coordination.roles must list all required roles")
    opencode_runtime_result = None
    evidence_refs = payload.get("evidence_artifact_refs")
    has_opencode_runtime_signal = (
        payload.get("mode") == "opencode"
        or (isinstance(evidence_refs, dict) and "opencode_preflight_report" in evidence_refs)
    )
    if has_opencode_runtime_signal and "opencode_agent_runtime" not in payload:
        raise ValueError("opencode_agent_runtime is required when judge_evidence_index.mode is opencode")
    if "opencode_agent_runtime" in payload:
        opencode_runtime_result = validate_opencode_agent_runtime_contract(
            payload.get("opencode_agent_runtime"),
            repo_root=repo_root,
        )
        if "run_id" in payload and opencode_runtime_result["opencode_preflight_report"].get("run_id") != payload.get("run_id"):
            raise ValueError("opencode_agent_runtime.opencode_preflight_report.run_id must match judge_evidence_index.run_id")
    graph_contract = validate_judge_graph_contract(
        architecture,
        opencode_runtime_result=opencode_runtime_result,
        minimum_worker_count=minimum_worker_count,
    )
    headline_contract = validate_judge_headline_contract(
        payload,
        boundary=boundary,
        architecture=architecture,
        opencode_runtime_result=opencode_runtime_result,
    )
    artifact_refs = validate_judge_evidence_artifact_refs(
        payload,
        expected_artifacts=expected_artifacts,
        repo_root=repo_root,
        opencode_runtime_result=opencode_runtime_result,
    )
    local_path_scan = validate_local_absolute_path_policy(payload, label=f"judge_evidence_index {path_text}")

    result = {
        "path": path_text,
        "status": "passed",
        "architecture_contracts": "passed",
        "graph_contract": graph_contract,
        "judge_headline": headline_contract,
        "evidence_artifact_refs": artifact_refs,
        "local_absolute_path_scan": local_path_scan,
    }
    if opencode_runtime_result is not None:
        result["opencode_agent_runtime"] = opencode_runtime_result
    return result


def worker_ids_from_entries(entries: Any, *, label: str) -> set[str]:
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"{label} must be a non-empty list")
    worker_ids: set[str] = set()
    for index, entry in enumerate(entries):
        entry_payload = require_object(entry, f"{label}[{index}]")
        worker_id = require_string(entry_payload.get("worker_id"), f"{label}[{index}].worker_id")
        worker_ids.add(worker_id)
    if len(worker_ids) != len(entries):
        raise ValueError(f"{label} worker_id values must be unique")
    return worker_ids


def entries_by_worker_id(entries: list[Any], *, label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(entries):
        entry_payload = require_object(entry, f"{label}[{index}]")
        worker_id = require_string(entry_payload.get("worker_id"), f"{label}[{index}].worker_id")
        result[worker_id] = entry_payload
    return result


def validate_context_agent_index_consistency(
    context_payload: dict[str, Any],
    agent_payload: dict[str, Any],
) -> dict[str, Any]:
    context_workers = context_payload.get("workers")
    agents = agent_payload.get("agents")
    agents_by_worker_id = require_object(agent_payload.get("agents_by_worker_id"), "agents_by_worker_id")
    context_worker_ids = worker_ids_from_entries(context_workers, label="context_pack.workers")
    agent_ids = worker_ids_from_entries(agents, label="agent_index.agents")
    indexed_ids = set(agents_by_worker_id)
    if context_worker_ids != agent_ids or context_worker_ids != indexed_ids:
        raise ValueError(
            "context_pack.workers, agent_index.agents, and agents_by_worker_id worker ids must match: "
            f"{sorted(context_worker_ids)} != {sorted(agent_ids)} != {sorted(indexed_ids)}"
        )

    context_by_worker_id = entries_by_worker_id(context_workers, label="context_pack.workers")
    agents_by_list_id = entries_by_worker_id(agents, label="agent_index.agents")
    comparable_fields = (
        "assignment_path",
        "request_path",
        "summary_path",
        "report_path",
        "slice_id",
        "function",
        "source_commit",
        "source_sha256",
    )
    for worker_id in sorted(context_worker_ids):
        context_worker = context_by_worker_id[worker_id]
        agent_entry = require_object(agents_by_worker_id[worker_id], f"agents_by_worker_id.{worker_id}")
        listed_agent = agents_by_list_id[worker_id]
        if "worker_id" in agent_entry and agent_entry.get("worker_id") != worker_id:
            raise ValueError(f"agents_by_worker_id.{worker_id}.worker_id must match map key")
        for field in comparable_fields:
            values = [payload.get(field) for payload in (context_worker, listed_agent, agent_entry) if field in payload]
            if values and any(value != values[0] for value in values[1:]):
                raise ValueError(f"worker {worker_id} field {field} must match across context_pack and agent_index")
        out_root_values = [
            payload.get("out_root")
            for payload in (context_worker, listed_agent, agent_entry)
            if isinstance(payload.get("out_root"), str)
        ]
        isolated_values = [
            payload.get("isolated_out_root")
            for payload in (context_worker, listed_agent, agent_entry)
            if isinstance(payload.get("isolated_out_root"), str)
        ]
        expected_isolated_out_root = isolated_values[0] if isolated_values else None
        if isolated_values and any(value != expected_isolated_out_root for value in isolated_values[1:]):
            raise ValueError(f"worker {worker_id} field isolated_out_root must match across context_pack and agent_index")
        if expected_isolated_out_root is not None:
            for out_root in out_root_values:
                if out_root != expected_isolated_out_root:
                    raise ValueError(f"worker {worker_id} out_root must match isolated_out_root")

    return {"status": "passed", "worker_count": len(context_worker_ids)}


def validate_resume_manifest_contract(
    payload: dict[str, Any],
    *,
    path_text: str,
    expected_artifacts: dict[str, Any],
    context_payload: dict[str, Any] | None,
    agent_payload: dict[str, Any] | None,
    repo_root: Path,
) -> dict[str, Any]:
    if payload.get("report_kind") != "resume-manifest":
        raise ValueError(f"resume_manifest report_kind must be resume-manifest: {path_text}")
    if payload.get("schema_version") != 1:
        raise ValueError("resume_manifest.schema_version must be 1")
    if payload.get("semantic_gate") is not False:
        raise ValueError("resume_manifest.semantic_gate must be false")
    if payload.get("chat_output_is_evidence") is not False:
        raise ValueError("resume_manifest.chat_output_is_evidence must be false")
    boundary = require_object(payload.get("claim_boundary"), "resume_manifest.claim_boundary")
    if boundary.get("semantic_gate") is not False:
        raise ValueError("resume_manifest.claim_boundary.semantic_gate must be false")
    if boundary.get("chat_output_is_evidence") is not False:
        raise ValueError("resume_manifest.claim_boundary.chat_output_is_evidence must be false")
    if boundary.get("generated_draft_semantic_pass") is not False:
        raise ValueError("resume_manifest.claim_boundary.generated_draft_semantic_pass must be false")
    if boundary.get("translation_coverage_numerator") != 0:
        raise ValueError("resume_manifest.claim_boundary.translation_coverage_numerator must be 0")

    ledger = require_object(payload.get("ledger"), "resume_manifest.ledger")
    if ledger.get("checkpoint_backend") != "sqlite":
        raise ValueError("resume_manifest.ledger.checkpoint_backend must be sqlite")
    ledger_path = require_string(ledger.get("path"), "resume_manifest.ledger.path")
    assert_repo_relative_posix(ledger_path)

    context_binding = validate_artifact_binding_shape(
        payload.get("context_pack"),
        "resume_manifest.context_pack",
        repo_root=repo_root,
    )
    agent_binding = validate_artifact_binding_shape(
        payload.get("agent_index"),
        "resume_manifest.agent_index",
        repo_root=repo_root,
    )
    expected_context = expected_artifacts.get("context_pack")
    expected_agent = expected_artifacts.get("agent_index")
    if isinstance(expected_context, str) and context_binding["path"] != expected_context:
        raise ValueError("resume_manifest.context_pack.path must match expected_artifacts.context_pack")
    if isinstance(expected_agent, str) and agent_binding["path"] != expected_agent:
        raise ValueError("resume_manifest.agent_index.path must match expected_artifacts.agent_index")

    if context_payload is not None:
        entrypoints = require_object(context_payload.get("entrypoints"), "context_pack.entrypoints")
        if entrypoints.get("resume_manifest") != path_text:
            raise ValueError("context_pack.entrypoints.resume_manifest must match expected_artifacts.resume_manifest")
    if agent_payload is not None:
        reports = require_object(agent_payload.get("reports"), "agent_index.reports")
        resume_report = require_object(reports.get("resume_manifest"), "agent_index.reports.resume_manifest")
        if resume_report.get("path") != path_text:
            raise ValueError("agent_index.reports.resume_manifest.path must match expected_artifacts.resume_manifest")

    verified_candidates: list[tuple[str, Any]] = []
    if isinstance(payload.get("verified_unsafe_baseline"), dict):
        verified_candidates.append(("resume_manifest.verified_unsafe_baseline", payload["verified_unsafe_baseline"]))
    payload_policy_ref = verified_unsafe_baseline_ref_from_container(payload.get("attempt_evidence_policy"))
    if isinstance(payload_policy_ref, dict):
        verified_candidates.append(("resume_manifest.attempt_evidence_policy.baseline_attempt.verified_unsafe_baseline", payload_policy_ref))
    if context_payload is not None:
        context_ref = verified_unsafe_baseline_ref_from_container(context_payload)
        if isinstance(context_ref, dict):
            verified_candidates.append(("context_pack.attempt_evidence_policy.baseline_attempt.verified_unsafe_baseline", context_ref))
    if agent_payload is not None:
        agent_ref = verified_unsafe_baseline_ref_from_container(agent_payload)
        if isinstance(agent_ref, dict):
            verified_candidates.append(("agent_index.attempt_evidence_policy.baseline_attempt.verified_unsafe_baseline", agent_ref))
        reports = agent_payload.get("reports") if isinstance(agent_payload.get("reports"), dict) else {}
        reports_ref = reports.get("verified_unsafe_baseline") if isinstance(reports, dict) else None
        if isinstance(reports_ref, dict):
            verified_candidates.append(("agent_index.reports.verified_unsafe_baseline", reports_ref))
    if "verified_unsafe_baseline" in expected_artifacts and not verified_candidates:
        raise ValueError("resume_manifest.verified_unsafe_baseline is required when expected_artifacts.verified_unsafe_baseline is declared")
    verified_baseline_contract = None
    if verified_candidates:
        compare_verified_unsafe_baseline_refs(verified_candidates)
        primary_label, primary_ref = verified_candidates[0]
        verified_baseline_contract = validate_verified_unsafe_baseline_ref(
            primary_ref,
            primary_label,
            repo_root=repo_root,
        )
        expected_verified = expected_artifacts.get("verified_unsafe_baseline")
        if isinstance(expected_verified, str) and verified_baseline_contract["path"] != expected_verified:
            raise ValueError("resume_manifest.verified_unsafe_baseline.path must match expected_artifacts.verified_unsafe_baseline")
        entrypoint_map = payload.get("entrypoints")
        if isinstance(entrypoint_map, dict) and entrypoint_map.get("verified_unsafe_baseline") != verified_baseline_contract["path"]:
            raise ValueError("resume_manifest.entrypoints.verified_unsafe_baseline must match verified_unsafe_baseline.path")
        if context_payload is not None:
            context_entrypoints = context_payload.get("entrypoints") if isinstance(context_payload.get("entrypoints"), dict) else {}
            if (
                isinstance(context_entrypoints, dict)
                and "verified_unsafe_baseline" in context_entrypoints
                and context_entrypoints.get("verified_unsafe_baseline") != verified_baseline_contract["path"]
            ):
                raise ValueError("context_pack.entrypoints.verified_unsafe_baseline must match verified_unsafe_baseline.path")

    entrypoints = payload.get("resume_entrypoints")
    if not isinstance(entrypoints, list):
        raise ValueError("resume_manifest.resume_entrypoints must be a list")
    for required in ("evaluate --profile", "run-plan --plan", "run-worker --assignment"):
        if required not in entrypoints:
            raise ValueError(f"resume_manifest.resume_entrypoints missing {required}")

    workers = payload.get("workers")
    if not isinstance(workers, list):
        raise ValueError("resume_manifest.workers must be a list")
    if payload.get("worker_count") != len(workers):
        raise ValueError("resume_manifest.worker_count must match workers length")
    actual_worker_ids = [
        require_string(
            require_object(worker, f"resume_manifest.workers[{index}]").get("worker_id"),
            f"resume_manifest.workers[{index}].worker_id",
        )
        for index, worker in enumerate(workers)
    ]
    declared_worker_ids = payload.get("worker_ids")
    if declared_worker_ids is not None:
        if not isinstance(declared_worker_ids, list) or not all(
            isinstance(worker_id, str) and worker_id for worker_id in declared_worker_ids
        ):
            raise ValueError("resume_manifest.worker_ids must be a non-empty string list when declared")
        if len(set(declared_worker_ids)) != len(declared_worker_ids):
            raise ValueError("resume_manifest.worker_ids must be unique")
        if declared_worker_ids != actual_worker_ids:
            raise ValueError("resume_manifest.worker_ids must match workers")
    if len(set(actual_worker_ids)) != len(actual_worker_ids):
        raise ValueError("resume_manifest.workers worker_id values must be unique")
    run_id = require_string(payload.get("run_id"), "resume_manifest.run_id")
    open_hint_ids_by_worker_id = resume_manifest_open_repair_hint_ids_by_worker(
        payload.get("repair_hints"),
        run_id=run_id,
    )
    for index, worker in enumerate(workers):
        worker_payload = require_object(worker, f"resume_manifest.workers[{index}]")
        require_string(worker_payload.get("worker_id"), f"resume_manifest.workers[{index}].worker_id")
        for field in ("assignment_path", "request_path", "summary_path", "report_path", "isolated_out_root"):
            value = worker_payload.get(field)
            if isinstance(value, str):
                assert_repo_relative_posix(value)
        validate_resume_manifest_worker_replay_commands(
            worker_payload,
            index=index,
            run_id=run_id,
            ledger_path=ledger_path,
            open_hint_ids_by_worker_id=open_hint_ids_by_worker_id,
            repo_root=repo_root,
        )
    worker_consistency = validate_resume_manifest_worker_consistency(
        workers,
        context_payload=context_payload,
        agent_payload=agent_payload,
    )
    local_path_scan = validate_local_absolute_path_policy(payload, label=f"resume_manifest {path_text}")
    return {
        "path": path_text,
        "status": "passed",
        "checkpoint_backend": "sqlite",
        "worker_count": len(workers),
        "worker_ids": actual_worker_ids,
        "worker_consistency": worker_consistency,
        **({"verified_unsafe_baseline": verified_baseline_contract} if verified_baseline_contract is not None else {}),
        "local_absolute_path_scan": local_path_scan,
    }


def validate_resume_manifest_worker_replay_commands(
    worker: dict[str, Any],
    *,
    index: int,
    run_id: str,
    ledger_path: str,
    open_hint_ids_by_worker_id: dict[str, set[str]],
    repo_root: Path,
) -> dict[str, Any]:
    worker_id = require_string(worker.get("worker_id"), f"resume_manifest.workers[{index}].worker_id")
    replay = require_object(worker.get("replay_commands"), f"resume_manifest.workers[{index}].replay_commands")
    run_worker = validate_resume_manifest_replay_command(
        replay.get("run_worker"),
        label=f"resume_manifest.workers[{index}].replay_commands.run_worker",
        expected_subcommand="run-worker",
        worker=worker,
        worker_id=worker_id,
        run_id=run_id,
        ledger_path=ledger_path,
        require_hint=False,
        repo_root=repo_root,
    )
    result: dict[str, Any] = {"run_worker": run_worker}
    if "retry_worker" in replay:
        retry_worker = validate_resume_manifest_replay_command(
            replay.get("retry_worker"),
            label=f"resume_manifest.workers[{index}].replay_commands.retry_worker",
            expected_subcommand="retry-worker",
            worker=worker,
            worker_id=worker_id,
            run_id=run_id,
            ledger_path=ledger_path,
            require_hint=True,
            expected_hint_ids=open_hint_ids_by_worker_id.get(worker_id, set()),
            repo_root=repo_root,
        )
        result["retry_worker"] = retry_worker
    return result


def resume_manifest_open_repair_hint_ids_by_worker(value: Any, *, run_id: str) -> dict[str, set[str]]:
    if not isinstance(value, dict):
        return {}
    hints = value.get("hints")
    if not isinstance(hints, list):
        return {}
    result: dict[str, set[str]] = {}
    for hint in hints:
        if not isinstance(hint, dict) or hint.get("status") != "open":
            continue
        hint_id = hint.get("hint_id")
        if not isinstance(hint_id, str) or not hint_id:
            continue
        worker_id = hint.get("worker_id")
        if not isinstance(worker_id, str) or not worker_id:
            worker_id = resume_manifest_worker_id_from_repair_hint_id(hint_id, run_id=run_id)
        if worker_id:
            result.setdefault(worker_id, set()).add(hint_id)
    return result
