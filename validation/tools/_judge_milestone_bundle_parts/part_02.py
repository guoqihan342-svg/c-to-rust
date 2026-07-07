def build_self_heal_classification(blocked_rollup: dict[str, Any]) -> dict[str, Any]:
    next_actions = object_list(blocked_rollup.get("next_actions"))
    route_counts: Counter[str] = Counter()
    next_action_counts: Counter[str] = Counter()
    smallest_next_test_kind_counts: Counter[str] = Counter()
    for action in next_actions:
        route = action.get("route")
        if isinstance(route, str) and route:
            route_counts[route] += 1
        next_action = action.get("next_action")
        if isinstance(next_action, str) and next_action:
            next_action_counts[next_action] += 1
        smallest_next_test_kind = action.get("smallest_next_test_kind")
        if isinstance(smallest_next_test_kind, str) and smallest_next_test_kind:
            smallest_next_test_kind_counts[smallest_next_test_kind] += 1
    if not smallest_next_test_kind_counts:
        for test in object_list(blocked_rollup.get("smallest_next_tests")):
            kind = test.get("kind")
            if isinstance(kind, str) and kind:
                smallest_next_test_kind_counts[kind] += 1
    return {
        "report_kind": "self-heal-classification",
        "source": "blocked_repairs_rollup",
        "status": blocked_rollup.get("status") if isinstance(blocked_rollup.get("status"), str) else "unknown",
        "blocked_repair_count": int_or_zero(blocked_rollup.get("blocked_repair_count")),
        "human_action_required_count": int_or_zero(blocked_rollup.get("human_action_required_count")),
        "status_counts": int_count_map(blocked_rollup.get("status_counts")),
        "blocked_reason_counts": int_count_map(blocked_rollup.get("blocked_reason_counts")),
        "ir_feature_gap_kinds": int_count_map(blocked_rollup.get("ir_feature_gap_kinds")),
        "forbidden_change_counts": int_count_map(blocked_rollup.get("forbidden_change_counts")),
        "source_span_kind_counts": int_count_map(blocked_rollup.get("source_span_kind_counts")),
        "route_counts": sorted_int_counter(route_counts),
        "next_action_counts": sorted_int_counter(next_action_counts),
        "smallest_next_test_kind_counts": sorted_int_counter(smallest_next_test_kind_counts),
        "next_action_count": len(next_actions),
        "sample_next_action_limit": SELF_HEAL_SAMPLE_NEXT_ACTION_LIMIT,
        "sample_next_actions": next_actions[:SELF_HEAL_SAMPLE_NEXT_ACTION_LIMIT],
        "semantic_gate": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
        "boundary": (
            "Self-heal classification is derived from fail-closed blocked-repair playbooks. It describes "
            "repair categories and next actions for judge review only; it is not a semantic gate and does "
            "not increase translator-generated coverage."
        ),
    }


def comparison_row(
    *,
    status: str,
    evidence_role: str,
    boundary: str,
    **extra: Any,
) -> dict[str, Any]:
    row = {
        "status": status,
        "evidence_role": evidence_role,
        "semantic_acceptance_claimed": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
        "boundary": boundary,
    }
    row.update(extra)
    return row


def build_publication_manifest(
    *,
    run_report: dict[str, Any],
    run_report_path: Path,
    out_path: Path,
    judge_entrypoints_run_report: dict[str, Any],
    entrypoint_reports: list[dict[str, Any]],
    claim_boundary: dict[str, Any],
    claim_scope: dict[str, Any],
    proof_classes: dict[str, Any],
    publishability: dict[str, Any],
    harness_architecture_summary: dict[str, Any],
    before_after_repair_exhibit: dict[str, Any],
    opencode_runtime: dict[str, Any],
    reproduction_commands: dict[str, Any],
    must_not_claim: list[str],
    known_gaps: list[dict[str, Any]],
    repo_root: Path,
) -> dict[str, Any]:
    config = run_report.get("config") if isinstance(run_report.get("config"), dict) else {}
    archive = (
        run_report.get("competition_config_archive")
        if isinstance(run_report.get("competition_config_archive"), dict)
        else None
    )
    artifact_refs = publication_artifact_refs(entrypoint_reports)
    if not artifact_refs and judge_entrypoints_run_report.get("status") == "present":
        artifact_refs.append(
            {
                **json.loads(json.dumps(judge_entrypoints_run_report)),
                "artifact_name": "judge_entrypoints_run_report",
                "entrypoint_id": "judge_entrypoints_run",
            }
        )
    repo_commit = source_commit_ref(repo_root=repo_root)
    return {
        "report_kind": "publication-manifest",
        "bundle_version": 1,
        "publication_scope": publication_scope(
            claim_scope=claim_scope,
            publishability=publishability,
        ),
        "source_commit": repo_commit,
        "repo_commit": repo_commit,
        "target_source_pin": publication_source_pin_ref(run_report),
        "judge_config": publication_config_ref(config),
        "competition_config_archive": publication_archive_ref(archive),
        "judge_entrypoints_run_report": judge_entrypoints_run_report,
        "readiness_report": artifact_ref_from_existing(run_report.get("readiness_report"), repo_root=repo_root)
        or {"path": "unknown", "status": "absent"},
        "judge_milestone_bundle": {
            "path": validator.repo_relative(out_path, repo_root),
            "status": "self",
            "hash_boundary": "The bundle does not embed its own sha256 because that would make the hash recursive.",
        },
        "run_report_path": validator.repo_relative(run_report_path, repo_root),
        "supported_subset": {
            "entrypoint_count": len([entry for entry in run_report.get("entrypoints", []) if isinstance(entry, dict)]),
            "entrypoint_ids": [
                entry.get("id")
                for entry in run_report.get("entrypoints", [])
                if isinstance(entry, dict)
            ],
            "proof_classes": proof_classes,
            "harness_graph_runtime": harness_architecture_summary.get("graph_runtime"),
            "harness_roles": harness_architecture_summary.get("roles", []),
            "repair_round_cap": int_or_zero(harness_architecture_summary.get("repair_round_cap")),
            "before_after_bound_unit_count": int_or_zero(
                before_after_repair_exhibit.get("rollup", {}).get("bound_unit_count")
                if isinstance(before_after_repair_exhibit.get("rollup"), dict)
                else 0
            ),
            "opencode_runtime_enabled": int_or_zero(opencode_runtime.get("enabled_entrypoint_count")) > 0,
        },
        "published_entrypoints": publication_entrypoints(entrypoint_reports),
        "published_artifact_refs": artifact_refs,
        "published_artifact_count": len(artifact_refs),
        "publishability": publishability,
        "release_tag_readiness": build_release_tag_readiness(
            repo_commit=repo_commit,
            publishability=publishability,
        ),
        "claim_scope": claim_scope,
        "claim_boundary": {
            "semantic_gate": False,
            "generated_draft_semantic_pass": False,
            "translation_coverage_numerator": 0,
            "publication_manifest_is_semantic_gate": False,
            "boundary": (
                "This manifest indexes the external review package. It does not create semantic acceptance, "
                "competition-exact proof, or translator-generated coverage."
            ),
            "source_boundary": claim_boundary.get("boundary"),
        },
        "reproduction_commands": reproduction_commands,
        "known_gaps": known_gaps,
        "known_non_goals": [
            "semantic acceptance",
            "competition-exact proof without competition host attestation",
            "translator-generated coverage increase",
            "project-level C-to-Rust completeness",
            "OpenCode chat output as semantic evidence",
        ],
        "must_not_claim": must_not_claim,
    }


def build_release_tag_readiness(*, repo_commit: dict[str, Any], publishability: dict[str, Any]) -> dict[str, Any]:
    return {
        "report_kind": "release-tag-readiness",
        "status": "not_tagged",
        "tag_name": None,
        "tag_target_commit": None,
        "repo_commit": repo_commit.get("commit") if isinstance(repo_commit.get("commit"), str) else None,
        "tag_matches_repo_commit": False,
        "remote_release_notes_status": "not_published",
        "external_review_record_status": "not_recorded",
        "external_milestone_claim_ready": False,
        "publishability_status": publishability.get("status"),
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
        "boundary": (
            "Tag, remote release notes, and external review records are publication readiness evidence only. "
            "They do not create semantic acceptance or translator-generated coverage."
        ),
    }


def publication_scope(*, claim_scope: dict[str, Any], publishability: dict[str, Any]) -> str:
    if publishability.get("external_milestone_claim_ready"):
        return "full"
    if publishability.get("all_entrypoints_run_publishable"):
        return "internal_preview_full"
    if claim_scope.get("external_review_index_ready"):
        return "partial"
    return "blocked"


def publication_entrypoints(entrypoint_reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": entry.get("id"),
            "status": entry.get("status"),
            "proof_class": entry.get("proof_class"),
            "run_id": entry.get("run_id"),
        }
        for entry in entrypoint_reports
    ]


def publication_artifact_refs(entrypoint_reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None]] = set()
    for entry in entrypoint_reports:
        artifacts = entry.get("artifacts", {})
        if not isinstance(artifacts, dict):
            continue
        for artifact_name, artifact in artifacts.items():
            if not isinstance(artifact, dict):
                continue
            path = artifact.get("path")
            sha256 = artifact.get("sha256")
            if not isinstance(path, str):
                continue
            key = (path, sha256 if isinstance(sha256, str) else None)
            if key in seen:
                continue
            seen.add(key)
            ref = dict(artifact)
            ref["artifact_name"] = artifact_name
            ref["entrypoint_id"] = entry.get("id")
            refs.append(ref)
    return refs


def publication_artifact_ref_blockers(entrypoint_reports: list[dict[str, Any]]) -> list[str]:
    blockers: list[str] = []
    for entry in entrypoint_reports:
        entrypoint_id = str(entry.get("id", "unknown"))
        artifacts = entry.get("artifacts", {})
        if not isinstance(artifacts, dict):
            continue
        for artifact_name, artifact in sorted(artifacts.items()):
            if not isinstance(artifact, dict):
                continue
            status = artifact.get("status")
            if status not in {"present", "passed"}:
                blockers.append(f"published_artifact_not_present:{entrypoint_id}:{artifact_name}:{status}")
    return blockers


def source_commit_ref(*, repo_root: Path) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        return {"status": "absent", "reason": f"{type(exc).__name__}: {exc}"}
    commit = completed.stdout.strip()
    if completed.returncode == 0 and len(commit) == 40 and all(char in "0123456789abcdef" for char in commit):
        return {"status": "present", "commit": commit}
    return {
        "status": "absent",
        "reason": (completed.stderr or completed.stdout or "git rev-parse HEAD failed").strip(),
    }


def publication_config_ref(config: dict[str, Any]) -> dict[str, Any]:
    path = config.get("path") if isinstance(config.get("path"), str) else "unknown"
    ref = {
        "path": path,
        "status": config.get("status", "present" if path != "unknown" else "absent"),
    }
    if isinstance(config.get("sha256"), str):
        ref["sha256"] = config["sha256"]
    return ref


def publication_source_pin_ref(run_report: dict[str, Any]) -> dict[str, Any]:
    validation = run_report.get("validation")
    if isinstance(validation, dict):
        contract = validation.get("source_pin_contract")
        if isinstance(contract, dict):
            return {
                "status": contract.get("status", "unknown"),
                "target_id": contract.get("target_id"),
                "repository": contract.get("repository"),
                "branch": contract.get("branch"),
                "canonical_commit": contract.get("canonical_commit"),
            }
    return {"status": "absent"}


def publication_archive_ref(archive: dict[str, Any] | None) -> dict[str, Any]:
    if archive is None:
        return {"status": "absent"}
    ref = {
        "status": archive.get("status", "present"),
        "root": archive.get("root"),
        "file_count": int_or_zero(archive.get("file_count")),
        "report_kind": archive.get("report_kind"),
    }
    files = archive.get("files")
    if isinstance(files, dict):
        ref["file_count"] = len(files)
        manifest = files.get("config/competition-env/bundle-manifest.json")
        if isinstance(manifest, dict):
            ref["bundle_manifest"] = {
                "path": manifest.get("path"),
                "sha256": manifest.get("sha256"),
                "status": manifest.get("status"),
            }
    materialized_manifest = archive.get("materialized_manifest")
    if isinstance(materialized_manifest, dict):
        ref["materialized_manifest"] = {
            "path": materialized_manifest.get("path"),
            "sha256": materialized_manifest.get("sha256"),
            "status": materialized_manifest.get("status"),
        }
    external_refs = archive.get("external_refs")
    if isinstance(external_refs, dict):
        ref["external_ref_count"] = len(external_refs)
        ref["external_refs"] = {
            path: {
                "path": entry.get("path"),
                "sha256": entry.get("sha256"),
                "status": entry.get("status"),
                "role": entry.get("role"),
            }
            for path, entry in sorted(external_refs.items())
            if isinstance(entry, dict)
        }
    return ref


def build_reproduction_commands(
    *,
    run_report: dict[str, Any],
    run_report_path: Path,
    repo_root: Path,
) -> dict[str, Any]:
    run_report_rel = validator.repo_relative(run_report_path, repo_root)
    bundle_rel = validator.repo_relative(run_report_path.parent / "judge-milestone-bundle.json", repo_root)
    config = run_report.get("config") if isinstance(run_report.get("config"), dict) else {}
    config_path = config.get("path") if isinstance(config.get("path"), str) else None
    if config_path:
        runner_command = (
            "python3 -B -m validation.tools.run_judge_entrypoints "
            f"--config {config_path} --out {run_report_rel}"
        )
    else:
        runner_command = f"python3 -B -m validation.tools.run_judge_entrypoints --out {run_report_rel}"
    return {
        "run_judge_entrypoints": runner_command,
        "build_bundle": (
            "python3 -B -m validation.tools.judge_milestone_bundle "
            f"--run-report {run_report_rel} --out {bundle_rel}"
        ),
        "entrypoints": [
            {
                "id": entry.get("id"),
                "command": entry.get("command"),
            }
            for entry in run_report.get("entrypoints", [])
            if isinstance(entry, dict)
        ],
    }


def artifact_refs_from_key_artifacts(value: object, *, repo_root: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    refs: dict[str, Any] = {}
    for key, raw_ref in value.items():
        ref = artifact_ref_from_existing(raw_ref, repo_root=repo_root)
        if ref is not None:
            refs[str(key)] = ref
    return refs


def artifact_ref_from_existing(value: object, *, repo_root: Path) -> dict[str, Any] | None:
    path_text: str | None = None
    expected_sha256: str | None = None
    expected_status: str | None = None
    if isinstance(value, str):
        path_text = value
    elif isinstance(value, dict) and isinstance(value.get("path"), str):
        path_text = value["path"]
        if isinstance(value.get("sha256"), str):
            expected_sha256 = value["sha256"]
        if isinstance(value.get("status"), str):
            expected_status = value["status"]
    if path_text is None:
        return None
    try:
        path = resolve_input_path(Path(path_text), repo_root=repo_root)
    except (OSError, ValueError):
        return {"path": path_text, "status": "invalid"}
    ref = artifact_ref(path, repo_root=repo_root)
    if expected_status == "present" and ref.get("status") != "present":
        ref["status"] = "status_mismatch"
        ref["expected_status"] = expected_status
        ref["current_status"] = "missing"
        return ref
    if expected_status == "present" and expected_sha256 is None:
        ref["status"] = "missing_expected_sha256"
        return ref
    if expected_sha256 is not None and ref.get("sha256") != expected_sha256:
        ref["status"] = "sha256_mismatch"
        ref["expected_sha256"] = expected_sha256
        if isinstance(ref.get("sha256"), str):
            ref["current_sha256"] = ref["sha256"]
        return ref
    return ref


def workflow_source_from_artifact(
    *,
    entrypoint_id: str,
    artifact: dict[str, Any] | None,
    repo_root: Path,
) -> dict[str, Any] | None:
    payload = load_present_json_artifact(artifact, repo_root=repo_root)
    if payload is None:
        return None
    unsafe_reduction = payload.get("unsafe_reduction", {}) if isinstance(payload.get("unsafe_reduction"), dict) else {}
    per_unit_statuses = payload.get("per_unit_statuses") if isinstance(payload.get("per_unit_statuses"), list) else []
    return {
        "entrypoint_id": entrypoint_id,
        "artifact": artifact,
        "units_total": int_or_zero(payload.get("units_total")),
        "units_converged": int_or_zero(payload.get("units_converged")),
        "avg_repair_rounds": number_or_zero(payload.get("avg_repair_rounds")),
        "auto_recovery_rate": number_or_zero(payload.get("auto_recovery_rate")),
        "repair_history_unit_count": sum(
            1 for unit in per_unit_statuses if isinstance(unit, dict) and isinstance(unit.get("repair_history"), dict)
        ),
        "auto_recovered_unit_count": sum(
            1 for unit in per_unit_statuses if isinstance(unit, dict) and unit.get("auto_recovered") is True
        ),
        "human_interventions": int_or_zero(payload.get("human_interventions")),
        "llm_calls": int_or_zero(payload.get("llm_calls")),
        "unsafe_reduction_status": unsafe_reduction.get("status", "unknown"),
        "baseline_total_unsafe": int_or_none(unsafe_reduction.get("baseline_total_unsafe")),
        "current_total_unsafe": int_or_none(unsafe_reduction.get("current_total_unsafe")),
        "reduced_by": int_or_none(unsafe_reduction.get("reduced_by")),
        "before_after_units": workflow_before_after_unit_summaries(per_unit_statuses),
    }


def route_governance_metrics_source_from_artifact(
    *,
    entrypoint_id: str,
    artifact: dict[str, Any] | None,
    repo_root: Path,
) -> dict[str, Any] | None:
    payload = load_present_json_artifact(artifact, repo_root=repo_root)
    if payload is None:
        return None
    metrics = payload.get("metrics", {}) if isinstance(payload.get("metrics"), dict) else {}
    inputs = payload.get("inputs", {}) if isinstance(payload.get("inputs"), dict) else {}
    evidence_governance = (
        inputs.get("evidence_governance", {}) if isinstance(inputs.get("evidence_governance"), dict) else {}
    )
    s2 = metrics.get("s2_workflow_metrics", {}) if isinstance(metrics.get("s2_workflow_metrics"), dict) else {}
    unsafe_reduction = s2.get("unsafe_reduction", {}) if isinstance(s2.get("unsafe_reduction"), dict) else {}
    retention = payload.get("retention_policy", {}) if isinstance(payload.get("retention_policy"), dict) else {}
    target_artifacts = (
        retention.get("target_artifacts", {}) if isinstance(retention.get("target_artifacts"), dict) else {}
    )
    return {
        "entrypoint_id": entrypoint_id,
        "artifact": artifact,
        "status": payload.get("status", "unknown"),
        "translation_coverage_numerator": int_or_zero(metrics.get("translation_coverage_numerator")),
        "accepted_evidence_semantic_pass_count": int_or_zero(
            metrics.get("accepted_evidence_semantic_pass_count")
        ),
        "tracked_route_decision_artifacts": int_or_zero(metrics.get("tracked_route_decision_artifacts")),
        "tracked_slice_gate_contexts": int_or_zero(metrics.get("tracked_slice_gate_contexts")),
        "tracked_capability_delta_ledgers": int_or_zero(metrics.get("tracked_capability_delta_ledgers")),
        "tracked_capability_delta_count": int_or_zero(metrics.get("tracked_capability_delta_count")),
        "capability_delta_ledger": capability_delta_ledger_source(metrics.get("capability_delta_ledger")),
        "evidence_root": evidence_governance.get("evidence_root")
        if isinstance(evidence_governance.get("evidence_root"), str)
        else None,
        "c2rust_baseline": c2rust_baseline_source(metrics.get("c2rust_baseline")),
        "blocked_repairs": blocked_repairs_source(metrics.get("blocked_repairs")),
        "s2_workflow_run_count": int_or_zero(s2.get("run_count")),
        "s2_unsafe_reduction_status": unsafe_reduction.get("status", "unknown"),
        "s2_reduced_by": int_or_zero(unsafe_reduction.get("reduced_by")),
        "retention_policy_present": bool(retention),
        "target_artifacts_committed": target_artifacts.get("committed")
        if isinstance(target_artifacts.get("committed"), bool)
        else None,
        "target_artifacts_retention_class": target_artifacts.get("retention_class")
        if isinstance(target_artifacts.get("retention_class"), str)
        else None,
        "claim_boundary": payload.get("claim_boundary") if isinstance(payload.get("claim_boundary"), str) else None,
    }


def evidence_cost_retention_source_from_artifact(
    *,
    entrypoint_id: str,
    artifact: dict[str, Any] | None,
    repo_root: Path,
) -> dict[str, Any] | None:
    payload = load_present_json_artifact(artifact, repo_root=repo_root)
    if payload is None:
        return None
    inventory = payload.get("inventory", {}) if isinstance(payload.get("inventory"), dict) else {}
    portability = payload.get("portability", {}) if isinstance(payload.get("portability"), dict) else {}
    policy_compliance = (
        payload.get("policy_compliance") if isinstance(payload.get("policy_compliance"), dict) else {}
    )
    runtime = inventory.get("runtime", {}) if isinstance(inventory.get("runtime"), dict) else {}
    retention_classes = inventory.get("retention_classes", {})
    if not isinstance(retention_classes, dict):
        retention_classes = {}
    pipelines = inventory.get("pipelines", [])
    pipeline_count = (
        len([pipeline for pipeline in pipelines if isinstance(pipeline, dict)])
        if isinstance(pipelines, list)
        else 0
    )
    return {
        "entrypoint_id": entrypoint_id,
        "artifact": artifact,
        "status": payload.get("status", "unknown"),
        "evidence_root": payload.get("evidence_root") if isinstance(payload.get("evidence_root"), str) else None,
        "failed_gates": payload.get("failed_gates") if isinstance(payload.get("failed_gates"), list) else [],
        "policy_compliance": {
            "policy_tier": policy_compliance.get("policy_tier", "unknown"),
            "status": policy_compliance.get("status", "unknown"),
            "failed_gates": policy_compliance.get("failed_gates")
            if isinstance(policy_compliance.get("failed_gates"), list)
            else [],
        },
        "artifact_count": int_or_zero(inventory.get("file_count")),
        "total_bytes": int_or_zero(inventory.get("total_bytes")),
        "retention_classes": normalize_retention_classes(retention_classes),
        "pipeline_count": pipeline_count,
        "runtime_observation_count": int_or_zero(runtime.get("observation_count")),
        "runtime_total_duration_ms": int_or_zero(runtime.get("total_duration_ms")),
        "runtime_max_duration_ms": int_or_zero(runtime.get("max_duration_ms")),
        "portability_status": portability.get("status", "unknown"),
        "claim_anchor_issue_count": int_or_zero(portability.get("claim_anchor_issue_count")),
        "profile_hash_issue_count": int_or_zero(portability.get("profile_hash_issue_count")),
        "diagnostic_host_metadata_count": int_or_zero(portability.get("diagnostic_host_metadata_count")),
    }


def opencode_source_from_artifact(
    *,
    entrypoint_id: str,
    artifact: dict[str, Any] | None,
    proof_class: str,
    repo_root: Path,
) -> dict[str, Any] | None:
    payload = load_present_json_artifact(artifact, repo_root=repo_root)
    if payload is None:
        return None
    headline = payload.get("judge_headline", {}) if isinstance(payload.get("judge_headline"), dict) else {}
    runtime = payload.get("opencode_agent_runtime", {}) if isinstance(payload.get("opencode_agent_runtime"), dict) else {}
    headline_runtime = headline.get("opencode_runtime", {}) if isinstance(headline.get("opencode_runtime"), dict) else {}
    enabled = bool(headline_runtime.get("enabled", runtime.get("runtime") == "opencode"))
    if not enabled:
        return None
    chat_value = headline_runtime.get("chat_output_is_evidence", runtime.get("chat_output_is_evidence"))
    semantic_value = headline_runtime.get("semantic_gate", runtime.get("semantic_gate"))
    boundary_fields_explicit = isinstance(chat_value, bool) and isinstance(semantic_value, bool)
    return {
        "entrypoint_id": entrypoint_id,
        "artifact": artifact,
        "worker_count": int_or_zero(headline_runtime.get("worker_count", runtime.get("worker_count"))),
        "all_contracts_executed": bool(
            headline_runtime.get("all_contracts_executed", runtime.get("all_contracts_executed"))
        ),
        "chat_output_is_evidence": chat_value if isinstance(chat_value, bool) else None,
        "semantic_gate": semantic_value if isinstance(semantic_value, bool) else None,
        "boundary_fields_explicit": boundary_fields_explicit,
        "repair_round_cap": int_or_zero(headline.get("repair_round_cap")),
        "preflight_proof_summary": opencode_preflight_proof_summary_from_index(
            payload,
            entrypoint_id=entrypoint_id,
            proof_class=proof_class,
            repo_root=repo_root,
        ),
    }


def opencode_preflight_proof_summary_from_index(
    payload: dict[str, Any],
    *,
    entrypoint_id: str,
    proof_class: str,
    repo_root: Path,
) -> dict[str, Any]:
    runtime = payload.get("opencode_agent_runtime") if isinstance(payload.get("opencode_agent_runtime"), dict) else {}
    refs = payload.get("evidence_artifact_refs") if isinstance(payload.get("evidence_artifact_refs"), dict) else {}
    raw_ref = runtime.get("opencode_preflight_report")
    if not isinstance(raw_ref, dict):
        raw_ref = refs.get("opencode_preflight_report")
    preflight_ref = artifact_ref_from_existing(raw_ref, repo_root=repo_root)
    if preflight_ref is None:
        return opencode_preflight_absent_summary(required=True, entrypoint_id=entrypoint_id)

    result: dict[str, Any] = {
        "status": "missing" if preflight_ref.get("status") != "present" else "failed",
        "required_when_opencode_runtime_enabled": True,
        "entrypoint_id": entrypoint_id,
        "preflight_report": preflight_ref,
        "proof_class": proof_class,
        "chat_output_is_evidence": False,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
        "boundary": (
            "OpenCode preflight proves GLM-5.1 command-contract availability only; "
            "it is not semantic acceptance or translator coverage."
        ),
    }
    if preflight_ref.get("status") != "present":
        return result

    try:
        preflight_payload = validator.load_json(resolve_input_path(Path(str(preflight_ref["path"])), repo_root=repo_root))
    except (OSError, ValueError, json.JSONDecodeError):
        result["status"] = "read_failed"
        return result

    availability = (
        preflight_payload.get("opencode_model_availability")
        if isinstance(preflight_payload.get("opencode_model_availability"), dict)
        else {}
    )
    launch_policy = (
        preflight_payload.get("launch_policy") if isinstance(preflight_payload.get("launch_policy"), dict) else {}
    )
    contract = (
        preflight_payload.get("contract_verification")
        if isinstance(preflight_payload.get("contract_verification"), dict)
        else {}
    )
    runtime_env = None
    try:
        runtime_env = validator.validate_opencode_runtime_env_contract(
            preflight_payload.get("opencode_runtime_env"),
            "opencode_preflight_proof_summary",
        )
    except ValueError:
        runtime_env = None
    result.update(
        {
            "run_id": preflight_payload.get("run_id"),
            "opencode_command": availability.get("opencode_command"),
            "opencode_agent": launch_policy.get("opencode_agent"),
            "opencode_model": launch_policy.get("opencode_model"),
            "opencode_variant": launch_policy.get("opencode_variant"),
            "required_model": availability.get("required_model"),
            "model_availability_status": availability.get("status"),
            "model_listed": availability.get("model_listed"),
            "model_probe_argv": availability.get("argv") if isinstance(availability.get("argv"), list) else [],
            "process_returncode": int_or_none(availability.get("process_returncode")),
            "model_probe_logs": opencode_model_probe_log_refs(availability, repo_root=repo_root),
            "contract_status": contract.get("status"),
            "marker_exists": preflight_payload.get("marker_exists"),
            "opencode_run_launched": preflight_payload.get("opencode_run_launched"),
            "opencode_run_argv_bound": opencode_preflight_session_contract_passed(
                preflight_payload,
                contract=contract,
                repo_root=repo_root,
            ),
        }
    )
    if runtime_env is not None:
        result["opencode_runtime_env"] = runtime_env
        result["opencode_runtime_env_sha256"] = runtime_env["env_sha256"]
    result["status"] = (
        "passed"
        if opencode_preflight_summary_passed(
            result,
            availability,
            preflight_payload=preflight_payload,
            contract=contract,
            repo_root=repo_root,
        )
        else "failed"
    )
    return result


def opencode_preflight_absent_summary(*, required: bool, entrypoint_id: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "absent",
        "required_when_opencode_runtime_enabled": required,
        "chat_output_is_evidence": False,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
        "opencode_agent": validator.COMPETITION_OPENCODE_AGENT,
        "opencode_variant": validator.COMPETITION_OPENCODE_VARIANT,
        "opencode_run_argv_bound": False,
        "boundary": (
            "OpenCode preflight proof is absent; runtime output is not semantic evidence "
            "and does not increase translator coverage."
        ),
    }
    if entrypoint_id is not None:
        result["entrypoint_id"] = entrypoint_id
    return result


def opencode_model_probe_log_refs(availability: dict[str, Any], *, repo_root: Path) -> dict[str, Any]:
    logs = availability.get("logs") if isinstance(availability.get("logs"), dict) else {}
    result: dict[str, Any] = {}
    for stream in ("stdout", "stderr"):
        path_text = logs.get(stream)
        if not isinstance(path_text, str):
            result[stream] = {"path": "unknown", "status": "absent"}
            continue
        try:
            result[stream] = artifact_ref(resolve_input_path(Path(path_text), repo_root=repo_root), repo_root=repo_root)
        except (OSError, ValueError):
            result[stream] = {"path": path_text, "status": "invalid"}
    return result


def opencode_preflight_summary_passed(
    summary: dict[str, Any],
    availability: dict[str, Any],
    *,
    preflight_payload: dict[str, Any],
    contract: dict[str, Any],
    repo_root: Path,
) -> bool:
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
    if not isinstance(summary.get("opencode_runtime_env"), dict):
        return False
    if summary.get("opencode_runtime_env_sha256") != summary["opencode_runtime_env"].get("env_sha256"):
        return False
    if not validator.opencode_models_argv_matches(
        summary.get("model_probe_argv"),
        expected_command=validator.COMPETITION_OPENCODE_COMMAND,
    ):
        return False
    try:
        validator.validate_opencode_model_probe_log_hashes(
            availability,
            "opencode_preflight_proof_summary",
            repo_root=repo_root,
        )
    except ValueError:
        return False
    if not opencode_preflight_session_contract_passed(
        preflight_payload,
        contract=contract,
        repo_root=repo_root,
    ):
        return False
    return True


def opencode_preflight_session_contract_passed(
    preflight_payload: dict[str, Any],
    *,
    contract: dict[str, Any],
    repo_root: Path,
) -> bool:
    try:
        if preflight_payload.get("process_returncode") != 0:
            return False
        preflight_runtime_env = validator.validate_opencode_runtime_env_contract(
            preflight_payload.get("opencode_runtime_env"),
            "opencode_preflight_proof_summary",
        )
        handoff_binding = validator.validate_hash_bound_artifact_binding(
            preflight_payload.get("handoff_contract"),
            "opencode_preflight_proof_summary.handoff_contract",
            repo_root=repo_root,
        )
        handoff_payload = validator.require_object(
            validator.load_json(validator.repo_path(handoff_binding["path"], repo_root=repo_root)),
            "opencode_preflight_proof_summary.handoff_contract file",
        )
        if handoff_payload.get("runner_kind") != "opencode-preflight":
            return False
        if handoff_payload.get("run_id") != preflight_payload.get("run_id"):
            return False
        handoff_runtime_env = validator.validate_opencode_runtime_env_contract(
            handoff_payload.get("opencode_runtime_env"),
            "opencode_preflight_proof_summary.handoff_contract",
        )
        if handoff_runtime_env != preflight_runtime_env:
            return False
        handoff_policy = validator.validate_opencode_launch_policy_binding(
            handoff_payload.get("launch_policy"),
            handoff_payload.get("launch_policy_sha256"),
            "opencode_preflight_proof_summary.handoff_contract",
        )
        preflight_policy = validator.validate_opencode_launch_policy_binding(
            preflight_payload.get("launch_policy"),
            preflight_payload.get("launch_policy_sha256"),
            "opencode_preflight_proof_summary.preflight_report",
        )
        if handoff_policy != preflight_policy:
            return False
        worker_command = handoff_payload.get("worker_command")
        if not isinstance(worker_command, list) or not worker_command or not all(
            isinstance(item, str) and item for item in worker_command
        ):
            return False
        worker_command_line = validator.require_string(
            handoff_payload.get("worker_command_line"),
            "opencode_preflight_proof_summary.handoff_contract.worker_command_line",
        )
        if worker_command_line != validator.shell_command_line(worker_command):
            return False
        if handoff_payload.get("worker_command_sha256") != validator.sha256_text(worker_command_line):
            return False
        report_argv = validator.require_string_argv(
            preflight_payload.get("argv"),
            "opencode_preflight_proof_summary.preflight_report.argv",
        )
        handoff_argv = validator.require_string_argv(
            handoff_payload.get("opencode_argv"),
            "opencode_preflight_proof_summary.handoff_contract.opencode_argv",
        )
        if report_argv != handoff_argv:
            return False
        validator.validate_opencode_run_argv_binding(
            report_argv,
            "opencode_preflight_proof_summary.preflight_report.argv",
            launch_policy=preflight_policy,
        )
        handoff_command_line = validator.require_string(
            handoff_payload.get("opencode_command_line"),
            "opencode_preflight_proof_summary.handoff_contract.opencode_command_line",
        )
        if handoff_command_line != validator.shell_command_line(handoff_argv):
            return False
        handoff_prompt = validator.require_string(
            handoff_payload.get("prompt"),
            "opencode_preflight_proof_summary.handoff_contract.prompt",
        )
        if handoff_prompt != handoff_argv[-1]:
            return False
        marker_path_text = validator.require_string(
            preflight_payload.get("marker_path"),
            "opencode_preflight_proof_summary.marker_path",
        )
        expected_marker_path = validator.require_string(
            handoff_payload.get("expected_marker_path"),
            "opencode_preflight_proof_summary.handoff_contract.expected_marker_path",
        )
        if marker_path_text != expected_marker_path:
            return False
        marker_path = validator.repo_path(marker_path_text, repo_root=repo_root)
        if not marker_path.is_file():
            return False
        session_binding = validator.validate_hash_bound_artifact_binding(
            preflight_payload.get("opencode_session_evidence"),
            "opencode_preflight_proof_summary.opencode_session_evidence",
            repo_root=repo_root,
        )
        session_evidence = validator.require_object(
            validator.load_json(validator.repo_path(session_binding["path"], repo_root=repo_root)),
            "opencode_preflight_proof_summary.opencode_session_evidence file",
        )
        validator.validate_opencode_session_evidence_contract(
            session_evidence,
            "opencode_preflight_proof_summary.opencode_session_evidence",
            repo_root=repo_root,
        )
        session_runtime_env = validator.validate_opencode_runtime_env_contract(
            session_evidence.get("opencode_runtime_env"),
            "opencode_preflight_proof_summary.opencode_session_evidence",
        )
        if session_runtime_env != preflight_runtime_env:
            return False
        validator.validate_opencode_contract_recomputed_from_session(
            embedded_verification=contract,
            session_evidence=session_evidence,
            worker_command=worker_command,
            summary_path=marker_path,
            label="opencode_preflight_proof_summary",
            repo_root=repo_root,
        )
    except (OSError, ValueError, json.JSONDecodeError, TypeError):
        return False
    return True
