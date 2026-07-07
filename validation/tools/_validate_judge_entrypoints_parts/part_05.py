def resume_manifest_worker_id_from_repair_hint_id(hint_id: str, *, run_id: str) -> str | None:
    prefix = f"repair:{run_id}:"
    if not hint_id.startswith(prefix):
        return None
    remainder = hint_id[len(prefix) :]
    if ":" not in remainder:
        return None
    worker_id, _root_cause = remainder.rsplit(":", 1)
    return worker_id or None


def validate_resume_manifest_replay_command(
    value: Any,
    *,
    label: str,
    expected_subcommand: str,
    worker: dict[str, Any],
    worker_id: str,
    run_id: str,
    ledger_path: str,
    require_hint: bool,
    expected_hint_ids: set[str] | None = None,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    command_payload = require_object(value, label)
    replay_safety = require_object(command_payload.get("replay_safety"), f"{label}.replay_safety")
    if replay_safety.get("status") != "ready":
        raise ValueError(f"{label}.replay_safety.status must be ready")
    argv = command_payload.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv):
        raise ValueError(f"{label}.argv must be a non-empty string list")
    command = require_string(command_payload.get("command"), f"{label}.command")
    if shlex.split(command, posix=True) != argv:
        raise ValueError(f"{label}.command must match argv")
    for argument in argv:
        assert_no_local_absolute_path(argument)
    assert_no_local_absolute_path(command)
    expected_prefix = ["python3", "-B", "-m", "validation.tools.opencode_agent_harness", expected_subcommand]
    if argv[: len(expected_prefix)] != expected_prefix:
        raise ValueError(f"{label} command must run opencode_agent_harness {expected_subcommand}")
    flags = argv_flags(argv, label=label)
    if flags.get("--db") != ledger_path:
        raise ValueError(f"resume_manifest worker {worker_id} {label} --db must match ledger.path")
    if flags.get("--run-id") != run_id:
        raise ValueError(f"resume_manifest worker {worker_id} {label} --run-id must match run_id")
    if flags.get("--worker-id") != worker_id:
        raise ValueError(f"resume_manifest worker {worker_id} {label} --worker-id must match worker_id")
    mode = flags.get("--mode")
    if mode not in {"deterministic", "opencode"}:
        raise ValueError(f"resume_manifest worker {worker_id} {label} --mode must be deterministic or opencode")
    hint_id = flags.get("--hint-id")
    if require_hint and not hint_id:
        raise ValueError(f"resume_manifest worker {worker_id} {label} command must include --hint-id")
    if require_hint and expected_hint_ids is not None and hint_id not in expected_hint_ids:
        raise ValueError(
            f"resume_manifest worker {worker_id} {label} --hint-id must match an open repair_hints entry for worker"
        )
    if not require_hint and hint_id:
        raise ValueError(f"resume_manifest worker {worker_id} {label} command must not include --hint-id")
    preflight = worker.get("opencode_preflight_report")
    if mode == "opencode":
        if not isinstance(preflight, dict) or not isinstance(preflight.get("path"), str):
            raise ValueError(f"resume_manifest worker {worker_id} {label} opencode_preflight_report is required")
        if preflight.get("status") != "passed":
            raise ValueError(f"resume_manifest worker {worker_id} {label} opencode_preflight_report.status must be passed")
        if not is_sha256_hex(preflight.get("sha256")):
            raise ValueError(f"resume_manifest worker {worker_id} {label} opencode_preflight_report.sha256 must be a sha256")
        preflight_path = require_string(preflight.get("path"), f"resume_manifest worker {worker_id} {label} opencode_preflight_report.path")
        preflight_file = repo_path(preflight_path, repo_root=repo_root)
        if not preflight_file.is_file():
            raise ValueError(f"resume_manifest worker {worker_id} {label} opencode_preflight_report.path missing")
        if sha256_file(preflight_file) != preflight["sha256"]:
            raise ValueError(f"resume_manifest worker {worker_id} {label} opencode_preflight_report.sha256 mismatch")
        if preflight.get("contract_status") != "executed":
            raise ValueError(
                f"resume_manifest worker {worker_id} {label} opencode_preflight_report.contract_status must be executed"
            )
        if flags.get("--opencode-preflight-report") != preflight["path"]:
            raise ValueError(
                f"resume_manifest worker {worker_id} {label} --opencode-preflight-report must match opencode_preflight_report.path"
            )
        if flags.get("--opencode-model") != COMPETITION_OPENCODE_MODEL:
            raise ValueError(
                f"resume_manifest worker {worker_id} {label} --opencode-model must be {COMPETITION_OPENCODE_MODEL}"
            )
        if flags.get("--opencode-agent") != COMPETITION_OPENCODE_AGENT:
            raise ValueError(
                f"resume_manifest worker {worker_id} {label} --opencode-agent must be {COMPETITION_OPENCODE_AGENT}"
            )
        if flags.get("--opencode-variant") != COMPETITION_OPENCODE_VARIANT:
            raise ValueError(
                f"resume_manifest worker {worker_id} {label} --opencode-variant must be {COMPETITION_OPENCODE_VARIANT}"
            )
        policy = preflight.get("launch_policy")
        if not isinstance(policy, dict) or policy.get("opencode_model") != COMPETITION_OPENCODE_MODEL:
            raise ValueError(
                f"resume_manifest worker {worker_id} {label} opencode_preflight_report.launch_policy.opencode_model "
                f"must be {COMPETITION_OPENCODE_MODEL}"
            )
        if policy.get("opencode_variant") != COMPETITION_OPENCODE_VARIANT:
            raise ValueError(
                f"resume_manifest worker {worker_id} {label} opencode_preflight_report.launch_policy.opencode_variant "
                f"must be {COMPETITION_OPENCODE_VARIANT}"
            )
        if policy.get("opencode_agent") != COMPETITION_OPENCODE_AGENT:
            raise ValueError(
                f"resume_manifest worker {worker_id} {label} opencode_preflight_report.launch_policy.opencode_agent "
                f"must be {COMPETITION_OPENCODE_AGENT}"
            )
        validate_opencode_preflight_binding(
            preflight,
            f"resume_manifest worker {worker_id} {label} opencode_preflight_report",
            repo_root=repo_root,
        )
    for field in ("assignment_path", "request_path", "summary_path", "report_path"):
        expected = worker.get(field)
        if isinstance(expected, str) and command_payload.get(field) != expected:
            raise ValueError(f"resume_manifest worker {worker_id} {label}.{field} must match worker {field}")
    expected_out_root = worker.get("isolated_out_root") or worker.get("out_root")
    if isinstance(expected_out_root, str) and command_payload.get("out_root") != expected_out_root:
        raise ValueError(f"resume_manifest worker {worker_id} {label}.out_root must match worker out_root")
    for field in ("assignment_path", "request_path", "summary_path", "report_path", "out_root"):
        value_text = command_payload.get(field)
        if isinstance(value_text, str):
            assert_repo_relative_posix(value_text)
    return {"status": "passed", "subcommand": expected_subcommand, "mode": mode}


def is_sha256_hex(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def argv_flags(argv: list[str], *, label: str) -> dict[str, str]:
    flags: dict[str, str] = {}
    index = 0
    while index < len(argv):
        part = argv[index]
        if part.startswith("--") and index + 1 < len(argv) and not argv[index + 1].startswith("--"):
            if part in flags:
                raise ValueError(f"{label} duplicate {part}")
            flags[part] = argv[index + 1]
            index += 2
            continue
        index += 1
    return flags


def validate_resume_manifest_worker_consistency(
    workers: list[Any],
    *,
    context_payload: dict[str, Any] | None,
    agent_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if context_payload is None or agent_payload is None:
        return {"status": "skipped", "reason": "context or agent payload not provided"}
    context_workers = context_payload.get("workers")
    agents = agent_payload.get("agents")
    agents_by_worker_id = agent_payload.get("agents_by_worker_id")
    if not isinstance(context_workers, list) or not isinstance(agents, list) or not isinstance(agents_by_worker_id, dict):
        return {"status": "skipped", "reason": "context or agent worker collections not declared"}

    resume_ids = worker_ids_from_entries(workers, label="resume_manifest.workers")
    context_ids = worker_ids_from_entries(context_workers, label="context_pack.workers")
    agent_ids = worker_ids_from_entries(agents, label="agent_index.agents")
    indexed_ids = set(agents_by_worker_id)
    if resume_ids != context_ids or resume_ids != agent_ids or resume_ids != indexed_ids:
        raise ValueError(
            "resume_manifest.workers worker ids must match context_pack.workers and agent_index: "
            f"{sorted(resume_ids)} != {sorted(context_ids)} != {sorted(agent_ids)} != {sorted(indexed_ids)}"
        )

    resume_by_worker_id = entries_by_worker_id(workers, label="resume_manifest.workers")
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
        "isolated_out_root",
    )
    for worker_id in sorted(resume_ids):
        indexed_agent = require_object(agents_by_worker_id[worker_id], f"agents_by_worker_id.{worker_id}")
        payloads = [
            resume_by_worker_id[worker_id],
            context_by_worker_id[worker_id],
            agents_by_list_id[worker_id],
            indexed_agent,
        ]
        for field in comparable_fields:
            values = [payload.get(field) for payload in payloads if field in payload]
            if values and any(value != values[0] for value in values[1:]):
                raise ValueError(
                    f"resume_manifest worker {worker_id} field {field} must match context_pack and agent_index"
                )
        out_root_values = [
            payload.get("out_root")
            for payload in payloads
            if isinstance(payload.get("out_root"), str)
        ]
        isolated_values = [
            payload.get("isolated_out_root")
            for payload in payloads
            if isinstance(payload.get("isolated_out_root"), str)
        ]
        expected_isolated_out_root = isolated_values[0] if isolated_values else None
        if isolated_values and any(value != expected_isolated_out_root for value in isolated_values[1:]):
            raise ValueError(
                f"resume_manifest worker {worker_id} field isolated_out_root must match context_pack and agent_index"
            )
        if expected_isolated_out_root is not None:
            for out_root in out_root_values:
                if out_root != expected_isolated_out_root:
                    raise ValueError(
                        f"resume_manifest worker {worker_id} out_root must match isolated_out_root"
                    )

    return {"status": "passed", "worker_count": len(resume_ids)}


def validate_worker_plan_contract(
    worker_plan_payload: dict[str, Any],
    context_payload: dict[str, Any],
    agent_payload: dict[str, Any],
    *,
    path_text: str,
) -> dict[str, Any]:
    if worker_plan_payload.get("schema_version") != 1:
        raise ValueError("worker_plan.schema_version must be 1")
    if worker_plan_payload.get("status") != "planned":
        raise ValueError("worker_plan.status must be planned")
    raw_planning_mode = worker_plan_payload.get("planning_mode")
    if isinstance(raw_planning_mode, str) and raw_planning_mode:
        planning_mode = raw_planning_mode
    elif isinstance(worker_plan_payload.get("source_file"), str) and worker_plan_payload.get("source_file"):
        planning_mode = "source_file"
    else:
        raise ValueError("worker_plan.planning_mode must be a non-empty string")
    plan_path = require_string(worker_plan_payload.get("plan_path"), "worker_plan.plan_path")
    assert_repo_relative_posix(plan_path)
    if plan_path != path_text:
        raise ValueError("worker_plan.plan_path must match expected_artifacts.worker_plan")

    context_entrypoints = require_object(context_payload.get("entrypoints"), "context_pack.entrypoints")
    context_worker_plan = context_entrypoints.get("worker_plan")
    if isinstance(context_worker_plan, str) and context_worker_plan != path_text:
        raise ValueError("context_pack.entrypoints.worker_plan must match expected_artifacts.worker_plan")

    planner = agent_payload.get("planner")
    if isinstance(planner, dict):
        planner_path = planner.get("plan_path")
        if isinstance(planner_path, str) and planner_path != path_text:
            raise ValueError("agent_index.planner.plan_path must match expected_artifacts.worker_plan")

    units = worker_plan_payload.get("units")
    plan_worker_ids = worker_ids_from_entries(units, label="worker_plan.units")
    context_workers = context_payload.get("workers")
    agents = agent_payload.get("agents")
    agents_by_worker_id = require_object(agent_payload.get("agents_by_worker_id"), "agents_by_worker_id")
    context_worker_ids = worker_ids_from_entries(context_workers, label="context_pack.workers")
    agent_ids = worker_ids_from_entries(agents, label="agent_index.agents")
    indexed_ids = set(agents_by_worker_id)
    if plan_worker_ids != context_worker_ids or plan_worker_ids != agent_ids or plan_worker_ids != indexed_ids:
        raise ValueError(
            "worker_plan.units worker ids must match context_pack.workers and agent_index: "
            f"{sorted(plan_worker_ids)} != {sorted(context_worker_ids)} != {sorted(agent_ids)} != {sorted(indexed_ids)}"
        )

    units_by_worker_id = entries_by_worker_id(units, label="worker_plan.units")
    context_by_worker_id = entries_by_worker_id(context_workers, label="context_pack.workers")
    agents_by_list_id = entries_by_worker_id(agents, label="agent_index.agents")
    comparable_fields = (
        "assignment_path",
        "request_path",
        "slice_id",
        "function",
        "source_commit",
        "require_source_commit",
        "source_file",
        "source_repo_root",
        "source_repository",
        "source_branch",
        "source_sha256",
    )
    for worker_id in sorted(plan_worker_ids):
        unit = units_by_worker_id[worker_id]
        context_worker = context_by_worker_id[worker_id]
        listed_agent = agents_by_list_id[worker_id]
        indexed_agent = require_object(agents_by_worker_id[worker_id], f"agents_by_worker_id.{worker_id}")
        for field in comparable_fields:
            values = [payload.get(field) for payload in (unit, context_worker, listed_agent, indexed_agent) if field in payload]
            if values and any(value != values[0] for value in values[1:]):
                raise ValueError(f"worker {worker_id} field {field} must match across worker_plan, context_pack, and agent_index")
        for field in ("assignment_path", "request_path", "out_root", "slice_spec", "source_repo_root", "source_file"):
            value = unit.get(field)
            if isinstance(value, str):
                assert_repo_relative_posix(value)
        out_root = unit.get("out_root")
        isolated_out_root = indexed_agent.get("isolated_out_root")
        if isinstance(out_root, str) and isinstance(isolated_out_root, str) and out_root != isolated_out_root:
            raise ValueError(f"worker {worker_id} out_root must match agent_index isolated_out_root")

    if isinstance(planner, dict) and planner.get("worker_count") != len(plan_worker_ids):
        raise ValueError("agent_index.planner.worker_count must match worker_plan.units")

    return {
        "status": "passed",
        "path": path_text,
        "planning_mode": planning_mode,
        "worker_count": len(plan_worker_ids),
    }


def entrypoint_profile_workers_by_id(entrypoint: dict[str, Any], *, repo_root: Path) -> dict[str, dict[str, Any]] | None:
    if not entrypoint_requires_multi_worker(entrypoint):
        return None
    profile_ref = entrypoint.get("profile")
    if not isinstance(profile_ref, dict):
        return None
    profile_binding = validate_ref(profile_ref, repo_root=repo_root)
    profile = load_json(repo_path(profile_binding["path"], repo_root=repo_root))
    profile_worker_ids = worker_ids_from_entries(
        profile.get("workers"),
        label=f"{entrypoint.get('id')}.profile.workers",
    )
    if len(profile_worker_ids) < 2:
        raise ValueError(f"{entrypoint.get('id')} multi-worker profile workers must contain at least 2 workers")
    return entries_by_worker_id(profile.get("workers"), label=f"{entrypoint.get('id')}.profile.workers")


def worker_profile_plan_tuple(worker: dict[str, Any], *, label: str) -> dict[str, str]:
    return {
        field: require_string(worker.get(field), f"{label}.{field}")
        for field in PROFILE_WORKER_PLAN_TUPLE_FIELDS
    }


def validate_entrypoint_profile_worker_plan_contract(
    entrypoint: dict[str, Any],
    worker_plan_payload: dict[str, Any],
    *,
    repo_root: Path,
) -> dict[str, Any]:
    profile_workers = entrypoint_profile_workers_by_id(entrypoint, repo_root=repo_root)
    if profile_workers is None:
        return {"status": "skipped", "reason": "entrypoint is not profile-bound multi-worker"}
    profile_worker_ids = set(profile_workers)
    plan_worker_ids = worker_ids_from_entries(worker_plan_payload.get("units"), label="worker_plan.units")
    if plan_worker_ids != profile_worker_ids:
        raise ValueError(
            "worker_plan.units worker ids must match entrypoint profile workers: "
            f"{sorted(plan_worker_ids)} != {sorted(profile_worker_ids)}"
        )
    plan_workers = entries_by_worker_id(worker_plan_payload.get("units"), label="worker_plan.units")
    for worker_id in sorted(plan_worker_ids):
        profile_tuple = worker_profile_plan_tuple(
            profile_workers[worker_id],
            label=f"{entrypoint.get('id')}.profile.workers[{worker_id}]",
        )
        plan_tuple = worker_profile_plan_tuple(
            plan_workers[worker_id],
            label=f"worker_plan.units[{worker_id}]",
        )
        if plan_tuple != profile_tuple:
            drifted_fields = sorted(
                field
                for field in PROFILE_WORKER_PLAN_TUPLE_FIELDS
                if plan_tuple.get(field) != profile_tuple.get(field)
            )
            raise ValueError(
                "worker_plan.units worker tuple must match entrypoint profile workers: "
                f"{worker_id} drifted fields {drifted_fields}"
            )
    return {
        "status": "passed",
        "worker_count": len(plan_worker_ids),
        "tuple_fields": list(PROFILE_WORKER_PLAN_TUPLE_FIELDS),
    }


def validate_context_ledger_contract(
    context_payload: dict[str, Any],
    agent_payload: dict[str, Any],
    *,
    context_path_text: str,
    agent_path_text: str,
    repo_root: Path,
) -> dict[str, Any]:
    contract = require_object(context_payload.get("context_management_contract"), "context_management_contract")
    resume_protocol = require_object(contract.get("resume_protocol"), "context_management_contract.resume_protocol")
    ledger_path_text = require_string(resume_protocol.get("ledger_path"), "context_management_contract.resume_protocol.ledger_path")
    assert_repo_relative_posix(ledger_path_text)
    ledger_path = repo_path(ledger_path_text, repo_root=repo_root)
    if not ledger_path.is_file():
        raise ValueError(f"context_management_contract.resume_protocol.ledger_path does not exist: {ledger_path_text}")

    context_sha = sha256_file(repo_path(context_path_text, repo_root=repo_root))
    agent_sha = sha256_file(repo_path(agent_path_text, repo_root=repo_root))
    try:
        with closing(sqlite3.connect(ledger_path)) as connection:
            context_row = connection.execute(
                """
                select context_pack_id, run_id, artifact_sha256, payload_json
                from context_packs
                where artifact_path=?
                """,
                (context_path_text,),
            ).fetchone()
            if context_row is None:
                raise ValueError("context ledger missing context_packs row for context_pack")
            if context_row[2] != context_sha:
                raise ValueError("context ledger context_packs artifact_sha256 must match context_pack")
            try:
                ledger_payload = json.loads(context_row[3])
            except json.JSONDecodeError as error:
                raise ValueError("context ledger context_packs payload_json must be valid JSON") from error
            if ledger_payload != context_payload:
                raise ValueError("context ledger context_packs payload_json must match context_pack")
            ledger_run_id = require_string(context_row[1], "context ledger context_packs.run_id")
            for payload_label, bound_payload in (("context_pack", context_payload), ("agent_index", agent_payload)):
                declared_run_id = bound_payload.get("run_id")
                if declared_run_id is not None and declared_run_id != ledger_run_id:
                    raise ValueError(f"context ledger context_packs run_id must match {payload_label} run_id")

            agent_row = connection.execute(
                """
                select sha256, status, semantic_role, run_id, payload_json
                from artifacts
                where kind='agent-index' and repo_rel_path=?
                """,
                (agent_path_text,),
            ).fetchone()
            if agent_row is None:
                raise ValueError("context ledger missing artifacts row for agent_index")
            if agent_row[0] != agent_sha:
                raise ValueError("context ledger agent-index artifact sha256 must match agent_index")
            if agent_row[1] not in {"present", "completed"} or agent_row[2] != "agent-index":
                raise ValueError("context ledger agent-index artifact row must be present/completed with semantic_role=agent-index")
            if agent_row[3] != ledger_run_id:
                raise ValueError("context ledger agent-index artifact run_id must match context_packs run_id")
            try:
                agent_ledger_payload = json.loads(agent_row[4])
            except (TypeError, json.JSONDecodeError) as error:
                raise ValueError("context ledger agent-index payload_json must be valid JSON") from error
            if agent_ledger_payload != agent_payload:
                raise ValueError("context ledger agent-index payload_json must match agent_index")

            summary_count = 0
            agents_by_worker_id = require_object(agent_payload.get("agents_by_worker_id"), "agents_by_worker_id")
            for worker_id, agent in sorted(agents_by_worker_id.items()):
                agent_entry = require_object(agent, f"agents_by_worker_id.{worker_id}")
                summary_path_text = require_string(agent_entry.get("summary_path"), f"agents_by_worker_id.{worker_id}.summary_path")
                assert_repo_relative_posix(summary_path_text)
                isolated_out_root_prefix = None
                isolated_out_root = agent_entry.get("isolated_out_root")
                if isinstance(isolated_out_root, str):
                    assert_repo_relative_posix(isolated_out_root)
                    isolated_out_root_prefix = isolated_out_root.rstrip("/") + "/"
                    if not summary_path_text.startswith(isolated_out_root_prefix):
                        raise ValueError(f"context ledger worker summary path must be under agent isolated_out_root: {worker_id}")
                summary_path = repo_path(summary_path_text, repo_root=repo_root)
                if not summary_path.is_file():
                    raise ValueError(f"context ledger worker summary does not exist: {summary_path_text}")
                summary_sha = sha256_file(summary_path)
                summary_row = connection.execute(
                    """
                    select sha256, status, semantic_role, run_id, agent_id
                    from artifacts
                    where kind='competition-run-summary' and repo_rel_path=?
                    """,
                    (summary_path_text,),
                ).fetchone()
                if summary_row is None:
                    raise ValueError(f"context ledger missing artifacts row for worker summary: {worker_id}")
                if summary_row[0] != summary_sha:
                    raise ValueError(f"context ledger worker summary sha256 must match file: {worker_id}")
                if not worker_summary_row_is_acceptable(
                    row_status=str(summary_row[1]),
                    semantic_role=str(summary_row[2]),
                    context_payload=context_payload,
                    summary_path=summary_path,
                ):
                    raise ValueError(f"context ledger worker summary row must be passed run-summary: {worker_id}")
                if summary_row[3] != ledger_run_id:
                    raise ValueError(f"context ledger worker summary run_id must match context_packs run_id: {worker_id}")
                if summary_row[4] != worker_id:
                    raise ValueError(f"context ledger worker summary agent_id must match worker_id: {worker_id}")
                report_path_text = agent_entry.get("report_path")
                if isinstance(report_path_text, str):
                    assert_repo_relative_posix(report_path_text)
                    if isolated_out_root_prefix is not None and not report_path_text.startswith(isolated_out_root_prefix):
                        raise ValueError(f"context ledger worker report path must be under agent isolated_out_root: {worker_id}")
                    report_path = repo_path(report_path_text, repo_root=repo_root)
                    if not report_path.is_file():
                        raise ValueError(f"context ledger worker report does not exist: {worker_id}")
                    report_sha = sha256_file(report_path)
                    report_row = connection.execute(
                        """
                        select sha256, status, semantic_role, agent_id, run_id
                        from artifacts
                        where kind='run-worker-report' and repo_rel_path=?
                        """,
                        (report_path_text,),
                    ).fetchone()
                    if report_row is None:
                        raise ValueError(
                            "context ledger missing artifacts row for worker report: "
                            f"worker_id={worker_id}; "
                            f"repo_rel_path={report_path_text}; "
                            f"ledger_path={ledger_path_text}; "
                            "expected kind=run-worker-report; "
                            "regenerate OpenCode artifacts on a real GLM-5.1/OpenCode host; "
                            "do not hand-edit target artifacts"
                        )
                    if report_row[0] != report_sha:
                        raise ValueError(f"context ledger worker report sha256 must match file: {worker_id}")
                    if report_row[1] not in {"passed", "failed", "blocked"} or report_row[2] != "worker-execution-report":
                        raise ValueError(f"context ledger worker report row must be passed/failed/blocked worker-execution-report: {worker_id}")
                    if report_row[3] != worker_id:
                        raise ValueError(f"context ledger worker report agent_id must match worker_id: {worker_id}")
                    if report_row[4] != ledger_run_id:
                        raise ValueError(f"context ledger worker report run_id must match context_packs run_id: {worker_id}")
                    report_payload = require_object(load_json(report_path), f"context ledger worker report file: {worker_id}")
                    agent_attempt_value = agent_entry.get("opencode_safety_transform_attempt")
                    report_attempt_value = report_payload.get("opencode_safety_transform_attempt")
                    if agent_attempt_value is not None or report_attempt_value is not None:
                        agent_attempt_ref = validate_artifact_binding_shape(
                            agent_attempt_value,
                            f"agents_by_worker_id.{worker_id}.opencode_safety_transform_attempt",
                            repo_root=repo_root,
                        )
                        report_attempt_ref = validate_artifact_binding_shape(
                            report_attempt_value,
                            f"context ledger worker report file.{worker_id}.opencode_safety_transform_attempt",
                            repo_root=repo_root,
                        )
                        if report_attempt_ref != agent_attempt_ref:
                            raise ValueError(
                                "context ledger worker report opencode_safety_transform_attempt "
                                f"must match agent_index: {worker_id}"
                            )
                        attempt_row = connection.execute(
                            """
                            select sha256, status, semantic_role, agent_id, run_id
                            from artifacts
                            where kind='opencode-safety-transform-attempt' and repo_rel_path=?
                            """,
                            (agent_attempt_ref["path"],),
                        ).fetchone()
                        if attempt_row is None:
                            raise ValueError(
                                "context ledger missing artifacts row for opencode safety transform attempt: "
                                f"worker_id={worker_id}; repo_rel_path={agent_attempt_ref['path']}"
                            )
                        if attempt_row[0] != agent_attempt_ref["sha256"]:
                            raise ValueError(f"context ledger opencode safety transform attempt sha256 must match file: {worker_id}")
                        if attempt_row[1] != report_row[1] or attempt_row[2] != "agent-safety-transform-attempt":
                            raise ValueError(
                                "context ledger opencode safety transform attempt row must match worker report status "
                                f"and semantic_role=agent-safety-transform-attempt: {worker_id}"
                            )
                        if attempt_row[3] != worker_id:
                            raise ValueError(
                                f"context ledger opencode safety transform attempt agent_id must match worker_id: {worker_id}"
                            )
                        if attempt_row[4] != ledger_run_id:
                            raise ValueError(
                                "context ledger opencode safety transform attempt run_id must match context_packs run_id: "
                                f"{worker_id}"
                            )
                        attempt_payload = require_object(
                            load_json(repo_path(agent_attempt_ref["path"], repo_root=repo_root)),
                            f"context ledger opencode safety transform attempt file: {worker_id}",
                        )
                        if attempt_payload.get("run_id") != ledger_run_id:
                            raise ValueError(
                                "context ledger opencode safety transform attempt file run_id must match context_packs run_id: "
                                f"{worker_id}"
                            )
                        if attempt_payload.get("worker_id") != worker_id:
                            raise ValueError(
                                "context ledger opencode safety transform attempt file worker_id must match worker_id: "
                                f"{worker_id}"
                            )
                        expected_worker_report_ref = {"path": report_path_text, "sha256": report_sha}
                        try:
                            event_rows = connection.execute(
                                """
                                select payload_json
                                from events
                                where run_id=? and event_type='worker_executed'
                                """,
                                (ledger_run_id,),
                            ).fetchall()
                        except sqlite3.OperationalError as error:
                            if "no such table" in str(error).lower():
                                raise ValueError(
                                    "context ledger missing events table for worker_executed opencode safety transform attempt"
                                ) from error
                            raise
                        worker_event_count = 0
                        matching_report_event_count = 0
                        matching_attempt_event_seen = False
                        for event_index, event_row in enumerate(event_rows):
                            try:
                                event_payload = require_object(
                                    json.loads(event_row[0]),
                                    f"context ledger worker_executed event[{event_index}]",
                                )
                            except json.JSONDecodeError as error:
                                raise ValueError("context ledger worker_executed payload_json must be valid JSON") from error
                            if event_payload.get("worker_id") != worker_id:
                                continue
                            worker_event_count += 1
                            event_report_ref = validate_artifact_binding_shape(
                                event_payload.get("worker_report"),
                                f"context ledger worker_executed event[{event_index}].worker_report",
                                repo_root=repo_root,
                            )
                            if event_report_ref != expected_worker_report_ref:
                                continue
                            matching_report_event_count += 1
                            event_attempt_ref = validate_artifact_binding_shape(
                                event_payload.get("opencode_safety_transform_attempt"),
                                f"context ledger worker_executed event[{event_index}].opencode_safety_transform_attempt",
                                repo_root=repo_root,
                            )
                            if event_attempt_ref != agent_attempt_ref:
                                raise ValueError(
                                    "context ledger worker_executed event opencode_safety_transform_attempt must match: "
                                    f"{worker_id}"
                                )
                            matching_attempt_event_seen = True
                            break
                        if worker_event_count == 0:
                            raise ValueError(
                                f"context ledger missing worker_executed event for opencode safety transform attempt: {worker_id}"
                            )
                        if matching_report_event_count == 0:
                            raise ValueError(
                                f"context ledger worker_executed event worker_report must match current report: {worker_id}"
                            )
                        if not matching_attempt_event_seen:
                            raise ValueError(
                                f"context ledger missing worker_executed event opencode safety transform attempt: {worker_id}"
                            )
                summary_count += 1
    except sqlite3.DatabaseError as error:
        raise ValueError(f"context ledger sqlite validation failed: {ledger_path_text}: {error}") from error

    return {
        "path": ledger_path_text,
        "context_pack_id": context_row[0],
        "run_id": context_row[1],
        "context_pack": context_path_text,
        "agent_index": agent_path_text,
        "worker_summary_count": summary_count,
        "status": "passed",
    }


def worker_summary_row_is_acceptable(
    *,
    row_status: str,
    semantic_role: str,
    context_payload: dict[str, Any],
    summary_path: Path,
) -> bool:
    if semantic_role != "run-summary":
        return False
    if row_status == "passed":
        return True
    policy = context_payload.get("attempt_evidence_policy")
    if row_status != "failed" or not isinstance(policy, dict) or policy.get("mode") != "baseline_repair_gate":
        return False
    summary = load_json(summary_path)
    final_gate = summary.get("final_gate") if isinstance(summary.get("final_gate"), dict) else {}
    return final_gate.get("status") == "failed"


def validate_repair_self_heal_contract(
    context_payload: dict[str, Any],
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    policy = context_payload.get("attempt_evidence_policy")
    if policy is None:
        return {"status": "skipped", "reason": "attempt_evidence_policy absent"}
    policy_payload = require_object(policy, "attempt_evidence_policy")
    if policy_payload.get("mode") != "baseline_repair_gate":
        return {"status": "skipped", "reason": f"unsupported attempt_evidence_policy mode: {policy_payload.get('mode')}"}
    baseline = require_object(policy_payload.get("baseline_attempt"), "attempt_evidence_policy.baseline_attempt")
    accepted = require_object(policy_payload.get("accepted_attempt"), "attempt_evidence_policy.accepted_attempt")
    baseline_attempt = baseline.get("attempt_number")
    if baseline_attempt != 1:
        raise ValueError("baseline_repair_gate baseline attempt_number must be 1")
    if baseline.get("expected_final_gate") != "failed":
        raise ValueError("baseline_repair_gate baseline expected_final_gate must be failed")
    root_cause_key = require_string(baseline.get("root_cause_key"), "baseline_repair_gate baseline root_cause_key")
    min_accepted_attempt = accepted.get("min_attempt_number")
    if not isinstance(min_accepted_attempt, int) or min_accepted_attempt < 2:
        raise ValueError("baseline_repair_gate accepted min_attempt_number must be >= 2")
    if accepted.get("require_hint_id") is not True:
        raise ValueError("baseline_repair_gate accepted require_hint_id must be true")
    before_after_contract = (
        validate_repair_before_after_contract(policy_payload, repo_root=repo_root) if repo_root is not None else None
    )

    workers = context_payload.get("workers")
    if not isinstance(workers, list) or not workers:
        raise ValueError("baseline_repair_gate requires context_pack.workers")
    checked_workers = 0
    for worker in workers:
        worker_payload = require_object(worker, "context_pack.workers[]")
        attempts = worker_payload.get("attempts")
        if not isinstance(attempts, list) or not attempts:
            continue
        first = next(
            (attempt for attempt in attempts if isinstance(attempt, dict) and attempt.get("attempt") == baseline_attempt),
            None,
        )
        if first is None:
            continue
        if first.get("summary_status") != "failed":
            raise ValueError("baseline_repair_gate attempt 1 summary_status must be failed")
        if first.get("root_cause_key") != root_cause_key:
            raise ValueError("baseline_repair_gate attempt 1 root_cause_key mismatch")
        hint_id = require_string(first.get("hint_id"), "baseline_repair_gate attempt 1 hint_id")
        if first.get("hint_status") != "opened":
            raise ValueError("baseline_repair_gate attempt 1 hint_status must be opened")
        accepted_attempt = next(
            (
                attempt
                for attempt in attempts
                if isinstance(attempt, dict)
                and isinstance(attempt.get("attempt"), int)
                and attempt["attempt"] >= min_accepted_attempt
                and int(attempt.get("exit_code", 1)) == 0
                and attempt.get("summary_status") == "passed"
            ),
            None,
        )
        if accepted_attempt is None:
            raise ValueError("baseline_repair_gate requires a passed accepted retry attempt")
        if accepted_attempt.get("hint_id") != hint_id or accepted_attempt.get("retry_of") != hint_id:
            raise ValueError("baseline_repair_gate accepted retry must bind the opened hint_id")
        if accepted_attempt.get("hint_status") != "revalidated_passed":
            raise ValueError("baseline_repair_gate accepted retry hint_status must be revalidated_passed")
        rollback = require_object(accepted_attempt.get("rollback_evidence"), "baseline_repair_gate rollback_evidence")
        rollback_path_text = require_string(rollback.get("path"), "baseline_repair_gate rollback_evidence.path")
        assert_repo_relative_posix(rollback_path_text)
        rollback_sha256 = rollback.get("sha256")
        if not isinstance(rollback_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", rollback_sha256):
            raise ValueError("baseline_repair_gate rollback_evidence.sha256 must be a sha256 hex string")
        if repo_root is not None:
            rollback_path = repo_path(rollback_path_text, repo_root=repo_root)
            if not rollback_path.is_file():
                raise ValueError("baseline_repair_gate rollback_evidence.path must exist")
            actual_rollback_sha256 = sha256_file(rollback_path)
            if rollback_sha256 != actual_rollback_sha256:
                raise ValueError("baseline_repair_gate rollback_evidence.sha256 does not match artifact")
        final_decision = require_object(worker_payload.get("final_decision"), "baseline_repair_gate worker final_decision")
        if final_decision.get("status") != "accepted":
            raise ValueError("baseline_repair_gate worker final_decision.status must be accepted")
        checked_workers += 1
    if checked_workers == 0:
        raise ValueError("baseline_repair_gate did not find a worker with repair attempts")
    result: dict[str, Any] = {"status": "passed", "checked_workers": checked_workers, "repair_round_cap": 5}
    if before_after_contract is not None:
        result["translation_before_after"] = before_after_contract
    return result


def validate_repair_before_after_contract(policy_payload: dict[str, Any], *, repo_root: Path) -> dict[str, Any]:
    verified_ref = validate_verified_unsafe_baseline_ref(
        require_object(
            require_object(policy_payload.get("baseline_attempt"), "attempt_evidence_policy.baseline_attempt").get(
                "verified_unsafe_baseline"
            ),
            "attempt_evidence_policy.baseline_attempt.verified_unsafe_baseline",
        ),
        "attempt_evidence_policy.baseline_attempt.verified_unsafe_baseline",
        repo_root=repo_root,
    )
    before_after_ref = validate_artifact_binding_shape(
        policy_payload.get("translation_before_after"),
        "attempt_evidence_policy.translation_before_after",
        repo_root=repo_root,
    )
    before_after_payload = load_json(repo_path(before_after_ref["path"], repo_root=repo_root))
    if before_after_payload.get("status") != "bound":
        raise ValueError("translation_before_after.status must be bound")
    baseline_verification = validate_verified_unsafe_baseline_ref(
        before_after_payload.get("baseline_verification"),
        "translation_before_after.baseline_verification",
        repo_root=repo_root,
    )
    expected = repair_verified_baseline_key(verified_ref)
    actual = repair_verified_baseline_key(baseline_verification)
    if actual != expected:
        raise ValueError("translation_before_after.baseline_verification must match baseline_repair_gate verified_unsafe_baseline")
    unsafe_reduction = require_object(before_after_payload.get("unsafe_reduction"), "translation_before_after.unsafe_reduction")
    if unsafe_reduction.get("status") != "measured":
        raise ValueError("translation_before_after.unsafe_reduction.status must be measured")
    reduced_by = unsafe_reduction.get("reduced_by")
    if not isinstance(reduced_by, int) or reduced_by <= 0:
        raise ValueError("translation_before_after.unsafe_reduction.reduced_by must be > 0")
    baseline_total = unsafe_reduction.get("baseline_total_unsafe")
    current_total = unsafe_reduction.get("current_total_unsafe")
    if not isinstance(baseline_total, int) or baseline_total < 0:
        raise ValueError("translation_before_after.unsafe_reduction.baseline_total_unsafe must be a non-negative integer")
    if not isinstance(current_total, int) or current_total < 0:
        raise ValueError("translation_before_after.unsafe_reduction.current_total_unsafe must be a non-negative integer")
    if baseline_total - current_total != reduced_by:
        raise ValueError("translation_before_after.unsafe_reduction.reduced_by must equal baseline-current unsafe count")
    return {
        "status": "passed",
        "path": before_after_ref["path"],
        "baseline_verification": actual,
        "unsafe_reduction": {
            "status": "measured",
            "baseline_total_unsafe": baseline_total,
            "current_total_unsafe": current_total,
            "reduced_by": reduced_by,
        },
    }


def repair_verified_baseline_key(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": value.get("path"),
        "sha256": value.get("sha256"),
        "status": value.get("status"),
        "semantic_pass": value.get("semantic_pass"),
        "semantic_claim_source": value.get("semantic_claim_source"),
        "generated_draft_semantic_pass": value.get("generated_draft_semantic_pass"),
    }


def validate_expected_json_local_path_policy(
    artifacts: dict[str, Any],
    *,
    repo_root: Path,
) -> dict[str, Any]:
    scanned: list[str] = []
    allowed_locations: list[str] = []
    for name, value in sorted(artifacts.items()):
        path_text = require_string(value, f"expected_artifacts.{name}")
        if not path_text.endswith(".json"):
            continue
        path = repo_path(path_text, repo_root=repo_root)
        if not path.is_file():
            continue
        scan = validate_local_absolute_path_policy(load_json(path), label=f"expected_artifacts.{name} {path_text}")
        scanned.append(path_text)
        for location in scan["host_trace_allowed_locations"]:
            allowed_locations.append(f"{path_text}{location}")
    return {
        "status": "passed",
        "scanned_count": len(scanned),
        "scanned_artifacts": scanned,
        "host_trace_allowed_count": len(allowed_locations),
        "host_trace_allowed_locations": allowed_locations,
    }


def validate_harness_artifact_contracts(
    artifacts: dict[str, Any],
    *,
    require_local_artifacts: bool,
    repo_root: Path,
    environment_profile: dict[str, Any] | None = None,
    smoke_contract: dict[str, Any] | None = None,
    entrypoint: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not require_local_artifacts:
        return {"status": "skipped", "reason": "require_local_artifacts=false"}
    result: dict[str, Any] = {"status": "passed"}
    context_payload: dict[str, Any] | None = None
    agent_payload: dict[str, Any] | None = None
    result["expected_json_local_path_policy"] = validate_expected_json_local_path_policy(artifacts, repo_root=repo_root)
    if "context_pack" in artifacts:
        context_path = repo_path(str(artifacts["context_pack"]), repo_root=repo_root)
        context_payload = load_json(context_path)
        result["context_pack"] = validate_context_management_contract(
            context_payload,
            path_text=str(artifacts["context_pack"]),
            expected_artifacts=artifacts,
            repo_root=repo_root,
        )
    if "agent_index" in artifacts:
        agent_path = repo_path(str(artifacts["agent_index"]), repo_root=repo_root)
        agent_payload = load_json(agent_path)
        result["agent_index"] = validate_agent_coordination_contract(
            agent_payload,
            path_text=str(artifacts["agent_index"]),
        )
    if context_payload is not None and agent_payload is not None:
        result["context_agent_consistency"] = validate_context_agent_index_consistency(
            context_payload,
            agent_payload,
        )
        if "worker_plan" in artifacts:
            worker_plan_path = repo_path(str(artifacts["worker_plan"]), repo_root=repo_root)
            worker_plan_payload = load_json(worker_plan_path)
            result["worker_plan"] = validate_worker_plan_contract(
                worker_plan_payload,
                context_payload,
                agent_payload,
                path_text=str(artifacts["worker_plan"]),
            )
            if entrypoint is not None:
                profile_worker_plan_contract = validate_entrypoint_profile_worker_plan_contract(
                    entrypoint,
                    worker_plan_payload,
                    repo_root=repo_root,
                )
                if profile_worker_plan_contract.get("status") != "skipped":
                    result["entrypoint_profile_worker_plan"] = profile_worker_plan_contract
        result["ledger_context_index"] = validate_context_ledger_contract(
            context_payload,
            agent_payload,
            context_path_text=str(artifacts["context_pack"]),
            agent_path_text=str(artifacts["agent_index"]),
            repo_root=repo_root,
        )
    if "resume_manifest" in artifacts:
        resume_manifest_path = repo_path(str(artifacts["resume_manifest"]), repo_root=repo_root)
        result["resume_manifest"] = validate_resume_manifest_contract(
            load_json(resume_manifest_path),
            path_text=str(artifacts["resume_manifest"]),
            expected_artifacts=artifacts,
            context_payload=context_payload,
            agent_payload=agent_payload,
            repo_root=repo_root,
        )
    if context_payload is not None:
        repair_contract = validate_repair_self_heal_contract(context_payload, repo_root=repo_root)
        if repair_contract.get("status") != "skipped":
            result["repair_self_heal"] = repair_contract
    if "opencode_safety_transform_attempt" in artifacts:
        attempt_path_text = require_string(
            artifacts.get("opencode_safety_transform_attempt"),
            "expected_artifacts.opencode_safety_transform_attempt",
        )
        attempt_path = repo_path(attempt_path_text, repo_root=repo_root)
        result["opencode_safety_transform_attempt"] = validate_opencode_safety_transform_attempt_contract(
            {"path": attempt_path_text, "sha256": sha256_file(attempt_path)},
            repo_root=repo_root,
        )
    if "opencode_hostless_rehearsal_report" in artifacts:
        rehearsal_path_text = require_string(
            artifacts.get("opencode_hostless_rehearsal_report"),
            "expected_artifacts.opencode_hostless_rehearsal_report",
        )
        rehearsal_path = repo_path(rehearsal_path_text, repo_root=repo_root)
        result["opencode_hostless_rehearsal_report"] = validate_opencode_hostless_rehearsal_contract(
            {"path": rehearsal_path_text, "sha256": sha256_file(rehearsal_path)},
            repo_root=repo_root,
        )
    if "judge_evidence_index" in artifacts:
        judge_index_path = repo_path(str(artifacts["judge_evidence_index"]), repo_root=repo_root)
        result["judge_evidence_index"] = validate_judge_evidence_index_contract(
            load_json(judge_index_path),
            path_text=str(artifacts["judge_evidence_index"]),
            repo_root=repo_root,
            expected_artifacts=artifacts,
            minimum_worker_count=2 if entrypoint is not None and entrypoint_requires_multi_worker(entrypoint) else 1,
        )
    if "competition_summary" in artifacts:
        competition_summary_path = repo_path(str(artifacts["competition_summary"]), repo_root=repo_root)
        entrypoint_proof_class = None
        entrypoint_run_id = None
        if entrypoint is not None:
            if entrypoint.get("proof_class") is not None:
                entrypoint_proof_class = str(entrypoint.get("proof_class"))
            if entrypoint.get("run_id") is not None:
                entrypoint_run_id = str(entrypoint.get("run_id"))
        result["competition_summary"] = validate_competition_summary_entrypoint_contract(
            load_json(competition_summary_path),
            expected_artifacts=artifacts,
            summary_path=competition_summary_path,
            environment_profile=environment_profile,
            entrypoint_proof_class=entrypoint_proof_class,
            entrypoint_run_id=entrypoint_run_id,
            repo_root=repo_root,
        )
    if "competition_smoke_summary" in artifacts:
        if smoke_contract is None:
            raise ValueError("competition_smoke_summary requires smoke_contract context")
        smoke_summary_path = repo_path(str(artifacts["competition_smoke_summary"]), repo_root=repo_root)
        smoke_summary_payload = load_json(smoke_summary_path)
        result["competition_smoke_summary"] = validate_competition_smoke_summary_contract(
            smoke_summary_payload,
            expected_artifacts=artifacts,
            environment_profile=environment_profile,
            entrypoint_proof_class=str(smoke_contract.get("proof_class")),
            entrypoint_run_id=str(smoke_contract.get("run_id")),
            repo_root=repo_root,
            verify_command_log_sha=True,
        )
        if "command_log" in artifacts:
            command_log_path = repo_path(str(artifacts["command_log"]), repo_root=repo_root)
            expected_log_steps = [
                require_string(step.get("step"), "competition_smoke_summary.steps[].step")
                for step in smoke_summary_payload.get("steps", [])
                if isinstance(step, dict)
            ]
            expected_step_results = {
                require_string(step.get("step"), "competition_smoke_summary.steps[].step"): step
                for step in smoke_summary_payload.get("steps", [])
                if isinstance(step, dict)
            }
            result["competition_smoke_command_log"] = validate_competition_smoke_command_log_contract(
                command_log_path,
                expected_steps=expected_log_steps,
                expected_step_results=expected_step_results,
                expected_run_id=require_string(smoke_summary_payload.get("run_id"), "competition_smoke_summary.run_id"),
                require_canonical=True,
                require_opencode_glm_model=smoke_summary_payload.get("proof_class") == "competition-exact",
            )
        if "vendored_clang_verification" in artifacts:
            vendored_clang_path = repo_path(str(artifacts["vendored_clang_verification"]), repo_root=repo_root)
            result["vendored_clang_verification"] = validate_vendored_clang_verification_contract(
                load_json(vendored_clang_path),
                smoke_summary=smoke_summary_payload,
                environment_profile=environment_profile,
            )
        if "evidence_governance_report" in artifacts:
            evidence_governance_path = repo_path(str(artifacts["evidence_governance_report"]), repo_root=repo_root)
            result["evidence_governance_report"] = validate_evidence_governance_report_contract(
                load_json(evidence_governance_path),
            )
        if "translator_coverage_matrix" in artifacts:
            coverage_matrix_path = repo_path(str(artifacts["translator_coverage_matrix"]), repo_root=repo_root)
            result["translator_coverage_matrix"] = validate_translator_coverage_matrix_report_contract(
                load_json(coverage_matrix_path),
            )
        if "milestone_release_report" in artifacts:
            milestone_report_path = repo_path(str(artifacts["milestone_release_report"]), repo_root=repo_root)
            result["milestone_release_report"] = validate_milestone_release_report_contract(
                load_json(milestone_report_path),
            )
    return result
