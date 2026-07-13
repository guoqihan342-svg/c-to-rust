from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .compiler_diagnostics import compiler_failure_fact
from validation.tools.replay_runtime_assertion import (
    localized_runtime_assertion_details,
)
from validation.tools.replay_negative_mutation import mutate_key_replay_assertion
from .context_security import (
    atomic_write_bytes,
    canonical_json_bytes,
    sha256_bytes,
    sha256_path,
)
from .exact_validation_artifacts import (
    Runner,
    execution_binding,
    failed,
    first_mismatch,
    forbidden_oracle_reference,
    gate,
    integer,
    make_dir,
    observables,
    phase,
    replay_binding,
    run,
    safe_json,
    valid_sha,
)


def compile_gate(
    runner: Runner,
    candidate: Path,
    work: Path,
    candidate_sha: str,
    target: dict[str, Any],
    target_sha: str | None,
    target_error: str | None,
) -> dict[str, Any]:
    if target_error:
        return failed(candidate_sha, "invalid_target_contract", target_error)
    result = run(
        runner,
        candidate_path=candidate,
        work_dir=make_dir(work),
        target_contract=target,
    )
    error = execution_binding(result, candidate_sha, target_sha)
    if error is None and result.get("status") == "passed" and result.get("returncode") == 0:
        return gate(
            candidate_sha,
            "passed",
            returncode=0,
            target_contract_sha256=target_sha,
        )
    failure_kind = error or "compile_failed"
    failure_message = "The exact candidate did not compile for the target contract."
    failure = (
        {"kind": failure_kind, "message": failure_message}
        if error is not None
        else compiler_failure_fact(failure_kind, failure_message, result)
    )
    return gate(
        candidate_sha,
        "failed",
        failures=[failure],
        returncode=integer(result.get("returncode")),
        target_contract_sha256=target_sha,
    )


def replay_gate(
    runner: Runner,
    candidate: Path,
    replay_test: Path,
    work: Path,
    candidate_sha: str,
    target: dict[str, Any],
    target_sha: str | None,
    fixture_identity: Any,
    fixture_sha: Any,
    prerequisite: bool,
    assertion_inventory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    test_sha = sha256_path(replay_test)
    if not prerequisite:
        return failed(
            candidate_sha,
            "rustc_prerequisite_failed",
            "Replay requires rustc success.",
        )
    result = run(
        runner,
        candidate_path=candidate,
        replay_test_path=replay_test,
        work_dir=make_dir(work),
        target_contract=target,
        shared_fixture_identity=fixture_identity,
        mode="positive",
    )
    error = replay_binding(result, candidate_sha, test_sha, target_sha, fixture_sha)
    if result.get("phase") == "compile" or result.get("status") != "passed":
        outputs = None
    else:
        try:
            outputs = observables(result)
        except ValueError:
            outputs, error = None, error or "invalid_observable_outputs"
    passed = (
        error is None
        and result.get("status") == "passed"
        and result.get("phase") == "run"
        and result.get("returncode") == 0
        and outputs is not None
    )
    execution = {
        "status": "passed" if passed else "failed",
        "phase": phase(result.get("phase")),
        "returncode": integer(result.get("returncode")),
    }
    base = {
        "generated_draft_replay_pass": passed,
        "replay_execution": execution,
        "replay_test_sha256": test_sha,
    }
    if not passed:
        compile_failed = error is None and result.get("phase") == "compile"
        failure_kind = "replay_compile_failed" if compile_failed else error or "replay_failed"
        failure_message = "The exact candidate replay did not run successfully."
        runtime_details = (
            localized_runtime_assertion_details(
                result.get("runtime_assertion_failure"), assertion_inventory
            )
            if error is None and result.get("phase") == "run"
            else None
        )
        if compile_failed:
            failure = compiler_failure_fact(failure_kind, failure_message, result)
        elif runtime_details is not None:
            failure = {
                "kind": "runtime_assertion_failed",
                "message": "A generated replay observable assertion failed.",
                "details": runtime_details,
            }
        else:
            failure = {"kind": failure_kind, "message": failure_message}
        return gate(
            candidate_sha,
            "failed",
            failures=[failure],
            **base,
        )
    output_sha = sha256_bytes(canonical_json_bytes(outputs))
    if result.get("observable_outputs_sha256") != output_sha:
        return failed(
            candidate_sha,
            "observable_output_sha256_mismatch",
            "Replay output hash does not bind its observables.",
            **base,
        )
    return gate(
        candidate_sha,
        "passed",
        **base,
        shared_fixture_identity_sha256=fixture_sha,
        observable_outputs=outputs,
        observable_outputs_sha256=output_sha,
        target_contract_sha256=target_sha,
    )


def oracle_gate(
    proof: Mapping[str, Any],
    candidate_sha: str,
    target_sha: str | None,
    target_error: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if target_error:
        return failed(candidate_sha, "invalid_target_contract", target_error), {}
    if not isinstance(proof, Mapping) or forbidden_oracle_reference(proof):
        return (
            failed(
                candidate_sha,
                "fresh_oracle_required",
                "Historical oracle reports are forbidden.",
            ),
            {},
        )
    try:
        identity = safe_json(proof["shared_fixture_identity"])
        outputs = observables(proof)
    except (KeyError, ValueError):
        return failed(
            candidate_sha,
            "fresh_oracle_invalid",
            "Fresh oracle payload is invalid.",
        ), {}
    fixture_sha = sha256_bytes(canonical_json_bytes(identity))
    output_sha = sha256_bytes(canonical_json_bytes(outputs))
    valid = (
        proof.get("schema_version") == 1
        and proof.get("status") == "passed"
        and valid_sha(proof.get("oracle_run_sha256"))
        and proof.get("target_contract_sha256") == target_sha
    )
    if not valid:
        return failed(
            candidate_sha,
            "fresh_oracle_invalid",
            "Fresh oracle bindings are invalid.",
        ), {}
    values = {
        "shared_fixture_identity": identity,
        "shared_fixture_identity_sha256": fixture_sha,
        "observable_outputs": outputs,
        "observable_outputs_sha256": output_sha,
    }
    return (
        gate(
            candidate_sha,
            "passed",
            fresh=True,
            provenance="fresh_run",
            oracle_run_sha256=proof["oracle_run_sha256"],
            shared_fixture_identity=identity,
            shared_fixture_identity_sha256=fixture_sha,
            observable_outputs=outputs,
            observable_outputs_sha256=output_sha,
            target_contract_sha256=target_sha,
        ),
        values,
    )


def schema_diff_gate(
    candidate_sha: str,
    oracle: Mapping[str, Any],
    oracle_values: Mapping[str, Any],
    replay: Mapping[str, Any],
) -> dict[str, Any]:
    if oracle.get("status") != "passed" or replay.get("status") != "passed":
        return failed(
            candidate_sha,
            "comparison_prerequisite_failed",
            "Oracle and replay must pass.",
        )
    mismatch = first_mismatch(
        oracle_values["observable_outputs"], replay["observable_outputs"]
    )
    fixture_match = (
        oracle_values["shared_fixture_identity_sha256"]
        == replay.get("shared_fixture_identity_sha256")
    )
    if mismatch is None and fixture_match:
        return gate(
            candidate_sha,
            "passed",
            first_mismatch=None,
            shared_fixture_identity_sha256=oracle_values[
                "shared_fixture_identity_sha256"
            ],
            oracle_observable_outputs_sha256=oracle_values[
                "observable_outputs_sha256"
            ],
            replay_observable_outputs_sha256=replay["observable_outputs_sha256"],
        )
    first = mismatch or {
        "path": "$fixture",
        "expected": oracle_values["shared_fixture_identity_sha256"],
        "actual": replay.get("shared_fixture_identity_sha256"),
    }
    return failed(
        candidate_sha,
        "value_mismatch" if mismatch else "fixture_mismatch",
        "C oracle and Rust replay differ.",
        first_mismatch=first,
    )


def negative_mutation_gate(
    runner: Runner,
    candidate: Path,
    original: Path,
    test_bytes: bytes,
    root: Path,
    candidate_sha: str,
    target: dict[str, Any],
    target_sha: str | None,
    fixture_identity: Any,
    fixture_sha: Any,
    prerequisite: bool,
) -> dict[str, Any]:
    mutated = mutate_key_replay_assertion(test_bytes.decode("utf-8"))
    if mutated is None:
        return failed(
            candidate_sha,
            "mutation_not_applicable",
            "Replay has no key assert_eq!.",
        )
    mutated_path = root / "negative-replay-test.rs"
    atomic_write_bytes(mutated_path, mutated.encode("utf-8"))
    if not prerequisite:
        return failed(
            candidate_sha,
            "replay_prerequisite_failed",
            "Negative replay requires a passing replay.",
        )
    result = run(
        runner,
        candidate_path=candidate,
        replay_test_path=mutated_path,
        work_dir=make_dir(root / "negative-replay"),
        target_contract=target,
        shared_fixture_identity=fixture_identity,
        mode="negative",
    )
    mutated_sha = sha256_path(mutated_path)
    error = replay_binding(result, candidate_sha, mutated_sha, target_sha, fixture_sha)
    detected = (
        error is None
        and result.get("status") == "failed"
        and result.get("phase") == "run"
        and isinstance(result.get("returncode"), int)
        and result.get("returncode") != 0
    )
    fields = {
        "mutation_detected": detected,
        "original_replay_test_sha256": sha256_path(original),
        "mutated_replay_test_sha256": mutated_sha,
        "replay_execution": {
            "status": "expected_failed" if detected else "failed",
            "phase": phase(result.get("phase")),
            "returncode": integer(result.get("returncode")),
        },
    }
    if detected:
        return gate(candidate_sha, "expected_failed", **fields)
    kind = error or (
        "mutation_compile_failed"
        if result.get("phase") == "compile"
        else "mutation_survived"
    )
    return failed(
        candidate_sha,
        kind,
        "The negative mutation was not detected.",
        **fields,
    )
