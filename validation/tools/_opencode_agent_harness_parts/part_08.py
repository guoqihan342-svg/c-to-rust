def validate_opencode_model_probe_log_hashes(
    model_availability: dict[str, Any],
    *,
    repo_root: Path,
    report_path: Path,
) -> None:
    logs = model_availability.get("logs")
    if not isinstance(logs, dict):
        raise SystemExit(
            "opencode preflight model availability logs are missing: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    for stream in ("stdout", "stderr"):
        log_path_text = logs.get(stream)
        if not isinstance(log_path_text, str) or not log_path_text:
            raise SystemExit(
                f"opencode preflight model availability {stream} log is missing: "
                f"{repo_relative(report_path, repo_root=repo_root)}"
            )
        log_path = repo_path(Path(log_path_text), repo_root=repo_root)
        if not log_path.is_file():
            raise SystemExit(
                f"opencode preflight model availability {stream} log does not exist: "
                f"{repo_relative(report_path, repo_root=repo_root)}"
            )
        expected_sha256 = model_availability.get(f"{stream}_sha256")
        log_text = log_path.read_text(encoding="utf-8")
        actual_sha256 = sha256_text(log_text)
        if expected_sha256 != actual_sha256:
            raise SystemExit(
                f"opencode preflight model availability {stream} hash mismatch: "
                f"{repo_relative(report_path, repo_root=repo_root)}"
            )
        if stream == "stdout":
            required_model = str(model_availability.get("required_model", ""))
            if not opencode_models_output_mentions_required_model(log_text, required_model):
                raise SystemExit(
                    f"opencode preflight model availability stdout missing {required_model}: "
                    f"{repo_relative(report_path, repo_root=repo_root)}"
                )


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


def opencode_models_output_sample(stdout: str, *, limit: int = 40) -> list[str]:
    sample: list[str] = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        sample.append(stripped[:240])
        if len(sample) >= limit:
            break
    return sample


def run_opencode_model_availability_probe(
    *,
    opencode_command: str,
    opencode_model: str | None,
    logs_dir: Path,
    opencode_process_env: dict[str, str],
    timeout_seconds: int,
    command_runner: Any,
    repo_root: Path,
    opencode_allow_non_competition_model: bool = False,
) -> dict[str, Any]:
    if opencode_model is None:
        opencode_model = COMPETITION_OPENCODE_MODEL
    if opencode_model != COMPETITION_OPENCODE_MODEL and not opencode_allow_non_competition_model:
        raise SystemExit(f"opencode_model must be {COMPETITION_OPENCODE_MODEL}")
    argv = build_opencode_models_argv(opencode_command=opencode_command)
    report_argv = portable_opencode_evidence_argv(
        argv,
        opencode_command=opencode_command,
    )
    started = time.monotonic()
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
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    stdout_path = logs_dir / "opencode-models.stdout.log"
    stderr_path = logs_dir / "opencode-models.stderr.log"
    atomic_write_text(stdout_path, stdout)
    atomic_write_text(stderr_path, stderr)
    returncode = int(completed.returncode)
    timed_out = completed_process_timed_out(completed)
    model_listed = returncode == 0 and opencode_models_output_mentions_required_model(stdout, opencode_model)
    if model_listed:
        status = "available"
        failure_reason = ""
    elif returncode == 0:
        status = "unavailable"
        failure_reason = "required_model_not_listed"
    elif timed_out:
        status = "probe_failed"
        failure_reason = "models_command_timeout"
    else:
        status = "probe_failed"
        failure_reason = "models_command_failed"
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "failure_reason": failure_reason,
        "opencode_command": opencode_command,
        "required_model": opencode_model,
        "argv": report_argv,
        "process_returncode": returncode,
        "elapsed_seconds": int(time.monotonic() - started),
        "model_listed": model_listed,
        "listed_model_sample": opencode_models_output_sample(stdout),
        "stdout_sha256": sha256_text(stdout),
        "stderr_sha256": sha256_text(stderr),
        "logs": {
            "stdout": repo_relative(stdout_path, repo_root=repo_root),
            "stderr": repo_relative(stderr_path, repo_root=repo_root),
        },
        "evidence_boundary": "model availability probe is a launch gate only; it is not semantic acceptance",
    }
    if timed_out:
        result["timed_out"] = True
        result["timeout_seconds"] = timeout_seconds
    return result


def opencode_contract_not_observed(
    *,
    worker_command: list[str],
    summary_path: Path,
    reason: str,
    repo_root: Path,
) -> dict[str, Any]:
    expected_worker_command_line = shell_command_line(worker_command)
    return {
        "expected_worker_command_line": expected_worker_command_line,
        "expected_summary_path": repo_relative(summary_path, repo_root=repo_root),
        "expected_worker_command_sha256": sha256_text(expected_worker_command_line),
        "executed_shell_command_count": 0,
        "executed_shell_commands": [],
        "first_tool_name": "",
        "first_shell_command": "",
        "first_shell_tool_name": "",
        "first_shell_workdir_status": "not_observed",
        "expected_workdir_status": "repo_root",
        "first_shell_command_matches_worker_command": False,
        "first_shell_workdir_matches_repo_root": False,
        "tools_before_first_shell": [],
        "contract_failure_reason": reason,
        "worker_command_seen": False,
        "summary_exists": summary_path.exists(),
        "status": "not-observed",
    }


def write_opencode_not_launched_session_evidence(
    *,
    evidence_path: Path,
    stdout_path: Path,
    stderr_path: Path,
    root_cause_key: str,
    opencode_runtime_env: dict[str, Any],
    repo_root: Path,
) -> dict[str, str]:
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "status": "not-launched",
        "root_cause_key": root_cause_key,
        "process_returncode": None,
        "stdout_path": repo_relative(stdout_path, repo_root=repo_root),
        "stderr_path": repo_relative(stderr_path, repo_root=repo_root),
        "opencode_runtime_env": opencode_runtime_env,
        "evidence_boundary": "OpenCode run was not launched because a preflight launch gate failed",
    }
    atomic_write_json(evidence_path, evidence)
    return {"path": repo_relative(evidence_path, repo_root=repo_root), "sha256": sha256_file(evidence_path)}


def portable_python_script_argv(script: str, *args: str) -> list[str]:
    return [*portable_python_command_argv(), "-B", script, *args]


def portable_python_module_argv(module: str, *args: str) -> list[str]:
    return [PORTABLE_PYTHON_COMMAND, "-B", "-m", module, *args]


def portable_python_command_argv() -> list[str]:
    global _RESOLVED_PYTHON_COMMAND
    override = os.environ.get(PYTHON_COMMAND_OVERRIDE_ENV)
    if override:
        return shlex.split(override, posix=os.name != "nt")
    if _RESOLVED_PYTHON_COMMAND is not None:
        return list(_RESOLVED_PYTHON_COMMAND)
    candidates: list[list[str]] = [[PORTABLE_PYTHON_COMMAND], ["python"]]
    if os.name == "nt":
        candidates.append(["py", "-3"])
    for candidate in candidates:
        if python_command_is_runnable(candidate):
            _RESOLVED_PYTHON_COMMAND = candidate
            return list(candidate)
    _RESOLVED_PYTHON_COMMAND = [PORTABLE_PYTHON_COMMAND]
    return list(_RESOLVED_PYTHON_COMMAND)


def python_command_is_runnable(candidate: list[str]) -> bool:
    try:
        completed = subprocess.run(
            [*candidate, "-B", "-c", "import sys"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return int(completed.returncode) == 0


def shell_command_line(argv: list[str]) -> str:
    return shlex.join([str(item) for item in argv])


def build_opencode_run_argv(
    *,
    opencode_command: str,
    opencode_model: str | None,
    opencode_agent: str | None,
    opencode_variant: str,
    opencode_skip_permissions: bool,
    worker_command: list[str],
    request_path: Path,
    summary_path: Path,
    repo_root: Path,
    handoff_contract_path: Path | None = None,
    opencode_allow_non_competition_model: bool = False,
) -> list[str]:
    launch_policy = opencode_launch_policy(
        opencode_command=opencode_command,
        opencode_model=opencode_model,
        opencode_agent=opencode_agent,
        opencode_variant=opencode_variant,
        opencode_skip_permissions=opencode_skip_permissions,
        opencode_allow_non_competition_model=opencode_allow_non_competition_model,
    )
    command_line = shell_command_line(worker_command)
    prompt_lines = [
        "Execute this assigned C-to-Rust worker exactly once.",
        "Use the shell/bash tool to run exactly the Command line string below.",
        "The first shell/bash/powershell/cmd tool call must be exactly the Command line string.",
        "Do not run init-run, assign-slice, retry-worker, or any other substitute harness command.",
        "Do not inspect an existing summary before running the command.",
        "The harness has already removed any stale expected summary before launching OpenCode.",
        "Run the repo-local deterministic command below, then stop.",
        "Do not call glob/read/grep/list/edit or any non-shell tool before the exact Command line.",
        "Do not explore files, spawn subagents, or infer a different slice before executing the command.",
        "Do not run substitute diagnostics instead of the command.",
        "Do not treat chat output as evidence; the required artifact is the competition-run-summary JSON.",
        f"Command: {json.dumps(worker_command)}",
        f"Command line: {command_line}",
        f"Request: {repo_relative(request_path, repo_root=repo_root)}",
        f"Expected summary: {repo_relative(summary_path, repo_root=repo_root)}",
    ]
    if handoff_contract_path is not None:
        prompt_lines.extend(
            [
                "Handoff contract is audit metadata; do not inspect it before the first command.",
                f"Handoff contract: {repo_relative(handoff_contract_path, repo_root=repo_root)}",
            ]
        )
    prompt = build_opencode_prompt(prompt_lines)
    resolved_opencode_command = resolve_subprocess_command(launch_policy["opencode_command"])
    argv = [
        resolved_opencode_command,
        "run",
        "--dir",
        str(repo_root),
        "--format",
        "json",
        "--variant",
        launch_policy["opencode_variant"],
    ]
    argv.extend(["--model", launch_policy["opencode_model"]])
    argv.extend(["--agent", launch_policy["opencode_agent"]])
    if launch_policy["opencode_skip_permissions"]:
        argv.append("--dangerously-skip-permissions")
    argv.append(prompt)
    return argv


def build_opencode_preflight_argv(
    *,
    opencode_command: str,
    opencode_model: str | None,
    opencode_agent: str | None,
    opencode_variant: str,
    opencode_skip_permissions: bool,
    marker_command: list[str],
    marker_path: Path,
    contract_path: Path,
    repo_root: Path,
    opencode_allow_non_competition_model: bool = False,
) -> list[str]:
    launch_policy = opencode_launch_policy(
        opencode_command=opencode_command,
        opencode_model=opencode_model,
        opencode_agent=opencode_agent,
        opencode_variant=opencode_variant,
        opencode_skip_permissions=opencode_skip_permissions,
        opencode_allow_non_competition_model=opencode_allow_non_competition_model,
    )
    command_line = shell_command_line(marker_command)
    prompt = build_opencode_prompt(
        [
            "Execute this OpenCode preflight command exactly once.",
            "Use the shell/bash tool to run exactly the Command line string below.",
            "The first shell/bash/powershell/cmd tool call must be exactly the Command line string.",
            "Do not call glob/read/grep/list/edit or any non-shell tool before the exact Command line.",
            "Do not inspect repository files or infer a different task before executing the command.",
            "Do not run init-run, assign-slice, run-worker, retry-worker, or any substitute harness command.",
            "After the command exits, stop immediately; do not run a second shell/read/list command.",
            "The required artifact is the preflight marker JSON, not chat output.",
            f"Command: {json.dumps(marker_command)}",
            f"Command line: {command_line}",
            f"Expected marker: {repo_relative(marker_path, repo_root=repo_root)}",
            "Handoff contract is audit metadata; do not inspect it before the first command.",
            f"Handoff contract: {repo_relative(contract_path, repo_root=repo_root)}",
        ]
    )
    resolved_opencode_command = resolve_subprocess_command(launch_policy["opencode_command"])
    argv = [
        resolved_opencode_command,
        "run",
        "--dir",
        str(repo_root),
        "--format",
        "json",
        "--variant",
        launch_policy["opencode_variant"],
    ]
    argv.extend(["--model", launch_policy["opencode_model"]])
    argv.extend(["--agent", launch_policy["opencode_agent"]])
    if launch_policy["opencode_skip_permissions"]:
        argv.append("--dangerously-skip-permissions")
    argv.append(prompt)
    return argv


def resolve_subprocess_command(command: str) -> str:
    if not command:
        raise SystemExit("opencode command must not be empty")
    if "/" in command or "\\" in command or Path(command).is_absolute():
        return command
    return shutil.which(command) or command


def build_opencode_prompt(prompt_lines: list[str]) -> str:
    return " ".join(line.strip() for line in prompt_lines if line.strip())


def verify_opencode_contract_execution(
    *,
    session_evidence: dict[str, Any],
    worker_command: list[str],
    summary_path: Path,
    repo_root: Path,
    allow_post_contract_artifact_inspection: bool = False,
) -> dict[str, Any]:
    expected_worker_command_line = shell_command_line(worker_command)
    tool_trace = extract_opencode_tool_trace(session_evidence)
    executed_shell_commands = extract_opencode_shell_commands(session_evidence)
    exact_worker_command_seen = any(
        command_matches_for_contract(command, expected_worker_command_line) for command in executed_shell_commands
    )
    first_shell_command = executed_shell_commands[0] if executed_shell_commands else ""
    first_tool_name = str(tool_trace[0]["tool"]) if tool_trace else ""
    first_shell_index = next(
        (index for index, item in enumerate(tool_trace) if item.get("is_shell_command")),
        None,
    )
    first_shell_tool_name = str(tool_trace[first_shell_index]["tool"]) if first_shell_index is not None else ""
    first_shell_workdir = (
        str(tool_trace[first_shell_index].get("workdir", "")) if first_shell_index is not None else ""
    )
    tools_before_first_shell = [
        str(item["tool"]) for item in tool_trace[:first_shell_index]
    ] if first_shell_index is not None else [str(item["tool"]) for item in tool_trace[:20]]
    first_shell_command_matches_worker_command = (
        bool(first_shell_command) and command_matches_for_contract(first_shell_command, expected_worker_command_line)
    )
    summary_exists = summary_path.exists()
    workdir_reported = bool(first_shell_workdir)
    workdir_matches_repo_root = opencode_workdir_matches_repo_root(first_shell_workdir, repo_root=repo_root)
    workdir_inferred_from_expected_artifact = (
        not workdir_reported
        and first_shell_command_matches_worker_command
        and summary_exists
    )
    workdir_satisfies_contract = workdir_matches_repo_root or workdir_inferred_from_expected_artifact
    post_contract_shell_commands = executed_shell_commands[1:] if first_shell_command_matches_worker_command else []
    post_contract_artifact_inspection_only = (
        allow_post_contract_artifact_inspection
        and bool(post_contract_shell_commands)
        and summary_exists
        and all(
            is_post_contract_artifact_inspection_command(
                command,
                artifact_path=summary_path,
                repo_root=repo_root,
            )
            for command in post_contract_shell_commands
        )
    )
    shell_count_satisfies_contract = len(executed_shell_commands) == 1 or post_contract_artifact_inspection_only
    status = "not-observed"
    if executed_shell_commands:
        status = (
            "executed"
            if (
                first_shell_command_matches_worker_command
                and workdir_satisfies_contract
                and not tools_before_first_shell
                and shell_count_satisfies_contract
            )
            else "not-executed"
        )
    contract_failure_reason = ""
    if status == "not-observed":
        contract_failure_reason = "no_shell_command_observed"
    elif status == "not-executed":
        if tools_before_first_shell:
            contract_failure_reason = "tool_before_first_shell_command"
        elif not workdir_satisfies_contract:
            contract_failure_reason = "opencode_workdir_mismatch"
        elif len(executed_shell_commands) > 1 and first_shell_command_matches_worker_command:
            contract_failure_reason = (
                "extra_shell_command_after_contract"
                if not allow_post_contract_artifact_inspection
                else "non_artifact_inspection_shell_command_after_contract"
            )
        else:
            contract_failure_reason = (
                "first_shell_command_mismatch_worker_command_seen_later"
                if exact_worker_command_seen
                else "first_shell_command_mismatch"
            )
    return {
        "expected_worker_command_line": expected_worker_command_line,
        "expected_summary_path": repo_relative(summary_path, repo_root=repo_root),
        "expected_worker_command_sha256": sha256_text(expected_worker_command_line),
        "executed_shell_command_count": len(executed_shell_commands),
        "executed_shell_commands": executed_shell_commands[:20],
        "post_contract_shell_command_count": len(post_contract_shell_commands),
        "post_contract_shell_commands": post_contract_shell_commands[:20],
        "allow_post_contract_artifact_inspection": allow_post_contract_artifact_inspection,
        "post_contract_artifact_inspection_only": post_contract_artifact_inspection_only,
        "first_tool_name": first_tool_name,
        "first_shell_command": first_shell_command,
        "first_shell_tool_name": first_shell_tool_name,
        "first_shell_workdir_status": (
            "repo_root"
            if workdir_matches_repo_root
            else "repo_root_inferred_from_expected_artifact"
            if workdir_inferred_from_expected_artifact
            else "non_repo_root"
        ),
        "expected_workdir_status": "repo_root",
        "first_shell_command_matches_worker_command": first_shell_command_matches_worker_command,
        "first_shell_workdir_matches_repo_root": workdir_satisfies_contract,
        "first_shell_workdir_reported": workdir_reported,
        "first_shell_workdir_inferred_from_expected_artifact": workdir_inferred_from_expected_artifact,
        "tools_before_first_shell": tools_before_first_shell[:20],
        "contract_failure_reason": contract_failure_reason,
        "worker_command_seen": exact_worker_command_seen,
        "summary_exists": summary_exists,
        "status": status,
    }


def is_post_contract_artifact_inspection_command(
    command: str,
    *,
    artifact_path: Path,
    repo_root: Path,
) -> bool:
    compact = " ".join(command.strip().split())
    lower = compact.lower()
    if any(token in lower for token in (";", "&&", "||", ">", " set-content", " remove-item", " del ", " rm ")):
        return False
    rel_posix = repo_relative(artifact_path, repo_root=repo_root)
    rel_windows = rel_posix.replace("/", "\\")
    artifact_abs = str(artifact_path)
    normalized_command = compact.replace("\\", "/")
    normalized_candidates = {
        rel_posix,
        rel_windows.replace("\\", "/"),
        artifact_abs.replace("\\", "/"),
    }
    if not any(candidate and candidate in normalized_command for candidate in normalized_candidates):
        return False
    allowed_prefixes = (
        "get-item -literalpath ",
        "test-path -literalpath ",
        "get-content -literalpath ",
        "dir ",
        "ls ",
        "type ",
        "cat ",
    )
    return lower.startswith(allowed_prefixes)


def extract_opencode_tool_trace(session_evidence: dict[str, Any]) -> list[dict[str, Any]]:
    events = opencode_session_events(session_evidence)
    tools: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        part = event.get("part")
        if not isinstance(part, dict):
            continue
        tool = str(part.get("tool", "")).lower().strip()
        if not tool:
            continue
        command = ""
        state = part.get("state")
        if isinstance(state, dict):
            tool_input = state.get("input")
            if isinstance(tool_input, dict):
                raw_command = tool_input.get("command") or tool_input.get("cmd")
                if isinstance(raw_command, str):
                    command = raw_command.strip()
                raw_workdir = tool_input.get("workdir") or tool_input.get("cwd")
                workdir = raw_workdir.strip() if isinstance(raw_workdir, str) else ""
            else:
                workdir = ""
        else:
            workdir = ""
        tools.append(
            {
                "tool": tool,
                "command": command,
                "workdir": workdir,
                "is_shell_command": tool in {"bash", "shell", "cmd", "powershell"} and bool(command),
            }
        )
    return tools


def opencode_workdir_matches_repo_root(workdir: str, *, repo_root: Path) -> bool:
    if not workdir:
        return False
    try:
        observed = normalize_windows_extended_path(Path(workdir).resolve())
        expected = normalize_windows_extended_path(repo_root.resolve())
    except OSError:
        return False
    return observed == expected


def extract_opencode_shell_commands(session_evidence: dict[str, Any]) -> list[str]:
    events = opencode_session_events(session_evidence)
    commands: list[str] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        part = event.get("part")
        if not isinstance(part, dict):
            continue
        tool = str(part.get("tool", "")).lower()
        if tool not in {"bash", "shell", "cmd", "powershell"}:
            continue
        state = part.get("state")
        if not isinstance(state, dict):
            continue
        tool_input = state.get("input")
        if not isinstance(tool_input, dict):
            continue
        command = tool_input.get("command") or tool_input.get("cmd")
        if isinstance(command, str) and command.strip():
            commands.append(command.strip())
    return commands


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


def parse_opencode_stdout_session(stdout: str) -> dict[str, Any]:
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


def normalize_command_for_contract(command: str) -> str:
    return " ".join(command.strip().split())


def command_matches_for_contract(observed_command: str, expected_command: str) -> bool:
    if normalize_command_for_contract(observed_command) == normalize_command_for_contract(expected_command):
        return True
    observed_argv = shell_argv_for_contract(observed_command)
    expected_argv = shell_argv_for_contract(expected_command)
    return bool(observed_argv) and observed_argv == expected_argv


def shell_argv_for_contract(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return []


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_blocked_worker_summary(
    *,
    run_id: str,
    proof_class: str,
    worker_id: str,
    request: dict[str, Any],
    root_cause_key: str,
    process_returncode: int,
    exit_code: int,
    elapsed_seconds: int,
    summary_path: Path,
    metrics_path: Path,
    opencode_contract_verification: dict[str, Any] | None,
    handoff_contract: dict[str, Any] | None,
    opencode_session_evidence: dict[str, Any] | None,
    repo_root: Path,
) -> None:
    worker_run_id = worker_request_run_id(request, worker_id=worker_id)
    target_id = str(request.get("target_id", "unknown"))
    slice_id = str(request.get("slice_id", "unknown"))
    unit_status = {
        "unit_id": f"{target_id}/{slice_id}",
        "source": "opencode-worker",
        "status": "blocked",
        "compiled": False,
        "semantic_pass": False,
        "refused": False,
        "blocked": True,
        "failed": False,
        "root_cause_key": root_cause_key,
        "process_returncode": process_returncode,
        "exit_code": exit_code,
        "worker_id": worker_id,
    }
    if opencode_contract_verification is not None:
        unit_status["opencode_contract_verification"] = opencode_contract_verification
    if handoff_contract is not None:
        unit_status["handoff_contract"] = handoff_contract
    if opencode_session_evidence is not None:
        unit_status["opencode_session_evidence"] = opencode_session_evidence

    metrics = {
        "schema_version": SCHEMA_VERSION,
        "run_id": worker_run_id,
        "proof_class": proof_class,
        "units_total": 1,
        "units_converged": 0,
        "units_baseline_only": 0,
        "unsafe_reduction": {
            "status": "not_measured",
            "baseline_total_unsafe": None,
            "current_total_unsafe": None,
            "reduced_by": None,
            "ratio": 0.0,
        },
        "avg_repair_rounds": 0.0,
        "auto_recovery_rate": 0.0,
        "human_interventions": 0,
        "always_compiles": False,
        "always_equivalent": False,
        "fail_closed_count": 1,
        "root_cause_counts": {root_cause_key: 1},
        "wall_clock_seconds": max(0, elapsed_seconds),
        "llm_calls": 1,
        "per_unit_statuses": [unit_status],
    }
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(metrics_path, metrics)

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "run_id": worker_run_id,
        "proof_class": proof_class,
        "profile_id": PROFILE_ID,
        "profile_sha256": sha256_file(repo_root / "config" / "competition-env" / "environment.json"),
        "clang_source": "missing",
        "cargo_mirror_activation": {
            "method": "CARGO_HOME",
            "path": "config/competition-env/cargo",
            "config_file": "config/competition-env/cargo/config.toml",
        },
        "elapsed_seconds": max(0, elapsed_seconds),
        "translator_version": "opencode-agent-harness",
        "slices": {
            "attempted": 1,
            "typed_ir_generated": 0,
            "compiled": 0,
            "semantic_pass": 0,
            "refused": 0,
            "blocked": 1,
            "failed": 0,
        },
        "unsafe_budget": {
            "status": "passed",
            "total_first_party_non_test_unsafe": 0,
            "ratio": 0.0,
        },
        "workflow_metrics": {
            "path": metrics_path.name,
            "sha256": sha256_file(metrics_path),
        },
        "artifact_roots": [
            "target/competition-out/evidence",
            "target/competition-out/summary",
            "target/competition-out/logs",
        ],
        "final_gate": {
            "status": "blocked",
            "validator": "opencode_agent_harness.py run-worker --mode opencode",
        },
    }
    atomic_write_json(summary_path, summary)


def write_opencode_handoff_contract(
    *,
    run_id: str,
    worker_id: str,
    attempt_number: int,
    request_path: Path,
    summary_path: Path,
    contract_path: Path,
    worker_command: list[str],
    opencode_argv: list[str],
    launch_policy: dict[str, Any],
    repo_root: Path,
    opencode_runtime_env: dict[str, Any] | None = None,
    assignment_request_path: Path | None = None,
) -> dict[str, str]:
    if not opencode_argv:
        raise SystemExit("opencode argv must not be empty")
    contract = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "worker_id": worker_id,
        "attempt": attempt_number,
        "runner_kind": "opencode-run",
        "request_path": repo_relative(request_path, repo_root=repo_root),
        "expected_summary_path": repo_relative(summary_path, repo_root=repo_root),
        "worker_command": worker_command,
        "worker_command_line": shell_command_line(worker_command),
        "worker_command_sha256": sha256_text(shell_command_line(worker_command)),
        "opencode_argv": opencode_argv,
        "opencode_command_line": shell_command_line(opencode_argv),
        "launch_policy": launch_policy,
        "launch_policy_sha256": opencode_launch_policy_sha256(launch_policy),
        "prompt": str(opencode_argv[-1]),
        "evidence_boundary": "chat output is diagnostic only; semantic acceptance requires the expected summary and validators",
    }
    if opencode_runtime_env is not None:
        contract["opencode_runtime_env"] = opencode_runtime_env
    if assignment_request_path is not None:
        contract["assignment_request_path"] = repo_relative(assignment_request_path, repo_root=repo_root)
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(contract_path, contract)
    return {"path": repo_relative(contract_path, repo_root=repo_root), "sha256": sha256_file(contract_path)}


def write_opencode_preflight_contract(
    *,
    run_id: str,
    contract_path: Path,
    marker_path: Path,
    marker_command: list[str],
    opencode_argv: list[str],
    launch_policy: dict[str, Any],
    repo_root: Path,
    opencode_runtime_env: dict[str, Any] | None = None,
) -> dict[str, str]:
    if not opencode_argv:
        raise SystemExit("opencode argv must not be empty")
    contract = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "runner_kind": "opencode-preflight",
        "expected_marker_path": repo_relative(marker_path, repo_root=repo_root),
        "worker_command": marker_command,
        "worker_command_line": shell_command_line(marker_command),
        "worker_command_sha256": sha256_text(shell_command_line(marker_command)),
        "opencode_argv": opencode_argv,
        "opencode_command_line": shell_command_line(opencode_argv),
        "launch_policy": launch_policy,
        "launch_policy_sha256": opencode_launch_policy_sha256(launch_policy),
        "prompt": str(opencode_argv[-1]),
        "evidence_boundary": "preflight proves exact-command compliance only; semantic acceptance requires worker summary and validators",
    }
    if opencode_runtime_env is not None:
        contract["opencode_runtime_env"] = opencode_runtime_env
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(contract_path, contract)
    return {"path": repo_relative(contract_path, repo_root=repo_root), "sha256": sha256_file(contract_path)}


def write_opencode_session_evidence(
    *,
    completed: subprocess.CompletedProcess[str],
    evidence_path: Path,
    stdout_path: Path,
    stderr_path: Path,
    repo_root: Path,
    opencode_runtime_env: dict[str, Any] | None = None,
) -> dict[str, str]:
    stdout = completed.stdout or ""
    evidence: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "process_returncode": int(completed.returncode),
        "stdout_path": repo_relative(stdout_path, repo_root=repo_root),
        "stderr_path": repo_relative(stderr_path, repo_root=repo_root),
        "stdout_sha256": sha256_file(stdout_path),
        "stderr_sha256": sha256_file(stderr_path),
    }
    if opencode_runtime_env is not None:
        evidence["opencode_runtime_env"] = opencode_runtime_env
    evidence.update(parse_opencode_stdout_session(stdout))
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(evidence_path, evidence)
    return {"path": repo_relative(evidence_path, repo_root=repo_root), "sha256": sha256_file(evidence_path)}


def write_merge_plan(
    *,
    db_path: Path,
    run_id: str,
    out_root: Path,
    proof_class: str,
    worker_summary_paths: list[str] | None = None,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    db_path = repo_path(db_path, repo_root=repo_root)
    out_root = repo_path(out_root, repo_root=repo_root)
    if worker_summary_paths is None:
        with closing(connect(db_path)) as connection:
            ensure_schema(connection)
            rows = connection.execute(
                """
                select repo_rel_path from artifacts
                where run_id=? and kind='competition-run-summary'
                order by repo_rel_path
                """,
                (run_id,),
            ).fetchall()
        summaries = [row[0] for row in rows]
    else:
        summaries = [
            repo_relative(repo_path(Path(summary), repo_root=repo_root), repo_root=repo_root)
            for summary in worker_summary_paths
        ]
    argv = portable_python_script_argv("validation/tools/run_competition.py")
    for summary in summaries:
        argv.extend(["--worker-summary", summary])
    argv.extend(["--out-root", repo_relative(out_root, repo_root=repo_root), "--proof-class", proof_class, "--run-id", run_id])
    merge_plan = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "path": repo_relative(out_root / "harness" / "merge-plan.json", repo_root=repo_root),
        "worker_summaries": summaries,
        "argv": argv,
        "validator": "validation/tools/validate_competition_run_summary.py",
    }
    merge_path = out_root / "harness" / "merge-plan.json"
    merge_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(merge_path, merge_plan)
    return merge_plan


def finalize_run(
    *,
    db_path: Path,
    run_id: str,
    status: str,
    summary_path: Path,
    final_gate_status: str | None = None,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    db_path = repo_path(db_path, repo_root=repo_root)
    summary_path = repo_path(summary_path, repo_root=repo_root)
    summary_rel = repo_relative(summary_path, repo_root=repo_root)
    summary_hash = sha256_file(summary_path)
    now = now_text()
    with closing(connect(db_path)) as connection:
        ensure_schema(connection)
        cursor = connection.execute(
            """
            update runs
            set status=?, ended_at=?, summary_path=?, summary_sha256=?,
                final_gate_status=coalesce(?, final_gate_status)
            where run_id=?
            """,
            (status, now, summary_rel, summary_hash, final_gate_status, run_id),
        )
        if cursor.rowcount == 0:
            raise SystemExit(f"unknown run_id: {run_id}")
        record_event(
            connection,
            run_id=run_id,
            event_type="run_finalized",
            payload={
                "status": status,
                "final_gate_status": final_gate_status,
                "summary_path": summary_rel,
                "summary_sha256": summary_hash,
            },
        )
        connection.commit()
    return {
        "status": "finalized",
        "run_id": run_id,
        "summary_path": summary_rel,
        "summary_sha256": summary_hash,
    }
