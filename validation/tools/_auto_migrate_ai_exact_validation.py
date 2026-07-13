from __future__ import annotations

from collections.abc import Callable, Mapping
import json
from pathlib import Path
from typing import Any

from validation.tools._ai_candidate_harness_parts.context_replay import (
    validate_replay_api_contract_binding,
)
from validation.tools._ai_candidate_harness_parts.provider_readiness import (
    evaluate_provider_readiness,
)
from validation.tools._ai_candidate_harness_parts.context import (
    canonical_json_bytes,
    sha256_path as _sha256_path,
)
from validation.tools._auto_migrate_ai_exact_results import (
    bound_replay_assertion_inventory,
    exact_replay_runner_result,
)


CompileRunner = Callable[[Path], dict[str, Any]]
ReplayRunner = Callable[[Path, Path], dict[str, Any]]


def validate_ai_exact_stage_contract(
    context_pack: dict[str, Any],
    ai_manifest: dict[str, Any],
    *,
    evidence_dir: Path,
    replay_test_path: Path,
    canonical_draft_path: Path,
) -> None:
    if ai_manifest.get("schema_version") not in {8, 9}:
        raise ValueError("AI exact stage requires candidate manifest schema_version 8 or 9")
    if context_pack.get("schema_version") != 4:
        raise ValueError("AI exact stage requires ContextPack schema_version 4")
    contract = context_pack.get("replay_api_contract")
    source = contract.get("source") if isinstance(contract, dict) else None
    expected_name = source.get("path") if isinstance(source, dict) else None
    target_id = context_pack.get("target_id")
    slice_id = context_pack.get("slice_id")
    bindings = ai_manifest.get("bindings")
    context_ref = bindings.get("context_pack") if isinstance(bindings, dict) else None
    context_name = context_ref.get("path") if isinstance(context_ref, dict) else None
    context_path = evidence_dir / str(context_name or "")
    candidates = ai_manifest.get("candidates")
    candidate = candidates[0] if isinstance(candidates, list) and len(candidates) == 1 else None
    selected_id = ai_manifest.get("selected_candidate_id")
    applied_artifact = candidate.get("applied_artifact") if isinstance(candidate, dict) else None
    input_hashes = candidate.get("input_artifact_hashes") if isinstance(candidate, dict) else None
    try:
        persisted_context = json.loads(context_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        persisted_context = None
    if (
        not isinstance(expected_name, str)
        or not isinstance(target_id, str)
        or not isinstance(slice_id, str)
        or ai_manifest.get("target_id") != target_id
        or ai_manifest.get("slice_id") != slice_id
        or ai_manifest.get("status") != "generated"
        or context_name != f"l3-{slice_id}-ai-context-pack.json"
        or context_path.is_symlink()
        or not context_path.is_file()
        or context_ref.get("sha256") != _sha256_path(context_path)
        or canonical_json_bytes(persisted_context) != canonical_json_bytes(context_pack)
        or not isinstance(candidate, dict)
        or selected_id != candidate.get("candidate_id")
        or candidate.get("applied") is not True
        or not isinstance(applied_artifact, dict)
        or canonical_draft_path.resolve()
        != (evidence_dir / str(applied_artifact.get("path") or "")).resolve()
        or canonical_draft_path.is_symlink()
        or not canonical_draft_path.is_file()
        or applied_artifact.get("sha256") != _sha256_path(canonical_draft_path)
        or candidate.get("rust_draft_sha256") != _sha256_path(canonical_draft_path)
        or not isinstance(input_hashes, dict)
        or input_hashes.get("context_pack") != context_ref.get("sha256")
        or replay_test_path.is_symlink()
        or not replay_test_path.is_file()
        or replay_test_path.resolve() != (evidence_dir / expected_name).resolve()
        or validate_replay_api_contract_binding(
            context_pack,
            evidence_dir / "ai-context-pack.json",
        )
        != "bound"
        or evaluate_provider_readiness(context_pack).get("status") != "ready"
    ):
        raise ValueError("AI exact stage requires a provider-ready replay-bound ContextPack")


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
    assertion_inventory = bound_replay_assertion_inventory(
        spec, proof_root, replay_test_path
    )

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
        return exact_replay_runner_result(
            result,
            candidate_path=path,
            replay_path=replay_path,
            target_sha256=target_sha,
            fixture_sha256=fixture_sha,
            observable_outputs=observable_outputs,
            sha256_path=sha256_path,
            sha256_observables=lambda value: sha256_bytes(
                canonical_json_bytes(value)
            ),
            assertion_inventory=assertion_inventory,
        )

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
        replay_assertion_inventory=assertion_inventory,
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
