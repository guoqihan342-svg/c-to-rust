def repair_attempt_payload(
    *,
    attempt_number: int,
    summary_status: str,
    process_returncode: int,
    exit_code: int,
    summary_path: str,
    report_path: str,
    logs: dict[str, str],
    root_cause_key: str | None = None,
    retry_of: str | None = None,
    rollback_evidence: dict[str, Any] | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    attempt = {
        "attempt": attempt_number,
        "summary_status": summary_status,
        "process_returncode": process_returncode,
        "exit_code": exit_code,
        "summary_path": summary_path,
        "worker_report_path": report_path,
        "logs": logs,
    }
    if root_cause_key:
        attempt["root_cause_key"] = root_cause_key
    if retry_of:
        attempt["retry_of"] = retry_of
    if rollback_evidence is not None:
        attempt["rollback_evidence"] = rollback_evidence
    if diagnostics is not None:
        attempt["diagnostics"] = diagnostics
    return attempt


def repair_attempt_from_result(result: dict[str, Any]) -> dict[str, Any]:
    repair_hint = result.get("repair_hint")
    root_cause_key = repair_hint.get("root_cause_key") if isinstance(repair_hint, dict) else None
    return repair_attempt_payload(
        attempt_number=int(result.get("attempt", 1)),
        summary_status=str(result.get("summary_status", "unknown")),
        process_returncode=int(result.get("process_returncode", 1)),
        exit_code=int(result.get("exit_code", 1)),
        summary_path=str(result.get("summary_path", "")),
        report_path=str(result.get("report_path", "")),
        logs=dict(result.get("logs", {})),
        root_cause_key=str(root_cause_key) if root_cause_key else None,
        retry_of=str(result.get("retry_of")) if result.get("retry_of") else None,
        rollback_evidence=result.get("rollback_evidence") if isinstance(result.get("rollback_evidence"), dict) else None,
        diagnostics=(
            repair_hint.get("diagnostics")
            if isinstance(repair_hint, dict) and isinstance(repair_hint.get("diagnostics"), dict)
            else None
        ),
    )


def append_repair_attempt(payload: dict[str, Any], attempt: dict[str, Any]) -> None:
    attempts = payload.get("attempts")
    if not isinstance(attempts, list):
        attempts = []
    attempt_number = attempt.get("attempt")
    if not any(isinstance(item, dict) and item.get("attempt") == attempt_number for item in attempts):
        attempts.append(attempt)
    attempts.sort(key=lambda item: int(item.get("attempt", 0)) if isinstance(item, dict) else 0)
    payload["attempts"] = attempts


def write_worker_rollback_evidence(
    *,
    hint_id: str,
    run_id: str,
    worker_id: str,
    summary_path: Path,
    report_dir: Path,
    repo_root: Path,
) -> dict[str, Any]:
    safe_hint_id = "".join(char if char.isalnum() or char in ("-", "_") else "-" for char in hint_id)
    evidence_path = report_dir / f"rollback-before-retry-{safe_hint_id}.json"
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "worker_id": worker_id,
        "hint_id": hint_id,
        "action": "removed_stale_summary_before_retry",
        "removed_summary": {
            "path": repo_relative(summary_path, repo_root=repo_root),
            "sha256": sha256_file(summary_path),
        },
        "last_good": {
            "status": "not_available",
            "reason": "opencode harness has no accepted last-good worker summary for this failed retry",
        },
    }
    atomic_write_json(evidence_path, evidence)
    return {"path": repo_relative(evidence_path, repo_root=repo_root), "sha256": sha256_file(evidence_path)}


def write_rejected_worker_summary_evidence(
    *,
    run_id: str,
    worker_id: str,
    summary_path: Path,
    report_dir: Path,
    opencode_contract_verification: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    evidence_path = report_dir / "rejected-summary-opencode-contract.json"
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "worker_id": worker_id,
        "action": "rejected_summary_due_to_opencode_contract",
        "rejected_summary": {
            "path": repo_relative(summary_path, repo_root=repo_root),
            "sha256": sha256_file(summary_path),
        },
        "opencode_contract_verification": opencode_contract_verification,
        "replacement": {
            "status": "blocked",
            "reason": "OpenCode did not execute the assigned worker command as the first shell command",
        },
    }
    atomic_write_json(evidence_path, evidence)
    return {"path": repo_relative(evidence_path, repo_root=repo_root), "sha256": sha256_file(evidence_path)}


def record_repair_hint(connection: sqlite3.Connection, *, hint: dict[str, Any]) -> None:
    now = now_text()
    existing = connection.execute("select payload_json from repair_hints where hint_id=?", (hint["hint_id"],)).fetchone()
    if existing is not None:
        existing_payload = json.loads(existing[0])
        existing_attempts = existing_payload.get("attempts")
        if isinstance(existing_attempts, list):
            for attempt in existing_attempts:
                if isinstance(attempt, dict):
                    append_repair_attempt(hint, attempt)
    connection.execute(
        """
        insert into repair_hints(hint_id, run_id, target_id, slice_id, root_cause_key, status, payload_json, created_at)
        values (?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(hint_id) do update set
          target_id=excluded.target_id,
          slice_id=excluded.slice_id,
          root_cause_key=excluded.root_cause_key,
          status=excluded.status,
          payload_json=excluded.payload_json,
          created_at=excluded.created_at
        """,
        (
            hint["hint_id"],
            hint["run_id"],
            hint["target_id"],
            hint["slice_id"],
            hint["root_cause_key"],
            "open",
            json.dumps(hint, sort_keys=True),
            now,
        ),
    )
    record_event(
        connection,
        run_id=str(hint["run_id"]),
        event_type="repair_hint_recorded",
        payload={
            "hint_id": hint["hint_id"],
            "worker_id": hint["worker_id"],
            "root_cause_key": hint["root_cause_key"],
            "attempt": hint["attempts"][-1]["attempt"] if isinstance(hint.get("attempts"), list) else None,
            "attempt_count": len(hint["attempts"]) if isinstance(hint.get("attempts"), list) else 0,
        },
    )


def load_open_repair_hint(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    worker_id: str,
    hint_id: str | None,
) -> dict[str, Any]:
    if hint_id:
        rows = connection.execute(
            "select hint_id, status, payload_json from repair_hints where run_id=? and hint_id=?",
            (run_id, hint_id),
        ).fetchall()
    else:
        rows = connection.execute(
            "select hint_id, status, payload_json from repair_hints where run_id=? and status='open' order by created_at desc",
            (run_id,),
        ).fetchall()
    for row_hint_id, status, payload_json in rows:
        payload = json.loads(payload_json)
        if payload.get("worker_id") != worker_id:
            continue
        if status != "open":
            raise SystemExit(f"repair hint is not open: {row_hint_id} ({status})")
        return payload
    raise SystemExit(f"no open repair hint for worker {worker_id}")


def mark_repair_hint_revalidated(
    connection: sqlite3.Connection,
    *,
    hint_id: str,
    status: str,
    result: dict[str, Any],
) -> None:
    row = connection.execute("select run_id, payload_json from repair_hints where hint_id=?", (hint_id,)).fetchone()
    if row is None:
        raise SystemExit(f"unknown repair hint: {hint_id}")
    run_id, payload_json = row
    payload = json.loads(payload_json)
    append_repair_attempt(payload, repair_attempt_from_result(result))
    payload["status"] = status
    payload["revalidation"] = {
        "exit_code": result.get("exit_code"),
        "summary_status": result.get("summary_status"),
        "report_path": result.get("report_path"),
    }
    connection.execute(
        "update repair_hints set status=?, payload_json=? where hint_id=?",
        (status, json.dumps(payload, sort_keys=True), hint_id),
    )
    attempt = repair_attempt_from_result(result)
    record_event(
        connection,
        run_id=str(run_id),
        event_type="repair_hint_revalidated",
        payload={
            "hint_id": hint_id,
            "status": status,
            "attempt": attempt["attempt"],
            "exit_code": result.get("exit_code"),
            "summary_status": result.get("summary_status"),
            "retry_of": attempt.get("retry_of"),
            "rollback_evidence": attempt.get("rollback_evidence"),
        },
    )


def annotate_retry_worker_metrics(
    connection: sqlite3.Connection,
    *,
    hint_id: str,
    result: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any] | None:
    summary_path = repo_path(Path(str(result.get("summary_path", ""))), repo_root=repo_root)
    if not summary_path.exists():
        return None
    summary = load_json(summary_path)
    binding = summary.get("workflow_metrics")
    if not isinstance(binding, dict):
        return None
    metrics_ref = binding.get("path")
    expected_sha = binding.get("sha256")
    if not isinstance(metrics_ref, str) or not isinstance(expected_sha, str):
        raise SystemExit("retry worker summary workflow_metrics.path and workflow_metrics.sha256 are required")
    metrics_path = resolve_summary_artifact(metrics_ref, summary_path=summary_path, repo_root=repo_root)
    if metrics_path is None:
        raise SystemExit(f"retry worker summary workflow_metrics.path does not exist: {metrics_ref}")
    if sha256_file(metrics_path) != expected_sha:
        raise SystemExit("retry worker summary workflow_metrics.sha256 does not match artifact before annotation")
    metrics = load_json(metrics_path)
    units = metrics.get("per_unit_statuses")
    if not isinstance(units, list) or len(units) != 1 or not isinstance(units[0], dict):
        return None

    row = connection.execute("select payload_json from repair_hints where hint_id=?", (hint_id,)).fetchone()
    if row is None:
        raise SystemExit(f"unknown repair hint for retry metrics: {hint_id}")
    hint_payload = json.loads(row[0])
    attempts = hint_payload.get("attempts")
    if not isinstance(attempts, list) or len(attempts) < 2:
        return None

    repair_rounds = len(attempts) - 1
    safe_hint_id = safe_file_component(hint_id)
    history_path = summary_path.parent / f"retry-repair-history-{safe_hint_id}.jsonl"
    history_events = retry_repair_history_events(hint_payload, result)
    atomic_write_text(history_path, "".join(json.dumps(event, sort_keys=True) + "\n" for event in history_events))
    statuses = [str(event.get("status")) for event in history_events if isinstance(event.get("status"), str)]
    rollback_ids = retry_rollback_ids(attempts)
    repair_history = {
        "patch_events_path": repo_relative(history_path, repo_root=repo_root),
        "patch_events_sha256": sha256_file(history_path),
        "statuses": statuses,
        "rollback_ids": rollback_ids,
        "verified": "verified" in statuses,
    }

    unit = units[0]
    root_cause_key = hint_payload.get("root_cause_key")
    if isinstance(root_cause_key, str) and root_cause_key:
        unit["root_cause_key"] = root_cause_key
        metrics["root_cause_counts"] = {root_cause_key: 1}
    unit["repair_rounds"] = repair_rounds
    unit["auto_recovered"] = repair_history["verified"] and result.get("summary_status") == "passed"
    unit["repair_history"] = repair_history
    units_total = int(metrics.get("units_total", 1)) if isinstance(metrics.get("units_total"), int) else 1
    metrics["avg_repair_rounds"] = repair_rounds / max(1, units_total)
    metrics["auto_recovery_rate"] = (1.0 if unit["auto_recovered"] else 0.0) / max(1, units_total)
    atomic_write_json(metrics_path, metrics)

    summary["workflow_metrics"]["sha256"] = sha256_file(metrics_path)
    atomic_write_json(summary_path, summary)

    annotation = {
        "history_path": repo_relative(history_path, repo_root=repo_root),
        "history_sha256": sha256_file(history_path),
        "metrics_path": repo_relative(metrics_path, repo_root=repo_root),
        "metrics_sha256": sha256_file(metrics_path),
        "summary_path": repo_relative(summary_path, repo_root=repo_root),
        "summary_sha256": sha256_file(summary_path),
        "repair_rounds": repair_rounds,
        "auto_recovered": bool(unit["auto_recovered"]),
        "unsafe_reduction": metrics.get("unsafe_reduction", {}),
    }
    record_artifact(
        connection,
        run_id=str(result["run_id"]),
        worker_id=str(result["worker_id"]),
        kind="retry-repair-history",
        path=history_path,
        status="verified" if annotation["auto_recovered"] else "recorded",
        semantic_role="repair-history",
        payload={"schema_version": SCHEMA_VERSION, "hint_id": hint_id, "events": history_events},
        repo_root=repo_root,
    )
    record_event(
        connection,
        run_id=str(result["run_id"]),
        event_type="retry_worker_metrics_annotated",
        payload={"hint_id": hint_id, **annotation},
    )
    return annotation


def annotate_opencode_worker_metrics(
    *,
    summary_path: Path,
    handoff_contract: dict[str, Any] | None,
    opencode_session_evidence: dict[str, Any] | None,
    opencode_contract_verification: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any] | None:
    if handoff_contract is None or opencode_session_evidence is None:
        return None
    summary = load_json(summary_path)
    binding = summary.get("workflow_metrics")
    if not isinstance(binding, dict):
        return None
    metrics_ref = binding.get("path")
    expected_sha = binding.get("sha256")
    if not isinstance(metrics_ref, str) or not isinstance(expected_sha, str):
        raise SystemExit("opencode worker summary workflow_metrics.path and workflow_metrics.sha256 are required")
    metrics_path = resolve_summary_artifact(metrics_ref, summary_path=summary_path, repo_root=repo_root)
    if metrics_path is None:
        raise SystemExit(f"opencode worker summary workflow_metrics.path does not exist: {metrics_ref}")
    if sha256_file(metrics_path) != expected_sha:
        raise SystemExit("opencode worker summary workflow_metrics.sha256 does not match artifact before annotation")
    metrics = load_json(metrics_path)
    units = metrics.get("per_unit_statuses")
    if not isinstance(units, list):
        return None

    updated_units = 0
    for unit in units:
        if not isinstance(unit, dict):
            continue
        unit["handoff_contract"] = json.loads(json.dumps(handoff_contract))
        unit["opencode_session_evidence"] = json.loads(json.dumps(opencode_session_evidence))
        unit["opencode_contract_verification"] = json.loads(json.dumps(opencode_contract_verification))
        updated_units += 1
    if updated_units == 0:
        return None

    atomic_write_json(metrics_path, metrics)
    summary["workflow_metrics"]["sha256"] = sha256_file(metrics_path)
    atomic_write_json(summary_path, summary)
    return {
        "metrics_path": repo_relative(metrics_path, repo_root=repo_root),
        "metrics_sha256": sha256_file(metrics_path),
        "summary_path": repo_relative(summary_path, repo_root=repo_root),
        "summary_sha256": sha256_file(summary_path),
        "updated_unit_count": updated_units,
        "semantic_gate": False,
        "evidence_boundary": "OpenCode session fields are audit provenance only; summary validators still own acceptance.",
    }


def write_opencode_safety_transform_attempt(
    *,
    run_id: str,
    worker_id: str,
    attempt_number: int,
    attempt_path: Path,
    summary_path: Path,
    summary_payload: dict[str, Any],
    handoff_contract: dict[str, Any] | None,
    opencode_session_evidence: dict[str, Any] | None,
    opencode_contract_verification: dict[str, Any],
    repo_root: Path,
) -> dict[str, str]:
    final_gate = summary_payload.get("final_gate") if isinstance(summary_payload.get("final_gate"), dict) else {}
    final_gate_status = str(final_gate.get("status", "unknown"))
    contract_status = str(opencode_contract_verification.get("status", "unknown"))
    status = "accepted" if final_gate_status == "passed" and contract_status == "executed" else "blocked"
    workflow_metrics_binding = summary_payload.get("workflow_metrics")
    workflow_metrics_ref: dict[str, Any] | None = None
    workflow_metrics_payload: dict[str, Any] | None = None
    if isinstance(workflow_metrics_binding, dict) and isinstance(workflow_metrics_binding.get("path"), str):
        workflow_metrics_path = resolve_summary_artifact(
            str(workflow_metrics_binding["path"]),
            summary_path=summary_path,
            repo_root=repo_root,
        )
        if workflow_metrics_path is not None and workflow_metrics_path.exists():
            workflow_metrics_ref = {
                "path": str(workflow_metrics_binding["path"]),
                "sha256": sha256_file(workflow_metrics_path),
            }
            workflow_metrics_payload = load_json(workflow_metrics_path)

    safety_transform_units = opencode_safety_transform_units(
        workflow_metrics_payload if workflow_metrics_payload is not None else {},
        attempt_number=attempt_number,
        repo_root=repo_root,
    )

    attempt = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "opencode-safety-transform-attempt",
        "run_id": run_id,
        "worker_id": worker_id,
        "attempt": attempt_number,
        "status": status,
        "summary": {
            "path": repo_relative(summary_path, repo_root=repo_root),
            "sha256": sha256_file(summary_path),
            "final_gate_status": final_gate_status,
        },
        "handoff_contract": json.loads(json.dumps(handoff_contract)) if handoff_contract is not None else None,
        "opencode_session_evidence": (
            json.loads(json.dumps(opencode_session_evidence)) if opencode_session_evidence is not None else None
        ),
        "contract_verification": json.loads(json.dumps(opencode_contract_verification)),
        "chat_output_is_evidence": False,
        "semantic_gate": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
        "attempt_contract": {
            "single_patch_per_round": True,
            "max_repair_rounds": REPAIR_ROUND_CAP,
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
        },
        "safety_transform_unit_count": len(safety_transform_units),
        "safety_transform_units": safety_transform_units,
        "evidence_boundary": (
            "This artifact records OpenCode command-contract participation in a safety-transform attempt. "
            "It does not make chat/session output semantic evidence; acceptance remains owned by the summary validators."
        ),
    }
    if workflow_metrics_ref is not None:
        attempt["workflow_metrics"] = workflow_metrics_ref
    root_cause = worker_summary_root_cause(summary_payload, summary_path=summary_path, repo_root=repo_root)
    if root_cause:
        attempt["root_cause_key"] = root_cause
    attempt_path.parent.mkdir(parents=True, exist_ok=True)
    numbered_attempt_path = opencode_numbered_safety_attempt_path(attempt_path, attempt_number=attempt_number)
    atomic_write_json(numbered_attempt_path, attempt)
    if numbered_attempt_path != attempt_path:
        atomic_write_json(attempt_path, attempt)
    return {
        "path": repo_relative(numbered_attempt_path, repo_root=repo_root),
        "sha256": sha256_file(numbered_attempt_path),
    }


def opencode_numbered_safety_attempt_path(attempt_path: Path, *, attempt_number: int) -> Path:
    if attempt_path.stem.endswith(f"-{attempt_number}"):
        return attempt_path
    return attempt_path.with_name(f"{attempt_path.stem}-{attempt_number}{attempt_path.suffix}")


def opencode_safety_transform_units(
    workflow_metrics: dict[str, Any],
    *,
    attempt_number: int,
    repo_root: Path,
) -> list[dict[str, Any]]:
    units = workflow_metrics.get("per_unit_statuses")
    if not isinstance(units, list):
        return []
    result: list[dict[str, Any]] = []
    for unit in units:
        if not isinstance(unit, dict):
            continue
        evidence = unit.get("translation_before_after")
        evidence = evidence if isinstance(evidence, dict) else {}
        repair_history = unit.get("repair_history")
        repair_history = repair_history if isinstance(repair_history, dict) else None
        if not evidence and repair_history is None:
            continue

        patch_evidence: dict[str, Any] = {}
        for field in ("baseline", "final", "accepted_patch", "patch_log"):
            value = evidence.get(field)
            if isinstance(value, dict):
                patch_evidence[field] = json.loads(json.dumps(value))

        verification_delta: dict[str, Any] = {}
        for field in (
            "baseline_verification",
            "oracle_evidence",
            "semantic_evidence",
            "unsafe_scan_evidence",
            "unsafe_reduction",
        ):
            value = evidence.get(field)
            if isinstance(value, dict):
                verification_delta[field] = json.loads(json.dumps(value))
        for field in ("compiled", "semantic_pass", "refused", "blocked", "failed"):
            if field in unit:
                verification_delta[field] = bool(unit.get(field))

        transform_unit: dict[str, Any] = {
            "unit_id": str(unit.get("unit_id", "unknown")),
            "status": str(unit.get("status", evidence.get("status", "unknown"))),
            "attempt": attempt_number,
            "round_contract": {
                "single_patch_per_round": True,
                "max_repair_rounds": REPAIR_ROUND_CAP,
            },
            "patch_evidence": patch_evidence,
            "verification_delta": verification_delta,
            "rounds": opencode_safety_transform_rounds(evidence, attempt_number=attempt_number),
            "accepted_retry_hint": opencode_accepted_retry_hint(unit, repair_history=repair_history, repo_root=repo_root),
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
        }
        if repair_history is not None:
            transform_unit["repair_history"] = json.loads(json.dumps(repair_history))
        if "repair_rounds" in unit:
            transform_unit["repair_rounds"] = int(unit.get("repair_rounds", 0) or 0)
        if "auto_recovered" in unit:
            transform_unit["auto_recovered"] = bool(unit.get("auto_recovered"))
        root_cause = unit.get("root_cause_key")
        if isinstance(root_cause, str) and root_cause:
            transform_unit["root_cause_key"] = root_cause
        result.append(transform_unit)
    return result


def opencode_safety_transform_rounds(evidence: dict[str, Any], *, attempt_number: int) -> list[dict[str, Any]]:
    if not evidence:
        return []
    round_payload: dict[str, Any] = {
        "round": attempt_number,
        "single_patch_per_round": True,
    }
    field_map = {
        "accepted_patch": "patch",
        "patch_log": "patch_log",
        "oracle_evidence": "oracle_evidence",
        "unsafe_reduction": "unsafe_delta",
        "unsafe_scan_evidence": "unsafe_scan_evidence",
        "baseline_verification": "baseline_verification",
    }
    for source_field, target_field in field_map.items():
        value = evidence.get(source_field)
        if isinstance(value, dict):
            round_payload[target_field] = json.loads(json.dumps(value))
    semantic_evidence = evidence.get("semantic_evidence")
    if isinstance(semantic_evidence, dict) and isinstance(semantic_evidence.get("schema_diff"), dict):
        round_payload["schema_diff"] = json.loads(json.dumps(semantic_evidence["schema_diff"]))
    if set(round_payload) == {"round", "single_patch_per_round"}:
        return []
    return [round_payload]


def opencode_accepted_retry_hint(
    unit: dict[str, Any],
    *,
    repair_history: dict[str, Any] | None,
    repo_root: Path,
) -> dict[str, Any]:
    if repair_history is None:
        return {"status": "not_exercised"}
    statuses = repair_history.get("statuses") if isinstance(repair_history.get("statuses"), list) else []
    rollback_ids = repair_history.get("rollback_ids") if isinstance(repair_history.get("rollback_ids"), list) else []
    verified = bool(repair_history.get("verified"))
    auto_recovered = bool(unit.get("auto_recovered", False))
    rollback_evidence = opencode_rollback_evidence_refs(rollback_ids, repo_root=repo_root)
    rollback_evidence_complete = bool(rollback_evidence) and [
        ref.get("path") for ref in rollback_evidence
    ] == rollback_ids and all(is_sha256_hex(ref.get("sha256")) for ref in rollback_evidence)
    status = "revalidated_passed" if verified and auto_recovered and rollback_evidence_complete else (
        "verified" if verified else "recorded"
    )
    hint = {
        "status": status,
        "repair_rounds": int(unit.get("repair_rounds", 0) or 0),
        "auto_recovered": auto_recovered,
        "statuses": json.loads(json.dumps(statuses)),
        "rollback_ids": json.loads(json.dumps(rollback_ids)),
        "rollback_evidence": rollback_evidence,
    }
    for field in ("patch_events_path", "patch_events_sha256"):
        value = repair_history.get(field)
        if isinstance(value, str) and value:
            hint[field] = value
    return hint


def opencode_rollback_evidence_refs(rollback_ids: list[Any], *, repo_root: Path) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for item in rollback_ids:
        if not isinstance(item, str) or not item:
            continue
        rollback_path = repo_path(Path(item), repo_root=repo_root)
        ref = {"path": repo_relative(rollback_path, repo_root=repo_root)}
        if rollback_path.exists():
            ref["sha256"] = sha256_file(rollback_path)
        refs.append(ref)
    return refs


def retry_repair_history_events(hint_payload: dict[str, Any], result: dict[str, Any]) -> list[dict[str, Any]]:
    events = []
    for attempt in hint_payload.get("attempts", []):
        if not isinstance(attempt, dict):
            continue
        events.append(
            {
                "attempt": attempt.get("attempt"),
                "status": attempt.get("summary_status", "unknown"),
                "exit_code": attempt.get("exit_code"),
                "retry_of": attempt.get("retry_of"),
                "root_cause_key": attempt.get("root_cause_key"),
                "rollback_evidence": attempt.get("rollback_evidence"),
            }
        )
    events.append(
        {
            "attempt": result.get("attempt"),
            "status": "verified",
            "summary_status": result.get("summary_status"),
            "exit_code": result.get("exit_code"),
            "report_path": result.get("report_path"),
        }
    )
    return events


def retry_rollback_ids(attempts: list[Any]) -> list[str]:
    rollback_ids = []
    for attempt in attempts:
        if not isinstance(attempt, dict):
            continue
        rollback = attempt.get("rollback_evidence")
        if not isinstance(rollback, dict):
            continue
        path = rollback.get("path")
        if isinstance(path, str) and path:
            rollback_ids.append(path)
    return rollback_ids


def resolve_summary_artifact(value: str, *, summary_path: Path, repo_root: Path) -> Path | None:
    checked_relative_path(value)
    candidates = [
        repo_root / value,
        summary_path.parent / value,
        summary_path.parent.parent / value,
    ]
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            resolved.relative_to(repo_root.resolve())
        except ValueError:
            continue
        if resolved.exists():
            return resolved
    return None


def safe_file_component(value: str) -> str:
    return "".join(char if char.isalnum() or char in ("-", "_") else "-" for char in value)


def opencode_runtime_env_contract(
    *,
    base_root: Path,
    scope: str,
    repo_root: Path,
) -> dict[str, Any]:
    base_root = repo_path(base_root, repo_root=repo_root)
    scope_text = safe_file_component(scope) or "opencode"
    runtime_root = base_root / "opencode-runtime" / scope_text
    runtime_paths = {
        "XDG_CONFIG_HOME": runtime_root / "config",
        "XDG_DATA_HOME": runtime_root / "data",
        "XDG_CACHE_HOME": runtime_root / "cache",
        "TMPDIR": runtime_root / "tmp",
        "TEMP": runtime_root / "tmp",
        "TMP": runtime_root / "tmp",
    }
    for path in {path for path in runtime_paths.values()}:
        path.mkdir(parents=True, exist_ok=True)
    env = {key: repo_relative(runtime_paths[key], repo_root=repo_root) for key in OPENCODE_RUNTIME_ENV_KEYS}
    runtime_root_rel = repo_relative(runtime_root, repo_root=repo_root)
    digest_payload = {
        "scope": scope_text,
        "runtime_root": runtime_root_rel,
        "env": env,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "isolated",
        "scope": scope_text,
        "runtime_root": runtime_root_rel,
        "env": env,
        "env_sha256": sha256_text(json.dumps(digest_payload, sort_keys=True)),
        "semantic_gate": False,
        "evidence_boundary": (
            "OpenCode runtime env isolation controls process-local agent state only; "
            "semantic acceptance still requires worker summaries and validators."
        ),
    }


def validate_opencode_runtime_env_contract(
    value: Any,
    *,
    context: str,
    repo_root: Path,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SystemExit(f"{context} opencode_runtime_env is missing")
    if value.get("status") != "isolated":
        raise SystemExit(f"{context} opencode_runtime_env is not isolated")
    scope = value.get("scope")
    runtime_root = value.get("runtime_root")
    env = value.get("env")
    if not isinstance(scope, str) or not scope:
        raise SystemExit(f"{context} opencode_runtime_env.scope is missing")
    if not isinstance(runtime_root, str) or not runtime_root:
        raise SystemExit(f"{context} opencode_runtime_env.runtime_root is missing")
    runtime_root_path = checked_relative_path(runtime_root)
    if len(runtime_root_path.parts) < 2 or runtime_root_path.parts[-2:] != ("opencode-runtime", scope):
        raise SystemExit(f"{context} opencode_runtime_env.runtime_root must end with opencode-runtime/<scope>")
    repo_path(Path(runtime_root_path.as_posix()), repo_root=repo_root)
    if not isinstance(env, dict):
        raise SystemExit(f"{context} opencode_runtime_env.env is missing")
    expected_env = {
        "XDG_CONFIG_HOME": runtime_root_path / "config",
        "XDG_DATA_HOME": runtime_root_path / "data",
        "XDG_CACHE_HOME": runtime_root_path / "cache",
        "TMPDIR": runtime_root_path / "tmp",
        "TEMP": runtime_root_path / "tmp",
        "TMP": runtime_root_path / "tmp",
    }
    if set(env) != set(expected_env):
        raise SystemExit(f"{context} opencode_runtime_env.env keys mismatch")
    normalized_env: dict[str, str] = {}
    for key in OPENCODE_RUNTIME_ENV_KEYS:
        path_text_value = env.get(key)
        if not isinstance(path_text_value, str) or not path_text_value:
            raise SystemExit(f"{context} opencode_runtime_env.env.{key} is missing")
        env_path = checked_relative_path(path_text_value)
        if env_path != expected_env[key]:
            raise SystemExit(f"{context} opencode_runtime_env.env.{key} must be under runtime_root")
        repo_path(Path(env_path.as_posix()), repo_root=repo_root)
        normalized_env[key] = env_path.as_posix()
    expected_digest = sha256_text(
        json.dumps(
            {
                "scope": scope,
                "runtime_root": runtime_root,
                "env": normalized_env,
            },
            sort_keys=True,
        )
    )
    if value.get("env_sha256") != expected_digest:
        raise SystemExit(f"{context} opencode_runtime_env.env_sha256 mismatch")
    return {
        **value,
        "scope": scope,
        "runtime_root": runtime_root,
        "env": normalized_env,
        "env_sha256": expected_digest,
    }


def opencode_runtime_process_env(
    runtime_env: dict[str, Any],
    *,
    repo_root: Path,
) -> dict[str, str]:
    process_env = dict(os.environ)
    env = runtime_env.get("env") if isinstance(runtime_env.get("env"), dict) else {}
    for key in OPENCODE_RUNTIME_ENV_KEYS:
        value = env.get(key)
        if isinstance(value, str):
            process_env[key] = str(repo_path(Path(value), repo_root=repo_root))
    return process_env


def opencode_launch_policy(
    *,
    opencode_command: str,
    opencode_model: str | None,
    opencode_agent: str | None,
    opencode_variant: str,
    opencode_skip_permissions: bool,
    opencode_allow_non_competition_model: bool = False,
) -> dict[str, Any]:
    if opencode_command != COMPETITION_OPENCODE_COMMAND:
        raise SystemExit(f"opencode_command must be {COMPETITION_OPENCODE_COMMAND}")
    if opencode_model is None:
        opencode_model = COMPETITION_OPENCODE_MODEL
    if opencode_model != COMPETITION_OPENCODE_MODEL and not opencode_allow_non_competition_model:
        raise SystemExit(f"opencode_model must be {COMPETITION_OPENCODE_MODEL}")
    if opencode_agent is None:
        opencode_agent = COMPETITION_OPENCODE_AGENT
    if opencode_agent != COMPETITION_OPENCODE_AGENT:
        raise SystemExit(f"opencode_agent must be {COMPETITION_OPENCODE_AGENT}")
    if opencode_variant != COMPETITION_OPENCODE_VARIANT:
        raise SystemExit(f"opencode_variant must be {COMPETITION_OPENCODE_VARIANT}")
    return {
        "opencode_command": opencode_command,
        "opencode_model": opencode_model,
        "opencode_agent": opencode_agent,
        "opencode_variant": opencode_variant,
        "opencode_skip_permissions": bool(opencode_skip_permissions),
    }


def normalize_opencode_launch_policy(
    policy: dict[str, Any],
    *,
    opencode_allow_non_competition_model: bool = False,
) -> dict[str, Any]:
    required_fields = {
        "opencode_command",
        "opencode_model",
        "opencode_agent",
        "opencode_variant",
        "opencode_skip_permissions",
    }
    missing_fields = required_fields.difference(policy.keys())
    if missing_fields:
        raise SystemExit("opencode preflight launch policy is missing fields: " + ", ".join(sorted(missing_fields)))
    if not isinstance(policy.get("opencode_agent"), str):
        raise SystemExit(f"opencode preflight launch policy opencode_agent must be {COMPETITION_OPENCODE_AGENT}")
    return opencode_launch_policy(
        opencode_command=str(policy.get("opencode_command", "")),
        opencode_model=policy.get("opencode_model") if isinstance(policy.get("opencode_model"), str) else None,
        opencode_agent=policy.get("opencode_agent"),
        opencode_variant=str(policy.get("opencode_variant", "")),
        opencode_skip_permissions=policy.get("opencode_skip_permissions") is True,
        opencode_allow_non_competition_model=opencode_allow_non_competition_model,
    )


def opencode_launch_policy_sha256(policy: dict[str, Any]) -> str:
    return sha256_text(json.dumps(policy, sort_keys=True))


def build_opencode_models_argv(*, opencode_command: str) -> list[str]:
    if opencode_command != COMPETITION_OPENCODE_COMMAND:
        raise SystemExit(f"opencode_command must be {COMPETITION_OPENCODE_COMMAND}")
    return [resolve_subprocess_command(opencode_command), "models"]


def portable_opencode_evidence_argv(argv: list[str], *, opencode_command: str) -> list[str]:
    if not argv:
        raise SystemExit("opencode argv must not be empty")
    if opencode_command != COMPETITION_OPENCODE_COMMAND:
        raise SystemExit(f"opencode_command must be {COMPETITION_OPENCODE_COMMAND}")
    evidence_argv = [str(item) for item in argv]
    evidence_argv[0] = opencode_command
    for index, item in enumerate(evidence_argv[:-1]):
        if item == "--dir":
            evidence_argv[index + 1] = "."
            break
    return evidence_argv


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
    return opencode_command_argv_matches(value[0], expected_command) and value[1] == "models"


def require_opencode_string_argv(
    value: Any,
    *,
    label: str,
    report_path: Path,
    repo_root: Path,
) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise SystemExit(
            f"{label} must be a non-empty string list: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    for argument in value:
        if LOCAL_ABSOLUTE_PATH_TEXT.search(argument):
            raise SystemExit(
                f"{label} must be portable and must not contain local absolute paths: "
                f"{repo_relative(report_path, repo_root=repo_root)}"
            )
    return value


def validate_opencode_run_argv_binding(
    value: Any,
    *,
    label: str,
    launch_policy: dict[str, Any],
    report_path: Path,
    repo_root: Path,
) -> list[str]:
    argv = require_opencode_string_argv(value, label=label, report_path=report_path, repo_root=repo_root)
    if len(argv) < 3 or not opencode_command_argv_matches(argv[0], launch_policy["opencode_command"]) or argv[1] != "run":
        raise SystemExit(
            f"{label} must run opencode run: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
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
                raise SystemExit(
                    f"{label} duplicate {item}: "
                    f"{repo_relative(report_path, repo_root=repo_root)}"
                )
            bool_flags.add(item)
            index += 1
            continue
        if item in flags:
            raise SystemExit(
                f"{label} duplicate {item}: "
                f"{repo_relative(report_path, repo_root=repo_root)}"
            )
        if index + 1 >= len(argv) or argv[index + 1].startswith("--"):
            raise SystemExit(
                f"{label} {item} must have a value: "
                f"{repo_relative(report_path, repo_root=repo_root)}"
            )
        flags[item] = argv[index + 1]
        index += 2
    if len(prompt) != 1 or not prompt[0].strip():
        raise SystemExit(
            f"{label} prompt must be the final non-empty argv item: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    required_flags = {"--dir", "--format", "--variant", "--model"}
    missing = sorted(required_flags - flags.keys())
    if missing:
        raise SystemExit(
            f"{label} missing {' '.join(missing)}: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    allowed_flags = set(required_flags)
    if launch_policy.get("opencode_agent") is not None:
        allowed_flags.add("--agent")
    unexpected_flags = sorted(set(flags) - allowed_flags)
    if unexpected_flags:
        raise SystemExit(
            f"{label} has unexpected flags: {' '.join(unexpected_flags)}: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    if flags["--dir"] != ".":
        raise SystemExit(
            f"{label} --dir must be portable repo root .: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    if flags["--format"] != "json":
        raise SystemExit(
            f"{label} --format must be json: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    if flags["--variant"] != launch_policy["opencode_variant"]:
        raise SystemExit(
            f"{label} --variant must be {launch_policy['opencode_variant']}: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    if flags["--model"] != launch_policy["opencode_model"]:
        raise SystemExit(
            f"{label} --model must be {launch_policy['opencode_model']}: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    expected_agent = launch_policy.get("opencode_agent")
    if expected_agent is None and "--agent" in flags:
        raise SystemExit(
            f"{label} --agent must be absent: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    if expected_agent is not None and flags.get("--agent") != expected_agent:
        raise SystemExit(
            f"{label} --agent must be {expected_agent}: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    skip_permissions_present = "--dangerously-skip-permissions" in bool_flags
    if skip_permissions_present != bool(launch_policy.get("opencode_skip_permissions")):
        raise SystemExit(
            f"{label} --dangerously-skip-permissions must match launch_policy: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    return argv
