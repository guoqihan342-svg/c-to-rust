def retry_worker(
    *,
    db_path: Path,
    run_id: str,
    worker_id: str,
    hint_id: str | None = None,
    mode: str = "deterministic",
    opencode_command: str = "opencode",
    opencode_model: str | None = None,
    opencode_agent: str | None = None,
    opencode_variant: str = "max",
    opencode_skip_permissions: bool = False,
    opencode_allow_non_competition_model: bool = False,
    opencode_preflight_report: Path | None = None,
    timeout_seconds: int = DEFAULT_SUBPROCESS_TIMEOUT_SECONDS,
    command_runner: Any = subprocess.run,
    repo_root: Path = REPO_ROOT,
    keep_open_on_failure: bool = False,
    repair_trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    db_path = repo_path(db_path, repo_root=repo_root)
    with closing(connect(db_path)) as connection:
        ensure_schema(connection)
        hint = load_open_repair_hint(connection, run_id=run_id, worker_id=worker_id, hint_id=hint_id)
        attempts = hint.get("attempts")
        attempt_number = len(attempts) + 1 if isinstance(attempts, list) else 2
        repair_rounds = max(0, attempt_number - 2)
        if repair_rounds >= REPAIR_ROUND_CAP:
            retry_result = mark_repair_hint_retry_limit_exceeded(
                connection,
                hint=hint,
                repair_rounds=repair_rounds,
            )
            connection.commit()
            return retry_result

    result = run_worker(
        db_path=db_path,
        run_id=run_id,
        worker_id=worker_id,
        mode=mode,
        opencode_command=opencode_command,
        opencode_model=opencode_model,
        opencode_agent=opencode_agent,
        opencode_variant=opencode_variant,
        opencode_skip_permissions=opencode_skip_permissions,
        opencode_allow_non_competition_model=opencode_allow_non_competition_model,
        opencode_preflight_report=opencode_preflight_report,
        timeout_seconds=timeout_seconds,
        command_runner=command_runner,
        repo_root=repo_root,
        attempt_number=attempt_number,
        retry_of=str(hint["hint_id"]),
        repair_trace=repair_trace,
    )
    hint_status = (
        "revalidated_passed"
        if int(result.get("exit_code", 1)) == 0 and result.get("summary_status") == "passed"
        else "revalidated_failed"
    )
    retry_metrics_annotation = None
    with closing(connect(db_path)) as connection:
        ensure_schema(connection)
        mark_repair_hint_revalidated(
            connection,
            hint_id=str(hint["hint_id"]),
            status=("open" if keep_open_on_failure and hint_status != "revalidated_passed" else hint_status),
            result=result,
        )
        if hint_status == "revalidated_passed":
            retry_metrics_annotation = annotate_retry_worker_metrics(
                connection,
                hint_id=str(hint["hint_id"]),
                result=result,
                repo_root=repo_root,
            )
        connection.commit()
    if retry_metrics_annotation is not None:
        result["retry_metrics_annotation"] = retry_metrics_annotation
        result["record_worker_summary"] = record_worker_summary(
            db_path=db_path,
            run_id=run_id,
            worker_id=worker_id,
            summary_path=repo_path(Path(str(result["summary_path"])), repo_root=repo_root),
            repo_root=repo_root,
        )

    retry_result = dict(result)
    retry_result["hint_id"] = hint["hint_id"]
    retry_result["hint_status"] = hint_status
    return retry_result


def mark_repair_hint_retry_limit_exceeded(
    connection: sqlite3.Connection,
    *,
    hint: dict[str, Any],
    repair_rounds: int,
) -> dict[str, Any]:
    retry_limit = {
        "status": "retry_limit_exceeded",
        "max_repair_rounds": REPAIR_ROUND_CAP,
        "observed_repair_rounds": repair_rounds,
        "boundary": "retry-worker refuses to launch another worker after the configured repair round cap",
    }
    payload = dict(hint)
    payload["status"] = "retry_limit_exceeded"
    payload["retry_limit"] = retry_limit
    hint_id = str(payload["hint_id"])
    connection.execute(
        "update repair_hints set status=?, payload_json=? where hint_id=?",
        ("retry_limit_exceeded", json.dumps(payload, sort_keys=True), hint_id),
    )
    record_event(
        connection,
        run_id=str(payload["run_id"]),
        event_type="repair_retry_limit_exceeded",
        payload={
            "hint_id": hint_id,
            "worker_id": payload.get("worker_id"),
            "repair_round_cap": REPAIR_ROUND_CAP,
            "repair_rounds": repair_rounds,
        },
    )
    result = {
        "schema_version": SCHEMA_VERSION,
        "run_id": str(payload["run_id"]),
        "worker_id": str(payload["worker_id"]),
        "hint_id": hint_id,
        "hint_status": "retry_limit_exceeded",
        "status": "retry_limit_exceeded",
        "exit_code": 1,
        "summary_status": str(payload.get("summary_status", "unknown")),
        "repair_round_cap": REPAIR_ROUND_CAP,
        "repair_rounds": repair_rounds,
        "retry_limit": retry_limit,
    }
    if isinstance(payload.get("summary_path"), str):
        result["summary_path"] = payload["summary_path"]
    if isinstance(payload.get("worker_report_path"), str):
        result["report_path"] = payload["worker_report_path"]
    if isinstance(payload.get("logs"), dict):
        result["logs"] = payload["logs"]
    if isinstance(payload.get("diagnostics"), dict):
        result["diagnostics"] = payload["diagnostics"]
    return result


def run_opencode_preflight(
    *,
    out_root: Path,
    run_id: str,
    opencode_command: str = "opencode",
    opencode_model: str | None = None,
    opencode_agent: str | None = None,
    opencode_variant: str = "max",
    opencode_skip_permissions: bool = False,
    opencode_allow_non_competition_model: bool = False,
    timeout_seconds: int = DEFAULT_SUBPROCESS_TIMEOUT_SECONDS,
    command_runner: Any = subprocess.run,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    out_root = repo_path(out_root, repo_root=repo_root)
    harness_dir = out_root / "harness"
    logs_dir = out_root / "logs"
    harness_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    marker_path = harness_dir / "opencode-preflight-marker.json"
    contract_path = harness_dir / "opencode-preflight-contract.json"
    if marker_path.exists():
        marker_path.unlink()
    opencode_runtime_env = opencode_runtime_env_contract(
        base_root=out_root,
        scope="preflight",
        repo_root=repo_root,
    )
    opencode_process_env = opencode_runtime_process_env(opencode_runtime_env, repo_root=repo_root)

    marker_command = portable_python_script_argv(
        "validation/tools/opencode_agent_harness.py",
        "write-preflight-marker",
        "--marker",
        repo_relative(marker_path, repo_root=repo_root),
        "--run-id",
        run_id,
    )
    launch_policy = opencode_launch_policy(
        opencode_command=opencode_command,
        opencode_model=opencode_model,
        opencode_agent=opencode_agent,
        opencode_variant=opencode_variant,
        opencode_skip_permissions=opencode_skip_permissions,
        opencode_allow_non_competition_model=opencode_allow_non_competition_model,
    )
    argv = build_opencode_preflight_argv(
        opencode_command=opencode_command,
        opencode_model=opencode_model,
        opencode_agent=opencode_agent,
        opencode_variant=opencode_variant,
        opencode_skip_permissions=opencode_skip_permissions,
        opencode_allow_non_competition_model=opencode_allow_non_competition_model,
        marker_command=marker_command,
        marker_path=marker_path,
        contract_path=contract_path,
        repo_root=repo_root,
    )
    report_argv = portable_opencode_evidence_argv(
        argv,
        opencode_command=launch_policy["opencode_command"],
    )
    contract_binding = write_opencode_preflight_contract(
        run_id=run_id,
        contract_path=contract_path,
        marker_path=marker_path,
        marker_command=marker_command,
        opencode_argv=report_argv,
        launch_policy=launch_policy,
        opencode_runtime_env=opencode_runtime_env,
        repo_root=repo_root,
    )
    started = time.monotonic()
    model_availability = run_opencode_model_availability_probe(
        opencode_command=launch_policy["opencode_command"],
        opencode_model=launch_policy["opencode_model"],
        opencode_allow_non_competition_model=opencode_allow_non_competition_model,
        logs_dir=logs_dir,
        opencode_process_env=opencode_process_env,
        timeout_seconds=timeout_seconds,
        command_runner=command_runner,
        repo_root=repo_root,
    )
    if model_availability.get("status") != "available":
        stdout_path = logs_dir / "opencode-preflight.stdout.log"
        stderr_path = logs_dir / "opencode-preflight.stderr.log"
        atomic_write_text(stdout_path, "")
        atomic_write_text(stderr_path, "")
        root_cause_key = "opencode_model_unavailable"
        session_binding = write_opencode_not_launched_session_evidence(
            evidence_path=logs_dir / "opencode-preflight-session-evidence.json",
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            root_cause_key=root_cause_key,
            opencode_runtime_env=opencode_runtime_env,
            repo_root=repo_root,
        )
        contract_verification = opencode_contract_not_observed(
            worker_command=marker_command,
            summary_path=marker_path,
            reason=root_cause_key,
            repo_root=repo_root,
        )
        report_path = harness_dir / "opencode-preflight-report.json"
        report: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "status": "failed",
            "exit_code": 1,
            "process_returncode": None,
            "elapsed_seconds": int(time.monotonic() - started),
            "argv": report_argv,
            "marker_path": repo_relative(marker_path, repo_root=repo_root),
            "marker_exists": False,
            "opencode_run_launched": False,
            "launch_policy": launch_policy,
            "launch_policy_sha256": opencode_launch_policy_sha256(launch_policy),
            "opencode_runtime_env": opencode_runtime_env,
            "handoff_contract": contract_binding,
            "opencode_session_evidence": session_binding,
            "opencode_model_availability": model_availability,
            "contract_verification": contract_verification,
            "logs": {
                "stdout": repo_relative(stdout_path, repo_root=repo_root),
                "stderr": repo_relative(stderr_path, repo_root=repo_root),
            },
            "report_path": repo_relative(report_path, repo_root=repo_root),
            "root_cause_key": root_cause_key,
            "h9_blocker": opencode_h9_blocker(
                root_cause_key=root_cause_key,
                launch_policy=launch_policy,
                opencode_run_launched=False,
                model_availability=model_availability,
            ),
            "evidence_boundary": "preflight proves exact-command compliance only; it is not semantic acceptance",
        }
        atomic_write_json(report_path, report)
        return report

    try:
        if command_runner is subprocess.run:
            completed = run_captured_process_with_timeout(
                argv,
                cwd=repo_root,
                timeout_seconds=timeout_seconds,
                env=opencode_process_env,
            )
        else:
            completed = command_runner(
                argv,
                cwd=repo_root,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=timeout_seconds,
                env=opencode_process_env,
            )
    except subprocess.TimeoutExpired as exc:
        completed = completed_process_from_timeout(argv, exc, timeout_seconds)
    except OSError as exc:
        completed = subprocess.CompletedProcess(
            argv,
            127,
            stdout="",
            stderr=f"{type(exc).__name__}: {exc}\n",
        )
    stdout_path = logs_dir / "opencode-preflight.stdout.log"
    stderr_path = logs_dir / "opencode-preflight.stderr.log"
    atomic_write_text(stdout_path, completed.stdout or "")
    atomic_write_text(stderr_path, completed.stderr or "")
    timed_out = completed_process_timed_out(completed)
    session_binding = write_opencode_session_evidence(
        completed=completed,
        evidence_path=logs_dir / "opencode-preflight-session-evidence.json",
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        opencode_runtime_env=opencode_runtime_env,
        repo_root=repo_root,
    )
    session_evidence = load_json(repo_path(Path(session_binding["path"]), repo_root=repo_root))
    contract_verification = verify_opencode_contract_execution(
        session_evidence=session_evidence,
        worker_command=marker_command,
        summary_path=marker_path,
        repo_root=repo_root,
        allow_post_contract_artifact_inspection=True,
    )
    marker_exists = marker_path.exists()
    marker_validation = validate_opencode_preflight_marker_payload(
        marker_path,
        run_id=run_id,
        repo_root=repo_root,
    ) if marker_exists else {"status": "missing", "reason": "marker file is absent"}
    marker_binding = {
        "path": repo_relative(marker_path, repo_root=repo_root),
        "sha256": sha256_file(marker_path),
    } if marker_exists else None
    preflight_passed = (
        int(completed.returncode) == 0
        and contract_verification.get("status") == "executed"
        and marker_exists
        and marker_validation.get("status") == "passed"
    )
    root_cause_key = None
    if not preflight_passed:
        if timed_out:
            root_cause_key = "process_timeout"
        elif int(completed.returncode) != 0:
            root_cause_key = "opencode_process_failed"
        elif contract_verification.get("status") != "executed":
            root_cause_key = "opencode_contract_not_executed"
        elif marker_exists and marker_validation.get("status") != "passed":
            root_cause_key = "invalid_preflight_marker"
        else:
            root_cause_key = "missing_preflight_marker"

    report_path = harness_dir / "opencode-preflight-report.json"
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "status": "passed" if preflight_passed else "failed",
        "exit_code": 0 if preflight_passed else 1,
        "process_returncode": int(completed.returncode),
        "elapsed_seconds": int(time.monotonic() - started),
        "argv": report_argv,
        "marker_path": repo_relative(marker_path, repo_root=repo_root),
        "marker_exists": marker_exists,
        "marker": marker_binding,
        "opencode_run_launched": True,
        "launch_policy": launch_policy,
        "launch_policy_sha256": opencode_launch_policy_sha256(launch_policy),
        "opencode_runtime_env": opencode_runtime_env,
        "handoff_contract": contract_binding,
        "opencode_session_evidence": session_binding,
        "opencode_model_availability": model_availability,
        "contract_verification": contract_verification,
        "marker_validation": marker_validation,
        "logs": {
            "stdout": repo_relative(stdout_path, repo_root=repo_root),
            "stderr": repo_relative(stderr_path, repo_root=repo_root),
        },
        "report_path": repo_relative(report_path, repo_root=repo_root),
        "evidence_boundary": "preflight proves exact-command compliance only; it is not semantic acceptance",
    }
    if timed_out:
        report["timed_out"] = True
        report["timeout_seconds"] = timeout_seconds
    if launch_policy["opencode_model"] != COMPETITION_OPENCODE_MODEL:
        report["non_competition_model_rehearsal"] = {
            "status": "local_rehearsal_only",
            "actual_model": launch_policy["opencode_model"],
            "required_competition_model": COMPETITION_OPENCODE_MODEL,
            "local_simulation_closes_p0_h9": False,
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
            "boundary": (
                "This preflight may prove local OpenCode wiring for a non-competition model, "
                "but it does not satisfy the GLM-5.1 competition host contract."
            ),
        }
        report["h9_blocker"] = opencode_h9_blocker(
            root_cause_key="non_competition_model_rehearsal",
            launch_policy=launch_policy,
            opencode_run_launched=True,
            model_availability=model_availability,
        )
    if root_cause_key is not None:
        report["root_cause_key"] = root_cause_key
        report["h9_blocker"] = opencode_h9_blocker(
            root_cause_key=root_cause_key,
            launch_policy=launch_policy,
            opencode_run_launched=True,
            model_availability=model_availability,
        )
    atomic_write_json(report_path, report)
    return report


def validate_opencode_preflight_report(
    report_path: Path | None,
    *,
    expected_run_id: str | None = None,
    opencode_command: str = "opencode",
    opencode_model: str | None = None,
    opencode_agent: str | None = None,
    opencode_variant: str = "max",
    opencode_skip_permissions: bool = False,
    opencode_allow_non_competition_model: bool = False,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    if report_path is None:
        raise SystemExit("opencode preflight report is required before --mode opencode")
    report_path = repo_path(report_path, repo_root=repo_root)
    if not report_path.exists():
        raise SystemExit(f"opencode preflight report does not exist: {repo_relative(report_path, repo_root=repo_root)}")
    report = load_json(report_path)
    contract_verification = report.get("contract_verification")
    contract_status = contract_verification.get("status") if isinstance(contract_verification, dict) else None
    if (
        report.get("status") != "passed"
        or int(report.get("exit_code", 1)) != 0
        or report.get("marker_exists") is not True
        or contract_status != "executed"
    ):
        raise SystemExit(
            "opencode preflight report is not passed: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    expected_launch_policy = opencode_launch_policy(
        opencode_command=opencode_command,
        opencode_model=opencode_model,
        opencode_agent=opencode_agent,
        opencode_variant=opencode_variant,
        opencode_skip_permissions=opencode_skip_permissions,
        opencode_allow_non_competition_model=opencode_allow_non_competition_model,
    )
    launch_policy = report.get("launch_policy")
    if not isinstance(launch_policy, dict):
        raise SystemExit(
            "opencode preflight launch policy is missing: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    actual_launch_policy = normalize_opencode_launch_policy(
        launch_policy,
        opencode_allow_non_competition_model=opencode_allow_non_competition_model,
    )
    actual_launch_policy_sha256 = report.get("launch_policy_sha256")
    if actual_launch_policy_sha256 != opencode_launch_policy_sha256(actual_launch_policy):
        raise SystemExit(
            "opencode preflight launch policy sha256 mismatch: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    if actual_launch_policy != expected_launch_policy:
        raise SystemExit(
            "opencode preflight launch policy mismatch: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    model_availability = report.get("opencode_model_availability")
    if not isinstance(model_availability, dict):
        raise SystemExit(
            "opencode preflight model availability is missing: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    try:
        model_probe_returncode = int(model_availability.get("process_returncode", 1))
    except (TypeError, ValueError):
        model_probe_returncode = 1
    availability_binding = {
        "status": str(model_availability.get("status", "")),
        "opencode_command": str(model_availability.get("opencode_command", "")),
        "required_model": str(model_availability.get("required_model", "")),
        "argv": model_availability.get("argv") if isinstance(model_availability.get("argv"), list) else [],
        "process_returncode": model_probe_returncode,
        "model_listed": model_availability.get("model_listed") is True,
    }
    if (
        availability_binding["status"] != "available"
        or availability_binding["opencode_command"] != expected_launch_policy["opencode_command"]
        or availability_binding["required_model"] != expected_launch_policy["opencode_model"]
        or availability_binding["process_returncode"] != 0
        or availability_binding["model_listed"] is not True
    ):
        raise SystemExit(
            "opencode preflight model availability is not passed: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    if not opencode_models_argv_matches(
        availability_binding["argv"],
        expected_command=expected_launch_policy["opencode_command"],
    ):
        raise SystemExit(
            "opencode preflight model availability argv must be opencode models: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    validate_opencode_model_probe_log_hashes(
        model_availability,
        repo_root=repo_root,
        report_path=report_path,
    )
    opencode_runtime_env = validate_opencode_runtime_env_contract(
        report.get("opencode_runtime_env"),
        context="opencode preflight report",
        repo_root=repo_root,
    )
    report_run_id = str(report.get("run_id", ""))
    if expected_run_id is not None and report_run_id != expected_run_id:
        raise SystemExit(f"opencode preflight run_id mismatch: {report_run_id} != {expected_run_id}")
    validate_opencode_preflight_session_contract(
        report,
        contract_verification=contract_verification,
        launch_policy=actual_launch_policy,
        run_id=report_run_id,
        report_path=report_path,
        opencode_allow_non_competition_model=opencode_allow_non_competition_model,
        repo_root=repo_root,
    )
    return {
        "path": repo_relative(report_path, repo_root=repo_root),
        "sha256": sha256_file(report_path),
        "status": "passed",
        "run_id": report_run_id,
        "contract_status": "executed",
        "launch_policy": actual_launch_policy,
        "launch_policy_sha256": opencode_launch_policy_sha256(actual_launch_policy),
        "opencode_model_availability": availability_binding,
        "opencode_runtime_env": opencode_runtime_env,
        "evidence_boundary": str(
            report.get(
                "evidence_boundary",
                "preflight proves exact-command compliance only; it is not semantic acceptance",
            )
        ),
    }


def validate_opencode_preflight_session_contract(
    report: dict[str, Any],
    *,
    contract_verification: dict[str, Any],
    launch_policy: dict[str, Any],
    run_id: str,
    report_path: Path,
    repo_root: Path,
    opencode_allow_non_competition_model: bool = False,
) -> None:
    if report.get("opencode_run_launched") is not True:
        raise SystemExit(
            "opencode preflight opencode_run_launched must be true: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    try:
        process_returncode = int(report.get("process_returncode"))
    except (TypeError, ValueError):
        process_returncode = -1
    if process_returncode != 0:
        raise SystemExit(
            "opencode preflight process_returncode must be 0: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )

    marker_value = report.get("marker_path")
    if not isinstance(marker_value, str) or not marker_value:
        raise SystemExit(
            "opencode preflight marker_path is required: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    marker_path = repo_path(Path(marker_value), repo_root=repo_root)
    if not marker_path.is_file():
        raise SystemExit(
            "opencode preflight marker_path does not exist: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    marker_ref_path = validate_hash_bound_artifact_ref(
        report.get("marker"),
        label="opencode preflight marker",
        report_path=report_path,
        repo_root=repo_root,
    )
    if marker_ref_path.resolve() != marker_path.resolve():
        raise SystemExit(
            "opencode preflight marker.path must match marker_path: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    marker_validation = validate_opencode_preflight_marker_payload(
        marker_path,
        run_id=run_id,
        repo_root=repo_root,
    )
    if marker_validation.get("status") != "passed":
        raise SystemExit(
            "opencode preflight marker payload invalid: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )

    handoff_path = validate_hash_bound_artifact_ref(
        report.get("handoff_contract"),
        label="opencode preflight handoff_contract",
        report_path=report_path,
        repo_root=repo_root,
    )
    handoff = load_json(handoff_path)
    if handoff.get("runner_kind") != "opencode-preflight":
        raise SystemExit(
            "opencode preflight handoff_contract.runner_kind must be opencode-preflight: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    if handoff.get("run_id") != run_id:
        raise SystemExit(
            "opencode preflight handoff_contract.run_id mismatch: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    handoff_policy = normalize_opencode_launch_policy(
        handoff["launch_policy"] if isinstance(handoff.get("launch_policy"), dict) else {},
        opencode_allow_non_competition_model=opencode_allow_non_competition_model,
    )
    if handoff_policy != launch_policy:
        raise SystemExit(
            "opencode preflight handoff_contract launch policy mismatch: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    if handoff.get("launch_policy_sha256") != opencode_launch_policy_sha256(handoff_policy):
        raise SystemExit(
            "opencode preflight handoff_contract launch policy sha256 mismatch: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    expected_marker = handoff.get("expected_marker_path")
    if expected_marker != marker_value:
        raise SystemExit(
            "opencode preflight marker_path must match handoff_contract.expected_marker_path: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    worker_command = handoff.get("worker_command")
    if (
        not isinstance(worker_command, list)
        or not worker_command
        or not all(isinstance(item, str) and item for item in worker_command)
    ):
        raise SystemExit(
            "opencode preflight handoff_contract.worker_command must be a non-empty string list: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    worker_command_line = handoff.get("worker_command_line")
    if worker_command_line != shell_command_line(worker_command):
        raise SystemExit(
            "opencode preflight handoff_contract.worker_command_line mismatch: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    if handoff.get("worker_command_sha256") != sha256_text(str(worker_command_line)):
        raise SystemExit(
            "opencode preflight handoff_contract.worker_command_sha256 mismatch: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    report_argv = require_opencode_string_argv(
        report.get("argv"),
        label="opencode preflight report argv",
        report_path=report_path,
        repo_root=repo_root,
    )
    handoff_argv = require_opencode_string_argv(
        handoff.get("opencode_argv"),
        label="opencode preflight handoff_contract.opencode_argv",
        report_path=report_path,
        repo_root=repo_root,
    )
    if report_argv != handoff_argv:
        raise SystemExit(
            "opencode preflight report argv must match handoff_contract.opencode_argv: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    validate_opencode_run_argv_binding(
        report_argv,
        label="opencode preflight report argv",
        launch_policy=launch_policy,
        report_path=report_path,
        repo_root=repo_root,
    )
    handoff_command_line = handoff.get("opencode_command_line")
    if handoff_command_line != shell_command_line(handoff_argv):
        raise SystemExit(
            "opencode preflight handoff_contract.opencode_command_line mismatch: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    if handoff.get("prompt") != handoff_argv[-1]:
        raise SystemExit(
            "opencode preflight handoff_contract.prompt must match opencode_argv prompt: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )

    session_path = validate_hash_bound_artifact_ref(
        report.get("opencode_session_evidence"),
        label="opencode preflight opencode_session_evidence",
        report_path=report_path,
        repo_root=repo_root,
    )
    recomputed = verify_opencode_contract_execution(
        session_evidence=load_json(session_path),
        worker_command=worker_command,
        summary_path=marker_path,
        repo_root=repo_root,
        allow_post_contract_artifact_inspection=True,
    )
    if recomputed.get("status") != "executed":
        raise SystemExit(
            "opencode preflight session contract was not executed: "
            f"{recomputed.get('contract_failure_reason', 'unknown')}: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    for key in (
        "expected_worker_command_line",
        "expected_summary_path",
        "expected_worker_command_sha256",
        "executed_shell_command_count",
        "executed_shell_commands",
        "first_shell_command",
        "first_shell_tool_name",
        "first_shell_workdir_status",
        "first_shell_command_matches_worker_command",
        "first_shell_workdir_matches_repo_root",
        "tools_before_first_shell",
        "worker_command_seen",
        "summary_exists",
        "status",
    ):
        if contract_verification.get(key) != recomputed.get(key):
            raise SystemExit(
                "opencode preflight session contract mismatch: "
                f"{key}: {repo_relative(report_path, repo_root=repo_root)}"
            )


def validate_hash_bound_artifact_ref(
    value: Any,
    *,
    label: str,
    report_path: Path,
    repo_root: Path,
) -> Path:
    if not isinstance(value, dict):
        raise SystemExit(f"{label} is required: {repo_relative(report_path, repo_root=repo_root)}")
    path_value = value.get("path")
    sha_value = value.get("sha256")
    if not isinstance(path_value, str) or not isinstance(sha_value, str):
        raise SystemExit(
            f"{label}.path and {label}.sha256 are required: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    artifact_path = repo_path(Path(path_value), repo_root=repo_root)
    if not artifact_path.is_file():
        raise SystemExit(f"{label}.path does not exist: {path_value}")
    if sha256_file(artifact_path) != sha_value:
        raise SystemExit(
            f"{label}.sha256 mismatch: {repo_relative(report_path, repo_root=repo_root)}"
        )
    return artifact_path


def validate_opencode_preflight_marker_payload(
    marker_path: Path,
    *,
    run_id: str,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    try:
        payload = load_json(marker_path)
    except Exception as error:  # noqa: BLE001 - convert malformed marker artifacts into fail-closed evidence.
        return {
            "status": "failed",
            "reason": f"marker_json_invalid:{type(error).__name__}",
        }
    failed_fields: list[str] = []
    if payload.get("report_kind") != "opencode-preflight-marker":
        failed_fields.append("report_kind")
    if payload.get("run_id") != run_id:
        failed_fields.append("run_id")
    if payload.get("status") != "written":
        failed_fields.append("status")
    return {
        "status": "passed" if not failed_fields else "failed",
        "failed_fields": failed_fields,
        "path": repo_relative(marker_path, repo_root=repo_root),
    }


def write_opencode_preflight_marker(
    *,
    marker_path: Path,
    run_id: str,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    marker_path = repo_path(marker_path, repo_root=repo_root)
    marker = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "opencode-preflight-marker",
        "run_id": run_id,
        "status": "written",
        "created_at": now_text(),
    }
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(marker_path, marker)
    return {
        "status": "written",
        "marker_path": repo_relative(marker_path, repo_root=repo_root),
        "sha256": sha256_file(marker_path),
    }


def worker_failure_root_cause(
    *,
    process_returncode: int,
    recorded: bool,
    summary_status: str,
    opencode_contract_verification: dict[str, Any] | None = None,
) -> str:
    if process_returncode == PROCESS_TIMEOUT_EXIT_CODE:
        return "process_timeout"
    if process_returncode != 0:
        return "worker_process_failed"
    if (
        opencode_contract_verification is not None
        and opencode_contract_verification.get("status") == "not-executed"
        and not recorded
    ):
        return "opencode_contract_not_executed"
    if not recorded:
        return "missing_summary"
    if summary_status != "passed":
        return "final_gate_failed"
    return "worker_failed"


def worker_summary_root_cause(
    summary: dict[str, Any] | None,
    *,
    summary_path: Path,
    repo_root: Path,
) -> str | None:
    if not isinstance(summary, dict):
        return None
    workflow_ref = summary.get("workflow_metrics")
    if not isinstance(workflow_ref, dict) or not isinstance(workflow_ref.get("path"), str):
        return None
    metrics_path = resolve_summary_artifact(str(workflow_ref["path"]), summary_path=summary_path, repo_root=repo_root)
    if metrics_path is None or not metrics_path.exists():
        return None
    try:
        metrics = load_json(metrics_path)
    except (OSError, json.JSONDecodeError):
        return None
    root_cause_counts = metrics.get("root_cause_counts")
    if isinstance(root_cause_counts, dict):
        for key, count in root_cause_counts.items():
            if isinstance(key, str) and key and isinstance(count, int) and count > 0:
                return key
    per_unit_statuses = metrics.get("per_unit_statuses")
    if isinstance(per_unit_statuses, list):
        for unit in per_unit_statuses:
            if isinstance(unit, dict) and isinstance(unit.get("root_cause_key"), str) and unit["root_cause_key"]:
                return str(unit["root_cause_key"])
    return None


def worker_repair_diagnostics(
    *,
    stdout_path: Path,
    stderr_path: Path,
    process_returncode: int,
    root_cause_key: str,
) -> dict[str, Any]:
    stdout_tail = redact_local_absolute_paths(file_tail(stdout_path, REPAIR_LOG_TAIL_CHARS))
    stderr_tail = redact_local_absolute_paths(file_tail(stderr_path, REPAIR_LOG_TAIL_CHARS))
    combined = "\n".join(part for part in [stderr_tail, stdout_tail] if part)
    diagnostics: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "root_cause_key": root_cause_key,
        "process_returncode": process_returncode,
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
        "primary_error": {
            "kind": "process",
            "message": root_cause_key,
        },
    }
    rustc_match = re.search(r"\berror\[(E\d+)\]:\s*(.+)", combined)
    if rustc_match:
        diagnostics["primary_error"] = {
            "kind": "rustc",
            "code": rustc_match.group(1),
            "message": rustc_match.group(2).strip(),
        }
    traceback_text = extract_python_traceback(combined)
    if traceback_text:
        diagnostics["python_traceback"] = traceback_text
        if diagnostics["primary_error"]["kind"] == "process":
            last_line = next((line.strip() for line in reversed(traceback_text.splitlines()) if line.strip()), "")
            diagnostics["primary_error"] = {
                "kind": "python",
                "message": last_line or "python traceback",
            }
    return diagnostics


def redact_local_absolute_paths(text: str) -> str:
    return LOCAL_ABSOLUTE_PATH_TEXT.sub("<local-absolute-path>", text)


def file_tail(path: Path, max_chars: int) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-max_chars:]


def extract_python_traceback(text: str) -> str:
    marker = "Traceback (most recent call last):"
    index = text.find(marker)
    if index < 0:
        return ""
    return text[index:][-REPAIR_LOG_TAIL_CHARS:]


def worker_repair_hint_payload(
    *,
    db_path: Path,
    run_id: str,
    worker_id: str,
    request: dict[str, Any],
    root_cause_key: str,
    summary_status: str,
    process_returncode: int,
    summary_path: Path,
    report_path: Path,
    stdout_path: Path,
    stderr_path: Path,
    repo_root: Path,
    exit_code: int,
    attempt_number: int,
    diagnostics: dict[str, Any],
    retry_of: str | None = None,
    rollback_evidence: dict[str, Any] | None = None,
    rejected_summary_evidence: dict[str, Any] | None = None,
    handoff_contract: dict[str, Any] | None = None,
    opencode_session_evidence: dict[str, Any] | None = None,
    opencode_contract_verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target_id = str(request.get("target_id", "unknown"))
    slice_id = str(request.get("slice_id", "unknown"))
    hint_id = f"repair:{run_id}:{worker_id}:{root_cause_key}"
    retry_command = portable_python_script_argv(
        "validation/tools/opencode_agent_harness.py",
        "retry-worker",
        "--db",
        repo_relative(db_path, repo_root=repo_root),
        "--run-id",
        run_id,
        "--worker-id",
        worker_id,
        "--hint-id",
        hint_id,
    )
    hint = {
        "schema_version": SCHEMA_VERSION,
        "hint_id": hint_id,
        "run_id": run_id,
        "worker_id": worker_id,
        "target_id": target_id,
        "slice_id": slice_id,
        "root_cause_key": root_cause_key,
        "status": "open",
        "summary_status": summary_status,
        "process_returncode": process_returncode,
        "summary_path": repo_relative(summary_path, repo_root=repo_root),
        "worker_report_path": repo_relative(report_path, repo_root=repo_root),
        "logs": {
            "stdout": repo_relative(stdout_path, repo_root=repo_root),
            "stderr": repo_relative(stderr_path, repo_root=repo_root),
        },
        "diagnostics": diagnostics,
        "attempts": [
            repair_attempt_payload(
                attempt_number=attempt_number,
                summary_status=summary_status,
                process_returncode=process_returncode,
                exit_code=exit_code,
                summary_path=repo_relative(summary_path, repo_root=repo_root),
                report_path=repo_relative(report_path, repo_root=repo_root),
                logs={
                    "stdout": repo_relative(stdout_path, repo_root=repo_root),
                    "stderr": repo_relative(stderr_path, repo_root=repo_root),
                },
                root_cause_key=root_cause_key,
                retry_of=retry_of,
                rollback_evidence=rollback_evidence,
                diagnostics=diagnostics,
            )
        ],
        "retry_command": retry_command,
        "revalidate_gate": "competition-run-summary.final_gate.status == passed",
    }
    if rejected_summary_evidence is not None:
        hint["rejected_summary_evidence"] = rejected_summary_evidence
    if handoff_contract is not None:
        hint["handoff_contract"] = handoff_contract
    if opencode_session_evidence is not None:
        hint["opencode_session_evidence"] = opencode_session_evidence
    if opencode_contract_verification is not None:
        hint["opencode_contract_verification"] = opencode_contract_verification
    return hint
