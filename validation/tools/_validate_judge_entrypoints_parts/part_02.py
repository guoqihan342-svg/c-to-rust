def manifest_profile_payload(manifest: dict[str, Any]) -> dict[str, Any]:
    for field in ("profile", "competition_profile"):
        value = manifest.get(field)
        if isinstance(value, dict):
            return value
    raise ValueError("tracked manifest must include profile or competition_profile")


def expected_manifest_reproduction_command_key(entry: dict[str, Any]) -> str:
    command = require_string(entry.get("command"), f"{entry.get('id')}.command")
    if "validation.tools.judge_demo" in command:
        return "judge_demo_command"
    if "validation.tools.opencode_agent_harness evaluate" in command:
        return "evaluate_profile_command"
    if "validation.tools.opencode_agent_harness run-batch-profile" in command:
        return "run_batch_profile_command"
    raise ValueError(f"{entry.get('id')} command is not a supported judge entrypoint command")


def manifest_source_commits(manifest: dict[str, Any]) -> list[str]:
    commits: set[str] = set()
    source = manifest.get("source")
    if isinstance(source, dict):
        for field in ("source_commit", "require_source_commit"):
            value = source.get(field)
            if isinstance(value, str):
                commits.add(value)
    workers = manifest.get("workers")
    if isinstance(workers, list):
        for worker in workers:
            if not isinstance(worker, dict):
                continue
            for field in ("source_commit", "require_source_commit"):
                value = worker.get(field)
                if isinstance(value, str):
                    commits.add(value)
    return sorted(commits)


def validate_expected_artifacts_under_out_root(entry: dict[str, Any], *, out_root: str) -> list[str]:
    assert_repo_relative_posix(out_root)
    out_root_prefix = out_root.rstrip("/") + "/"
    artifacts = require_object(entry.get("expected_artifacts"), f"{entry.get('id')}.expected_artifacts")
    artifact_paths: list[str] = []
    for name, value in sorted(artifacts.items()):
        path_text = require_string(value, f"{entry.get('id')}.expected_artifacts.{name}")
        assert_repo_relative_posix(path_text)
        if not path_text.startswith(out_root_prefix):
            raise ValueError(f"{entry.get('id')} expected_artifacts.{name} must be under reproduction --out-root")
        artifact_paths.append(path_text)
    return artifact_paths


def validate_tracked_manifest_contract(
    entry: dict[str, Any],
    *,
    config: dict[str, Any],
    claim_boundary: dict[str, Any],
    source_pin_contract: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    manifest_ref = require_object(entry.get("tracked_manifest"), f"{entry.get('id')}.tracked_manifest")
    manifest_path = require_string(manifest_ref.get("path"), f"{entry.get('id')}.tracked_manifest.path")
    manifest = load_json(repo_path(manifest_path, repo_root=repo_root))
    if manifest.get("status") != "passed":
        raise ValueError(f"{entry.get('id')} tracked manifest status must be passed")
    if manifest.get("target_id") != config.get("target_id"):
        raise ValueError(f"{entry.get('id')} tracked manifest target_id must match judge target_id")
    if manifest.get("proof_class") != entry.get("proof_class"):
        raise ValueError(f"{entry.get('id')} tracked manifest proof_class must match entrypoint")

    environment_ref = require_object(config.get("environment_profile"), "environment_profile")
    environment = require_object(manifest.get("environment_profile"), f"{entry.get('id')} tracked manifest environment_profile")
    for field in ("path", "sha256"):
        if environment.get(field) != environment_ref.get(field):
            raise ValueError(f"{entry.get('id')} tracked manifest environment_profile.{field} must match judge config")

    manifest_boundary = require_object(manifest.get("claim_boundary"), f"{entry.get('id')} tracked manifest claim_boundary")
    for field in ("semantic_claim_source", "generated_draft_semantic_pass", "translation_coverage_numerator"):
        if manifest_boundary.get(field) != claim_boundary.get(field):
            raise ValueError(f"{entry.get('id')} tracked manifest claim_boundary.{field} must match judge config")

    if source_pin_contract:
        allowed_commits = set(source_pin_contract["allowed_commits"])
        disallowed = sorted(commit for commit in manifest_source_commits(manifest) if commit not in allowed_commits)
        if disallowed:
            raise ValueError(f"{entry.get('id')} tracked manifest uses commits outside source_pin_policy: {disallowed}")

    profile_ref = require_object(entry.get("profile"), f"{entry.get('id')}.profile")
    profile = manifest_profile_payload(manifest)
    if profile.get("path") != profile_ref.get("path"):
        raise ValueError(f"{entry.get('id')} tracked manifest profile path must match entrypoint profile")
    if profile.get("sha256") != profile_ref.get("sha256"):
        raise ValueError(f"{entry.get('id')} tracked manifest profile sha256 must match entrypoint profile")

    reproduction = require_object(manifest.get("reproduction"), f"{entry.get('id')} tracked manifest reproduction")
    command_key = expected_manifest_reproduction_command_key(entry)
    manifest_command = require_string(reproduction.get(command_key), f"{entry.get('id')} tracked manifest reproduction.{command_key}")
    if manifest_command != entry.get("command"):
        raise ValueError(f"{entry.get('id')} tracked manifest reproduction command must match entrypoint command")
    flags = parsed_command_flags(manifest_command)
    profile_path = require_command_flag(flags, "--profile", f"{entry.get('id')} tracked manifest reproduction.{command_key}")
    run_id = require_command_flag(flags, "--run-id", f"{entry.get('id')} tracked manifest reproduction.{command_key}")
    out_root = require_command_flag(flags, "--out-root", f"{entry.get('id')} tracked manifest reproduction.{command_key}")
    if profile_path != profile_ref.get("path"):
        raise ValueError(f"{entry.get('id')} tracked manifest reproduction --profile must match entrypoint profile")
    if run_id != entry.get("run_id"):
        raise ValueError(f"{entry.get('id')} tracked manifest reproduction --run-id must match entrypoint run_id")
    expected_artifact_paths = validate_expected_artifacts_under_out_root(entry, out_root=out_root)
    validate_local_absolute_path_policy(reproduction, label=f"{entry.get('id')} tracked manifest reproduction")
    return {
        "path": manifest_path,
        "manifest_kind": manifest.get("manifest_kind"),
        "reproduction_command_key": command_key,
        "reproduction_out_root": out_root,
        "expected_artifact_count": len(expected_artifact_paths),
        "source_commits": manifest_source_commits(manifest),
        "status": "passed",
    }


def entrypoint_metadata(entry: dict[str, Any]) -> dict[str, Any]:
    judge_focus = entry.get("judge_focus", [])
    return {
        "id": entry.get("id"),
        "purpose": entry.get("purpose"),
        "priority": entry.get("priority"),
        "proof_class": entry.get("proof_class", "unknown"),
        "run_id": entry.get("run_id", "unknown"),
        "judge_focus": list(judge_focus) if isinstance(judge_focus, list) else [],
    }


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def validate_test_contract(
    config: dict[str, Any],
    *,
    entrypoints: list[dict[str, Any]],
    claim_boundary: dict[str, Any],
) -> dict[str, Any]:
    contract = require_object(config.get("test_contract"), "test_contract")
    features = require_object(config.get("harness_features_demonstrated"), "harness_features_demonstrated")
    required_features = contract.get("required_harness_features", list(REQUIRED_HARNESS_FEATURES))
    if not isinstance(required_features, list) or not required_features:
        raise ValueError("test_contract.required_harness_features must be a non-empty list")
    if list(required_features) != list(REQUIRED_HARNESS_FEATURES):
        raise ValueError(f"test_contract.required_harness_features must be {list(REQUIRED_HARNESS_FEATURES)}")
    missing_features = [feature for feature in required_features if features.get(feature) is not True]
    if missing_features:
        raise ValueError(f"harness_features_demonstrated missing true features: {missing_features}")

    entrypoint_ids = [require_string(entry.get("id"), "entrypoint.id") for entry in entrypoints]
    if len(set(entrypoint_ids)) != len(entrypoint_ids):
        raise ValueError(f"entrypoint ids must be unique: {entrypoint_ids}")
    required_entrypoint_ids = contract.get("required_entrypoint_ids")
    if not isinstance(required_entrypoint_ids, list) or not required_entrypoint_ids:
        raise ValueError("test_contract.required_entrypoint_ids must be a non-empty list")
    if set(required_entrypoint_ids) != set(entrypoint_ids):
        raise ValueError(
            "test_contract.required_entrypoint_ids must match entrypoints: "
            f"{required_entrypoint_ids} != {entrypoint_ids}"
        )

    required_artifacts = contract.get("required_expected_artifacts", [])
    if not isinstance(required_artifacts, list):
        raise ValueError("test_contract.required_expected_artifacts must be a list")
    for entry in entrypoints:
        if is_competition_smoke_entrypoint(entry):
            continue
        artifacts = require_object(entry.get("expected_artifacts"), f"{entry.get('id')}.expected_artifacts")
        missing = [name for name in required_artifacts if name not in artifacts]
        if missing:
            raise ValueError(f"{entry.get('id')} missing required expected artifacts: {missing}")

    if contract.get("semantic_claim_source") != claim_boundary.get("semantic_claim_source"):
        raise ValueError("test_contract.semantic_claim_source must match claim_boundary")
    if contract.get("generated_draft_semantic_pass") is not claim_boundary.get("generated_draft_semantic_pass"):
        raise ValueError("test_contract.generated_draft_semantic_pass must match claim_boundary")
    if contract.get("translation_coverage_numerator") != claim_boundary.get("translation_coverage_numerator"):
        raise ValueError("test_contract.translation_coverage_numerator must match claim_boundary")
    if contract.get("commands_must_use_portable_python3_b") is not True:
        raise ValueError("test_contract.commands_must_use_portable_python3_b must be true")

    repair_round_cap = contract.get("repair_round_cap", 5)
    if repair_round_cap != 5:
        raise ValueError("test_contract.repair_round_cap must be 5")
    required_roles = contract.get("required_agent_roles", list(REQUIRED_AGENT_ROLES))
    if set(required_roles) != set(REQUIRED_AGENT_ROLES):
        raise ValueError(f"test_contract.required_agent_roles must be {list(REQUIRED_AGENT_ROLES)}")
    required_context_stages = contract.get("required_context_pipeline_stages", list(REQUIRED_CONTEXT_STAGES))
    if list(required_context_stages) != list(REQUIRED_CONTEXT_STAGES):
        raise ValueError(f"test_contract.required_context_pipeline_stages must be {list(REQUIRED_CONTEXT_STAGES)}")

    context_contract = require_object(contract.get("context_pack_contract"), "test_contract.context_pack_contract")
    if context_contract.get("chat_output_is_evidence") is not False:
        raise ValueError("test_contract.context_pack_contract.chat_output_is_evidence must be false")
    if context_contract.get("semantic_gate") is not False:
        raise ValueError("test_contract.context_pack_contract.semantic_gate must be false")
    if context_contract.get("evidence_policy") != "on-disk-artifacts-only":
        raise ValueError("test_contract.context_pack_contract.evidence_policy must be on-disk-artifacts-only")
    if context_contract.get("checkpoint_backend") != "sqlite":
        raise ValueError("test_contract.context_pack_contract.checkpoint_backend must be sqlite")
    if context_contract.get("worker_state_source") != "agent-index.agents_by_worker_id":
        raise ValueError("test_contract.context_pack_contract.worker_state_source must be agent-index.agents_by_worker_id")

    agent_contract = require_object(contract.get("agent_index_contract"), "test_contract.agent_index_contract")
    if agent_contract.get("chat_output_is_evidence") is not False:
        raise ValueError("test_contract.agent_index_contract.chat_output_is_evidence must be false")
    if agent_contract.get("semantic_gate") is not False:
        raise ValueError("test_contract.agent_index_contract.semantic_gate must be false")
    if agent_contract.get("checkpoint_backend") != "sqlite":
        raise ValueError("test_contract.agent_index_contract.checkpoint_backend must be sqlite")
    if agent_contract.get("worker_isolation") != "per-worker out_root":
        raise ValueError("test_contract.agent_index_contract.worker_isolation must be per-worker out_root")

    return {
        "required_entrypoint_ids": entrypoint_ids,
        "required_harness_features": list(required_features),
        "required_expected_artifacts": list(required_artifacts),
        "required_context_pipeline_stages": list(required_context_stages),
        "required_agent_roles": list(required_roles),
        "repair_round_cap": repair_round_cap,
        "commands_must_use_portable_python3_b": True,
        "status": "passed",
    }


def validate_context_management_contract(
    payload: dict[str, Any],
    *,
    path_text: str,
    expected_artifacts: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    if payload.get("report_kind") != "context-pack":
        raise ValueError(f"context_pack report_kind must be context-pack: {path_text}")
    contract = require_object(payload.get("context_management_contract"), "context_management_contract")
    if contract.get("contract_kind") != "context-management":
        raise ValueError("context_management_contract.contract_kind must be context-management")
    if contract.get("schema_version") != 1:
        raise ValueError("context_management_contract.schema_version must be 1")
    if contract.get("chat_output_is_evidence") is not False:
        raise ValueError("context_management_contract.chat_output_is_evidence must be false")
    if contract.get("semantic_gate") is not False:
        raise ValueError("context_management_contract.semantic_gate must be false")
    if contract.get("evidence_policy") != "on-disk-artifacts-only":
        raise ValueError("context_management_contract.evidence_policy must be on-disk-artifacts-only")

    context_pack_path = require_string(contract.get("context_pack"), "context_management_contract.context_pack")
    agent_index_path = require_string(contract.get("agent_index"), "context_management_contract.agent_index")
    assert_repo_relative_posix(context_pack_path)
    assert_repo_relative_posix(agent_index_path)
    if expected_artifacts.get("context_pack") and context_pack_path != expected_artifacts["context_pack"]:
        raise ValueError("context_management_contract.context_pack must match expected_artifacts.context_pack")
    if expected_artifacts.get("agent_index") and agent_index_path != expected_artifacts["agent_index"]:
        raise ValueError("context_management_contract.agent_index must match expected_artifacts.agent_index")

    primary_report = contract.get("primary_report")
    if isinstance(primary_report, str):
        assert_repo_relative_posix(primary_report)
    resume_protocol = require_object(contract.get("resume_protocol"), "context_management_contract.resume_protocol")
    if resume_protocol.get("checkpoint_backend") != "sqlite":
        raise ValueError("context_management_contract.resume_protocol.checkpoint_backend must be sqlite")
    ledger_path = resume_protocol.get("ledger_path")
    if isinstance(ledger_path, str):
        assert_repo_relative_posix(ledger_path)
    if resume_protocol.get("worker_state_source") != "agent-index.agents_by_worker_id":
        raise ValueError("context_management_contract.resume_protocol.worker_state_source must be agent-index.agents_by_worker_id")

    pipeline = payload.get("context_management_contract", {}).get("pipeline")
    if not isinstance(pipeline, list) or not pipeline:
        raise ValueError("context_management_contract.pipeline must be a non-empty list")
    stage_names = []
    for item in pipeline:
        if not isinstance(item, dict) or not isinstance(item.get("stage"), str):
            raise ValueError(
                f"context_management_contract.pipeline stages must be {list(REQUIRED_CONTEXT_STAGES)}"
            )
        stage_names.append(item["stage"])
    stages = set(stage_names)
    missing_stages = [stage for stage in REQUIRED_CONTEXT_STAGES if stage not in stages]
    if missing_stages:
        raise ValueError(f"context_management_contract.pipeline missing stages: {missing_stages}")
    if stage_names != list(REQUIRED_CONTEXT_STAGES):
        raise ValueError(f"context_management_contract.pipeline stages must be {list(REQUIRED_CONTEXT_STAGES)}")
    repair_stage = next(item for item in pipeline if isinstance(item, dict) and item.get("stage") == "repair")
    if repair_stage.get("max_rounds") != 5:
        raise ValueError("context_management_contract repair max_rounds must be 5")
    worker_stage = next(item for item in pipeline if isinstance(item, dict) and item.get("stage") == "translate")
    if worker_stage.get("fanout") is not True:
        raise ValueError("context_management_contract translate stage must be fanout")

    entrypoints = require_object(payload.get("entrypoints"), "context_pack.entrypoints")
    report_entrypoint = contract.get("report_entrypoint")
    if isinstance(report_entrypoint, str):
        if report_entrypoint not in entrypoints:
            raise ValueError("context_pack.entrypoints must include context_management_contract.report_entrypoint")
        if not isinstance(entrypoints.get(report_entrypoint), str):
            raise ValueError(f"context_pack.entrypoints.{report_entrypoint} must be a repo-relative POSIX string")
    for key, value in sorted(entrypoints.items()):
        if not isinstance(key, str) or not key:
            raise ValueError("context_pack.entrypoints keys must be non-empty strings")
        if value is None:
            continue
        if not isinstance(value, str):
            raise ValueError(f"context_pack.entrypoints.{key} must be a repo-relative POSIX string or null")
        try:
            assert_repo_relative_posix(value)
        except ValueError as error:
            raise ValueError(f"context_pack.entrypoints.{key}: {error}") from error
    if isinstance(primary_report, str) and entrypoints.get("primary_report") not in (None, primary_report):
        raise ValueError("context_pack.entrypoints.primary_report must match context_management_contract.primary_report")
    for artifact_key in ("batch_profile_report", "run_plan_report"):
        expected_value = expected_artifacts.get(artifact_key)
        if isinstance(expected_value, dict):
            expected_value = expected_value.get("path")
        if isinstance(expected_value, str) and entrypoints.get(artifact_key) != expected_value:
            raise ValueError(
                f"context_pack.entrypoints.{artifact_key} must match expected_artifacts.{artifact_key}"
            )

    return {
        "path": path_text,
        "status": "passed",
        "pipeline_stages": list(REQUIRED_CONTEXT_STAGES),
        "repair_round_cap": 5,
        "entrypoint_count": len(entrypoints),
    }


def validate_agent_coordination_contract(
    payload: dict[str, Any],
    *,
    path_text: str,
) -> dict[str, Any]:
    if payload.get("report_kind") != "agent-index":
        raise ValueError(f"agent_index report_kind must be agent-index: {path_text}")
    contract = require_object(payload.get("agent_coordination_contract"), "agent_coordination_contract")
    if contract.get("contract_kind") != "agent-coordination":
        raise ValueError("agent_coordination_contract.contract_kind must be agent-coordination")
    if contract.get("schema_version") != 1:
        raise ValueError("agent_coordination_contract.schema_version must be 1")
    if contract.get("chat_output_is_evidence") is not False:
        raise ValueError("agent_coordination_contract.chat_output_is_evidence must be false")
    if contract.get("semantic_gate") is not False:
        raise ValueError("agent_coordination_contract.semantic_gate must be false")
    if contract.get("checkpoint_backend") != "sqlite":
        raise ValueError("agent_coordination_contract.checkpoint_backend must be sqlite")

    roles = require_object(contract.get("roles"), "agent_coordination_contract.roles")
    missing_roles = [role for role in REQUIRED_AGENT_ROLES if role not in roles]
    if missing_roles:
        raise ValueError(f"agent_coordination_contract.roles missing roles: {missing_roles}")
    if set(roles) != set(REQUIRED_AGENT_ROLES):
        raise ValueError(f"agent_coordination_contract.roles must be {list(REQUIRED_AGENT_ROLES)}")
    repairer = require_object(roles.get("repairer"), "agent_coordination_contract.roles.repairer")
    if repairer.get("round_cap") != 5:
        raise ValueError("agent_coordination_contract.roles.repairer.round_cap must be 5")
    worker = require_object(roles.get("worker"), "agent_coordination_contract.roles.worker")
    if worker.get("isolation") != "per-worker out_root":
        raise ValueError("agent_coordination_contract.roles.worker.isolation must be per-worker out_root")

    agents_by_worker_id = require_object(payload.get("agents_by_worker_id"), "agents_by_worker_id")
    agents = payload.get("agents")
    if not isinstance(agents, list) or not agents:
        raise ValueError("agent_index.agents must be a non-empty list")
    if contract.get("worker_count") != len(agents_by_worker_id):
        raise ValueError("agent_coordination_contract.worker_count must match agents_by_worker_id")
    for worker_id, agent in sorted(agents_by_worker_id.items()):
        agent_payload = require_object(agent, f"agents_by_worker_id.{worker_id}")
        if agent_payload.get("worker_id") != worker_id:
            raise ValueError(f"agents_by_worker_id key must match worker_id: {worker_id}")
        for field in ("assignment_path", "request_path", "summary_path", "report_path", "isolated_out_root"):
            assert_repo_relative_posix(require_string(agent_payload.get(field), f"{worker_id}.{field}"))
    local_path_scan = validate_local_absolute_path_policy(payload, label=f"agent_index {path_text}")

    return {
        "path": path_text,
        "status": "passed",
        "roles": list(REQUIRED_AGENT_ROLES),
        "worker_count": len(agents_by_worker_id),
        "repair_round_cap": 5,
        "local_absolute_path_scan": local_path_scan,
    }


def validate_sha256_hex(value: Any, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{label} must be a sha256 hex string")
    return value


def validate_artifact_binding_shape(
    value: Any,
    label: str,
    *,
    repo_root: Path | None = None,
) -> dict[str, str]:
    binding = require_object(value, label)
    path_text = require_string(binding.get("path"), f"{label}.path")
    assert_repo_relative_posix(path_text)
    sha256 = validate_sha256_hex(binding.get("sha256"), f"{label}.sha256")
    if repo_root is not None:
        validate_ref({"path": path_text, "sha256": sha256}, repo_root=repo_root)
    return {"path": path_text, "sha256": sha256}


def validate_verified_unsafe_baseline_ref(
    value: Any,
    label: str,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    binding = validate_artifact_binding_shape(value, label, repo_root=repo_root)
    payload = require_object(value, label)
    status = payload.get("status")
    if status is not None and status != "passed":
        raise ValueError(f"{label}.status must be passed")
    semantic_pass = payload.get("semantic_pass")
    if semantic_pass is not None and semantic_pass is not True:
        raise ValueError(f"{label}.semantic_pass must be true")
    source = payload.get("semantic_claim_source")
    if source is not None and source != "verified_unsafe_baseline_gates":
        raise ValueError(f"{label}.semantic_claim_source must be verified_unsafe_baseline_gates")
    generated = payload.get("generated_draft_semantic_pass")
    if generated is not None and generated is not False:
        raise ValueError(f"{label}.generated_draft_semantic_pass must be false")
    result = dict(payload)
    result.update(binding)
    if repo_root is not None:
        artifact_payload = load_json(repo_path(binding["path"], repo_root=repo_root))
        if artifact_payload.get("status") != "passed":
            raise ValueError(f"{label}.status must be passed")
        if artifact_payload.get("semantic_pass") is not True:
            raise ValueError(f"{label}.semantic_pass must be true")
        if artifact_payload.get("semantic_claim_source") != "verified_unsafe_baseline_gates":
            raise ValueError(f"{label}.semantic_claim_source must be verified_unsafe_baseline_gates")
        if artifact_payload.get("generated_draft_semantic_pass") is not False:
            raise ValueError(f"{label}.generated_draft_semantic_pass must be false")
        validate_verified_unsafe_baseline_deep_contract(artifact_payload, label)
    return result


def validate_verified_unsafe_baseline_deep_contract(payload: dict[str, Any], label: str) -> None:
    c2rust_output = validate_verified_baseline_nested_artifact_ref(
        payload.get("c2rust_output"),
        f"{label}.c2rust_output",
        required_status="generated",
    )
    compile_artifact = validate_verified_baseline_nested_artifact_ref(
        payload.get("compile_artifact"),
        f"{label}.compile_artifact",
        required_status="compiled",
    )
    direct = require_object(payload.get("direct_c2rust_replay"), f"{label}.direct_c2rust_replay")
    if direct.get("status") != "passed":
        raise ValueError(f"{label}.direct_c2rust_replay.status must be passed")
    if direct.get("semantic_pass") is not False:
        raise ValueError(f"{label}.direct_c2rust_replay.semantic_pass must be false")
    if direct.get("observable_replay_pass") is not True:
        raise ValueError(f"{label}.direct_c2rust_replay.observable_replay_pass must be true")
    if direct.get("c2rust_output") != c2rust_output:
        raise ValueError(f"{label}.direct_c2rust_replay.c2rust_output must match c2rust_output")
    if direct.get("compile_artifact") != compile_artifact:
        raise ValueError(f"{label}.direct_c2rust_replay.compile_artifact must match compile_artifact")
    direct_artifact = require_object(direct.get("artifact"), f"{label}.direct_c2rust_replay.artifact")
    validate_direct_c2rust_replay_artifact_ref(direct_artifact, f"{label}.direct_c2rust_replay.artifact")

    gate_refs = payload.get("same_output_gate_refs")
    if not isinstance(gate_refs, dict):
        raise ValueError(f"{label}.same_output_gate_refs missing")
    missing = sorted(set(VERIFIED_UNSAFE_BASELINE_SAME_OUTPUT_GATES) - set(gate_refs))
    if missing:
        raise ValueError(f"{label}.same_output_gate_refs missing gates: {', '.join(missing)}")
    for gate in VERIFIED_UNSAFE_BASELINE_SAME_OUTPUT_GATES:
        gate_label = f"{label}.same_output_gate_refs.{gate}"
        gate_ref = require_object(gate_refs.get(gate), gate_label)
        validate_verified_baseline_gate_ref(
            gate_ref,
            gate_label,
            expected_output=c2rust_output,
            expected_compile_artifact=compile_artifact,
            require_sha=gate != "final_verification",
        )
        if gate == "rust_replay":
            validate_direct_c2rust_replay_gate_ref(gate_ref, gate_label)


def validate_verified_baseline_nested_artifact_ref(
    value: Any,
    label: str,
    *,
    required_status: str,
) -> dict[str, Any]:
    payload = require_object(value, label)
    path_text = require_string(payload.get("path"), f"{label}.path")
    assert_repo_relative_posix(path_text)
    validate_sha256_hex(payload.get("sha256"), f"{label}.sha256")
    if payload.get("status") != required_status:
        raise ValueError(f"{label}.status must be {required_status}")
    return {
        "path": path_text,
        "sha256": payload["sha256"],
        "status": required_status,
    }


def validate_verified_baseline_gate_ref(
    value: dict[str, Any],
    label: str,
    *,
    expected_output: dict[str, Any],
    expected_compile_artifact: dict[str, Any],
    require_sha: bool,
) -> None:
    path_text = require_string(value.get("path"), f"{label}.path")
    assert_repo_relative_posix(path_text)
    if require_sha:
        validate_sha256_hex(value.get("sha256"), f"{label}.sha256")
    elif value.get("sha256") is not None:
        validate_sha256_hex(value.get("sha256"), f"{label}.sha256")
    if not isinstance(value.get("status"), str) or not value.get("status"):
        raise ValueError(f"{label}.status must be a non-empty string")
    if value.get("binding") != "same_c2rust_output":
        raise ValueError(f"{label}.binding must be same_c2rust_output")
    if value.get("c2rust_output") != expected_output:
        raise ValueError(f"{label}.c2rust_output must match verified baseline output")
    if value.get("compile_artifact") != expected_compile_artifact:
        raise ValueError(f"{label}.compile_artifact must match verified baseline compile artifact")


def validate_direct_c2rust_replay_gate_ref(value: dict[str, Any], label: str) -> None:
    path_text = str(value.get("path", ""))
    if not path_text.endswith("-c2rust-direct-replay.json"):
        raise ValueError(f"{label}.path must point to direct C2Rust replay evidence")
    if value.get("replay_kind") != "direct_c2rust_output_replay":
        raise ValueError(f"{label}.replay_kind must be direct_c2rust_output_replay")
    if value.get("correctness_role") != "direct_replay_evidence":
        raise ValueError(f"{label}.correctness_role must be direct_replay_evidence")


def validate_direct_c2rust_replay_artifact_ref(value: dict[str, Any], label: str) -> None:
    path_text = require_string(value.get("path"), f"{label}.path")
    assert_repo_relative_posix(path_text)
    if not path_text.endswith("-c2rust-direct-replay.json"):
        raise ValueError(f"{label}.path must point to direct C2Rust replay evidence")
    validate_sha256_hex(value.get("sha256"), f"{label}.sha256")
    if value.get("status") != "passed":
        raise ValueError(f"{label}.status must be passed")


def verified_unsafe_baseline_ref_from_container(value: Any) -> Any | None:
    if not isinstance(value, dict):
        return None
    direct = value.get("verified_unsafe_baseline")
    if isinstance(direct, dict):
        return direct
    policy = value.get("attempt_evidence_policy")
    if isinstance(policy, dict):
        policy_ref = verified_unsafe_baseline_ref_from_container(policy)
        if isinstance(policy_ref, dict):
            return policy_ref
    baseline_attempt = value.get("baseline_attempt")
    if isinstance(baseline_attempt, dict):
        candidate = baseline_attempt.get("verified_unsafe_baseline")
        if isinstance(candidate, dict):
            return candidate
    return None


def compare_verified_unsafe_baseline_refs(candidates: list[tuple[str, Any]]) -> None:
    if len(candidates) < 2:
        return
    first_label, first_ref = candidates[0]
    first_binding = validate_artifact_binding_shape(first_ref, first_label, repo_root=None)
    for label, ref in candidates[1:]:
        binding = validate_artifact_binding_shape(ref, label, repo_root=None)
        if binding != first_binding:
            raise ValueError("verified_unsafe_baseline must match across resume_manifest, context_pack, and agent_index")


def validate_route_governance_metrics_report_contract(ref: dict[str, str], *, repo_root: Path) -> dict[str, Any]:
    path_text = ref["path"]
    path = repo_path(path_text, repo_root=repo_root)
    payload = load_json(path)
    schema = load_json(ROUTE_GOVERNANCE_METRICS_SCHEMA)
    try:
        jsonschema.validate(payload, schema)
    except jsonschema.ValidationError as error:
        path = jsonschema_error_path(error)
        raise ValueError(
            "route_governance_metrics_report must match validation/route-governance-metrics.schema.json: "
            f"{path}: {error.message}"
        ) from error
    metrics = require_object(payload.get("metrics"), "route_governance_metrics_report.metrics")
    retention = require_object(payload.get("retention_policy"), "route_governance_metrics_report.retention_policy")
    return {
        "status": "passed",
        "path": path_text,
        "translation_coverage_numerator": metrics.get("translation_coverage_numerator"),
        "accepted_evidence_semantic_pass_count": metrics.get("accepted_evidence_semantic_pass_count"),
        "tracked_route_decision_artifacts": metrics.get("tracked_route_decision_artifacts"),
        "tracked_slice_gate_contexts": metrics.get("tracked_slice_gate_contexts"),
        "retention_policy": {
            "report_kind": retention.get("report_kind"),
            "target_artifacts_committed": retention.get("target_artifacts", {}).get("committed")
            if isinstance(retention.get("target_artifacts"), dict)
            else None,
        },
    }


def jsonschema_error_path(error: jsonschema.ValidationError) -> str:
    parts = ["$"]
    for item in error.absolute_path:
        if isinstance(item, int):
            parts.append(f"[{item}]")
        else:
            parts.append(f".{item}")
    return "".join(parts)


def validate_opencode_launch_policy_binding(value: Any, sha_value: Any, label: str) -> dict[str, Any]:
    policy = require_object(value, f"{label}.launch_policy")
    command = require_string(policy.get("opencode_command"), f"{label}.launch_policy.opencode_command")
    if command != COMPETITION_OPENCODE_COMMAND:
        raise ValueError(f"{label}.launch_policy.opencode_command must be {COMPETITION_OPENCODE_COMMAND}")
    variant = require_string(policy.get("opencode_variant"), f"{label}.launch_policy.opencode_variant")
    if variant != COMPETITION_OPENCODE_VARIANT:
        raise ValueError(f"{label}.launch_policy.opencode_variant must be {COMPETITION_OPENCODE_VARIANT}")
    model = policy.get("opencode_model")
    if not isinstance(model, str) or not model:
        raise ValueError(f"{label}.launch_policy.opencode_model must be a non-empty string")
    if model != COMPETITION_OPENCODE_MODEL:
        raise ValueError(f"{label}.launch_policy.opencode_model must be {COMPETITION_OPENCODE_MODEL}")
    agent = policy.get("opencode_agent")
    if agent != COMPETITION_OPENCODE_AGENT:
        raise ValueError(f"{label}.launch_policy.opencode_agent must be {COMPETITION_OPENCODE_AGENT}")
    if not isinstance(policy.get("opencode_skip_permissions"), bool):
        raise ValueError(f"{label}.launch_policy.opencode_skip_permissions must be a boolean")
    normalized = {
        "opencode_command": command,
        "opencode_model": model,
        "opencode_agent": agent,
        "opencode_variant": variant,
        "opencode_skip_permissions": policy["opencode_skip_permissions"],
    }
    expected_sha = sha256_text(json.dumps(normalized, sort_keys=True))
    actual_sha = validate_sha256_hex(sha_value, f"{label}.launch_policy_sha256")
    if actual_sha != expected_sha:
        raise ValueError(f"{label}.launch_policy_sha256 must match launch_policy")
    return normalized


def validate_opencode_runtime_env_contract(value: Any, label: str) -> dict[str, Any]:
    runtime_env = require_object(value, f"{label}.opencode_runtime_env")
    if runtime_env.get("status") != "isolated":
        raise ValueError(f"{label}.opencode_runtime_env.status must be isolated")
    scope = require_string(runtime_env.get("scope"), f"{label}.opencode_runtime_env.scope")
    runtime_root = require_string(runtime_env.get("runtime_root"), f"{label}.opencode_runtime_env.runtime_root")
    assert_repo_relative_posix(runtime_root)
    runtime_root_path = PurePosixPath(runtime_root)
    if len(runtime_root_path.parts) < 2 or runtime_root_path.parts[-2:] != ("opencode-runtime", scope):
        raise ValueError(f"{label}.opencode_runtime_env.runtime_root must end with opencode-runtime/<scope>")
    env = require_object(runtime_env.get("env"), f"{label}.opencode_runtime_env.env")
    expected_env = {
        "XDG_CONFIG_HOME": runtime_root_path / "config",
        "XDG_DATA_HOME": runtime_root_path / "data",
        "XDG_CACHE_HOME": runtime_root_path / "cache",
        "TMPDIR": runtime_root_path / "tmp",
        "TEMP": runtime_root_path / "tmp",
        "TMP": runtime_root_path / "tmp",
    }
    if set(env) != set(OPENCODE_RUNTIME_ENV_KEYS):
        raise ValueError(f"{label}.opencode_runtime_env.env keys must match OpenCode runtime keys")
    normalized_env: dict[str, str] = {}
    for key in OPENCODE_RUNTIME_ENV_KEYS:
        path_text = require_string(env.get(key), f"{label}.opencode_runtime_env.env.{key}")
        assert_repo_relative_posix(path_text)
        env_path = PurePosixPath(path_text)
        if env_path != expected_env[key]:
            raise ValueError(f"{label}.opencode_runtime_env.env.{key} must be under runtime_root")
        normalized_env[key] = env_path.as_posix()
    if runtime_env.get("semantic_gate") is not False:
        raise ValueError(f"{label}.opencode_runtime_env.semantic_gate must be false")
    expected_sha = sha256_text(
        json.dumps(
            {
                "scope": scope,
                "runtime_root": runtime_root_path.as_posix(),
                "env": normalized_env,
            },
            sort_keys=True,
        )
    )
    actual_sha = validate_sha256_hex(runtime_env.get("env_sha256"), f"{label}.opencode_runtime_env.env_sha256")
    if actual_sha != expected_sha:
        raise ValueError(f"{label}.opencode_runtime_env.env_sha256 must match opencode_runtime_env")
    return {
        **runtime_env,
        "scope": scope,
        "runtime_root": runtime_root_path.as_posix(),
        "env": normalized_env,
        "env_sha256": expected_sha,
        "semantic_gate": False,
    }


def compare_opencode_runtime_env(
    actual: dict[str, Any],
    expected: dict[str, Any],
    label: str,
    *,
    expected_label: str,
) -> None:
    if actual != expected:
        raise ValueError(f"{label}.opencode_runtime_env must match {expected_label}.opencode_runtime_env")


def compare_opencode_launch_policy(
    actual: dict[str, Any],
    expected: dict[str, Any],
    label: str,
    *,
    expected_label: str = "opencode_agent_runtime.opencode_preflight_report",
) -> None:
    comparable_fields = (
        "opencode_command",
        "opencode_model",
        "opencode_agent",
        "opencode_variant",
        "opencode_skip_permissions",
    )
    actual_policy = {field: actual.get(field) for field in comparable_fields}
    expected_policy = {field: expected.get(field) for field in comparable_fields}
    if actual_policy != expected_policy:
        raise ValueError(f"{label}.launch_policy must match {expected_label}")


def opencode_command_argv_matches(command_arg: Any, expected_command: str) -> bool:
    if not isinstance(command_arg, str) or not command_arg:
        return False
    if command_arg == expected_command:
        return True
    command_name = command_arg.replace("\\", "/").rsplit("/", 1)[-1]
    command_stem = command_name.rsplit(".", 1)[0]
    expected = expected_command.casefold()
    return command_name.casefold() == expected or command_stem.casefold() == expected


def opencode_models_argv_matches(value: Any, *, expected_command: str) -> bool:
    if not isinstance(value, list) or len(value) != 2:
        return False
    return value == [expected_command, "models"]


def require_string_argv(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{label} must be a non-empty string list")
    for argument in value:
        assert_no_local_absolute_path(argument)
    return value


def validate_opencode_run_argv_binding(value: Any, label: str, *, launch_policy: dict[str, Any]) -> list[str]:
    argv = require_string_argv(value, label)
    if len(argv) < 3 or not opencode_command_argv_matches(argv[0], launch_policy["opencode_command"]) or argv[1] != "run":
        raise ValueError(f"{label} must run opencode run")
    flags: dict[str, str] = {}
    bool_flags: set[str] = set()
    prompt: list[str] = []
    index = 2
    while index < len(argv):
        item = argv[index]
        if not item.startswith("--"):
            prompt = argv[index:]
            break
        if item == "--dangerously-skip-permissions":
            if item in bool_flags:
                raise ValueError(f"{label} duplicate {item}")
            bool_flags.add(item)
            index += 1
            continue
        if item in flags:
            raise ValueError(f"{label} duplicate {item}")
        if index + 1 >= len(argv) or argv[index + 1].startswith("--"):
            raise ValueError(f"{label} {item} must have a value")
        flags[item] = argv[index + 1]
        index += 2
    if len(prompt) != 1 or not prompt[0].strip():
        raise ValueError(f"{label} prompt must be the final non-empty argv item")
    required_flags = {
        "--dir",
        "--format",
        "--variant",
        "--model",
    }
    missing = sorted(required_flags - flags.keys())
    if missing:
        raise ValueError(f"{label} missing {' '.join(missing)}")
    allowed_flags = set(required_flags)
    if launch_policy.get("opencode_agent") is not None:
        allowed_flags.add("--agent")
    unexpected_flags = sorted(set(flags) - allowed_flags)
    if unexpected_flags:
        raise ValueError(f"{label} has unexpected flags: {' '.join(unexpected_flags)}")
    if flags["--dir"] != ".":
        raise ValueError(f"{label} --dir must be portable repo root .")
    if flags["--format"] != "json":
        raise ValueError(f"{label} --format must be json")
    if flags["--variant"] != launch_policy["opencode_variant"]:
        raise ValueError(f"{label} --variant must be {launch_policy['opencode_variant']}")
    if flags["--model"] != launch_policy["opencode_model"]:
        raise ValueError(f"{label} --model must be {launch_policy['opencode_model']}")
    expected_agent = launch_policy.get("opencode_agent")
    if expected_agent is None and "--agent" in flags:
        raise ValueError(f"{label} --agent must be absent")
    if expected_agent is not None and flags.get("--agent") != expected_agent:
        raise ValueError(f"{label} --agent must be {expected_agent}")
    skip_permissions_present = "--dangerously-skip-permissions" in bool_flags
    if skip_permissions_present != bool(launch_policy.get("opencode_skip_permissions")):
        raise ValueError(f"{label} --dangerously-skip-permissions must match launch_policy")
    return argv


def opencode_model_id_matches_required(model_id: str, required_model: str) -> bool:
    candidate = model_id.strip().strip("`'\"*,")
    if candidate == required_model:
        return True
    if "/" in candidate:
        return candidate.rsplit("/", 1)[1] == required_model
    return False


def opencode_models_output_mentions_required_model(stdout: str, required_model: str) -> bool:
    for line in stdout.splitlines():
        for token in re.split(r"\s+", line.strip()):
            if token and opencode_model_id_matches_required(token, required_model):
                return True
    return False


def shell_command_line(argv: list[Any]) -> str:
    return shlex.join([str(item) for item in argv])


def normalize_command_for_contract(command: str) -> str:
    return " ".join(command.strip().split())


def shell_argv_for_contract(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return []


def command_matches_for_contract(observed_command: str, expected_command: str) -> bool:
    if normalize_command_for_contract(observed_command) == normalize_command_for_contract(expected_command):
        return True
    observed_argv = shell_argv_for_contract(observed_command)
    expected_argv = shell_argv_for_contract(expected_command)
    return bool(observed_argv) and observed_argv == expected_argv


def opencode_session_events(session_evidence: dict[str, Any]) -> list[Any]:
    events = session_evidence.get("session_events")
    if isinstance(events, list):
        return events
    session = session_evidence.get("session")
    if isinstance(session, list):
        return session
    if isinstance(session, dict):
        if "part" in session or "type" in session:
            return [session]
        events = session.get("events")
        if isinstance(events, list):
            return events
    return []


def extract_opencode_tool_trace(session_evidence: dict[str, Any]) -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    for event in opencode_session_events(session_evidence):
        if not isinstance(event, dict):
            continue
        part = event.get("part")
        if not isinstance(part, dict):
            continue
        tool = str(part.get("tool", "")).lower().strip()
        if not tool:
            continue
        command = ""
        workdir = ""
        state = part.get("state")
        if isinstance(state, dict):
            tool_input = state.get("input")
            if isinstance(tool_input, dict):
                raw_command = tool_input.get("command") or tool_input.get("cmd")
                if isinstance(raw_command, str):
                    command = raw_command.strip()
                raw_workdir = tool_input.get("workdir") or tool_input.get("cwd")
                if isinstance(raw_workdir, str):
                    workdir = raw_workdir.strip()
        tools.append(
            {
                "tool": tool,
                "command": command,
                "workdir": workdir,
                "is_shell_command": tool in {"bash", "shell", "cmd", "powershell"} and bool(command),
            }
        )
    return tools


def extract_opencode_shell_commands(session_evidence: dict[str, Any]) -> list[str]:
    commands: list[str] = []
    for item in extract_opencode_tool_trace(session_evidence):
        if item.get("is_shell_command") and isinstance(item.get("command"), str):
            commands.append(str(item["command"]))
    return commands


def opencode_workdir_matches_repo_root(workdir: str, *, repo_root: Path) -> bool:
    if not workdir:
        return False
    try:
        return Path(workdir).resolve() == repo_root.resolve()
    except OSError:
        return False


def recompute_opencode_contract_execution(
    *,
    session_evidence: dict[str, Any],
    worker_command: list[Any],
    summary_path: Path,
    repo_root: Path,
) -> dict[str, Any]:
    expected_worker_command_line = shell_command_line(worker_command)
    tool_trace = extract_opencode_tool_trace(session_evidence)
    executed_shell_commands = extract_opencode_shell_commands(session_evidence)
    exact_worker_command_seen = any(
        command_matches_for_contract(command, expected_worker_command_line) for command in executed_shell_commands
    )
    first_shell_command = executed_shell_commands[0] if executed_shell_commands else ""
    first_tool_name = str(tool_trace[0]["tool"]) if tool_trace else ""
    first_shell_index = next((index for index, item in enumerate(tool_trace) if item.get("is_shell_command")), None)
    first_shell_tool_name = str(tool_trace[first_shell_index]["tool"]) if first_shell_index is not None else ""
    first_shell_workdir = str(tool_trace[first_shell_index].get("workdir", "")) if first_shell_index is not None else ""
    tools_before_first_shell = (
        [str(item["tool"]) for item in tool_trace[:first_shell_index]]
        if first_shell_index is not None
        else [str(item["tool"]) for item in tool_trace[:20]]
    )
    first_shell_command_matches_worker_command = (
        bool(first_shell_command) and command_matches_for_contract(first_shell_command, expected_worker_command_line)
    )
    workdir_matches_repo_root = opencode_workdir_matches_repo_root(first_shell_workdir, repo_root=repo_root)
    status = "not-observed"
    if executed_shell_commands:
        status = (
            "executed"
            if (
                first_shell_command_matches_worker_command
                and workdir_matches_repo_root
                and not tools_before_first_shell
                and len(executed_shell_commands) == 1
            )
            else "not-executed"
        )
    contract_failure_reason = ""
    if status == "not-observed":
        contract_failure_reason = "no_shell_command_observed"
    elif status == "not-executed":
        if tools_before_first_shell:
            contract_failure_reason = "tool_before_first_shell_command"
        elif not workdir_matches_repo_root:
            contract_failure_reason = "opencode_workdir_mismatch"
        elif len(executed_shell_commands) > 1 and first_shell_command_matches_worker_command:
            contract_failure_reason = "extra_shell_command_after_contract"
        else:
            contract_failure_reason = (
                "first_shell_command_mismatch_worker_command_seen_later"
                if exact_worker_command_seen
                else "first_shell_command_mismatch"
            )
    return {
        "expected_worker_command_line": expected_worker_command_line,
        "expected_summary_path": repo_relative(summary_path, repo_root),
        "expected_worker_command_sha256": sha256_text(expected_worker_command_line),
        "executed_shell_command_count": len(executed_shell_commands),
        "executed_shell_commands": executed_shell_commands[:20],
        "first_tool_name": first_tool_name,
        "first_shell_command": first_shell_command,
        "first_shell_tool_name": first_shell_tool_name,
        "first_shell_workdir_status": "repo_root" if workdir_matches_repo_root else "non_repo_root",
        "expected_workdir_status": "repo_root",
        "first_shell_command_matches_worker_command": first_shell_command_matches_worker_command,
        "first_shell_workdir_matches_repo_root": workdir_matches_repo_root,
        "tools_before_first_shell": tools_before_first_shell[:20],
        "contract_failure_reason": contract_failure_reason,
        "worker_command_seen": exact_worker_command_seen,
        "summary_exists": summary_path.exists(),
        "status": status,
    }
