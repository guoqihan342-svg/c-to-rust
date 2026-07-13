from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .context_security import atomic_write_bytes, sha256_bytes, sha256_path
from .exact_validation_artifacts import (
    Runner,
    binding_failures,
    fact,
    gate,
    new_dir,
    persist,
    read_input,
    require_sha,
)
from .exact_validation_contracts import (
    abi_gate,
    alias_gate,
    mask_noncode,
    target_contract as normalize_target_contract,
    unsafe_ledger_gate,
    unsafe_scan_gate,
)
from .exact_validation_runners import (
    compile_gate,
    negative_mutation_gate,
    oracle_gate,
    replay_gate,
    schema_diff_gate,
)
from validation.tools.replay_assertion_inventory import (
    validate_inventory_fixture_identity,
    validate_inventory_source_markers,
)


def validate_exact_candidate(
    candidate_path: Path,
    *,
    candidate_sha256: str,
    generated_replay_test: Path,
    fresh_oracle_proof: Mapping[str, Any],
    unsafe_policy: Mapping[str, Any],
    unsafe_ledger: Mapping[str, Any],
    target_contract: Mapping[str, Any],
    attempt_dir: Path,
    compile_runner: Runner,
    replay_runner: Runner,
    replay_assertion_inventory: dict[str, Any] | None = None,
    alias_proof: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Return ten exact, SHA-bound gate payloads for one frozen candidate.

    The injected runners execute only; this validator owns every acceptance
    decision. The returned mapping can be passed to extract_gate_failure_facts.
    """
    selected_sha = require_sha(candidate_sha256, "candidate_sha256")
    candidate = read_input(candidate_path, "candidate")
    replay_bytes = read_input(generated_replay_test, "generated replay test")
    root = new_dir(attempt_dir)
    frozen = root / "candidate.rs"
    replay_test = root / "generated-replay-test.rs"
    atomic_write_bytes(frozen, candidate)
    atomic_write_bytes(replay_test, replay_bytes)
    actual_sha = sha256_bytes(candidate)
    if actual_sha != selected_sha:
        return persist(root, selected_sha, binding_failures(selected_sha, actual_sha))
    target, target_sha, target_error = normalize_target_contract(target_contract)
    oracle, oracle_values = oracle_gate(
        fresh_oracle_proof, selected_sha, target_sha, target_error
    )
    if replay_assertion_inventory is not None:
        try:
            validate_inventory_source_markers(
                replay_assertion_inventory,
                replay_bytes.decode("utf-8"),
            )
            validate_inventory_fixture_identity(
                replay_assertion_inventory,
                oracle_values.get("shared_fixture_identity"),
            )
        except (UnicodeError, ValueError):
            replay_assertion_inventory = None
    rustc = compile_gate(
        compile_runner,
        frozen,
        root / "compile",
        selected_sha,
        target,
        target_sha,
        target_error,
    )
    replay = replay_gate(
        replay_runner,
        frozen,
        replay_test,
        root / "replay",
        selected_sha,
        target,
        target_sha,
        oracle_values.get("shared_fixture_identity"),
        oracle_values.get("shared_fixture_identity_sha256"),
        rustc["status"] == "passed",
        replay_assertion_inventory,
    )
    schema_diff = schema_diff_gate(selected_sha, oracle, oracle_values, replay)
    negative = negative_mutation_gate(
        replay_runner,
        frozen,
        replay_test,
        replay_bytes,
        root,
        selected_sha,
        target,
        target_sha,
        oracle_values.get("shared_fixture_identity"),
        oracle_values.get("shared_fixture_identity_sha256"),
        rustc["status"] == replay["status"] == "passed",
    )
    source = mask_noncode(candidate.decode("utf-8"))
    scan, tokens, policy = unsafe_scan_gate(source, selected_sha, unsafe_policy)
    ledger = unsafe_ledger_gate(selected_sha, unsafe_ledger, tokens, policy)
    alias = alias_gate(selected_sha, source, alias_proof, target_sha, target_error)
    abi = abi_gate(selected_sha, rustc, replay, oracle, target_sha, target_error)
    gates = {
        "rustc": rustc,
        "generated_replay": replay,
        "schema_diff": schema_diff,
        "negative_mutation": negative,
        "unsafe_scan": scan,
        "unsafe_ledger": ledger,
        "alias_contract": alias,
        "abi_contract": abi,
        "oracle_contract": oracle,
    }
    unchanged = sha256_path(frozen) == selected_sha
    accepted = unchanged and all(
        value.get("candidate_sha256") == selected_sha
        and value.get("status")
        == ("expected_failed" if key == "negative_mutation" else "passed")
        for key, value in gates.items()
    )
    reason = "candidate_sha_drift" if not unchanged else "required_gate_failed"
    gates["final_verification"] = gate(
        selected_sha,
        "passed" if accepted else "failed",
        semantic_pass=accepted,
        required_gates=list(gates),
        failures=[]
        if accepted
        else [fact(reason, "Exact validation did not accept this candidate.")],
    )
    return persist(root, selected_sha, gates)
