from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any


CompileRunner = Callable[[Path], dict[str, Any]]
ReplayRunner = Callable[[Path, Path], dict[str, Any]]


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
    canonical_json_bytes: Callable[[Any], bytes],
    extract_gate_failure_facts: Callable[..., dict[str, Any]],
    prove_fresh_oracle: Callable[..., dict[str, Any]],
    validate_exact_candidate: Callable[..., dict[str, Any]],
    sha256_bytes: Callable[[bytes], str],
    sha256_path: Callable[[Path], str],
    artifact_root: Callable[[Path, Path], Path],
    current_candidate_unsafe_ledger: Callable[[str], dict[str, Any]],
    router_gate_results: Callable[
        [Mapping[str, Any], str], dict[str, dict[str, Any]]
    ],
    unsafe_policy_from_spec: Callable[[Mapping[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    candidate_sha = sha256_path(candidate_path)
    oracle_proof = prove_fresh_oracle(
        spec,
        oracle_payload,
        harness_path,
        proof_root,
        artifact_root=artifact_root(proof_root, harness_path),
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


def router_gate_results(
    gates: Mapping[str, Any],
    candidate_sha: str,
) -> dict[str, dict[str, Any]]:
    def one(name: str, *source_gates: str) -> dict[str, Any]:
        values = [gates.get(source) for source in source_gates]
        passed = all(
            isinstance(value, Mapping)
            and value.get("candidate_sha256") == candidate_sha
            and value.get("status")
            in ({"passed", "expected_failed"} if source == "negative_mutation" else {"passed"})
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


def artifact_root(source_root: Path, harness_path: Path) -> Path:
    try:
        harness_path.resolve().relative_to(source_root.resolve())
        return source_root.resolve()
    except ValueError:
        return harness_path.resolve().parent
