def validate_opencode_contract_recomputed_from_session(
    *,
    embedded_verification: dict[str, Any],
    session_evidence: dict[str, Any],
    worker_command: list[Any],
    summary_path: Path,
    label: str,
    repo_root: Path,
    verification_field: str = "contract_verification",
) -> dict[str, Any]:
    recomputed = recompute_opencode_contract_execution(
        session_evidence=session_evidence,
        worker_command=worker_command,
        summary_path=summary_path,
        repo_root=repo_root,
    )
    reason = recomputed.get("contract_failure_reason") or recomputed.get("status")
    if recomputed.get("status") != "executed":
        raise ValueError(
            f"{label}.{verification_field}.status recomputed from opencode_session_evidence "
            f"must be executed: {reason}"
        )
    for field in (
        "expected_worker_command_line",
        "expected_summary_path",
        "expected_worker_command_sha256",
        "executed_shell_command_count",
        "executed_shell_commands",
        "first_tool_name",
        "first_shell_command",
        "first_shell_tool_name",
        "first_shell_workdir_status",
        "expected_workdir_status",
        "first_shell_command_matches_worker_command",
        "first_shell_workdir_matches_repo_root",
        "tools_before_first_shell",
        "contract_failure_reason",
        "worker_command_seen",
        "summary_exists",
        "status",
    ):
        if field in embedded_verification and embedded_verification.get(field) != recomputed.get(field):
            raise ValueError(
                f"{label}.{verification_field}.{field} must match recomputed opencode_session_evidence"
            )
    if recomputed.get("first_shell_workdir_matches_repo_root") is not True:
        raise ValueError(f"{label}.{verification_field}.first_shell_workdir_matches_repo_root must be true")
    if recomputed.get("expected_workdir_status") != "repo_root":
        raise ValueError(f"{label}.{verification_field}.expected_workdir_status must be repo_root")
    if recomputed.get("contract_failure_reason") != "":
        raise ValueError(f"{label}.{verification_field}.contract_failure_reason must be empty")
    for command in recomputed.get("executed_shell_commands", []):
        assert_no_local_absolute_path(command)
    return recomputed


def parse_opencode_stdout_session_for_contract(stdout: str) -> dict[str, Any]:
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError as error:
        events = []
        jsonl_error = None
        for line in stdout.splitlines():
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as line_error:
                jsonl_error = line_error
                break
        if events and jsonl_error is None:
            return {
                "parsed": True,
                "format": "jsonl",
                "session_events": events,
            }
        return {
            "parsed": False,
            "parse_error": str(jsonl_error or error),
            "raw_output": stdout[:20000],
        }
    return {
        "parsed": True,
        "format": "json",
        "session": parsed,
    }


def validate_opencode_session_raw_log_binding(
    session_evidence: dict[str, Any],
    label: str,
    *,
    repo_root: Path,
) -> None:
    for stream in ("stdout", "stderr"):
        stream_path_text = require_string(session_evidence.get(f"{stream}_path"), f"{label}.{stream}_path")
        expected_sha256 = validate_sha256_hex(
            session_evidence.get(f"{stream}_sha256"),
            f"{label}.{stream}_sha256",
        )
        stream_path = repo_path(stream_path_text, repo_root=repo_root)
        if not stream_path.is_file():
            raise ValueError(f"{label}.{stream}_path must exist")
        if sha256_file(stream_path) != expected_sha256:
            raise ValueError(f"{label}.{stream}_sha256 must match {stream}_path")

    stdout_path = repo_path(require_string(session_evidence.get("stdout_path"), f"{label}.stdout_path"), repo_root=repo_root)
    parsed_stdout = parse_opencode_stdout_session_for_contract(stdout_path.read_text(encoding="utf-8"))
    for field in ("format", "parsed"):
        if parsed_stdout.get(field) != session_evidence.get(field):
            raise ValueError(f"{label}.{field} must match parsed stdout")
    if parsed_stdout.get("session_events") != session_evidence.get("session_events"):
        raise ValueError(f"{label}.session_events must match parsed stdout")


def validate_opencode_session_evidence_contract(
    session_evidence: dict[str, Any],
    label: str,
    *,
    repo_root: Path | None = None,
) -> None:
    if session_evidence.get("format") != "jsonl":
        raise ValueError(f"{label}.format must be jsonl")
    if session_evidence.get("parsed") is not True:
        raise ValueError(f"{label}.parsed must be true")
    returncode = session_evidence.get("process_returncode")
    if not isinstance(returncode, int) or isinstance(returncode, bool) or returncode != 0:
        raise ValueError(f"{label}.process_returncode must be 0")
    if repo_root is not None:
        validate_opencode_session_raw_log_binding(session_evidence, label, repo_root=repo_root)


def validate_hash_bound_artifact_binding(
    value: Any,
    label: str,
    *,
    repo_root: Path,
) -> dict[str, str]:
    try:
        return validate_artifact_binding_shape(value, label, repo_root=repo_root)
    except ValueError as error:
        if "sha256 mismatch" in str(error):
            raise ValueError(f"{label} sha256 mismatch") from error
        raise


def validate_opencode_model_probe_log_hashes(
    availability: dict[str, Any],
    label: str,
    *,
    repo_root: Path,
) -> None:
    logs = require_object(availability.get("logs"), f"{label}.opencode_model_availability.logs")
    for stream in ("stdout", "stderr"):
        log_path_text = require_string(logs.get(stream), f"{label}.opencode_model_availability.logs.{stream}")
        expected_sha256 = validate_sha256_hex(
            availability.get(f"{stream}_sha256"),
            f"{label}.opencode_model_availability.{stream}_sha256",
        )
        log_path = repo_path(log_path_text, repo_root=repo_root)
        if not log_path.is_file():
            raise ValueError(f"{label}.opencode_model_availability.logs.{stream} must exist")
        log_text = log_path.read_text(encoding="utf-8")
        actual_sha256 = sha256_text(log_text)
        if actual_sha256 != expected_sha256:
            raise ValueError(f"{label}.opencode_model_availability.logs.{stream} sha256 mismatch")
        if stream == "stdout" and not opencode_models_output_mentions_required_model(
            log_text,
            COMPETITION_OPENCODE_MODEL,
        ):
            raise ValueError(
                f"{label}.opencode_model_availability.logs.stdout must list {COMPETITION_OPENCODE_MODEL}"
            )


def validate_opencode_preflight_binding(
    value: Any,
    label: str,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    binding = require_object(value, label)
    result = validate_artifact_binding_shape(binding, label, repo_root=repo_root)
    if binding.get("status") != "passed":
        raise ValueError(f"{label}.status must be passed")
    if binding.get("contract_status") != "executed":
        raise ValueError(f"{label}.contract_status must be executed")
    launch_policy = validate_opencode_launch_policy_binding(
        binding.get("launch_policy"),
        binding.get("launch_policy_sha256"),
        label,
    )
    result.update(
        {
            "status": "passed",
            "contract_status": "executed",
            "launch_policy": launch_policy,
            "launch_policy_sha256": sha256_text(json.dumps(launch_policy, sort_keys=True)),
        }
    )
    if "run_id" in binding:
        result["run_id"] = require_string(binding.get("run_id"), f"{label}.run_id")
    if repo_root is not None:
        preflight_payload = load_json(repo_path(result["path"], repo_root=repo_root))
        if preflight_payload.get("status") != "passed":
            raise ValueError(f"{label} file status must be passed")
        if preflight_payload.get("opencode_run_launched") is not True:
            raise ValueError(f"{label} file opencode_run_launched must be true")
        process_returncode = preflight_payload.get("process_returncode")
        if not isinstance(process_returncode, int) or process_returncode != 0:
            raise ValueError(f"{label} file process_returncode must be 0")
        if preflight_payload.get("marker_exists") is not True:
            raise ValueError(f"{label} file marker_exists must be true")
        preflight_runtime_env = validate_opencode_runtime_env_contract(
            preflight_payload.get("opencode_runtime_env"),
            label,
        )
        if "run_id" in preflight_payload:
            file_run_id = require_string(preflight_payload.get("run_id"), f"{label} file.run_id")
            if "run_id" in result and file_run_id != result["run_id"]:
                raise ValueError(f"{label} file.run_id must match binding run_id")
            result["run_id"] = file_run_id
        payload_policy = validate_opencode_launch_policy_binding(
            preflight_payload.get("launch_policy"),
            preflight_payload.get("launch_policy_sha256"),
            f"{label} file",
        )
        if payload_policy != launch_policy:
            raise ValueError(f"{label} file launch_policy must match binding")
        verification = require_object(preflight_payload.get("contract_verification"), f"{label}.contract_verification")
        if verification.get("status") != "executed":
            raise ValueError(f"{label}.contract_verification.status must be executed")
        for field in ("first_shell_command_matches_worker_command", "worker_command_seen", "summary_exists"):
            if verification.get(field) is not True:
                raise ValueError(f"{label}.contract_verification.{field} must be true")
        if verification.get("tools_before_first_shell") != []:
            raise ValueError(f"{label}.contract_verification.tools_before_first_shell must be []")
        handoff_binding = validate_hash_bound_artifact_binding(
            preflight_payload.get("handoff_contract"),
            f"{label}.handoff_contract",
            repo_root=repo_root,
        )
        handoff_payload = require_object(
            load_json(repo_path(handoff_binding["path"], repo_root=repo_root)),
            f"{label}.handoff_contract file",
        )
        if handoff_payload.get("runner_kind") != "opencode-preflight":
            raise ValueError(f"{label}.handoff_contract.runner_kind must be opencode-preflight")
        if handoff_payload.get("run_id") != result.get("run_id"):
            raise ValueError(f"{label}.handoff_contract.run_id must match preflight run_id")
        handoff_runtime_env = validate_opencode_runtime_env_contract(
            handoff_payload.get("opencode_runtime_env"),
            f"{label}.handoff_contract",
        )
        compare_opencode_runtime_env(
            handoff_runtime_env,
            preflight_runtime_env,
            f"{label}.handoff_contract",
            expected_label=label,
        )
        handoff_policy = validate_opencode_launch_policy_binding(
            handoff_payload.get("launch_policy"),
            handoff_payload.get("launch_policy_sha256"),
            f"{label}.handoff_contract",
        )
        if handoff_policy != launch_policy:
            raise ValueError(f"{label}.handoff_contract.launch_policy must match preflight launch_policy")
        worker_command = handoff_payload.get("worker_command")
        if not isinstance(worker_command, list) or not worker_command or not all(
            isinstance(item, str) and item for item in worker_command
        ):
            raise ValueError(f"{label}.handoff_contract.worker_command must be a non-empty string list")
        worker_command_line = require_string(
            handoff_payload.get("worker_command_line"),
            f"{label}.handoff_contract.worker_command_line",
        )
        if worker_command_line != shell_command_line(worker_command):
            raise ValueError(f"{label}.handoff_contract.worker_command_line must match worker_command")
        worker_command_sha256 = validate_sha256_hex(
            handoff_payload.get("worker_command_sha256"),
            f"{label}.handoff_contract.worker_command_sha256",
        )
        if worker_command_sha256 != sha256_text(worker_command_line):
            raise ValueError(f"{label}.handoff_contract.worker_command_sha256 must match worker_command_line")
        report_argv = require_string_argv(preflight_payload.get("argv"), f"{label}.argv")
        handoff_argv = require_string_argv(
            handoff_payload.get("opencode_argv"),
            f"{label}.handoff_contract.opencode_argv",
        )
        if report_argv != handoff_argv:
            raise ValueError(f"{label}.argv must match handoff_contract.opencode_argv")
        validate_opencode_run_argv_binding(report_argv, f"{label}.argv", launch_policy=launch_policy)
        handoff_command_line = require_string(
            handoff_payload.get("opencode_command_line"),
            f"{label}.handoff_contract.opencode_command_line",
        )
        if handoff_command_line != shell_command_line(handoff_argv):
            raise ValueError(f"{label}.handoff_contract.opencode_command_line must match opencode_argv")
        handoff_prompt = require_string(handoff_payload.get("prompt"), f"{label}.handoff_contract.prompt")
        if handoff_prompt != handoff_argv[-1]:
            raise ValueError(f"{label}.handoff_contract.prompt must match opencode_argv prompt")
        expected_marker_path = require_string(
            handoff_payload.get("expected_marker_path"),
            f"{label}.handoff_contract.expected_marker_path",
        )
        marker_path_text = require_string(preflight_payload.get("marker_path"), f"{label}.marker_path")
        if marker_path_text != expected_marker_path:
            raise ValueError(f"{label}.marker_path must match handoff_contract.expected_marker_path")
        marker_path = repo_path(marker_path_text, repo_root=repo_root)
        if not marker_path.is_file():
            raise ValueError(f"{label}.marker_path must exist")
        marker_binding = validate_hash_bound_artifact_binding(
            preflight_payload.get("marker"),
            f"{label}.marker",
            repo_root=repo_root,
        )
        if marker_binding["path"] != marker_path_text:
            raise ValueError(f"{label}.marker.path must match marker_path")
        marker_payload = require_object(load_json(marker_path), f"{label}.marker file")
        if marker_payload.get("report_kind") != "opencode-preflight-marker":
            raise ValueError(f"{label}.marker.report_kind must be opencode-preflight-marker")
        if marker_payload.get("run_id") != result.get("run_id"):
            raise ValueError(f"{label}.marker.run_id must match preflight run_id")
        if marker_payload.get("status") != "written":
            raise ValueError(f"{label}.marker.status must be written")
        session_binding = validate_hash_bound_artifact_binding(
            preflight_payload.get("opencode_session_evidence"),
            f"{label}.opencode_session_evidence",
            repo_root=repo_root,
        )
        session_evidence = require_object(
            load_json(repo_path(session_binding["path"], repo_root=repo_root)),
            f"{label}.opencode_session_evidence file",
        )
        validate_opencode_session_evidence_contract(
            session_evidence,
            f"{label}.opencode_session_evidence",
            repo_root=repo_root,
        )
        session_runtime_env = validate_opencode_runtime_env_contract(
            session_evidence.get("opencode_runtime_env"),
            f"{label}.opencode_session_evidence",
        )
        compare_opencode_runtime_env(
            session_runtime_env,
            preflight_runtime_env,
            f"{label}.opencode_session_evidence",
            expected_label=label,
        )
        validate_opencode_contract_recomputed_from_session(
            embedded_verification=verification,
            session_evidence=session_evidence,
            worker_command=worker_command,
            summary_path=marker_path,
            label=label,
            repo_root=repo_root,
        )
        availability = require_object(
            preflight_payload.get("opencode_model_availability"),
            f"{label}.opencode_model_availability is required",
        )
        if availability.get("status") != "available":
            raise ValueError(f"{label}.opencode_model_availability.status must be available")
        if availability.get("model_listed") is not True:
            raise ValueError(f"{label}.opencode_model_availability.model_listed must be true")
        if availability.get("required_model") != COMPETITION_OPENCODE_MODEL:
            raise ValueError(
                f"{label}.opencode_model_availability.required_model must be {COMPETITION_OPENCODE_MODEL}"
            )
        if availability.get("opencode_command") != COMPETITION_OPENCODE_COMMAND:
            raise ValueError(
                f"{label}.opencode_model_availability.opencode_command must be {COMPETITION_OPENCODE_COMMAND}"
            )
        if int(availability.get("process_returncode", -1)) != 0:
            raise ValueError(f"{label}.opencode_model_availability.process_returncode must be 0")
        if not opencode_models_argv_matches(
            availability.get("argv"),
            expected_command=launch_policy["opencode_command"],
        ):
            raise ValueError(f"{label}.opencode_model_availability.argv must be opencode models")
        validate_opencode_model_probe_log_hashes(availability, label, repo_root=repo_root)
        result["opencode_runtime_env"] = preflight_runtime_env
    return result


def validate_opencode_worker_runtime(
    value: Any,
    *,
    index: int,
    expected_preflight: dict[str, Any],
    repo_root: Path | None = None,
) -> dict[str, Any]:
    label = f"opencode_agent_runtime.workers[{index}]"
    worker = require_object(value, label)
    worker_id = require_string(worker.get("worker_id"), f"{label}.worker_id")
    if worker.get("chat_output_is_evidence") is not False:
        raise ValueError(f"{label}.chat_output_is_evidence must be false")
    if worker.get("semantic_gate") is not False:
        raise ValueError(f"{label}.semantic_gate must be false")
    if worker.get("contract_verification_status") != "executed":
        raise ValueError(f"{label}.contract_verification_status must be executed")

    bindings = {
        "summary": validate_artifact_binding_shape(worker.get("summary"), f"{label}.summary", repo_root=repo_root),
        "worker_report": validate_artifact_binding_shape(
            worker.get("worker_report"),
            f"{label}.worker_report",
            repo_root=repo_root,
        ),
        "handoff_contract": validate_artifact_binding_shape(
            worker.get("handoff_contract"),
            f"{label}.handoff_contract",
            repo_root=repo_root,
        ),
        "opencode_session_evidence": validate_artifact_binding_shape(
            worker.get("opencode_session_evidence"),
            f"{label}.opencode_session_evidence",
            repo_root=repo_root,
        ),
    }
    logs = require_object(worker.get("logs"), f"{label}.logs")
    bindings["logs_stdout"] = validate_artifact_binding_shape(logs.get("stdout"), f"{label}.logs.stdout", repo_root=repo_root)
    bindings["logs_stderr"] = validate_artifact_binding_shape(logs.get("stderr"), f"{label}.logs.stderr", repo_root=repo_root)
    if worker.get("opencode_safety_transform_attempt") is not None:
        bindings["opencode_safety_transform_attempt"] = validate_artifact_binding_shape(
            worker.get("opencode_safety_transform_attempt"),
            f"{label}.opencode_safety_transform_attempt",
            repo_root=repo_root,
        )
    worker_preflight = validate_opencode_preflight_binding(
        worker.get("opencode_preflight_report"),
        f"{label}.opencode_preflight_report",
        repo_root=repo_root,
    )
    if worker_preflight["path"] != expected_preflight["path"] or worker_preflight["sha256"] != expected_preflight["sha256"]:
        raise ValueError(f"{label}.opencode_preflight_report must match opencode_agent_runtime.opencode_preflight_report")
    compare_opencode_launch_policy(worker_preflight["launch_policy"], expected_preflight["launch_policy"], f"{label}.opencode_preflight_report")
    if worker_preflight.get("run_id") != expected_preflight.get("run_id"):
        raise ValueError(f"{label}.opencode_preflight_report.run_id must match opencode_agent_runtime.opencode_preflight_report")

    verification = require_object(worker.get("opencode_contract_verification"), f"{label}.opencode_contract_verification")
    if verification.get("status") != "executed":
        raise ValueError(f"{label}.opencode_contract_verification.status must be executed")
    for field in ("first_shell_command_matches_worker_command", "worker_command_seen", "summary_exists"):
        if verification.get(field) is not True:
            raise ValueError(f"{label}.opencode_contract_verification.{field} must be true")
    if verification.get("tools_before_first_shell") != []:
        raise ValueError(f"{label}.opencode_contract_verification.tools_before_first_shell must be []")
    command_count = verification.get("executed_shell_command_count")
    if not isinstance(command_count, int) or command_count < 1:
        raise ValueError(f"{label}.opencode_contract_verification.executed_shell_command_count must be >= 1")
    executed_commands = verification.get("executed_shell_commands")
    if not isinstance(executed_commands, list) or not executed_commands or not all(isinstance(item, str) for item in executed_commands):
        raise ValueError(f"{label}.opencode_contract_verification.executed_shell_commands must be a non-empty string list")
    for command in executed_commands:
        assert_no_local_absolute_path(command)

    recomputed_contract = None
    summary_final_gate_status = None
    if repo_root is not None:
        worker_report_payload = require_object(
            load_json(repo_path(bindings["worker_report"]["path"], repo_root=repo_root)),
            f"{label}.worker_report file",
        )
        if worker_report_payload.get("report_kind") != "run-worker-report":
            raise ValueError(f"{label}.worker_report.report_kind must be run-worker-report")
        if worker_report_payload.get("worker_id") != worker_id:
            raise ValueError(f"{label}.worker_report.worker_id must match worker_id")
        if worker_report_payload.get("runner_kind") != "opencode-run":
            raise ValueError(f"{label}.worker_report.runner_kind must be opencode-run")
        if worker_report_payload.get("mode") != "opencode":
            raise ValueError(f"{label}.worker_report.mode must be opencode")
        if worker_report_payload.get("recorded") is not True:
            raise ValueError(f"{label}.worker_report.recorded must be true")
        for field in ("exit_code", "process_returncode"):
            value = worker_report_payload.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value != 0:
                raise ValueError(f"{label}.worker_report.{field} must be 0")
        worker_runtime_env = validate_opencode_runtime_env_contract(
            worker_report_payload.get("opencode_runtime_env"),
            f"{label}.worker_report",
        )
        report_summary_path = require_string(
            worker_report_payload.get("summary_path"),
            f"{label}.worker_report.summary_path",
        )
        if report_summary_path != bindings["summary"]["path"]:
            raise ValueError(f"{label}.worker_report.summary_path must match summary.path")
        summary_path = repo_path(bindings["summary"]["path"], repo_root=repo_root)
        try:
            validate_competition_run_summary.validate_summary(summary_path, repo_root=repo_root)
        except SystemExit as error:
            raise ValueError(f"{label}.summary must satisfy competition run summary contract: {error}") from error
        summary_payload = require_object(
            load_json(summary_path),
            f"{label}.summary file",
        )
        summary_final_gate = (
            summary_payload.get("final_gate") if isinstance(summary_payload.get("final_gate"), dict) else {}
        )
        summary_final_gate_status = str(summary_final_gate.get("status", "failed"))
        report_summary_status = require_string(
            worker_report_payload.get("summary_status"),
            f"{label}.worker_report.summary_status",
        )
        if report_summary_status != summary_final_gate_status:
            raise ValueError(f"{label}.worker_report.summary_status must match summary final_gate.status")
        if "opencode_safety_transform_attempt" in bindings:
            report_attempt = validate_artifact_binding_shape(
                worker_report_payload.get("opencode_safety_transform_attempt"),
                f"{label}.worker_report.opencode_safety_transform_attempt",
                repo_root=repo_root,
            )
            if report_attempt != bindings["opencode_safety_transform_attempt"]:
                raise ValueError(
                    f"{label}.worker_report.opencode_safety_transform_attempt "
                    "must match opencode_safety_transform_attempt"
                )
        handoff_payload = require_object(
            load_json(repo_path(bindings["handoff_contract"]["path"], repo_root=repo_root)),
            f"{label}.handoff_contract file",
        )
        if handoff_payload.get("runner_kind") != "opencode-run":
            raise ValueError(f"{label}.handoff_contract.runner_kind must be opencode-run")
        if handoff_payload.get("worker_id") != worker_id:
            raise ValueError(f"{label}.handoff_contract.worker_id must match worker_id")
        if "run_id" in expected_preflight and handoff_payload.get("run_id") != expected_preflight.get("run_id"):
            raise ValueError(f"{label}.handoff_contract.run_id must match opencode_preflight_report.run_id")
        handoff_policy = validate_opencode_launch_policy_binding(
            handoff_payload.get("launch_policy"),
            handoff_payload.get("launch_policy_sha256"),
            f"{label}.handoff_contract",
        )
        compare_opencode_launch_policy(
            handoff_policy,
            expected_preflight["launch_policy"],
            f"{label}.handoff_contract",
            expected_label="opencode_preflight_report",
        )
        handoff_runtime_env = validate_opencode_runtime_env_contract(
            handoff_payload.get("opencode_runtime_env"),
            f"{label}.handoff_contract",
        )
        compare_opencode_runtime_env(
            handoff_runtime_env,
            worker_runtime_env,
            f"{label}.handoff_contract",
            expected_label=f"{label}.worker_report",
        )
        worker_command = handoff_payload.get("worker_command")
        if not isinstance(worker_command, list) or not worker_command or not all(
            isinstance(item, str) and item for item in worker_command
        ):
            raise ValueError(f"{label}.handoff_contract.worker_command must be a non-empty string list")
        worker_command_line = require_string(
            handoff_payload.get("worker_command_line"),
            f"{label}.handoff_contract.worker_command_line",
        )
        if worker_command_line != shell_command_line(worker_command):
            raise ValueError(f"{label}.handoff_contract.worker_command_line must match worker_command")
        worker_command_sha256 = validate_sha256_hex(
            handoff_payload.get("worker_command_sha256"),
            f"{label}.handoff_contract.worker_command_sha256",
        )
        if worker_command_sha256 != sha256_text(worker_command_line):
            raise ValueError(f"{label}.handoff_contract.worker_command_sha256 must match worker_command_line")
        expected_summary_path = require_string(
            handoff_payload.get("expected_summary_path"),
            f"{label}.handoff_contract.expected_summary_path",
        )
        if expected_summary_path != bindings["summary"]["path"]:
            raise ValueError(f"{label}.handoff_contract.expected_summary_path must match summary.path")
        opencode_argv = validate_opencode_run_argv_binding(
            handoff_payload.get("opencode_argv"),
            f"{label}.handoff_contract.opencode_argv",
            launch_policy=handoff_policy,
        )
        opencode_command_line = require_string(
            handoff_payload.get("opencode_command_line"),
            f"{label}.handoff_contract.opencode_command_line",
        )
        if opencode_command_line != shell_command_line(opencode_argv):
            raise ValueError(f"{label}.handoff_contract.opencode_command_line must match opencode_argv")
        handoff_prompt = require_string(handoff_payload.get("prompt"), f"{label}.handoff_contract.prompt")
        if handoff_prompt != opencode_argv[-1]:
            raise ValueError(f"{label}.handoff_contract.prompt must match opencode_argv prompt")
        session_evidence = require_object(
            load_json(repo_path(bindings["opencode_session_evidence"]["path"], repo_root=repo_root)),
            f"{label}.opencode_session_evidence file",
        )
        validate_opencode_session_evidence_contract(
            session_evidence,
            f"{label}.opencode_session_evidence",
            repo_root=repo_root,
        )
        session_runtime_env = validate_opencode_runtime_env_contract(
            session_evidence.get("opencode_runtime_env"),
            f"{label}.opencode_session_evidence",
        )
        compare_opencode_runtime_env(
            session_runtime_env,
            worker_runtime_env,
            f"{label}.opencode_session_evidence",
            expected_label=f"{label}.worker_report",
        )
        recomputed_contract = validate_opencode_contract_recomputed_from_session(
            embedded_verification=verification,
            session_evidence=session_evidence,
            worker_command=worker_command,
            summary_path=repo_path(expected_summary_path, repo_root=repo_root),
            label=label,
            repo_root=repo_root,
            verification_field="opencode_contract_verification",
        )

    return {
        "worker_id": worker_id,
        "status": "passed",
        "contract_verification_status": "executed",
        "bindings": bindings,
        "recomputed_contract": recomputed_contract,
        "summary_final_gate_status": summary_final_gate_status,
        "opencode_runtime_env": worker_runtime_env if repo_root is not None else None,
    }


def validate_opencode_agent_runtime_contract(
    value: Any,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    runtime = require_object(value, "opencode_agent_runtime")
    if runtime.get("runtime") != "opencode":
        raise ValueError("opencode_agent_runtime.runtime must be opencode")
    if runtime.get("chat_output_is_evidence") is not False:
        raise ValueError("opencode_agent_runtime.chat_output_is_evidence must be false")
    if runtime.get("semantic_gate") is not False:
        raise ValueError("opencode_agent_runtime.semantic_gate must be false")
    workers = runtime.get("workers")
    if not isinstance(workers, list) or not workers:
        raise ValueError("opencode_agent_runtime.workers must be a non-empty list")
    worker_count = runtime.get("worker_count")
    if not isinstance(worker_count, int) or worker_count != len(workers):
        raise ValueError("opencode_agent_runtime.worker_count must match workers length")
    preflight = validate_opencode_preflight_binding(
        runtime.get("opencode_preflight_report"),
        "opencode_agent_runtime.opencode_preflight_report",
        repo_root=repo_root,
    )
    if runtime.get("all_contracts_executed") is not True:
        raise ValueError("opencode_agent_runtime.all_contracts_executed must be true")
    if runtime.get("failed_or_missing_contract_workers") != []:
        raise ValueError("opencode_agent_runtime.failed_or_missing_contract_workers must be []")
    counts = require_object(runtime.get("contract_status_counts"), "opencode_agent_runtime.contract_status_counts")
    if counts != {"executed": worker_count}:
        raise ValueError("opencode_agent_runtime.contract_status_counts must equal {'executed': worker_count}")

    worker_results = [
        validate_opencode_worker_runtime(worker, index=index, expected_preflight=preflight, repo_root=repo_root)
        for index, worker in enumerate(workers)
    ]
    worker_ids = [worker["worker_id"] for worker in worker_results]
    if len(set(worker_ids)) != len(worker_ids):
        raise ValueError("opencode_agent_runtime.workers worker_id values must be unique")
    return {
        "status": "passed",
        "runtime": "opencode",
        "worker_count": worker_count,
        "contract_status_counts": {"executed": worker_count},
        "opencode_preflight_report": preflight,
        "worker_ids": worker_ids,
        "worker_summary_final_gate_statuses": {
            worker["worker_id"]: worker.get("summary_final_gate_status") for worker in worker_results
        },
    }


def validate_hostless_rehearsal_bound_report(
    payload: dict[str, Any],
    field: str,
    *,
    expected_report_kind: str,
    repo_root: Path,
) -> dict[str, str]:
    label = f"opencode_hostless_rehearsal_report.{field}"
    binding = validate_hash_bound_artifact_binding(payload.get(field), label, repo_root=repo_root)
    report_payload = require_object(load_json(repo_path(binding["path"], repo_root=repo_root)), f"{label} file")
    if report_payload.get("report_kind") != expected_report_kind:
        raise ValueError(f"{label}.report_kind must be {expected_report_kind}")
    return binding


def validate_opencode_hostless_rehearsal_contract(ref: dict[str, Any], *, repo_root: Path) -> dict[str, Any]:
    binding = validate_artifact_binding_shape(ref, "opencode_hostless_rehearsal_report", repo_root=repo_root)
    payload = load_json(repo_path(binding["path"], repo_root=repo_root))
    if payload.get("report_kind") != "opencode-hostless-rehearsal-report":
        raise ValueError("opencode_hostless_rehearsal_report.report_kind must be opencode-hostless-rehearsal-report")
    if payload.get("proof_class") != "local-simulation":
        raise ValueError("opencode_hostless_rehearsal_report.proof_class must be local-simulation")
    if payload.get("mode") != "opencode":
        raise ValueError("opencode_hostless_rehearsal_report.mode must be opencode")
    if payload.get("closes_p0_h9") is not False:
        raise ValueError("opencode_hostless_rehearsal_report.closes_p0_h9 must be false")
    if payload.get("semantic_gate") is not False:
        raise ValueError("opencode_hostless_rehearsal_report.semantic_gate must be false")
    if payload.get("chat_output_is_evidence") is not False:
        raise ValueError("opencode_hostless_rehearsal_report.chat_output_is_evidence must be false")
    if payload.get("generated_draft_semantic_pass") is not False:
        raise ValueError("opencode_hostless_rehearsal_report.generated_draft_semantic_pass must be false")
    if payload.get("translation_coverage_numerator") != 0:
        raise ValueError("opencode_hostless_rehearsal_report.translation_coverage_numerator must be 0")
    require_string(payload.get("rehearsal_runner"), "opencode_hostless_rehearsal_report.rehearsal_runner")

    h9_contract = require_object(payload.get("h9_contract"), "opencode_hostless_rehearsal_report.h9_contract")
    if h9_contract.get("status") != "blocked":
        raise ValueError("opencode_hostless_rehearsal_report.h9_contract.status must be blocked")
    if h9_contract.get("required_agent_tool") != COMPETITION_OPENCODE_COMMAND:
        raise ValueError("opencode_hostless_rehearsal_report.h9_contract.required_agent_tool must be opencode")
    if h9_contract.get("required_agent") != COMPETITION_OPENCODE_AGENT:
        raise ValueError(
            "opencode_hostless_rehearsal_report.h9_contract.required_agent must be c2rust-migrator"
        )
    if h9_contract.get("required_model") != COMPETITION_OPENCODE_MODEL:
        raise ValueError("opencode_hostless_rehearsal_report.h9_contract.required_model must be GLM-5.1")
    if h9_contract.get("required_variant") != COMPETITION_OPENCODE_VARIANT:
        raise ValueError("opencode_hostless_rehearsal_report.h9_contract.required_variant must be max")
    if h9_contract.get("required_proof_class") != "competition-exact":
        raise ValueError("opencode_hostless_rehearsal_report.h9_contract.required_proof_class must be competition-exact")
    if h9_contract.get("local_simulation_closes_p0_h9") is not False:
        raise ValueError(
            "opencode_hostless_rehearsal_report.h9_contract.local_simulation_closes_p0_h9 must be false"
        )

    batch_profile_report = validate_hostless_rehearsal_bound_report(
        payload,
        "batch_profile_report",
        expected_report_kind="batch-profile-report",
        repo_root=repo_root,
    )
    run_plan_report = validate_hostless_rehearsal_bound_report(
        payload,
        "run_plan_report",
        expected_report_kind="run-plan-report",
        repo_root=repo_root,
    )
    context_binding = validate_hash_bound_artifact_binding(
        payload.get("context_pack"),
        "opencode_hostless_rehearsal_report.context_pack",
        repo_root=repo_root,
    )
    agent_binding = validate_hash_bound_artifact_binding(
        payload.get("agent_index"),
        "opencode_hostless_rehearsal_report.agent_index",
        repo_root=repo_root,
    )
    context_payload = require_object(
        load_json(repo_path(context_binding["path"], repo_root=repo_root)),
        "opencode_hostless_rehearsal_report.context_pack file",
    )
    agent_payload = require_object(
        load_json(repo_path(agent_binding["path"], repo_root=repo_root)),
        "opencode_hostless_rehearsal_report.agent_index file",
    )
    context_contract = validate_context_management_contract(
        context_payload,
        path_text=context_binding["path"],
        expected_artifacts={
            "context_pack": context_binding["path"],
            "agent_index": agent_binding["path"],
            "batch_profile_report": batch_profile_report["path"],
            "run_plan_report": run_plan_report["path"],
        },
        repo_root=repo_root,
    )
    agent_contract = validate_agent_coordination_contract(agent_payload, path_text=agent_binding["path"])
    context_agent_consistency = validate_context_agent_index_consistency(context_payload, agent_payload)
    top_level_preflight = validate_opencode_preflight_binding(
        payload.get("opencode_preflight_report"),
        "opencode_hostless_rehearsal_report.opencode_preflight_report",
        repo_root=repo_root,
    )
    runtime = require_object(payload.get("opencode_runtime"), "opencode_hostless_rehearsal_report.opencode_runtime")
    runtime_result = validate_opencode_agent_runtime_contract(runtime, repo_root=repo_root)
    compare_artifact_binding(
        runtime_result["opencode_preflight_report"],
        top_level_preflight,
        "opencode_hostless_rehearsal_report.opencode_runtime.opencode_preflight_report",
    )
    worker_count = runtime_result["worker_count"]

    workers = payload.get("workers")
    if not isinstance(workers, list) or len(workers) != worker_count:
        raise ValueError("opencode_hostless_rehearsal_report.workers length must match worker_count")
    runtime_workers = runtime.get("workers")
    runtime_workers_by_id = entries_by_worker_id(runtime_workers, label="opencode_hostless_rehearsal_report.opencode_runtime.workers")
    worker_ids = []
    for index, worker_value in enumerate(workers):
        worker = require_object(worker_value, f"opencode_hostless_rehearsal_report.workers[{index}]")
        worker_id = require_string(worker.get("worker_id"), f"opencode_hostless_rehearsal_report.workers[{index}].worker_id")
        worker_ids.append(worker_id)
        runtime_worker = runtime_workers_by_id.get(worker_id)
        if runtime_worker is None:
            raise ValueError(f"opencode_hostless_rehearsal_report.workers[{index}].worker_id must exist in opencode_runtime.workers")
        if worker.get("semantic_gate") is not False:
            raise ValueError(f"opencode_hostless_rehearsal_report.workers[{index}].semantic_gate must be false")
        for field, runtime_field in (
            ("summary", "summary"),
            ("report", "worker_report"),
            ("handoff_contract", "handoff_contract"),
            ("opencode_session_evidence", "opencode_session_evidence"),
        ):
            top_binding = validate_hash_bound_artifact_binding(
                worker.get(field),
                f"opencode_hostless_rehearsal_report.workers[{index}].{field}",
                repo_root=repo_root,
            )
            compare_artifact_binding(
                top_binding,
                require_object(
                    runtime_worker.get(runtime_field),
                    f"opencode_hostless_rehearsal_report.opencode_runtime.workers[{index}].{runtime_field}",
                ),
                f"opencode_hostless_rehearsal_report.workers[{index}].{field}",
            )
        worker_preflight = validate_opencode_preflight_binding(
            worker.get("opencode_preflight_report"),
            f"opencode_hostless_rehearsal_report.workers[{index}].opencode_preflight_report",
            repo_root=repo_root,
        )
        compare_artifact_binding(
            worker_preflight,
            top_level_preflight,
            f"opencode_hostless_rehearsal_report.workers[{index}].opencode_preflight_report",
        )
        verification = require_object(
            worker.get("opencode_contract_verification"),
            f"opencode_hostless_rehearsal_report.workers[{index}].opencode_contract_verification",
        )
        if verification.get("status") != "executed":
            raise ValueError(
                f"opencode_hostless_rehearsal_report.workers[{index}].opencode_contract_verification.status must be executed"
            )
        runtime_verification = require_object(
            runtime_worker.get("opencode_contract_verification"),
            f"opencode_hostless_rehearsal_report.opencode_runtime.workers[{index}].opencode_contract_verification",
        )
        if verification != runtime_verification:
            raise ValueError(
                f"opencode_hostless_rehearsal_report.workers[{index}].opencode_contract_verification must match opencode_runtime.workers"
            )
        recomputed_summary_status = runtime_result["worker_summary_final_gate_statuses"].get(worker_id)
        if worker.get("summary_status") != recomputed_summary_status:
            raise ValueError(
                f"opencode_hostless_rehearsal_report.workers[{index}].summary_status must match summary final_gate.status"
            )
    if len(set(worker_ids)) != len(worker_ids):
        raise ValueError("opencode_hostless_rehearsal_report.workers worker_id values must be unique")
    if worker_ids != runtime_result["worker_ids"]:
        raise ValueError("opencode_hostless_rehearsal_report.workers worker_id order must match opencode_runtime.workers")
    return {
        "status": "passed",
        "report_kind": "opencode-hostless-rehearsal-report",
        "proof_class": "local-simulation",
        "closes_p0_h9": False,
        "required_agent_tool": COMPETITION_OPENCODE_COMMAND,
        "required_agent": COMPETITION_OPENCODE_AGENT,
        "required_model": COMPETITION_OPENCODE_MODEL,
        "required_variant": COMPETITION_OPENCODE_VARIANT,
        "worker_count": worker_count,
        "worker_ids": worker_ids,
        "batch_profile_report": batch_profile_report,
        "run_plan_report": run_plan_report,
        "context_contract": context_contract,
        "agent_contract": agent_contract,
        "context_agent_consistency": context_agent_consistency,
        "opencode_preflight_report": top_level_preflight,
    }


def artifact_ref_key_for_expected_artifact(name: str) -> str:
    return EXPECTED_ARTIFACT_REF_ALIASES.get(name, name)


def judge_evidence_ref_key_allowed(name: str, allowed_ref_keys: set[str]) -> bool:
    if name in allowed_ref_keys:
        return True
    return bool(re.fullmatch(r"internal_review_checklist_[2-9][0-9]*", name))


def validate_opencode_safety_transform_attempt_contract(ref: dict[str, Any], *, repo_root: Path) -> dict[str, Any]:
    binding = validate_artifact_binding_shape(ref, "opencode_safety_transform_attempt", repo_root=repo_root)
    payload = load_json(repo_path(binding["path"], repo_root=repo_root))
    if payload.get("report_kind") != "opencode-safety-transform-attempt":
        raise ValueError("opencode_safety_transform_attempt.report_kind must be opencode-safety-transform-attempt")
    if payload.get("chat_output_is_evidence") is not False:
        raise ValueError("opencode_safety_transform_attempt.chat_output_is_evidence must be false")
    if payload.get("semantic_gate") is not False:
        raise ValueError("opencode_safety_transform_attempt.semantic_gate must be false")
    if payload.get("generated_draft_semantic_pass") is not False:
        raise ValueError("opencode_safety_transform_attempt.generated_draft_semantic_pass must be false")
    if payload.get("translation_coverage_numerator") != 0:
        raise ValueError("opencode_safety_transform_attempt.translation_coverage_numerator must be 0")
    if payload.get("status") != "accepted":
        raise ValueError("opencode_safety_transform_attempt.status must be accepted")
    run_id = require_string(payload.get("run_id"), "opencode_safety_transform_attempt.run_id")
    worker_id = require_string(payload.get("worker_id"), "opencode_safety_transform_attempt.worker_id")
    attempt_number = payload.get("attempt")
    if not isinstance(attempt_number, int) or isinstance(attempt_number, bool) or attempt_number < 1:
        raise ValueError("opencode_safety_transform_attempt.attempt must be a positive integer")

    summary_payload = require_object(payload.get("summary"), "opencode_safety_transform_attempt.summary")
    summary = validate_artifact_binding_shape(
        summary_payload,
        "opencode_safety_transform_attempt.summary",
        repo_root=repo_root,
    )
    if summary_payload.get("final_gate_status") != "passed":
        raise ValueError("opencode_safety_transform_attempt.summary.final_gate_status must be passed")
    summary_path = repo_path(summary["path"], repo_root=repo_root)
    try:
        validate_competition_run_summary.validate_summary(summary_path, repo_root=repo_root)
    except SystemExit as error:
        raise ValueError(f"opencode_safety_transform_attempt.summary validation failed: {error}") from error
    worker_summary_payload = load_json(summary_path)
    if worker_summary_payload.get("run_id") != run_id:
        raise ValueError("opencode_safety_transform_attempt.summary.run_id must match run_id")
    worker_final_gate = require_object(
        worker_summary_payload.get("final_gate"),
        "opencode_safety_transform_attempt.summary.final_gate",
    )
    if summary_payload.get("final_gate_status") != worker_final_gate.get("status"):
        raise ValueError("opencode_safety_transform_attempt.summary.final_gate_status must match worker summary final_gate.status")
    workflow_metrics = validate_artifact_binding_shape(
        require_object(payload.get("workflow_metrics"), "opencode_safety_transform_attempt.workflow_metrics"),
        "opencode_safety_transform_attempt.workflow_metrics",
        repo_root=repo_root,
    )
    worker_workflow_metrics = validate_artifact_binding_shape(
        require_object(
            worker_summary_payload.get("workflow_metrics"),
            "opencode_safety_transform_attempt.summary.workflow_metrics",
        ),
        "opencode_safety_transform_attempt.summary.workflow_metrics",
        repo_root=repo_root,
    )
    compare_artifact_binding(
        workflow_metrics,
        worker_workflow_metrics,
        "opencode_safety_transform_attempt.workflow_metrics must match worker summary workflow_metrics",
    )
    workflow_metrics_payload = require_object(
        load_json(repo_path(workflow_metrics["path"], repo_root=repo_root)),
        "opencode_safety_transform_attempt.workflow_metrics file",
    )
    workflow_metric_units = opencode_workflow_metric_units_by_id(workflow_metrics_payload)

    contract = require_object(payload.get("attempt_contract"), "opencode_safety_transform_attempt.attempt_contract")
    if contract.get("single_patch_per_round") is not True:
        raise ValueError("opencode_safety_transform_attempt.attempt_contract.single_patch_per_round must be true")
    if contract.get("max_repair_rounds") != 5:
        raise ValueError("opencode_safety_transform_attempt.attempt_contract.max_repair_rounds must be 5")
    if contract.get("semantic_gate") is not False:
        raise ValueError("opencode_safety_transform_attempt.attempt_contract.semantic_gate must be false")
    if contract.get("translation_coverage_numerator") != 0:
        raise ValueError("opencode_safety_transform_attempt.attempt_contract.translation_coverage_numerator must be 0")

    verification = require_object(
        payload.get("contract_verification"),
        "opencode_safety_transform_attempt.contract_verification",
    )
    required_verification_fields = (
        "expected_worker_command_line",
        "expected_summary_path",
        "expected_worker_command_sha256",
        "executed_shell_command_count",
        "executed_shell_commands",
        "first_tool_name",
        "first_shell_command",
        "first_shell_tool_name",
        "first_shell_workdir_status",
        "expected_workdir_status",
        "first_shell_command_matches_worker_command",
        "first_shell_workdir_matches_repo_root",
        "tools_before_first_shell",
        "contract_failure_reason",
        "worker_command_seen",
        "summary_exists",
        "status",
    )
    for field in required_verification_fields:
        if field not in verification:
            raise ValueError(f"opencode_safety_transform_attempt.contract_verification.{field} is required")
    handoff_binding = validate_hash_bound_artifact_binding(
        payload.get("handoff_contract"),
        "opencode_safety_transform_attempt.handoff_contract",
        repo_root=repo_root,
    )
    handoff_payload = require_object(
        load_json(repo_path(handoff_binding["path"], repo_root=repo_root)),
        "opencode_safety_transform_attempt.handoff_contract file",
    )
    if handoff_payload.get("runner_kind") != "opencode-run":
        raise ValueError("opencode_safety_transform_attempt.handoff_contract.runner_kind must be opencode-run")
    if handoff_payload.get("run_id") != run_id:
        raise ValueError("opencode_safety_transform_attempt.handoff_contract.run_id must match run_id")
    if handoff_payload.get("worker_id") != worker_id:
        raise ValueError("opencode_safety_transform_attempt.handoff_contract.worker_id must match worker_id")
    if handoff_payload.get("attempt") != attempt_number:
        raise ValueError("opencode_safety_transform_attempt.handoff_contract.attempt must match attempt")
    launch_policy = validate_opencode_launch_policy_binding(
        handoff_payload.get("launch_policy"),
        handoff_payload.get("launch_policy_sha256"),
        "opencode_safety_transform_attempt.handoff_contract",
    )
    handoff_runtime_env = validate_opencode_runtime_env_contract(
        handoff_payload.get("opencode_runtime_env"),
        "opencode_safety_transform_attempt.handoff_contract",
    )
    worker_command = require_string_argv(
        handoff_payload.get("worker_command"),
        "opencode_safety_transform_attempt.handoff_contract.worker_command",
    )
    worker_command_line = require_string(
        handoff_payload.get("worker_command_line"),
        "opencode_safety_transform_attempt.handoff_contract.worker_command_line",
    )
    if worker_command_line != shell_command_line(worker_command):
        raise ValueError("opencode_safety_transform_attempt.handoff_contract.worker_command_line must match worker_command")
    worker_command_sha256 = validate_sha256_hex(
        handoff_payload.get("worker_command_sha256"),
        "opencode_safety_transform_attempt.handoff_contract.worker_command_sha256",
    )
    if worker_command_sha256 != sha256_text(worker_command_line):
        raise ValueError("opencode_safety_transform_attempt.handoff_contract.worker_command_sha256 must match worker_command_line")
    expected_summary_path = require_string(
        handoff_payload.get("expected_summary_path"),
        "opencode_safety_transform_attempt.handoff_contract.expected_summary_path",
    )
    if expected_summary_path != summary["path"]:
        raise ValueError("opencode_safety_transform_attempt.handoff_contract.expected_summary_path must match summary.path")
    opencode_argv = validate_opencode_run_argv_binding(
        handoff_payload.get("opencode_argv"),
        "opencode_safety_transform_attempt.handoff_contract.opencode_argv",
        launch_policy=launch_policy,
    )
    opencode_command_line = require_string(
        handoff_payload.get("opencode_command_line"),
        "opencode_safety_transform_attempt.handoff_contract.opencode_command_line",
    )
    if opencode_command_line != shell_command_line(opencode_argv):
        raise ValueError("opencode_safety_transform_attempt.handoff_contract.opencode_command_line must match opencode_argv")
    prompt = require_string(
        handoff_payload.get("prompt"),
        "opencode_safety_transform_attempt.handoff_contract.prompt",
    )
    if prompt != opencode_argv[-1]:
        raise ValueError("opencode_safety_transform_attempt.handoff_contract.prompt must match opencode_argv prompt")
    session_binding = validate_hash_bound_artifact_binding(
        payload.get("opencode_session_evidence"),
        "opencode_safety_transform_attempt.opencode_session_evidence",
        repo_root=repo_root,
    )
    session_evidence = require_object(
        load_json(repo_path(session_binding["path"], repo_root=repo_root)),
        "opencode_safety_transform_attempt.opencode_session_evidence file",
    )
    validate_opencode_session_evidence_contract(
        session_evidence,
        "opencode_safety_transform_attempt.opencode_session_evidence",
        repo_root=repo_root,
    )
    session_runtime_env = validate_opencode_runtime_env_contract(
        session_evidence.get("opencode_runtime_env"),
        "opencode_safety_transform_attempt.opencode_session_evidence",
    )
    compare_opencode_runtime_env(
        session_runtime_env,
        handoff_runtime_env,
        "opencode_safety_transform_attempt.opencode_session_evidence",
        expected_label="opencode_safety_transform_attempt.handoff_contract",
    )
    recomputed_contract = validate_opencode_contract_recomputed_from_session(
        embedded_verification=verification,
        session_evidence=session_evidence,
        worker_command=worker_command,
        summary_path=summary_path,
        label="opencode_safety_transform_attempt",
        repo_root=repo_root,
    )

    units = payload.get("safety_transform_units")
    if not isinstance(units, list) or not units:
        raise ValueError("opencode_safety_transform_attempt.safety_transform_units must be a non-empty list")
    if payload.get("safety_transform_unit_count") != len(units):
        raise ValueError("opencode_safety_transform_attempt.safety_transform_unit_count must match units length")

    round_count = 0
    rollback_ref_count = 0
    for index, unit_value in enumerate(units):
        unit = require_object(unit_value, f"opencode_safety_transform_attempt.safety_transform_units[{index}]")
        round_count += validate_opencode_safety_transform_unit_contract(unit, index=index, repo_root=repo_root)
        retry_hint = require_object(
            unit.get("accepted_retry_hint"),
            f"opencode_safety_transform_attempt.safety_transform_units[{index}].accepted_retry_hint",
        )
        rollback_ref_count += validate_opencode_accepted_retry_hint_contract(
            retry_hint,
            index=index,
            repo_root=repo_root,
        )
        repair_history = unit.get("repair_history")
        if repair_history is not None:
            validate_opencode_repair_history_contract(
                repair_history,
                retry_hint,
                index=index,
                repo_root=repo_root,
            )
        validate_opencode_safety_transform_unit_matches_workflow_metrics(
            unit,
            workflow_metric_units,
            index=index,
            repo_root=repo_root,
        )

    result: dict[str, Any] = {
        "status": "passed",
        "path": binding["path"],
        "summary": summary,
        "unit_count": len(units),
        "round_count": round_count,
        "repair_round_cap": 5,
        "rollback_ref_count": rollback_ref_count,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
        "contract_verification_status": "executed",
        "handoff_contract": handoff_binding,
        "opencode_session_evidence": session_binding,
        "recomputed_contract": recomputed_contract,
        "launch_policy": launch_policy,
        "opencode_runtime_env": handoff_runtime_env,
    }
    result["workflow_metrics"] = workflow_metrics
    return result
