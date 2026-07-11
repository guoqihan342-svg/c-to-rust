from __future__ import annotations

from collections.abc import Callable, Mapping
import json
from pathlib import Path
from typing import Any

from validation.tools import validate_judge_entrypoints as judge_validator
from validation.tools.ai_candidate_harness import (
    canonical_json_bytes,
    extract_gate_failure_facts,
    prove_fresh_oracle,
    route_candidates,
    validate_exact_candidate,
)
from validation.tools._ai_candidate_harness_parts.context import (
    atomic_write_json,
    sha256_bytes,
    sha256_path,
)
from validation.tools._auto_migrate_ai_repair import repair_ai_candidate_after_validation


CompileRunner = Callable[[Path], dict[str, Any]]
ReplayRunner = Callable[[Path, Path], dict[str, Any]]


def run_ai_exact_stage(
    spec: Mapping[str, Any],
    *,
    context_pack: dict[str, Any],
    ai_manifest: dict[str, Any],
    evidence_dir: Path,
    canonical_draft_path: Path,
    deterministic_candidate_path: Path | None,
    c2rust_baseline: Mapping[str, Any] | None,
    c2rust_baseline_manifest_path: Path | None,
    replay_test_path: Path,
    oracle_payload: Mapping[str, Any],
    harness_path: Path,
    proof_root: Path,
    compile_runner: CompileRunner,
    replay_runner: ReplayRunner,
    max_repair_rounds: int,
    opencode_command: str,
    resolved_model: str,
    agent: str,
    variant: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    slice_id = str(spec["slice_id"])
    attempts_root = evidence_dir / "ai-exact-attempts"
    ai_result = _validate_with_new_attempt(
        spec,
        label="ai-initial",
        candidate_path=canonical_draft_path,
        replay_test_path=replay_test_path,
        oracle_payload=oracle_payload,
        harness_path=harness_path,
        proof_root=proof_root,
        attempts_root=attempts_root,
        compile_runner=compile_runner,
        replay_runner=replay_runner,
    )
    deterministic_result = None
    c2rust_baseline_result = None
    canonical_changed = False

    if (
        ai_result["status"] != "passed"
        and deterministic_candidate_path is not None
        and deterministic_candidate_path.is_file()
        and sha256_path(deterministic_candidate_path) != ai_result["candidate_sha256"]
    ):
        deterministic_result = _validate_with_new_attempt(
            spec,
            label="typed-ir",
            candidate_path=deterministic_candidate_path,
            replay_test_path=replay_test_path,
            oracle_payload=oracle_payload,
            harness_path=harness_path,
            proof_root=proof_root,
            attempts_root=attempts_root,
            compile_runner=compile_runner,
            replay_runner=replay_runner,
        )

    if (
        ai_result["status"] != "passed"
        and not (deterministic_result and deterministic_result["status"] == "passed")
        and max_repair_rounds > 0
    ):
        def validate_repair(path: Path, round_number: int) -> dict[str, Any]:
            result = _validate_with_new_attempt(
                spec,
                label=f"ai-repair-{round_number:02d}",
                candidate_path=path,
                replay_test_path=replay_test_path,
                oracle_payload=oracle_payload,
                harness_path=harness_path,
                proof_root=proof_root,
                attempts_root=attempts_root,
                compile_runner=compile_runner,
                replay_runner=replay_runner,
            )
            return result["repair_validation_result"]

        ai_manifest, repair_report = repair_ai_candidate_after_validation(
            context_pack,
            ai_manifest,
            out_dir=evidence_dir,
            canonical_draft_path=canonical_draft_path,
            initial_failure_facts=ai_result["repair_validation_result"],
            validation_runner=validate_repair,
            max_rounds=max_repair_rounds,
            opencode_command=opencode_command,
            resolved_model=resolved_model,
            agent=agent,
            variant=variant,
            timeout_seconds=timeout_seconds,
        )
        if repair_report and repair_report.get("status") == "candidate_ready_for_common_validation":
            canonical_changed = True
            ai_result = _validate_with_new_attempt(
                spec,
                label="ai-repair-final",
                candidate_path=canonical_draft_path,
                replay_test_path=replay_test_path,
                oracle_payload=oracle_payload,
                harness_path=harness_path,
                proof_root=proof_root,
                attempts_root=attempts_root,
                compile_runner=compile_runner,
                replay_runner=replay_runner,
            )

    baseline_path, baseline_audit = resolve_current_c2rust_baseline_candidate(
        c2rust_baseline,
        manifest_path=c2rust_baseline_manifest_path,
        evidence_dir=evidence_dir,
        repo_root=proof_root,
    )
    if baseline_path is not None:
        baseline_sha = sha256_path(baseline_path)
        prior_result = next(
            (
                result
                for result in (ai_result, deterministic_result)
                if result is not None and result.get("candidate_sha256") == baseline_sha
            ),
            None,
        )
        if prior_result is not None:
            c2rust_baseline_result = prior_result
            baseline_audit.update(
                status="duplicate",
                reason="duplicate_exact_artifact_sha256",
                duplicate_candidate_sha256=baseline_sha,
            )
        elif not any(
            result is not None and result.get("status") == "passed"
            for result in (ai_result, deterministic_result)
        ):
            c2rust_baseline_result = _validate_with_new_attempt(
                spec,
                label="c2rust-baseline",
                candidate_path=baseline_path,
                replay_test_path=replay_test_path,
                oracle_payload=oracle_payload,
                harness_path=harness_path,
                proof_root=proof_root,
                attempts_root=attempts_root,
                compile_runner=compile_runner,
                replay_runner=replay_runner,
            )
            baseline_audit.update(
                status="exact_gates_completed",
                reason="fresh_exact_gates_passed"
                if c2rust_baseline_result["status"] == "passed"
                else "fresh_exact_gates_failed",
                exact_validation_status=c2rust_baseline_result["status"],
            )
        else:
            baseline_audit.update(
                status="not_attempted",
                reason="higher_priority_candidate_passed",
            )

    candidates = [_router_candidate("opencode-glm51-1", "opencode-ai", ai_result)]
    if deterministic_result is not None:
        candidates.append(
            _router_candidate("typed-ir:clang-lowered", "typed-ir", deterministic_result)
        )
    if c2rust_baseline_result is not None:
        candidates.append(
            _router_candidate(
                "c2rust-baseline:raw-current-run",
                "c2rust-baseline",
                c2rust_baseline_result,
            )
        )
    router = route_candidates(candidates, provider_invocations=1)
    selected_id = router.get("selected_candidate_id")
    if selected_id == "typed-ir:clang-lowered" and deterministic_candidate_path is not None:
        canonical_draft_path.write_bytes(deterministic_candidate_path.read_bytes())
        canonical_changed = True
        _mark_ai_not_applied(ai_manifest, evidence_dir, slice_id)
    elif selected_id == "c2rust-baseline:raw-current-run" and baseline_path is not None:
        canonical_draft_path.write_bytes(baseline_path.read_bytes())
        canonical_changed = True
        _mark_ai_not_applied(ai_manifest, evidence_dir, slice_id)

    summaries: dict[str, Any] = {}
    summaries["ai"] = _persist_candidate_result(
        ai_result,
        evidence_dir / f"l3-{slice_id}-ai-exact-validation.json",
    )
    if deterministic_result is not None:
        summaries["typed_ir"] = _persist_candidate_result(
            deterministic_result,
            evidence_dir / f"l3-{slice_id}-typed-ir-exact-validation.json",
        )
    if c2rust_baseline_result is not None and baseline_audit["status"] != "duplicate":
        summaries["c2rust_baseline"] = _persist_candidate_result(
            c2rust_baseline_result,
            evidence_dir / f"l3-{slice_id}-c2rust-baseline-exact-validation.json",
        )
    router_path = evidence_dir / f"l3-{slice_id}-ai-router.json"
    router_payload = {
        **router,
        "candidate_evidence": summaries,
        "candidate_source_audit": {"c2rust_baseline": baseline_audit},
        "canonical_draft_sha256": sha256_path(canonical_draft_path),
        "semantic_pass": selected_id is not None,
    }
    atomic_write_json(router_path, router_payload)
    return {
        "ai_manifest": ai_manifest,
        "router": router_payload,
        "router_path": router_path,
        "canonical_changed": canonical_changed,
    }


def resolve_current_c2rust_baseline_candidate(
    baseline_manifest: Mapping[str, Any] | None,
    *,
    manifest_path: Path | None,
    evidence_dir: Path,
    repo_root: Path,
) -> tuple[Path | None, dict[str, Any]]:
    audit: dict[str, Any] = {
        "source": "c2rust-baseline",
        "status": "rejected",
        "reason": "baseline_manifest_missing",
    }
    if not isinstance(baseline_manifest, Mapping) or manifest_path is None:
        return None, audit

    evidence_root = evidence_dir.resolve()
    resolved_manifest = manifest_path.resolve()
    try:
        resolved_manifest.relative_to(evidence_root)
    except ValueError:
        audit["reason"] = "baseline_manifest_outside_current_run"
        return None, audit
    if not resolved_manifest.is_file() or resolved_manifest.is_symlink():
        audit["reason"] = "baseline_manifest_not_reopenable"
        return None, audit
    try:
        reopened = json.loads(resolved_manifest.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        audit["reason"] = "baseline_manifest_invalid_json"
        return None, audit
    if not isinstance(reopened, dict) or canonical_json_bytes(reopened) != canonical_json_bytes(
        dict(baseline_manifest)
    ):
        audit["reason"] = "baseline_manifest_payload_drift"
        return None, audit

    manifest_status = reopened.get("status")
    audit["manifest_status"] = manifest_status if isinstance(manifest_status, str) else "invalid"
    if manifest_status != "generated":
        audit["reason"] = "baseline_manifest_not_generated"
        return None, audit
    output = reopened.get("output")
    if not isinstance(output, dict) or output.get("status") != "generated":
        audit["reason"] = "baseline_output_not_generated"
        return None, audit
    output_path_value = output.get("path")
    declared_sha = output.get("sha256")
    if not isinstance(output_path_value, str) or not output_path_value:
        audit["reason"] = "baseline_output_path_missing"
        return None, audit
    if not _is_sha256(declared_sha):
        audit["reason"] = "baseline_output_sha256_invalid"
        return None, audit

    output_path = _resolve_current_run_artifact(
        output_path_value,
        evidence_root=evidence_root,
        repo_root=repo_root.resolve(),
    )
    if output_path is None:
        audit["reason"] = "baseline_output_not_reopenable_in_current_run"
        return None, audit
    if judge_validator.sha256_file(output_path) != declared_sha:
        audit["reason"] = "baseline_output_sha256_mismatch"
        return None, audit

    candidate_sha = sha256_path(output_path)
    audit.update(
        status="eligible_for_exact_gates",
        reason="current_run_manifest_and_output_reopened",
        manifest={
            "path": resolved_manifest.relative_to(evidence_root).as_posix(),
            "sha256": sha256_path(resolved_manifest),
        },
        artifact={
            "path": output_path.relative_to(evidence_root).as_posix(),
            "declared_sha256": declared_sha,
            "candidate_sha256": candidate_sha,
        },
    )
    return output_path, audit


def _resolve_current_run_artifact(
    value: str,
    *,
    evidence_root: Path,
    repo_root: Path,
) -> Path | None:
    configured = Path(value)
    candidates = (
        [configured]
        if configured.is_absolute()
        else [repo_root / configured, evidence_root / configured]
    )
    for candidate in candidates:
        resolved = candidate.resolve()
        try:
            resolved.relative_to(evidence_root)
        except ValueError:
            continue
        if resolved.is_file() and not resolved.is_symlink():
            return resolved
    return None


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _validate_with_new_attempt(
    spec: Mapping[str, Any],
    *,
    label: str,
    candidate_path: Path,
    replay_test_path: Path,
    oracle_payload: Mapping[str, Any],
    harness_path: Path,
    proof_root: Path,
    attempts_root: Path,
    compile_runner: CompileRunner,
    replay_runner: ReplayRunner,
) -> dict[str, Any]:
    candidate_sha = sha256_path(candidate_path)
    attempt_dir = next_attempt_dir(attempts_root, label, candidate_sha)
    result = validate_auto_migrate_candidate(
        spec,
        candidate_path=candidate_path,
        replay_test_path=replay_test_path,
        oracle_payload=oracle_payload,
        harness_path=harness_path,
        proof_root=proof_root,
        attempt_dir=attempt_dir,
        compile_runner=compile_runner,
        replay_runner=replay_runner,
    )
    result["attempt_dir"] = attempt_dir.as_posix()
    return result


def next_attempt_dir(root: Path, label: str, candidate_sha: str) -> Path:
    safe_label = "".join(character if character.isalnum() or character in "-_" else "-" for character in label)
    for ordinal in range(1, 100):
        candidate = root / f"{ordinal:02d}-{safe_label}-{candidate_sha[:12]}"
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise ValueError("AI exact validation attempt limit exceeded")


def _router_candidate(candidate_id: str, source: str, result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "source": source,
        "artifact_sha256": result["candidate_sha256"],
        "gate_results": result["router_gate_results"],
    }


def _persist_candidate_result(result: Mapping[str, Any], path: Path) -> dict[str, Any]:
    payload = dict(result)
    attempt_dir = Path(str(payload.pop("attempt_dir")))
    persist_exact_validation_summary(payload, path=path, attempt_dir=attempt_dir)
    return {"path": path.name, "sha256": sha256_path(path), "status": payload["status"]}


def _mark_ai_not_applied(manifest: dict[str, Any], evidence_dir: Path, slice_id: str) -> None:
    candidates = manifest.get("candidates")
    if isinstance(candidates, list) and len(candidates) == 1 and isinstance(candidates[0], dict):
        candidate = candidates[0]
        candidate["applied"] = False
        candidate.pop("applied_artifact", None)
        candidate.pop("rust_draft_sha256", None)
    manifest.pop("selected_candidate_id", None)
    atomic_write_json(evidence_dir / f"l3-{slice_id}-ai-candidate-manifest.json", manifest)


def validate_auto_migrate_candidate(
    spec: Mapping[str, Any],
    *,
    candidate_path: Path,
    replay_test_path: Path,
    oracle_payload: Mapping[str, Any],
    harness_path: Path,
    proof_root: Path,
    attempt_dir: Path,
    compile_runner: CompileRunner,
    replay_runner: ReplayRunner,
) -> dict[str, Any]:
    candidate_sha = sha256_path(candidate_path)
    oracle_proof = prove_fresh_oracle(
        spec,
        oracle_payload,
        harness_path,
        proof_root,
        artifact_root=_artifact_root(proof_root, harness_path),
    )
    target_contract = oracle_proof.get("target_contract", {})
    target_sha = oracle_proof.get("target_contract_sha256")
    fixture_identity = oracle_proof.get("shared_fixture_identity")
    fixture_sha = (
        sha256_bytes(canonical_json_bytes(fixture_identity))
        if isinstance(fixture_identity, dict)
        else None
    )
    observable_outputs = oracle_proof.get("observable_outputs")

    def exact_compile_runner(**kwargs: Any) -> dict[str, Any]:
        path = Path(kwargs["candidate_path"])
        result = compile_runner(path)
        return {
            "status": "passed" if result.get("returncode") == 0 else "failed",
            "returncode": int(result.get("returncode", 1)),
            "candidate_sha256": sha256_path(path),
            "target_contract_sha256": target_sha,
            "errors": result.get("errors", []),
        }

    def exact_replay_runner(**kwargs: Any) -> dict[str, Any]:
        path = Path(kwargs["candidate_path"])
        replay_path = Path(kwargs["replay_test_path"])
        result = replay_runner(path, replay_path)
        phase = str(result.get("phase", "compile"))
        returncode = (
            result.get("run_returncode")
            if phase == "run"
            else result.get("compile_returncode")
        )
        return {
            "status": str(result.get("status", "failed")),
            "phase": phase,
            "returncode": int(returncode if isinstance(returncode, int) else 1),
            "candidate_sha256": sha256_path(path),
            "replay_test_sha256": sha256_path(replay_path),
            "shared_fixture_identity_sha256": fixture_sha,
            "target_contract_sha256": target_sha,
            "observable_outputs": observable_outputs,
            "observable_outputs_sha256": (
                sha256_bytes(canonical_json_bytes(observable_outputs))
                if observable_outputs is not None
                else None
            ),
        }

    exact_oracle_proof = {
        key: oracle_proof.get(key)
        for key in (
            "schema_version",
            "status",
            "shared_fixture_identity",
            "oracle_run_sha256",
            "target_contract_sha256",
            "observable_outputs",
        )
    }
    gates = validate_exact_candidate(
        candidate_path,
        candidate_sha256=candidate_sha,
        generated_replay_test=replay_test_path,
        fresh_oracle_proof=exact_oracle_proof,
        unsafe_policy=unsafe_policy_from_spec(spec),
        unsafe_ledger=current_candidate_unsafe_ledger(candidate_sha),
        target_contract=target_contract,
        attempt_dir=attempt_dir,
        compile_runner=exact_compile_runner,
        replay_runner=exact_replay_runner,
        alias_proof=None,
    )
    validation_result = extract_gate_failure_facts(
        gates,
        selected_candidate_sha256=candidate_sha,
    )
    return {
        "schema_version": 1,
        "status": "passed" if validation_result["status"] == "passed" else "failed",
        "candidate_sha256": candidate_sha,
        "semantic_pass": validation_result["status"] == "passed",
        "oracle_proof": oracle_proof,
        "gate_index": {
            "path": (attempt_dir / "gate-index.json").name,
            "sha256": sha256_path(attempt_dir / "gate-index.json"),
        },
        "gates": gates,
        "repair_validation_result": validation_result,
        "router_gate_results": router_gate_results(gates, candidate_sha),
    }


def persist_exact_validation_summary(
    result: Mapping[str, Any],
    *,
    path: Path,
    attempt_dir: Path,
) -> dict[str, Any]:
    payload = dict(result)
    gate_index = dict(payload.get("gate_index", {}))
    gate_index["path"] = attempt_dir.relative_to(path.parent).as_posix() + "/gate-index.json"
    payload["gate_index"] = gate_index
    atomic_write_json(path, payload)
    return payload


def router_gate_results(
    gates: Mapping[str, Any],
    candidate_sha: str,
) -> dict[str, dict[str, Any]]:
    def one(name: str, *source_gates: str) -> dict[str, Any]:
        values = [gates.get(source) for source in source_gates]
        passed = all(
            isinstance(value, Mapping)
            and value.get("candidate_sha256") == candidate_sha
            and value.get("status") in ({"passed", "expected_failed"} if source == "negative_mutation" else {"passed"})
            for source, value in zip(source_gates, values)
        )
        return {
            "status": "passed" if passed else "failed",
            "candidate_sha256": candidate_sha,
            "source_gates": list(source_gates),
        }

    return {
        "compile": one("compile", "rustc"),
        "oracle": one("oracle", "oracle_contract"),
        "replay": one("replay", "generated_replay"),
        "schema_diff": one("schema_diff", "schema_diff"),
        "negative_diff": one("negative_diff", "negative_mutation"),
        "unsafe": one("unsafe", "unsafe_scan", "unsafe_ledger"),
        "alias_abi": one("alias_abi", "alias_contract", "abi_contract"),
        "final_verification": one("final_verification", "final_verification"),
    }


def unsafe_policy_from_spec(spec: Mapping[str, Any]) -> dict[str, Any]:
    rust_boundary = spec.get("rust_boundary", {})
    policy = rust_boundary.get("unsafe_policy", {}) if isinstance(rust_boundary, Mapping) else {}
    maximum = policy.get("max_unsafe_tokens", 0) if isinstance(policy, Mapping) else 0
    if not isinstance(maximum, int) or isinstance(maximum, bool) or not 0 <= maximum <= 128:
        maximum = 0
    return {
        "schema_version": 1,
        "max_unsafe_tokens": maximum,
        "require_ledger": True,
    }


def current_candidate_unsafe_ledger(candidate_sha: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "passed",
        "provenance": "current_candidate",
        "candidate_sha256": candidate_sha,
        "entries": [],
    }


def _artifact_root(source_root: Path, harness_path: Path) -> Path:
    try:
        harness_path.resolve().relative_to(source_root.resolve())
        return source_root.resolve()
    except ValueError:
        return harness_path.resolve().parent
