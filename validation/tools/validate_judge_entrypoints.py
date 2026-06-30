#!/usr/bin/env python3
"""Validate judge-facing harness entrypoint indexes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "config" / "competition-env" / "judge-entrypoints" / "flashdb-harness.json"
LOCAL_ABSOLUTE_PATH = re.compile(r"(?:^|[^A-Za-z0-9_])(?:[A-Za-z]:[\\/]|/mnt/[A-Za-z]/)")
REQUIRED_HARNESS_FEATURES = (
    "h1_evaluate_one_click",
    "h2_multi_worker_fanout",
    "h3_precise_repair_self_heal",
    "h4_before_after_exhibit",
    "h5_context_management",
    "h6_judge_reports",
)
REQUIRED_AGENT_ROLES = ("planner", "worker", "repairer", "verifier", "reporter")
REQUIRED_CONTEXT_STAGES = ("plan", "translate", "verify", "repair")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--require-local-artifacts",
        action="store_true",
        help="Fail when expected target artifacts listed by the entrypoint index are not present locally.",
    )
    args = parser.parse_args()

    result = validate_config(
        args.config,
        require_local_artifacts=args.require_local_artifacts,
        repo_root=REPO_ROOT,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repo_relative(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def repo_path(path_text: str, *, repo_root: Path) -> Path:
    assert_repo_relative_posix(path_text)
    return repo_root / Path(*PurePosixPath(path_text).parts)


def assert_repo_relative_posix(path_text: str) -> None:
    if not isinstance(path_text, str) or not path_text:
        raise ValueError("path must be a non-empty string")
    path = PurePosixPath(path_text)
    if "\\" in path_text or path.is_absolute() or path_text.startswith("~"):
        raise ValueError(f"path must be repo-relative POSIX: {path_text}")
    if len(path_text) >= 2 and path_text[1] == ":":
        raise ValueError(f"path must not use a drive prefix: {path_text}")
    if ".." in path.parts:
        raise ValueError(f"path must not contain parent traversal: {path_text}")


def assert_no_local_absolute_path(text: str) -> None:
    if not isinstance(text, str):
        raise ValueError("command/text must be a string")
    if LOCAL_ABSOLUTE_PATH.search(text):
        raise ValueError(f"text contains local absolute path: {text}")


def validate_ref(ref: dict[str, Any], *, repo_root: Path) -> dict[str, Any]:
    path_text = ref.get("path")
    expected_sha = ref.get("sha256")
    if not isinstance(path_text, str) or not isinstance(expected_sha, str):
        raise ValueError("artifact ref must include path and sha256 strings")
    path = repo_path(path_text, repo_root=repo_root)
    if not path.is_file():
        raise ValueError(f"artifact ref path does not exist: {path_text}")
    actual_sha = sha256_file(path)
    if expected_sha != actual_sha:
        raise ValueError(f"artifact ref sha256 mismatch for {path_text}: {expected_sha} != {actual_sha}")
    return {"path": path_text, "sha256": actual_sha, "status": "present"}


def validate_expected_artifacts(
    artifacts: dict[str, Any],
    *,
    require_local_artifacts: bool,
    repo_root: Path,
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    if not isinstance(artifacts, dict):
        raise ValueError("expected_artifacts must be an object")
    for name, path_text in sorted(artifacts.items()):
        if not isinstance(path_text, str):
            raise ValueError(f"expected artifact path must be a string: {name}")
        path = repo_path(path_text, repo_root=repo_root)
        artifact = {"path": path_text, "status": "present" if path.is_file() else "missing"}
        if path.is_file():
            artifact["sha256"] = sha256_file(path)
        elif require_local_artifacts:
            raise ValueError(f"expected artifact is missing: {path_text}")
        result[str(name)] = artifact
    return result


def validate_claim_boundary(config: dict[str, Any]) -> dict[str, Any]:
    boundary = config.get("claim_boundary")
    if not isinstance(boundary, dict):
        raise ValueError("claim_boundary must be an object")
    if boundary.get("semantic_claim_source") != "accepted_evidence_binding":
        raise ValueError("claim_boundary.semantic_claim_source must be accepted_evidence_binding")
    if boundary.get("generated_draft_semantic_pass") is not False:
        raise ValueError("claim_boundary.generated_draft_semantic_pass must be false")
    if boundary.get("translation_coverage_numerator") != 0:
        raise ValueError("claim_boundary.translation_coverage_numerator must be 0")
    return {
        "semantic_claim_source": boundary["semantic_claim_source"],
        "generated_draft_semantic_pass": boundary["generated_draft_semantic_pass"],
        "translation_coverage_numerator": boundary["translation_coverage_numerator"],
    }


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def validate_test_contract(
    config: dict[str, Any],
    *,
    entrypoints: list[dict[str, Any]],
    claim_boundary: dict[str, Any],
) -> dict[str, Any]:
    contract = require_object(config.get("test_contract"), "test_contract")
    features = require_object(config.get("harness_features_demonstrated"), "harness_features_demonstrated")
    required_features = contract.get("required_harness_features", list(REQUIRED_HARNESS_FEATURES))
    if not isinstance(required_features, list) or not required_features:
        raise ValueError("test_contract.required_harness_features must be a non-empty list")
    missing_features = [feature for feature in required_features if features.get(feature) is not True]
    if missing_features:
        raise ValueError(f"harness_features_demonstrated missing true features: {missing_features}")

    entrypoint_ids = [require_string(entry.get("id"), "entrypoint.id") for entry in entrypoints]
    if len(set(entrypoint_ids)) != len(entrypoint_ids):
        raise ValueError(f"entrypoint ids must be unique: {entrypoint_ids}")
    required_entrypoint_ids = contract.get("required_entrypoint_ids")
    if not isinstance(required_entrypoint_ids, list) or not required_entrypoint_ids:
        raise ValueError("test_contract.required_entrypoint_ids must be a non-empty list")
    if set(required_entrypoint_ids) != set(entrypoint_ids):
        raise ValueError(
            "test_contract.required_entrypoint_ids must match entrypoints: "
            f"{required_entrypoint_ids} != {entrypoint_ids}"
        )

    required_artifacts = contract.get("required_expected_artifacts", [])
    if not isinstance(required_artifacts, list):
        raise ValueError("test_contract.required_expected_artifacts must be a list")
    for entry in entrypoints:
        artifacts = require_object(entry.get("expected_artifacts"), f"{entry.get('id')}.expected_artifacts")
        missing = [name for name in required_artifacts if name not in artifacts]
        if missing:
            raise ValueError(f"{entry.get('id')} missing required expected artifacts: {missing}")

    if contract.get("semantic_claim_source") != claim_boundary.get("semantic_claim_source"):
        raise ValueError("test_contract.semantic_claim_source must match claim_boundary")
    if contract.get("generated_draft_semantic_pass") is not claim_boundary.get("generated_draft_semantic_pass"):
        raise ValueError("test_contract.generated_draft_semantic_pass must match claim_boundary")
    if contract.get("translation_coverage_numerator") != claim_boundary.get("translation_coverage_numerator"):
        raise ValueError("test_contract.translation_coverage_numerator must match claim_boundary")

    repair_round_cap = contract.get("repair_round_cap", 5)
    if repair_round_cap != 5:
        raise ValueError("test_contract.repair_round_cap must be 5")
    required_roles = contract.get("required_agent_roles", list(REQUIRED_AGENT_ROLES))
    if set(required_roles) != set(REQUIRED_AGENT_ROLES):
        raise ValueError(f"test_contract.required_agent_roles must be {list(REQUIRED_AGENT_ROLES)}")
    required_context_stages = contract.get("required_context_pipeline_stages", list(REQUIRED_CONTEXT_STAGES))
    if list(required_context_stages) != list(REQUIRED_CONTEXT_STAGES):
        raise ValueError(f"test_contract.required_context_pipeline_stages must be {list(REQUIRED_CONTEXT_STAGES)}")

    context_contract = require_object(contract.get("context_pack_contract"), "test_contract.context_pack_contract")
    if context_contract.get("chat_output_is_evidence") is not False:
        raise ValueError("test_contract.context_pack_contract.chat_output_is_evidence must be false")
    if context_contract.get("semantic_gate") is not False:
        raise ValueError("test_contract.context_pack_contract.semantic_gate must be false")
    if context_contract.get("evidence_policy") != "on-disk-artifacts-only":
        raise ValueError("test_contract.context_pack_contract.evidence_policy must be on-disk-artifacts-only")
    if context_contract.get("checkpoint_backend") != "sqlite":
        raise ValueError("test_contract.context_pack_contract.checkpoint_backend must be sqlite")
    if context_contract.get("worker_state_source") != "agent-index.agents_by_worker_id":
        raise ValueError("test_contract.context_pack_contract.worker_state_source must be agent-index.agents_by_worker_id")

    agent_contract = require_object(contract.get("agent_index_contract"), "test_contract.agent_index_contract")
    if agent_contract.get("chat_output_is_evidence") is not False:
        raise ValueError("test_contract.agent_index_contract.chat_output_is_evidence must be false")
    if agent_contract.get("semantic_gate") is not False:
        raise ValueError("test_contract.agent_index_contract.semantic_gate must be false")
    if agent_contract.get("checkpoint_backend") != "sqlite":
        raise ValueError("test_contract.agent_index_contract.checkpoint_backend must be sqlite")
    if agent_contract.get("worker_isolation") != "per-worker out_root":
        raise ValueError("test_contract.agent_index_contract.worker_isolation must be per-worker out_root")

    return {
        "required_entrypoint_ids": entrypoint_ids,
        "required_harness_features": list(required_features),
        "required_expected_artifacts": list(required_artifacts),
        "required_context_pipeline_stages": list(required_context_stages),
        "required_agent_roles": list(required_roles),
        "repair_round_cap": repair_round_cap,
        "status": "passed",
    }


def validate_context_management_contract(
    payload: dict[str, Any],
    *,
    path_text: str,
    expected_artifacts: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    if payload.get("report_kind") != "context-pack":
        raise ValueError(f"context_pack report_kind must be context-pack: {path_text}")
    contract = require_object(payload.get("context_management_contract"), "context_management_contract")
    if contract.get("contract_kind") != "context-management":
        raise ValueError("context_management_contract.contract_kind must be context-management")
    if contract.get("schema_version") != 1:
        raise ValueError("context_management_contract.schema_version must be 1")
    if contract.get("chat_output_is_evidence") is not False:
        raise ValueError("context_management_contract.chat_output_is_evidence must be false")
    if contract.get("semantic_gate") is not False:
        raise ValueError("context_management_contract.semantic_gate must be false")
    if contract.get("evidence_policy") != "on-disk-artifacts-only":
        raise ValueError("context_management_contract.evidence_policy must be on-disk-artifacts-only")

    context_pack_path = require_string(contract.get("context_pack"), "context_management_contract.context_pack")
    agent_index_path = require_string(contract.get("agent_index"), "context_management_contract.agent_index")
    assert_repo_relative_posix(context_pack_path)
    assert_repo_relative_posix(agent_index_path)
    if expected_artifacts.get("context_pack") and context_pack_path != expected_artifacts["context_pack"]:
        raise ValueError("context_management_contract.context_pack must match expected_artifacts.context_pack")
    if expected_artifacts.get("agent_index") and agent_index_path != expected_artifacts["agent_index"]:
        raise ValueError("context_management_contract.agent_index must match expected_artifacts.agent_index")

    primary_report = contract.get("primary_report")
    if isinstance(primary_report, str):
        assert_repo_relative_posix(primary_report)
    resume_protocol = require_object(contract.get("resume_protocol"), "context_management_contract.resume_protocol")
    if resume_protocol.get("checkpoint_backend") != "sqlite":
        raise ValueError("context_management_contract.resume_protocol.checkpoint_backend must be sqlite")
    ledger_path = resume_protocol.get("ledger_path")
    if isinstance(ledger_path, str):
        assert_repo_relative_posix(ledger_path)
    if resume_protocol.get("worker_state_source") != "agent-index.agents_by_worker_id":
        raise ValueError("context_management_contract.resume_protocol.worker_state_source must be agent-index.agents_by_worker_id")

    pipeline = payload.get("context_management_contract", {}).get("pipeline")
    if not isinstance(pipeline, list) or not pipeline:
        raise ValueError("context_management_contract.pipeline must be a non-empty list")
    stages = {item.get("stage") for item in pipeline if isinstance(item, dict)}
    missing_stages = [stage for stage in REQUIRED_CONTEXT_STAGES if stage not in stages]
    if missing_stages:
        raise ValueError(f"context_management_contract.pipeline missing stages: {missing_stages}")
    repair_stage = next(item for item in pipeline if isinstance(item, dict) and item.get("stage") == "repair")
    if repair_stage.get("max_rounds") != 5:
        raise ValueError("context_management_contract repair max_rounds must be 5")
    worker_stage = next(item for item in pipeline if isinstance(item, dict) and item.get("stage") == "translate")
    if worker_stage.get("fanout") is not True:
        raise ValueError("context_management_contract translate stage must be fanout")

    return {
        "path": path_text,
        "status": "passed",
        "pipeline_stages": list(REQUIRED_CONTEXT_STAGES),
        "repair_round_cap": 5,
    }


def validate_agent_coordination_contract(
    payload: dict[str, Any],
    *,
    path_text: str,
) -> dict[str, Any]:
    if payload.get("report_kind") != "agent-index":
        raise ValueError(f"agent_index report_kind must be agent-index: {path_text}")
    contract = require_object(payload.get("agent_coordination_contract"), "agent_coordination_contract")
    if contract.get("contract_kind") != "agent-coordination":
        raise ValueError("agent_coordination_contract.contract_kind must be agent-coordination")
    if contract.get("schema_version") != 1:
        raise ValueError("agent_coordination_contract.schema_version must be 1")
    if contract.get("chat_output_is_evidence") is not False:
        raise ValueError("agent_coordination_contract.chat_output_is_evidence must be false")
    if contract.get("semantic_gate") is not False:
        raise ValueError("agent_coordination_contract.semantic_gate must be false")
    if contract.get("checkpoint_backend") != "sqlite":
        raise ValueError("agent_coordination_contract.checkpoint_backend must be sqlite")

    roles = require_object(contract.get("roles"), "agent_coordination_contract.roles")
    missing_roles = [role for role in REQUIRED_AGENT_ROLES if role not in roles]
    if missing_roles:
        raise ValueError(f"agent_coordination_contract.roles missing roles: {missing_roles}")
    repairer = require_object(roles.get("repairer"), "agent_coordination_contract.roles.repairer")
    if repairer.get("round_cap") != 5:
        raise ValueError("agent_coordination_contract.roles.repairer.round_cap must be 5")
    worker = require_object(roles.get("worker"), "agent_coordination_contract.roles.worker")
    if worker.get("isolation") != "per-worker out_root":
        raise ValueError("agent_coordination_contract.roles.worker.isolation must be per-worker out_root")

    agents_by_worker_id = require_object(payload.get("agents_by_worker_id"), "agents_by_worker_id")
    agents = payload.get("agents")
    if not isinstance(agents, list) or not agents:
        raise ValueError("agent_index.agents must be a non-empty list")
    if contract.get("worker_count") != len(agents_by_worker_id):
        raise ValueError("agent_coordination_contract.worker_count must match agents_by_worker_id")
    for worker_id, agent in sorted(agents_by_worker_id.items()):
        agent_payload = require_object(agent, f"agents_by_worker_id.{worker_id}")
        if agent_payload.get("worker_id") != worker_id:
            raise ValueError(f"agents_by_worker_id key must match worker_id: {worker_id}")
        for field in ("assignment_path", "request_path", "summary_path", "report_path", "isolated_out_root"):
            assert_repo_relative_posix(require_string(agent_payload.get(field), f"{worker_id}.{field}"))

    return {
        "path": path_text,
        "status": "passed",
        "roles": list(REQUIRED_AGENT_ROLES),
        "worker_count": len(agents_by_worker_id),
        "repair_round_cap": 5,
    }


def validate_judge_evidence_index_contract(payload: dict[str, Any], *, path_text: str) -> dict[str, Any]:
    if payload.get("report_kind") != "judge-evidence-index":
        raise ValueError(f"judge_evidence_index report_kind must be judge-evidence-index: {path_text}")
    boundary = require_object(payload.get("claim_boundary"), "judge_evidence_index.claim_boundary")
    if boundary.get("semantic_claim_source") != "accepted_evidence_binding":
        raise ValueError("judge_evidence_index.claim_boundary.semantic_claim_source must be accepted_evidence_binding")
    if boundary.get("generated_draft_semantic_pass") is not False:
        raise ValueError("judge_evidence_index.claim_boundary.generated_draft_semantic_pass must be false")
    if boundary.get("translation_coverage_numerator") != 0:
        raise ValueError("judge_evidence_index.claim_boundary.translation_coverage_numerator must be 0")
    if boundary.get("index_is_semantic_gate") is not False:
        raise ValueError("judge_evidence_index.claim_boundary.index_is_semantic_gate must be false")

    architecture = require_object(payload.get("harness_architecture"), "judge_evidence_index.harness_architecture")
    contracts = require_object(architecture.get("architecture_contracts"), "judge_evidence_index.architecture_contracts")
    context_contract = require_object(contracts.get("context_management"), "judge_evidence_index.context_management")
    agent_contract = require_object(contracts.get("agent_coordination"), "judge_evidence_index.agent_coordination")
    if context_contract.get("chat_output_is_evidence") is not False or context_contract.get("semantic_gate") is not False:
        raise ValueError("judge_evidence_index.context_management must keep chat_output_is_evidence=false and semantic_gate=false")
    if agent_contract.get("chat_output_is_evidence") is not False or agent_contract.get("semantic_gate") is not False:
        raise ValueError("judge_evidence_index.agent_coordination must keep chat_output_is_evidence=false and semantic_gate=false")
    roles = agent_contract.get("roles")
    if not isinstance(roles, list) or set(roles) != set(REQUIRED_AGENT_ROLES):
        raise ValueError("judge_evidence_index.agent_coordination.roles must list all required roles")

    return {"path": path_text, "status": "passed", "architecture_contracts": "passed"}


def worker_ids_from_entries(entries: Any, *, label: str) -> set[str]:
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"{label} must be a non-empty list")
    worker_ids: set[str] = set()
    for index, entry in enumerate(entries):
        entry_payload = require_object(entry, f"{label}[{index}]")
        worker_id = require_string(entry_payload.get("worker_id"), f"{label}[{index}].worker_id")
        worker_ids.add(worker_id)
    if len(worker_ids) != len(entries):
        raise ValueError(f"{label} worker_id values must be unique")
    return worker_ids


def entries_by_worker_id(entries: list[Any], *, label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(entries):
        entry_payload = require_object(entry, f"{label}[{index}]")
        worker_id = require_string(entry_payload.get("worker_id"), f"{label}[{index}].worker_id")
        result[worker_id] = entry_payload
    return result


def validate_context_agent_index_consistency(
    context_payload: dict[str, Any],
    agent_payload: dict[str, Any],
) -> dict[str, Any]:
    context_workers = context_payload.get("workers")
    agents = agent_payload.get("agents")
    agents_by_worker_id = require_object(agent_payload.get("agents_by_worker_id"), "agents_by_worker_id")
    context_worker_ids = worker_ids_from_entries(context_workers, label="context_pack.workers")
    agent_ids = worker_ids_from_entries(agents, label="agent_index.agents")
    indexed_ids = set(agents_by_worker_id)
    if context_worker_ids != agent_ids or context_worker_ids != indexed_ids:
        raise ValueError(
            "context_pack.workers, agent_index.agents, and agents_by_worker_id worker ids must match: "
            f"{sorted(context_worker_ids)} != {sorted(agent_ids)} != {sorted(indexed_ids)}"
        )

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
    )
    for worker_id in sorted(context_worker_ids):
        context_worker = context_by_worker_id[worker_id]
        agent_entry = require_object(agents_by_worker_id[worker_id], f"agents_by_worker_id.{worker_id}")
        listed_agent = agents_by_list_id[worker_id]
        for field in comparable_fields:
            values = [payload.get(field) for payload in (context_worker, listed_agent, agent_entry) if field in payload]
            if values and any(value != values[0] for value in values[1:]):
                raise ValueError(f"worker {worker_id} field {field} must match across context_pack and agent_index")

    return {"status": "passed", "worker_count": len(context_worker_ids)}


def validate_harness_artifact_contracts(
    artifacts: dict[str, Any],
    *,
    require_local_artifacts: bool,
    repo_root: Path,
) -> dict[str, Any]:
    if not require_local_artifacts:
        return {"status": "skipped", "reason": "require_local_artifacts=false"}
    result: dict[str, Any] = {"status": "passed"}
    context_payload: dict[str, Any] | None = None
    agent_payload: dict[str, Any] | None = None
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
    if "judge_evidence_index" in artifacts:
        judge_index_path = repo_path(str(artifacts["judge_evidence_index"]), repo_root=repo_root)
        result["judge_evidence_index"] = validate_judge_evidence_index_contract(
            load_json(judge_index_path),
            path_text=str(artifacts["judge_evidence_index"]),
        )
    return result


def validate_config(
    config_path: Path,
    *,
    require_local_artifacts: bool = False,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    config_path = config_path if config_path.is_absolute() else repo_root / config_path
    config = load_json(config_path)
    errors: list[str] = []
    entrypoint_results: list[dict[str, Any]] = []

    try:
        if config.get("schema_version") != 1:
            raise ValueError("schema_version must be 1")
        if config.get("manifest_kind") != "judge-entrypoints":
            raise ValueError("manifest_kind must be judge-entrypoints")
        if config.get("status") != "active":
            raise ValueError("status must be active")
        claim_boundary = validate_claim_boundary(config)
        validate_ref(config["environment_profile"], repo_root=repo_root)
        assert_no_local_absolute_path(str(config.get("source_pin", {}).get("checkout_command", "")))
    except (KeyError, ValueError) as error:
        errors.append(str(error))
        claim_boundary = {}

    entrypoints = config.get("entrypoints")
    if not isinstance(entrypoints, list) or not entrypoints:
        errors.append("entrypoints must be a non-empty list")
        entrypoints = []

    valid_entrypoints: list[dict[str, Any]] = []
    for entry in entrypoints:
        try:
            if not isinstance(entry, dict):
                raise ValueError("entrypoint must be an object")
            valid_entrypoints.append(entry)
            command = entry.get("command")
            if not isinstance(command, str) or "python -B" not in command:
                raise ValueError(f"entrypoint command must use python -B: {entry.get('id')}")
            assert_no_local_absolute_path(command)
            for command_text in entry.get("verification_commands", []):
                assert_no_local_absolute_path(str(command_text))
            audit_command = entry.get("audit_command")
            if isinstance(audit_command, str):
                assert_no_local_absolute_path(audit_command)
            expected_artifacts = entry.get("expected_artifacts", {})
            entrypoint_results.append(
                {
                    "id": entry.get("id"),
                    "status": "passed",
                    "purpose": entry.get("purpose"),
                    "profile": validate_ref(entry["profile"], repo_root=repo_root),
                    "tracked_manifest": validate_ref(entry["tracked_manifest"], repo_root=repo_root),
                    "expected_artifacts": validate_expected_artifacts(
                        expected_artifacts,
                        require_local_artifacts=require_local_artifacts,
                        repo_root=repo_root,
                    ),
                    "harness_contracts": validate_harness_artifact_contracts(
                        expected_artifacts,
                        require_local_artifacts=require_local_artifacts,
                        repo_root=repo_root,
                    ),
                }
            )
        except (KeyError, ValueError) as error:
            entrypoint_results.append({"id": entry.get("id") if isinstance(entry, dict) else None, "status": "failed"})
            errors.append(str(error))

    try:
        test_contract = validate_test_contract(config, entrypoints=valid_entrypoints, claim_boundary=claim_boundary)
    except ValueError as error:
        test_contract = {}
        errors.append(str(error))

    return {
        "status": "failed" if errors else "passed",
        "config": {"path": repo_relative(config_path, repo_root), "sha256": sha256_file(config_path)},
        "entrypoint_count": len(entrypoint_results),
        "entrypoints": entrypoint_results,
        "claim_boundary": claim_boundary,
        "test_contract": test_contract,
        "require_local_artifacts": require_local_artifacts,
        "errors": errors,
    }


if __name__ == "__main__":
    raise SystemExit(main())
