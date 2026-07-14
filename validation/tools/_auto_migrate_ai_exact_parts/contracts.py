from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CompileRunner = Callable[[Path], dict[str, Any]]
ReplayRunner = Callable[[Path, Path], dict[str, Any]]
Dependency = Callable[..., Any]


@dataclass(frozen=True)
class StageInputs:
    spec: Mapping[str, Any]
    slice_id: str
    context_pack: dict[str, Any]
    ai_manifest: dict[str, Any]
    evidence_dir: Path
    canonical_draft_path: Path
    deterministic_candidate_path: Path | None
    c2rust_baseline: Mapping[str, Any] | None
    c2rust_baseline_manifest_path: Path | None
    replay_test_path: Path
    oracle_payload: Mapping[str, Any]
    harness_path: Path
    proof_root: Path
    attempts_root: Path
    compile_runner: CompileRunner
    replay_runner: ReplayRunner
    max_repair_rounds: int
    opencode_command: str
    resolved_model: str
    agent: str
    variant: str
    timeout_seconds: int


@dataclass(frozen=True)
class StageDependencies:
    validate_ai_exact_stage_contract: Dependency
    resolve_current_c2rust_baseline_candidate: Dependency
    validate_with_new_attempt: Dependency
    classify_ai_repair_eligibility: Dependency
    passed_gate_count: Dependency
    repair_c2rust_candidate_after_validation: Dependency
    c2rust_repair_report_binding: Dependency
    repair_ai_candidate_after_validation: Dependency
    manifest_candidate_id: Dependency
    manifest_generator_metadata: Dependency
    router_candidate: Dependency
    route_candidates: Dependency
    sync_duplicate_audit: Dependency
    sha256_path: Dependency
    mark_ai_not_applied: Dependency
    persist_candidate_result: Dependency
    atomic_write_json: Dependency


@dataclass
class CandidateState:
    ai_manifest: dict[str, Any]
    baseline_path: Path | None
    baseline_audit: dict[str, Any]
    ai_result: dict[str, Any]
    ai_repair_eligibility: dict[str, Any]
    c2rust_repair_eligibility: dict[str, Any]
    deterministic_result: dict[str, Any] | None = None
    c2rust_baseline_result: dict[str, Any] | None = None
    c2rust_repair_result: dict[str, Any] | None = None
    c2rust_repair_audit: dict[str, Any] | None = None
    c2rust_repaired_candidate_path: Path | None = None
    canonical_changed: bool = False
