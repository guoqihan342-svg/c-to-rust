#!/usr/bin/env python3
"""Evaluate a finite cross-project suite with a noncompetition AI model."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Callable

from validation.tools._ai_auxiliary_suite_support import (
    artifact_ref,
    atomic_write_bytes,
    atomic_write_json,
    failed_unit,
    isolated_opencode_environment,
    load_object,
    repo_path,
    reserve_output_root,
    required_string,
    safe_identifier,
    sha256_path,
    validate_unit_identities,
)
from validation.tools._ai_candidate_harness_parts.model_identity import (
    resolve_model_identity,
)
from validation.tools._run_competition_provider_circuit import ProviderCircuit
from validation.tools._validate_ai_exact_evidence_parts import validate_evidence
from validation.tools._validate_ai_exact_evidence_parts.io import EvidenceError
from validation.tools.validate_ai_finite_cross_project_suite import validate_suite
from validation.tools import validate_competition_run_summary as summary_validator


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SUITE = Path("validation/ai-finite-cross-project-suite.json")
DEFAULT_OUT_ROOT = Path("target/ai-auxiliary-cross-project-suite")
DEFAULT_MODEL = "opencode/deepseek-v4-flash-free"
DEFAULT_AGENT = "c2rust-candidate"
DEFAULT_VARIANT = "max"
REPORT_NAME = "ai-auxiliary-cross-project-suite-report.json"
MAX_CAPTURE_BYTES = 2_000_000

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
UnitRunner = Callable[..., dict[str, Any]]


def run_command(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, **kwargs)


def run_unit(
    *,
    item: dict[str, Any],
    index: int,
    repo_root: Path,
    evidence_root: Path,
    logs_root: Path,
    report_path: Path,
    model: str,
    agent: str,
    variant: str,
    timeout_seconds: int,
    repair_rounds: int,
    opencode_command: str,
    command_runner: CommandRunner = run_command,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    evidence_root = repo_path(repo_root, evidence_root)
    logs_root = repo_path(repo_root, logs_root)
    report_path = repo_path(repo_root, report_path)
    spec_ref = item.get("slice_spec")
    if not isinstance(spec_ref, dict) or not isinstance(spec_ref.get("path"), str):
        return failed_unit(item, index, "slice_spec_ref_invalid")
    try:
        spec_path = repo_path(repo_root, Path(spec_ref["path"]))
        spec = load_object(spec_path, "slice spec")
        target_id = safe_identifier(required_string(spec, "target_id"), "spec.target_id")
        slice_id = safe_identifier(required_string(spec, "slice_id"), "spec.slice_id")
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        return failed_unit(item, index, f"slice_spec_invalid:{error}")
    if item.get("slice_id") != slice_id:
        return failed_unit(item, index, "suite_slice_identity_mismatch")
    expected_spec_sha = spec_ref.get("sha256")
    observed_spec_ref = artifact_ref(spec_path, root=repo_root)
    if observed_spec_ref["sha256"] != expected_spec_sha:
        return failed_unit(item, index, "slice_spec_sha256_mismatch_before_launch")

    command = [
        sys.executable,
        "-B",
        "-m",
        "validation.tools.auto_migrate",
        "--slice-spec",
        spec_path.relative_to(repo_root).as_posix(),
        "--out-root",
        evidence_root.relative_to(repo_root).as_posix(),
        "--competition-clang-lane",
        "--ai-first-candidate",
        "--ai-model",
        model,
        "--ai-agent",
        agent,
        "--ai-variant",
        variant,
        "--ai-timeout-seconds",
        str(timeout_seconds),
        "--ai-repair-rounds",
        str(repair_rounds),
        "--ai-opencode-command",
        opencode_command,
        "--ai-deterministic-fallback",
        "off",
    ]
    started = time.monotonic()
    with isolated_opencode_environment(f"{index:02d}-{target_id}-{slice_id}") as (environment, runtime):
        try:
            completed = command_runner(
                command,
                cwd=repo_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=max(300, timeout_seconds * (repair_rounds + 1) + 180),
                env=environment,
            )
            returncode = completed.returncode
            stdout = completed.stdout
            stderr = completed.stderr
        except (OSError, subprocess.TimeoutExpired) as error:
            return failed_unit(item, index, f"auto_migrate_launch_failed:{type(error).__name__}")
    duration_ms = round((time.monotonic() - started) * 1000)
    log_prefix = f"{index:02d}-{target_id}-{slice_id}"
    stdout_path = logs_root / f"{log_prefix}.stdout.log"
    stderr_path = logs_root / f"{log_prefix}.stderr.log"
    atomic_write_bytes(stdout_path, stdout.encode("utf-8")[:MAX_CAPTURE_BYTES])
    atomic_write_bytes(stderr_path, stderr.encode("utf-8")[:MAX_CAPTURE_BYTES])

    evidence_dir = evidence_root / target_id / "auto-translation" / slice_id
    prefix = f"l3-{slice_id}"
    candidate_manifest_path = evidence_dir / f"{prefix}-ai-candidate-manifest.json"
    unit = {
        "index": index,
        "item_id": item.get("id"),
        "project_id": item.get("project_id"),
        "construct_family": item.get("construct_family"),
        "target_id": target_id,
        "slice_id": slice_id,
        "status": "execution_failed",
        "returncode": returncode,
        "duration_ms": duration_ms,
        "provider_invocations": 0,
        "repair_rounds": 0,
        "auxiliary_exact_pass": False,
        "reason": None,
        "runtime_isolation": runtime,
        "artifacts": {
            "slice_spec": observed_spec_ref,
            "stdout": artifact_ref(stdout_path, root=repo_root),
            "stderr": artifact_ref(stderr_path, root=repo_root),
        },
        "_candidate_manifest_path": candidate_manifest_path,
    }
    if sha256_path(spec_path) != observed_spec_ref["sha256"]:
        unit["status"] = "contract_failed"
        unit["reason"] = "slice_spec_sha256_changed_during_execution"
        return unit
    if not candidate_manifest_path.is_file():
        unit["reason"] = "ai_candidate_manifest_missing"
        return unit
    try:
        manifest = load_object(candidate_manifest_path, "AI candidate manifest")
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        unit["status"] = "contract_failed"
        unit["reason"] = "ai_candidate_manifest_unreadable"
        return unit
    unit["artifacts"]["candidate_manifest"] = artifact_ref(
        candidate_manifest_path, root=repo_root
    )
    unit["provider_invocations"] = manifest.get("provider_invocations", 0)
    unit["repair_rounds"] = sum(
        1
        for candidate in manifest.get("candidates", [])
        if isinstance(candidate, dict) and candidate.get("purpose") == "repair_candidate"
    )
    fresh = summary_validator.validate_fresh_ai_manifest(
        manifest,
        manifest_path=candidate_manifest_path,
        policy={
            "model": model,
            "agent": agent,
            "variant": variant,
            "opencode_command": opencode_command,
        },
        summary_path=report_path,
        repo_root=repo_root,
    )
    unexpected = sorted(
        set(fresh["reasons"]) - {"ai_candidate_not_competition_eligible"}
    )
    if unexpected:
        unit["status"] = "contract_failed"
        unit["reason"] = "fresh_manifest_invalid:" + ",".join(unexpected)
        return unit
    if manifest.get("status") == "blocked":
        failure = manifest.get("failure")
        unit["status"] = "provider_blocked"
        unit["reason"] = (
            failure.get("kind") if isinstance(failure, dict) else "provider_blocked"
        )
        return unit
    if returncode != 0 or manifest.get("status") != "generated":
        unit["reason"] = f"auto_migrate_returncode:{returncode}"
        return unit
    try:
        exact = validate_evidence(
            target_id=target_id,
            slice_id=slice_id,
            evidence_root=evidence_root,
            require_semantic_pass=False,
        )
    except EvidenceError as error:
        unit["status"] = "contract_failed"
        unit["reason"] = f"exact_evidence_invalid:{error.code}"
        return unit
    auto_manifest_path = evidence_dir / f"{prefix}-auto-translation-manifest.json"
    router_path = evidence_dir / f"{prefix}-ai-router.json"
    for name, path in (("auto_manifest", auto_manifest_path), ("router", router_path)):
        if path.is_file():
            unit["artifacts"][name] = artifact_ref(path, root=repo_root)
    unit["selected_candidate_id"] = exact.get("selected_candidate_id")
    unit["auxiliary_exact_pass"] = exact.get("semantic_pass") is True
    unit["status"] = "exact_pass" if unit["auxiliary_exact_pass"] else "exact_failed"
    unit["reason"] = None if unit["auxiliary_exact_pass"] else "common_exact_gates_failed"
    return unit


def run_suite(
    *,
    suite: Path = DEFAULT_SUITE,
    out_root: Path = DEFAULT_OUT_ROOT,
    model: str = DEFAULT_MODEL,
    agent: str = DEFAULT_AGENT,
    variant: str = DEFAULT_VARIANT,
    timeout_seconds: int = 180,
    repair_rounds: int = 1,
    max_workers: int = 1,
    opencode_command: str = "opencode",
    repo_root: Path = REPO_ROOT,
    unit_runner: UnitRunner = run_unit,
) -> tuple[int, dict[str, Any], Path]:
    root = repo_root.resolve()
    suite_path = repo_path(root, suite)
    output_root = repo_path(root, out_root)
    report_path = output_root / "summary" / REPORT_NAME
    identity = resolve_model_identity(model)
    if identity.competition_eligible:
        raise ValueError("auxiliary suite requires a noncompetition resolved model")
    if isinstance(max_workers, bool) or not isinstance(max_workers, int) or not 1 <= max_workers <= 4:
        raise ValueError("max_workers must be between 1 and 4")
    suite_payload = load_object(suite_path, "AI finite cross-project suite")
    items = suite_payload.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 20:
        raise ValueError("suite.items must contain 1..20 entries")
    validate_unit_identities(items)
    reserve_output_root(output_root)
    preflight = validate_suite(suite_path, root)
    if preflight.get("contract_status") != "passed" or preflight.get("status") != "ready":
        report = base_report(
            suite_path,
            suite_payload,
            root,
            identity,
            model,
            agent,
            variant,
            max_workers,
            preflight,
            status="blocked",
            exit_code=2,
            units=[],
            circuit=ProviderCircuit().summary(),
        )
        atomic_write_json(report_path, report)
        return 2, report, report_path

    evidence_root = output_root / "evidence"
    logs_root = output_root / "logs"
    circuit = ProviderCircuit()
    units_by_index: dict[int, dict[str, Any]] = {}
    indexed_items = list(enumerate(items))
    for offset in range(0, len(indexed_items), max_workers):
        batch: list[tuple[int, dict[str, Any], str]] = []
        for index, item in indexed_items[offset : offset + max_workers]:
            if not isinstance(item, dict):
                units_by_index[index] = failed_unit({}, index, "suite_item_invalid")
                continue
            unit_id = f"{item.get('project_id')}/{item.get('slice_id')}"
            if not circuit.request(unit_id):
                skipped = failed_unit(item, index, "provider_circuit_open")
                skipped["status"] = "skipped"
                skipped["returncode"] = None
                units_by_index[index] = skipped
                continue
            batch.append((index, item, unit_id))
        if not batch:
            continue
        with ThreadPoolExecutor(max_workers=len(batch)) as executor:
            futures = {
                executor.submit(
                    unit_runner,
                    item=item,
                    index=index,
                    repo_root=root,
                    evidence_root=evidence_root,
                    logs_root=logs_root,
                    report_path=report_path,
                    model=model,
                    agent=agent,
                    variant=variant,
                    timeout_seconds=timeout_seconds,
                    repair_rounds=repair_rounds,
                    opencode_command=opencode_command,
                ): (index, item, unit_id)
                for index, item, unit_id in batch
            }
            for future in as_completed(futures):
                index, item, unit_id = futures[future]
                try:
                    unit = future.result()
                except Exception as error:
                    unit = failed_unit(
                        item,
                        index,
                        f"unit_runner_failed:{type(error).__name__}",
                    )
                manifest_path = unit.pop("_candidate_manifest_path", None)
                if isinstance(manifest_path, Path):
                    circuit.observe_manifest(unit_id, manifest_path)
                units_by_index[index] = unit
    units = [units_by_index[index] for index in sorted(units_by_index)]
    statuses = [unit["status"] for unit in units]
    if any(status in {"contract_failed", "execution_failed"} for status in statuses):
        status, exit_code = "failed", 1
    elif any(status in {"provider_blocked", "skipped"} for status in statuses):
        status, exit_code = "blocked", 2
    else:
        status, exit_code = "completed", 0
    report = base_report(
        suite_path,
        suite_payload,
        root,
        identity,
        model,
        agent,
        variant,
        max_workers,
        preflight,
        status=status,
        exit_code=exit_code,
        units=units,
        circuit=circuit.summary(),
    )
    atomic_write_json(report_path, report)
    return exit_code, report, report_path


def base_report(
    suite_path: Path,
    suite: dict[str, Any],
    root: Path,
    identity: Any,
    model: str,
    agent: str,
    variant: str,
    max_workers: int,
    preflight: dict[str, Any],
    *,
    status: str,
    exit_code: int,
    units: list[dict[str, Any]],
    circuit: dict[str, Any],
) -> dict[str, Any]:
    counts = {
        name: sum(unit.get("status") == name for unit in units)
        for name in (
            "exact_pass",
            "exact_failed",
            "provider_blocked",
            "contract_failed",
            "execution_failed",
            "skipped",
        )
    }
    return {
        "schema_version": 1,
        "status": status,
        "exit_code": exit_code,
        "suite": {
            "id": suite.get("suite_id"),
            "path": suite_path.relative_to(root).as_posix(),
            "sha256": sha256_path(suite_path),
        },
        "model": {
            "provider": identity.provider_label,
            "logical_model": identity.logical_model,
            "resolved_model": model,
            "agent": agent,
            "variant": variant,
            "competition_eligible": False,
            "evaluation_scope": "auxiliary-local-validation",
        },
        "preflight": {
            "contract_status": preflight.get("contract_status"),
            "status": preflight.get("status"),
            "summary": preflight.get("summary"),
        },
        "claim_boundary": {
            "semantic_gate": False,
            "competition_success_numerator": 0,
            "translation_coverage_numerator": 0,
            "closes_p0_a6": False,
            "closes_p0_a10": False,
            "closes_p0_h9": False,
            "auxiliary_exact_pass_is_quality_signal_only": True,
        },
        "execution": {
            "max_workers": max_workers,
            "batch_circuit_updates": True,
            "outer_retries": 0,
        },
        "summary": {
            "items_total": len(units),
            "attempted": sum(unit.get("status") != "skipped" for unit in units),
            "provider_invocations": sum(
                value
                for unit in units
                for value in [unit.get("provider_invocations")]
                if isinstance(value, int) and not isinstance(value, bool)
            ),
            "candidates_generated": sum(
                unit.get("status") in {"exact_pass", "exact_failed"} for unit in units
            ),
            "auxiliary_exact_pass": counts["exact_pass"],
            **counts,
        },
        "provider_circuit": circuit,
        "units": units,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--agent", default=DEFAULT_AGENT)
    parser.add_argument("--variant", default=DEFAULT_VARIANT)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--repair-rounds", type=int, choices=range(0, 6), default=1)
    parser.add_argument("--max-workers", type=int, choices=range(1, 5), default=1)
    parser.add_argument("--opencode-command", default="opencode")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        exit_code, report, _ = run_suite(
            suite=args.suite,
            out_root=args.out_root,
            model=args.model,
            agent=args.agent,
            variant=args.variant,
            timeout_seconds=args.timeout_seconds,
            repair_rounds=args.repair_rounds,
            max_workers=args.max_workers,
            opencode_command=args.opencode_command,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
