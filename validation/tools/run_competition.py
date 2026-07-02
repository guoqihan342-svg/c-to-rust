#!/usr/bin/env python3
"""Linux-first OpenCode competition runner.

This wrapper is intentionally thin: it orchestrates existing validators and
writes the shared competition-run-summary contract. Translation correctness
still comes from per-slice evidence and final validation gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPO_ROOT / "config" / "competition-env" / "environment.json"
SUMMARY_VALIDATOR = REPO_ROOT / "validation" / "tools" / "validate_competition_run_summary.py"
AUTO_MIGRATE = REPO_ROOT / "validation" / "tools" / "auto_migrate.py"
AUTO_EVIDENCE_VALIDATOR = REPO_ROOT / "validation" / "tools" / "validate_auto_translation_evidence.py"
EXTRACT_SOURCE_SLICE = REPO_ROOT / "validation" / "tools" / "extract_source_slice.py"
UNSAFE_BUDGET = REPO_ROOT / "validation" / "tools" / "unsafe_budget.py"


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
ExtractionSpecInput = Path | dict[str, Any]


class CompetitionRunResult:
    def __init__(self, *, exit_code: int, summary_path: Path, summary: dict[str, Any]) -> None:
        self.exit_code = exit_code
        self.summary_path = summary_path
        self.summary = summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slice-spec", action="append", dest="slice_specs", type=Path, default=[])
    parser.add_argument("--extract-spec", action="append", dest="extraction_specs", type=Path, default=[])
    parser.add_argument("--worker-summary", action="append", dest="worker_summaries", type=Path, default=[])
    parser.add_argument("--source-repo-root", "--repo-root", dest="source_repo_root")
    parser.add_argument("--source-file")
    parser.add_argument("--function")
    parser.add_argument("--target-id")
    parser.add_argument("--slice-id")
    parser.add_argument("--source-repository")
    parser.add_argument("--source-branch")
    parser.add_argument("--source-commit")
    parser.add_argument("--require-source-commit")
    parser.add_argument("--compiler-command-source")
    parser.add_argument("--include-path", action="append", dest="include_paths", default=[])
    parser.add_argument("--define", action="append", dest="defines", default=[])
    parser.add_argument("--out-root", type=Path, default=REPO_ROOT / "target" / "competition-out")
    parser.add_argument(
        "--reuse-accepted-evidence",
        action="store_true",
        help="validate committed accepted evidence for each slice instead of regenerating candidates",
    )
    parser.add_argument(
        "--accepted-evidence-root",
        type=Path,
        default=REPO_ROOT / "validation" / "evidence",
        help="evidence root used with --reuse-accepted-evidence",
    )
    parser.add_argument(
        "--proof-class",
        default="local-simulation",
        choices=["competition-exact", "ci-approximation", "wsl-local-simulation", "local-simulation"],
    )
    parser.add_argument("--run-id")
    args = parser.parse_args()
    extraction_specs: list[ExtractionSpecInput] = list(args.extraction_specs)
    direct_extraction_spec = direct_extraction_spec_from_args(args, parser)
    if direct_extraction_spec is not None:
        extraction_specs.append(direct_extraction_spec)
    if not args.slice_specs and not extraction_specs and not args.worker_summaries:
        parser.error(
            "at least one --slice-spec, --extract-spec, --worker-summary, "
            "or direct extraction argument group is required"
        )

    result = run_competition(
        slice_specs=args.slice_specs,
        extraction_specs=extraction_specs,
        worker_summaries=args.worker_summaries,
        out_root=args.out_root,
        proof_class=args.proof_class,
        run_id=args.run_id,
        repo_root=REPO_ROOT,
        reuse_accepted_evidence=args.reuse_accepted_evidence,
        accepted_evidence_root=args.accepted_evidence_root,
    )
    print(json.dumps(result.summary, indent=2, sort_keys=True))
    return result.exit_code


def run_competition(
    *,
    slice_specs: list[Path],
    extraction_specs: list[ExtractionSpecInput] | None = None,
    worker_summaries: list[Path] | None = None,
    out_root: Path,
    proof_class: str,
    command_runner: CommandRunner = subprocess.run,
    repo_root: Path = REPO_ROOT,
    run_id: str | None = None,
    reuse_accepted_evidence: bool = False,
    accepted_evidence_root: Path | None = None,
) -> CompetitionRunResult:
    extraction_specs = extraction_specs or []
    worker_summaries = worker_summaries or []
    if not slice_specs and not extraction_specs and not worker_summaries:
        raise SystemExit(
            "at least one --slice-spec, --extract-spec, --worker-summary, "
            "or direct extraction argument group is required"
        )

    repo_root = repo_root.resolve()
    out_root = out_root if out_root.is_absolute() else repo_root / out_root
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "summary").mkdir(parents=True, exist_ok=True)
    logs_dir = out_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    evidence_root = out_root / "evidence"
    evidence_root.mkdir(parents=True, exist_ok=True)
    accepted_evidence_root = accepted_evidence_root or repo_root / "validation" / "evidence"
    if not accepted_evidence_root.is_absolute():
        accepted_evidence_root = repo_root / accepted_evidence_root
    generated_slice_specs_root = out_root / "slice-specs"
    generated_slice_specs_root.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    run_id = run_id or time.strftime("run-%Y%m%dT%H%M%SZ", time.gmtime())
    slice_failures = 0
    gate_failures = 0
    typed_ir_generated = 0
    compiled = 0
    semantic_pass = 0
    refused = 0
    blocked = 0
    worker_statuses = load_worker_summary_statuses(
        worker_summaries,
        proof_class=proof_class,
        repo_root=repo_root,
        out_root=out_root,
    )
    unit_statuses = []
    for worker in worker_statuses:
        unit_statuses.extend(workflow_unit_statuses_from_worker(worker))
    worker_workflow_metrics = [
        worker["workflow_metrics"] for worker in worker_statuses if isinstance(worker.get("workflow_metrics"), dict)
    ]
    for worker in worker_statuses:
        worker_slices = worker["slices"]
        typed_ir_generated += worker_slices["typed_ir_generated"]
        compiled += worker_slices["compiled"]
        semantic_pass += worker_slices["semantic_pass"]
        refused += worker_slices["refused"]
        blocked += worker_slices["blocked"]
        slice_failures += worker_slices["failed"]
        if worker["status"] != "passed":
            gate_failures += 1

    environment_result = run_logged_step(
        "environment-check",
        ["bash", "-lc", "source config/competition-env/env.sh; bash config/competition-env/toolchain-check.sh"],
        command_runner=command_runner,
        repo_root=repo_root,
        logs_dir=logs_dir,
        out_root=out_root,
    )
    if environment_result.returncode != 0 and proof_class == "competition-exact":
        gate_failures += 1

    generated_slice_specs, extraction_failures, extraction_unit_statuses = extract_slice_specs(
        extraction_specs,
        generated_slice_specs_root=generated_slice_specs_root,
        command_runner=command_runner,
        repo_root=repo_root,
        logs_dir=logs_dir,
        out_root=out_root,
    )
    unit_statuses.extend(extraction_unit_statuses)
    slice_failures += extraction_failures

    all_slice_specs = list(slice_specs) + generated_slice_specs
    generated_slice_spec_paths = {path.resolve() for path in generated_slice_specs}
    specs = [load_slice_spec(path, repo_root=repo_root) for path in all_slice_specs]
    for spec_path, spec in specs:
        target_id = required_str(spec, "target_id")
        slice_id = required_str(spec, "slice_id")
        unit_source = "extract-spec" if spec_path.resolve() in generated_slice_spec_paths else "slice-spec"
        slice_evidence_root = accepted_evidence_root if reuse_accepted_evidence else evidence_root
        if not reuse_accepted_evidence:
            auto_result = run_logged_step(
                f"auto-migrate-{slice_id}",
                [
                    sys.executable,
                    rel_script(AUTO_MIGRATE, repo_root),
                    "--slice-spec",
                    rel_path(spec_path, repo_root),
                    "--out-root",
                    rel_path(evidence_root, repo_root),
                    "--competition-clang-lane",
                ],
                command_runner=command_runner,
                repo_root=repo_root,
                logs_dir=logs_dir,
                out_root=out_root,
            )
            if auto_result.returncode != 0:
                slice_failures += 1
                unit_statuses.append(
                    workflow_unit_status(
                        target_id=target_id,
                        slice_id=slice_id,
                        source=unit_source,
                        status="failed",
                        compiled=False,
                        semantic_pass=False,
                        refused=False,
                        blocked=False,
                        failed=True,
                    )
                )
                continue

        final = load_final_verification(slice_evidence_root, target_id, slice_id)
        compiled_unit = final.get("rust_check_status") == "passed"
        semantic_unit = final.get("semantic_pass") is True
        final_status = str(final.get("status", "failed"))
        if compiled_unit:
            compiled += 1
        if semantic_unit:
            semantic_pass += 1
        else:
            if final_status == "refused":
                refused += 1
            elif final_status == "blocked":
                blocked += 1
            else:
                slice_failures += 1
        typed_ir_generated += 1
        repair_metrics = self_healing_repair_metrics(
            slice_evidence_root,
            target_id,
            slice_id,
            semantic_unit,
            repo_root=repo_root,
            out_root=out_root,
        )
        translation_before_after = load_translation_before_after(slice_evidence_root, target_id, slice_id)
        unit_statuses.append(
            workflow_unit_status(
                target_id=target_id,
                slice_id=slice_id,
                source=unit_source,
                status=workflow_status_from_final(final_status=final_status, semantic_pass=semantic_unit),
                compiled=compiled_unit,
                semantic_pass=semantic_unit,
                refused=final_status == "refused",
                blocked=final_status == "blocked",
                failed=not semantic_unit and final_status not in {"refused", "blocked"},
                repair_rounds=repair_metrics["repair_rounds"],
                auto_recovered=repair_metrics["auto_recovered"],
                repair_history=repair_metrics.get("repair_history"),
                llm_calls=repair_metrics["llm_calls"],
                translation_before_after=translation_before_after,
            )
        )

        validation_result = run_logged_step(
            f"validate-evidence-{slice_id}",
            [
                sys.executable,
                rel_script(AUTO_EVIDENCE_VALIDATOR, repo_root),
                "--target-id",
                target_id,
                "--slice-id",
                slice_id,
                "--slice-spec",
                rel_path(spec_path, repo_root),
                "--evidence-root",
                rel_path(slice_evidence_root, repo_root),
                "--require-semantic-pass",
            ],
            command_runner=command_runner,
            repo_root=repo_root,
            logs_dir=logs_dir,
            out_root=out_root,
        )
        if validation_result.returncode != 0:
            gate_failures += 1

    unsafe_result = run_logged_step(
        "unsafe-budget",
        [sys.executable, rel_script(UNSAFE_BUDGET, repo_root), "--max-ratio", "0.10"],
        command_runner=command_runner,
        repo_root=repo_root,
        logs_dir=logs_dir,
        out_root=out_root,
    )
    openspec_result = run_logged_step(
        "openspec-validate",
        ["bash", "-lc", "openspec validate --all --strict"],
        command_runner=command_runner,
        repo_root=repo_root,
        logs_dir=logs_dir,
        out_root=out_root,
    )

    unsafe_summary = unsafe_budget_summary(unsafe_result)
    if unsafe_summary["status"] != "passed" or openspec_result.returncode != 0:
        gate_failures += 1

    status = "passed" if slice_failures == 0 and gate_failures == 0 and semantic_pass > 0 else "failed"
    summary = {
        "schema_version": 1,
        "run_id": run_id,
        "proof_class": proof_class,
        "profile_id": profile_id(repo_root),
        "profile_sha256": sha256(PROFILE_PATH if repo_root == REPO_ROOT else repo_root / "config/competition-env/environment.json"),
        "clang_source": clang_source(repo_root),
        "cargo_mirror_activation": {
            "method": "CARGO_HOME",
            "path": "config/competition-env/cargo",
            "config_file": "config/competition-env/cargo/config.toml",
        },
        "elapsed_seconds": int(time.monotonic() - started),
        "translator_version": "0.1.0",
        "slices": {
            "attempted": len(slice_specs)
            + len(extraction_specs)
            + sum(worker["slices"]["attempted"] for worker in worker_statuses),
            "typed_ir_generated": typed_ir_generated,
            "compiled": compiled,
            "semantic_pass": semantic_pass,
            "refused": refused,
            "blocked": blocked,
            "failed": slice_failures,
        },
        "unsafe_budget": unsafe_summary,
        "artifact_roots": [
            "target/competition-out/evidence",
            "target/competition-out/summary",
            "target/competition-out/logs",
        ],
        "final_gate": {
            "status": status,
            "validator": "validate_auto_translation_evidence.py --require-semantic-pass",
        },
    }
    if worker_statuses:
        summary["workers"] = {
            "count": len(worker_statuses),
            "summaries": [public_worker_summary_status(worker) for worker in worker_statuses],
        }
    summary_path = write_summary_with_workflow_metrics(
        summary,
        unit_statuses=unit_statuses,
        worker_workflow_metrics=worker_workflow_metrics,
        out_root=out_root,
        repo_root=repo_root,
    )

    summary_validation = run_logged_step(
        "validate-competition-summary",
        [sys.executable, rel_script(SUMMARY_VALIDATOR, repo_root), "--summary", rel_path(summary_path, repo_root)],
        command_runner=command_runner,
        repo_root=repo_root,
        logs_dir=logs_dir,
        out_root=out_root,
    )
    if summary_validation.returncode != 0:
        gate_failures += 1
        summary["final_gate"]["status"] = "failed"
        summary_path = write_summary_with_workflow_metrics(
            summary,
            unit_statuses=unit_statuses,
            worker_workflow_metrics=worker_workflow_metrics,
            out_root=out_root,
            repo_root=repo_root,
        )

    return CompetitionRunResult(
        exit_code=0 if summary["final_gate"]["status"] == "passed" and slice_failures == 0 and gate_failures == 0 else 1,
        summary_path=summary_path,
        summary=summary,
    )


def run_step(command: list[str], *, command_runner: CommandRunner, repo_root: Path) -> subprocess.CompletedProcess[str]:
    return command_runner(
        command,
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )


def load_worker_summary_statuses(
    worker_summaries: list[Path],
    *,
    proof_class: str,
    repo_root: Path,
    out_root: Path,
) -> list[dict[str, Any]]:
    statuses = []
    seen: set[str] = set()
    for path in worker_summaries:
        resolved = resolve_worker_summary_path(path, repo_root=repo_root, out_root=out_root)
        seen_key = os.path.normcase(str(resolved.resolve()))
        if seen_key in seen:
            raise SystemExit(f"duplicate worker summary path: {summary_reference_path(resolved, repo_root=repo_root, out_root=out_root)}")
        seen.add(seen_key)
        summary = json.loads(resolved.read_text(encoding="utf-8"))
        worker_proof_class = str(summary.get("proof_class", "unknown"))
        if worker_proof_class != proof_class:
            raise SystemExit(
                f"worker summary proof_class {worker_proof_class} does not match parent proof_class {proof_class}: "
                f"{summary_reference_path(resolved, repo_root=repo_root, out_root=out_root)}"
            )
        workflow_metrics = load_bound_workflow_metrics(
            summary,
            summary_path=resolved,
            repo_root=repo_root,
            out_root=out_root,
        )
        slices = summary.get("slices", {})
        final_gate = summary.get("final_gate", {})
        status = final_gate.get("status") if isinstance(final_gate, dict) else "failed"
        if status not in {"passed", "failed", "blocked"}:
            status = "failed"
        worker_slices = {
            key: nonnegative_int(slices.get(key))
            for key in [
                "attempted",
                "typed_ir_generated",
                "compiled",
                "semantic_pass",
                "refused",
                "blocked",
                "failed",
            ]
        }
        worker_id = resolved.relative_to((out_root / "workers").resolve()).parts[0]
        assignment_metadata = load_worker_assignment_request_metadata(
            worker_id=worker_id,
            out_root=out_root,
            repo_root=repo_root,
        )
        status_entry = {
            "path": summary_reference_path(resolved, repo_root=repo_root, out_root=out_root),
            "worker_id": worker_id,
            "status": status,
            "proof_class": worker_proof_class,
            "attempted": worker_slices["attempted"],
            "semantic_pass": worker_slices["semantic_pass"],
            "failed": worker_slices["failed"],
            "slices": worker_slices,
            "workflow_metrics": workflow_metrics,
        }
        status_entry.update(assignment_metadata)
        statuses.append(
            status_entry
        )
    return statuses


def load_worker_assignment_request_metadata(
    *,
    worker_id: str,
    out_root: Path,
    repo_root: Path,
) -> dict[str, Any]:
    request_path = out_root / "harness" / "assignments" / f"{worker_id}-request.json"
    if not request_path.exists():
        return {}
    request = json.loads(request_path.read_text(encoding="utf-8"))
    metadata: dict[str, Any] = {
        "assignment_request": summary_reference_path(request_path, repo_root=repo_root, out_root=out_root),
    }
    for field in [
        "target_id",
        "slice_id",
        "function",
        "source_repo_root",
        "source_repository",
        "source_branch",
        "source_file",
        "source_commit",
        "source_sha256",
        "require_source_commit",
    ]:
        value = request.get(field)
        if isinstance(value, str) and value:
            metadata[field] = value
    slice_specs = request.get("slice_specs")
    if isinstance(slice_specs, list) and all(isinstance(item, str) and item for item in slice_specs):
        metadata["slice_specs"] = slice_specs
    return metadata


def resolve_worker_summary_path(path: Path, *, repo_root: Path, out_root: Path) -> Path:
    candidates = [path] if path.is_absolute() else [repo_root / path, out_root / path]
    resolved = next((candidate.resolve() for candidate in candidates if candidate.exists()), candidates[0].resolve())
    worker_root = (out_root / "workers").resolve()
    try:
        relative_to_workers = resolved.relative_to(worker_root)
    except ValueError as error:
        raise SystemExit(
            f"worker summary path must resolve under out_root/workers: "
            f"{summary_reference_path(resolved, repo_root=repo_root, out_root=out_root)}"
        ) from error
    if (
        len(relative_to_workers.parts) != 3
        or relative_to_workers.parts[1] != "summary"
        or relative_to_workers.parts[2] != "competition-run-summary.json"
    ):
        raise SystemExit(
            "worker summary path must match workers/<worker-id>/summary/competition-run-summary.json: "
            f"{summary_reference_path(resolved, repo_root=repo_root, out_root=out_root)}"
        )
    if not resolved.exists():
        raise SystemExit(f"worker summary path does not exist: {summary_reference_path(resolved, repo_root=repo_root, out_root=out_root)}")
    return resolved


def load_bound_workflow_metrics(
    summary: dict[str, Any],
    *,
    summary_path: Path,
    repo_root: Path,
    out_root: Path,
) -> dict[str, Any] | None:
    binding = summary.get("workflow_metrics")
    if not isinstance(binding, dict):
        return None
    metrics_ref = binding.get("path")
    expected_sha = binding.get("sha256")
    if not isinstance(metrics_ref, str) or not isinstance(expected_sha, str):
        raise SystemExit("worker summary workflow_metrics.path and workflow_metrics.sha256 are required when bound")
    metrics_path = resolve_bound_artifact(metrics_ref, summary_path=summary_path, repo_root=repo_root, out_root=out_root)
    if metrics_path is None:
        raise SystemExit(f"worker summary workflow_metrics.path does not exist: {metrics_ref}")
    if sha256(metrics_path) != expected_sha:
        raise SystemExit("worker summary workflow_metrics.sha256 does not match artifact")
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    if not isinstance(metrics, dict):
        raise SystemExit(f"worker summary workflow_metrics artifact must be an object: {metrics_ref}")
    return metrics


def public_worker_summary_status(worker: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in worker.items() if key != "workflow_metrics"}


def resolve_bound_artifact(
    value: str,
    *,
    summary_path: Path,
    repo_root: Path,
    out_root: Path,
) -> Path | None:
    if not is_safe_posix_relative(value):
        return None
    candidates = [
        repo_root / value,
        out_root / value,
        summary_path.parent / value,
        summary_path.parent.parent / value,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def is_safe_posix_relative(value: str) -> bool:
    if not value or "\\" in value or value.startswith("/") or value.startswith("~"):
        return False
    if len(value) >= 2 and value[1] == ":":
        return False
    return ".." not in Path(value).parts


def workflow_unit_statuses_from_worker(worker: dict[str, Any]) -> list[dict[str, Any]]:
    slices = worker["slices"]
    attempted = int(slices["attempted"])
    metrics = worker.get("workflow_metrics")
    per_unit_statuses = metrics.get("per_unit_statuses") if isinstance(metrics, dict) else None
    if isinstance(per_unit_statuses, list) and len(per_unit_statuses) == attempted:
        return [worker_unit_status_copy(unit, worker) for unit in per_unit_statuses]
    if attempted == 0:
        return []
    if attempted == 1:
        return [worker_unit_status_copy(workflow_unit_status_from_worker(worker), worker)]
    return synthetic_worker_unit_statuses(worker)


def worker_unit_status_copy(unit: Any, worker: dict[str, Any]) -> Any:
    if not isinstance(unit, dict):
        return unit
    copied = dict(unit)
    copied.setdefault("worker_summary_path", worker["path"])
    repair_history = copied.get("repair_history")
    if isinstance(repair_history, dict):
        normalized_repair_history = dict(repair_history)
        patch_events_path = normalized_repair_history.get("patch_events_path")
        if isinstance(patch_events_path, str) and is_safe_posix_relative(patch_events_path):
            patch_parts = Path(patch_events_path).parts
            if patch_parts and patch_parts[0] not in {"workers", "evidence", "target", "validation"}:
                worker_summary_parent = Path(str(worker["path"])).parent
                normalized_repair_history["patch_events_path"] = (
                    worker_summary_parent / Path(patch_events_path)
                ).as_posix()
        copied["repair_history"] = normalized_repair_history
    return copied


def synthetic_worker_unit_statuses(worker: dict[str, Any]) -> list[dict[str, Any]]:
    slices = worker["slices"]
    attempted = int(slices["attempted"])
    categories: list[tuple[str, int, dict[str, Any]]] = [
        (
            "converged",
            int(slices["semantic_pass"]),
            {
                "status": "converged",
                "compiled": True,
                "semantic_pass": True,
                "refused": False,
                "blocked": False,
                "failed": False,
            },
        ),
        (
            "baseline-only",
            max(0, int(slices["compiled"]) - int(slices["semantic_pass"])),
            {
                "status": "baseline-only",
                "compiled": True,
                "semantic_pass": False,
                "refused": False,
                "blocked": False,
                "failed": False,
            },
        ),
        (
            "refused",
            int(slices["refused"]),
            {
                "status": "refused",
                "compiled": False,
                "semantic_pass": False,
                "refused": True,
                "blocked": False,
                "failed": False,
            },
        ),
        (
            "blocked",
            int(slices["blocked"]),
            {
                "status": "blocked",
                "compiled": False,
                "semantic_pass": False,
                "refused": False,
                "blocked": True,
                "failed": False,
            },
        ),
        (
            "failed",
            int(slices["failed"]),
            {
                "status": "failed",
                "compiled": False,
                "semantic_pass": False,
                "refused": False,
                "blocked": False,
                "failed": True,
            },
        ),
    ]
    statuses: list[dict[str, Any]] = []
    for category, count, payload in categories:
        for _ in range(max(0, count)):
            statuses.append(
                {
                    "unit_id": f"{worker['path']}#{len(statuses) + 1}",
                    "source": "worker-summary",
                    "worker_summary_path": worker["path"],
                    "synthetic": True,
                    "synthetic_reason": "worker metrics did not provide matching per_unit_statuses",
                    "synthetic_category": category,
                    **payload,
                }
            )
    while len(statuses) < attempted:
        statuses.append(
            {
                "unit_id": f"{worker['path']}#{len(statuses) + 1}",
                "source": "worker-summary",
                "worker_summary_path": worker["path"],
                "synthetic": True,
                "synthetic_reason": "worker summary counts did not classify every attempted unit",
                "synthetic_category": "unclassified",
                "status": "unclassified",
                "compiled": False,
                "semantic_pass": False,
                "refused": False,
                "blocked": False,
                "failed": worker["status"] != "passed",
            }
        )
    return statuses[:attempted]


def workflow_unit_status_from_worker(worker: dict[str, Any]) -> dict[str, Any]:
    slices = worker["slices"]
    attempted = int(slices["attempted"])
    status = {
        "unit_id": worker["path"],
        "source": "worker-summary",
        "status": "converged" if worker["status"] == "passed" else worker["status"],
        "compiled": attempted > 0 and int(slices["compiled"]) == attempted,
        "semantic_pass": attempted > 0 and int(slices["semantic_pass"]) == attempted,
        "refused": int(slices["refused"]) > 0,
        "blocked": int(slices["blocked"]) > 0,
        "failed": worker["status"] != "passed" or int(slices["failed"]) > 0,
    }
    metrics = worker.get("workflow_metrics")
    per_unit_statuses = metrics.get("per_unit_statuses") if isinstance(metrics, dict) else None
    if attempted == 1 and isinstance(per_unit_statuses, list) and len(per_unit_statuses) == 1:
        worker_unit = per_unit_statuses[0]
        if isinstance(worker_unit, dict):
            for key in [
                "repair_rounds",
                "auto_recovered",
                "repair_history",
                "llm_calls",
                "root_cause_key",
                "opencode_contract_verification",
                "handoff_contract",
                "opencode_session_evidence",
            ]:
                if key in worker_unit:
                    status[key] = worker_unit[key]
    return status


def workflow_unit_status(
    *,
    target_id: str,
    slice_id: str,
    source: str,
    status: str,
    compiled: bool,
    semantic_pass: bool,
    refused: bool,
    blocked: bool,
    failed: bool,
    repair_rounds: int = 0,
    auto_recovered: bool = False,
    repair_history: dict[str, Any] | None = None,
    llm_calls: int = 0,
    translation_before_after: dict[str, Any] | None = None,
) -> dict[str, Any]:
    status_payload = {
        "unit_id": f"{target_id}/{slice_id}",
        "source": source,
        "status": status,
        "compiled": compiled,
        "semantic_pass": semantic_pass,
        "refused": refused,
        "blocked": blocked,
        "failed": failed,
    }
    if repair_rounds > 0:
        status_payload["repair_rounds"] = repair_rounds
        status_payload["auto_recovered"] = auto_recovered
        if repair_history is not None:
            status_payload["repair_history"] = repair_history
    if llm_calls > 0:
        status_payload["llm_calls"] = llm_calls
    if translation_before_after is not None:
        status_payload["translation_before_after"] = translation_before_after
    return status_payload


def workflow_status_from_final(*, final_status: str, semantic_pass: bool) -> str:
    if semantic_pass:
        return "converged"
    if final_status in {"refused", "blocked"}:
        return final_status
    return "failed"


def write_summary_with_workflow_metrics(
    summary: dict[str, Any],
    *,
    unit_statuses: list[dict[str, Any]],
    worker_workflow_metrics: list[dict[str, Any]],
    out_root: Path,
    repo_root: Path,
) -> Path:
    summary_dir = out_root / "summary"
    workflow_metrics_path = summary_dir / "workflow-metrics.json"
    metrics = build_workflow_metrics(
        summary,
        unit_statuses=unit_statuses,
        worker_workflow_metrics=worker_workflow_metrics,
    )
    workflow_metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary["workflow_metrics"] = {
        "path": summary_reference_path(workflow_metrics_path, repo_root=repo_root, out_root=out_root),
        "sha256": sha256(workflow_metrics_path),
    }
    summary_path = summary_dir / "competition-run-summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path


def build_workflow_metrics(
    summary: dict[str, Any],
    *,
    unit_statuses: list[dict[str, Any]],
    worker_workflow_metrics: list[dict[str, Any]],
) -> dict[str, Any]:
    slices = summary["slices"]
    attempted = int(slices["attempted"])
    compiled = int(slices["compiled"])
    semantic_pass = int(slices["semantic_pass"])
    refused = int(slices["refused"])
    blocked = int(slices["blocked"])
    failed = int(slices["failed"])
    unsafe_budget = summary["unsafe_budget"]
    direct_unit_statuses = [
        unit for unit in unit_statuses if isinstance(unit, dict) and "worker_summary_path" not in unit
    ]
    repair_rounds = weighted_metric_with_direct_units(
        worker_workflow_metrics,
        "avg_repair_rounds",
        direct_unit_statuses,
        "repair_rounds",
        attempted,
    )
    auto_recovery_rate = weighted_metric_with_direct_units(
        worker_workflow_metrics,
        "auto_recovery_rate",
        direct_unit_statuses,
        "auto_recovered",
        attempted,
    )
    return {
        "schema_version": 1,
        "run_id": summary["run_id"],
        "proof_class": summary["proof_class"],
        "units_total": attempted,
        "units_converged": semantic_pass,
        "units_baseline_only": max(0, compiled - semantic_pass),
        "unsafe_reduction": aggregate_unsafe_reduction(
            worker_workflow_metrics,
            unsafe_budget,
            attempted=attempted,
            direct_unit_statuses=direct_unit_statuses,
        ),
        "translation_before_after": summarize_translation_before_after(unit_statuses),
        "avg_repair_rounds": repair_rounds,
        "auto_recovery_rate": auto_recovery_rate,
        "human_interventions": sum_worker_int_metric(worker_workflow_metrics, "human_interventions"),
        "always_compiles": attempted > 0 and compiled == attempted and failed == 0,
        "always_equivalent": attempted > 0 and semantic_pass == attempted and failed == 0,
        "fail_closed_count": refused + blocked,
        "root_cause_counts": root_cause_counts(unit_statuses),
        "wall_clock_seconds": summary["elapsed_seconds"],
        "llm_calls": sum_worker_int_metric(worker_workflow_metrics, "llm_calls")
        + sum_unit_int_metric(direct_unit_statuses, "llm_calls"),
        "per_unit_statuses": unit_statuses,
    }


def summarize_translation_before_after(unit_statuses: list[dict[str, Any]]) -> dict[str, Any]:
    bound_units = []
    measured_unsafe_unit_count = 0
    accepted_patch_unit_count = 0
    for unit in unit_statuses:
        if not isinstance(unit, dict):
            continue
        evidence = unit.get("translation_before_after")
        if not isinstance(evidence, dict):
            continue
        unsafe_reduction = evidence.get("unsafe_reduction")
        if isinstance(unsafe_reduction, dict) and unsafe_reduction.get("status") == "measured":
            baseline = nonnegative_count(unsafe_reduction.get("baseline_total_unsafe"))
            current = nonnegative_count(unsafe_reduction.get("current_total_unsafe"))
            reduced_by = nonnegative_count(unsafe_reduction.get("reduced_by"))
            if baseline is not None and current is not None and reduced_by is not None and baseline > current:
                measured_unsafe_unit_count += 1
        if isinstance(evidence.get("accepted_patch"), dict) or isinstance(evidence.get("patch_log"), dict):
            accepted_patch_unit_count += 1
        bound_unit = {
            "unit_id": unit.get("unit_id", "unknown"),
            "status": evidence.get("status", "bound"),
            "unsafe_reduction": unsafe_reduction if isinstance(unsafe_reduction, dict) else {},
        }
        baseline_verification = evidence.get("baseline_verification")
        if isinstance(baseline_verification, dict):
            bound_unit["baseline_verification"] = baseline_verification
        bound_units.append(bound_unit)
    return {
        "status": "bound" if bound_units else "not_provided",
        "unit_count": len(bound_units),
        "measured_unsafe_unit_count": measured_unsafe_unit_count,
        "accepted_patch_unit_count": accepted_patch_unit_count,
        "units": bound_units,
    }


def aggregate_unsafe_reduction(
    metrics: list[dict[str, Any]],
    unsafe_budget: dict[str, Any],
    *,
    attempted: int,
    direct_unit_statuses: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    fallback = {
        "status": "not_measured",
        "baseline_total_unsafe": None,
        "current_total_unsafe": unsafe_budget["total_first_party_non_test_unsafe"],
        "reduced_by": None,
        "ratio": unsafe_budget["ratio"],
    }
    if attempted <= 0:
        return fallback

    baseline_total = 0
    current_total = 0
    measured_units = 0
    for metric in metrics:
        unsafe_reduction = metric.get("unsafe_reduction")
        if not isinstance(unsafe_reduction, dict) or unsafe_reduction.get("status") != "measured":
            return fallback
        baseline = nonnegative_count(unsafe_reduction.get("baseline_total_unsafe"))
        current = nonnegative_count(unsafe_reduction.get("current_total_unsafe"))
        reduced_by = nonnegative_count(unsafe_reduction.get("reduced_by"))
        if baseline is None or current is None or reduced_by is None or baseline - current != reduced_by:
            return fallback
        baseline_total += baseline
        current_total += current
        measured_units += nonnegative_int(metric.get("units_total"))

    for unit in direct_unit_statuses or []:
        unsafe_reduction = measured_unit_translation_unsafe_reduction(unit)
        if unsafe_reduction is None:
            continue
        baseline_total += unsafe_reduction["baseline"]
        current_total += unsafe_reduction["current"]
        measured_units += 1

    if measured_units != attempted:
        return fallback
    ratio = 0.0 if baseline_total == 0 else current_total / baseline_total
    return {
        "status": "measured",
        "baseline_total_unsafe": baseline_total,
        "current_total_unsafe": current_total,
        "reduced_by": baseline_total - current_total,
        "ratio": ratio,
    }


def measured_unit_translation_unsafe_reduction(unit: dict[str, Any]) -> dict[str, int] | None:
    evidence = unit.get("translation_before_after")
    if not isinstance(evidence, dict):
        return None
    unsafe_reduction = evidence.get("unsafe_reduction")
    if not isinstance(unsafe_reduction, dict) or unsafe_reduction.get("status") != "measured":
        return None
    baseline = nonnegative_count(unsafe_reduction.get("baseline_total_unsafe"))
    current = nonnegative_count(unsafe_reduction.get("current_total_unsafe"))
    reduced_by = nonnegative_count(unsafe_reduction.get("reduced_by"))
    if baseline is None or current is None or reduced_by is None:
        return None
    if baseline - current != reduced_by or reduced_by <= 0:
        return None
    return {"baseline": baseline, "current": current}


def weighted_worker_metric(metrics: list[dict[str, Any]], key: str, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    numerator = 0.0
    for metric in metrics:
        units = nonnegative_int(metric.get("units_total"))
        value = metric.get(key)
        if isinstance(value, (int, float)) and value >= 0:
            numerator += float(value) * units
    return numerator / denominator


def weighted_metric_with_direct_units(
    metrics: list[dict[str, Any]],
    worker_key: str,
    unit_statuses: list[dict[str, Any]],
    unit_key: str,
    denominator: int,
) -> float:
    if denominator <= 0:
        return 0.0
    numerator = weighted_worker_metric(metrics, worker_key, denominator) * denominator
    for unit in unit_statuses:
        value = unit.get(unit_key)
        if isinstance(value, bool):
            numerator += 1.0 if value else 0.0
        elif isinstance(value, (int, float)) and value >= 0:
            numerator += float(value)
    return numerator / denominator


def sum_worker_int_metric(metrics: list[dict[str, Any]], key: str) -> int:
    total = 0
    for metric in metrics:
        total += nonnegative_int(metric.get(key))
    return total


def sum_unit_int_metric(unit_statuses: list[dict[str, Any]], key: str) -> int:
    total = 0
    for unit in unit_statuses:
        if not isinstance(unit, dict):
            continue
        total += nonnegative_int(unit.get(key))
    return total


def root_cause_counts(unit_statuses: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for unit in unit_statuses:
        if not isinstance(unit, dict):
            continue
        root_cause = unit.get("root_cause_key")
        if isinstance(root_cause, str) and root_cause:
            counts[root_cause] = counts.get(root_cause, 0) + 1
    return counts


def nonnegative_int(value: Any) -> int:
    return value if isinstance(value, int) and value >= 0 else 0


def nonnegative_count(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) and value >= 0 else None


def summary_reference_path(path: Path, *, repo_root: Path, out_root: Path) -> str:
    resolved = path.resolve()
    for root in [repo_root.resolve(), out_root.resolve()]:
        try:
            return resolved.relative_to(root).as_posix()
        except ValueError:
            continue
    return resolved.as_posix()


def direct_extraction_spec_from_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> dict[str, Any] | None:
    required = {
        "source_repo_root": "--source-repo-root",
        "source_file": "--source-file",
        "function": "--function",
        "target_id": "--target-id",
        "slice_id": "--slice-id",
    }
    present = any(getattr(args, key) for key in required)
    present = present or any(
        [
            args.source_commit,
            args.source_repository,
            args.source_branch,
            args.require_source_commit,
            args.compiler_command_source,
            args.include_paths,
            args.defines,
        ]
    )
    if not present:
        return None
    missing = [flag for key, flag in required.items() if not getattr(args, key)]
    if missing:
        parser.error("direct extraction args require " + ", ".join(missing))
    extraction: dict[str, Any] = {
        "repo_root": args.source_repo_root,
        "source_file": args.source_file,
        "function": args.function,
        "target_id": args.target_id,
        "slice_id": args.slice_id,
        "include_paths": list(args.include_paths),
        "defines": list(args.defines),
    }
    if args.source_commit:
        extraction["source_commit"] = args.source_commit
    if args.source_repository:
        extraction["source_repository"] = args.source_repository
    if args.source_branch:
        extraction["source_branch"] = args.source_branch
    if args.require_source_commit:
        extraction["require_source_commit"] = args.require_source_commit
    if args.compiler_command_source:
        extraction["compiler_command_source"] = args.compiler_command_source
    return extraction


def extract_slice_specs(
    extraction_specs: list[ExtractionSpecInput],
    *,
    generated_slice_specs_root: Path,
    command_runner: CommandRunner,
    repo_root: Path,
    logs_dir: Path,
    out_root: Path,
) -> tuple[list[Path], int, list[dict[str, Any]]]:
    generated = []
    failures = 0
    unit_statuses = []
    for spec_path in extraction_specs:
        extraction = load_extraction_spec(spec_path, repo_root=repo_root)
        target_id = required_str(extraction, "target_id")
        slice_id = required_str(extraction, "slice_id")
        output_path = generated_slice_specs_root / f"{target_id}-{slice_id}.json"
        command = extraction_command(extraction, output_path=output_path, repo_root=repo_root)
        result = run_logged_step(
            f"extract-slice-{slice_id}",
            command,
            command_runner=command_runner,
            repo_root=repo_root,
            logs_dir=logs_dir,
            out_root=out_root,
        )
        if result.returncode != 0:
            failures += 1
            unit_statuses.append(
                workflow_unit_status(
                    target_id=target_id,
                    slice_id=slice_id,
                    source="extract-spec",
                    status="failed",
                    compiled=False,
                    semantic_pass=False,
                    refused=False,
                    blocked=False,
                    failed=True,
                )
            )
            continue
        generated.append(output_path)
    return generated, failures, unit_statuses


def load_extraction_spec(path: ExtractionSpecInput, *, repo_root: Path) -> dict[str, Any]:
    if isinstance(path, dict):
        return dict(path)
    resolved = path if path.is_absolute() else repo_root / path
    return json.loads(resolved.read_text(encoding="utf-8"))


def extraction_command(extraction: dict[str, Any], *, output_path: Path, repo_root: Path) -> list[str]:
    command = [
        sys.executable,
        rel_script(EXTRACT_SOURCE_SLICE, repo_root),
        "--repo-root",
        required_str(extraction, "repo_root"),
        "--source-file",
        required_str(extraction, "source_file"),
        "--function",
        required_str(extraction, "function"),
        "--target-id",
        required_str(extraction, "target_id"),
        "--slice-id",
        required_str(extraction, "slice_id"),
        "--out",
        rel_path(output_path, repo_root),
    ]
    optional_string_args = [
        ("source_repository", "--source-repository"),
        ("source_branch", "--source-branch"),
        ("source_commit", "--source-commit"),
        ("require_source_commit", "--require-source-commit"),
        ("compiler_command_source", "--compiler-command-source"),
    ]
    for key, flag in optional_string_args:
        value = extraction.get(key)
        if isinstance(value, str) and value:
            command.extend([flag, value])
    for include_path in string_list(extraction.get("include_paths")):
        command.extend(["--include-path", include_path])
    for define in string_list(extraction.get("defines")):
        command.extend(["--define", define])
    return command


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise SystemExit("extract spec include_paths/defines must be lists of non-empty strings")
    return value


def run_logged_step(
    step: str,
    command: list[str],
    *,
    command_runner: CommandRunner,
    repo_root: Path,
    logs_dir: Path,
    out_root: Path,
) -> subprocess.CompletedProcess[str]:
    result = run_step(command, command_runner=command_runner, repo_root=repo_root)
    append_command_log(
        step=step,
        command=command,
        result=result,
        repo_root=repo_root,
        logs_dir=logs_dir,
        out_root=out_root,
    )
    return result


def append_command_log(
    *,
    step: str,
    command: list[str],
    result: subprocess.CompletedProcess[str],
    repo_root: Path,
    logs_dir: Path,
    out_root: Path,
) -> None:
    log_path = logs_dir / "commands.jsonl"
    entry = {
        "step": step,
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "log_path": summary_log_path(log_path, repo_root=repo_root, out_root=out_root),
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def summary_log_path(path: Path, *, repo_root: Path, out_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().relative_to(out_root.resolve()).as_posix()


def load_slice_spec(path: Path, *, repo_root: Path) -> tuple[Path, dict[str, Any]]:
    resolved = path if path.is_absolute() else repo_root / path
    return resolved, json.loads(resolved.read_text(encoding="utf-8"))


def load_final_verification(evidence_root: Path, target_id: str, slice_id: str) -> dict[str, Any]:
    path = evidence_root / target_id / "auto-translation" / slice_id / f"l3-{slice_id}-final-verification.json"
    if not path.exists():
        return {"status": "failed", "semantic_pass": False, "rust_check_status": "missing"}
    return json.loads(path.read_text(encoding="utf-8"))


def load_translation_before_after(evidence_root: Path, target_id: str, slice_id: str) -> dict[str, Any] | None:
    path = evidence_root / target_id / "auto-translation" / slice_id / f"l3-{slice_id}-translation-before-after.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    return payload


def self_healing_repair_metrics(
    evidence_root: Path,
    target_id: str,
    slice_id: str,
    semantic_pass: bool,
    *,
    repo_root: Path,
    out_root: Path,
) -> dict[str, Any]:
    events_path = (
        evidence_root
        / target_id
        / "auto-translation"
        / slice_id
        / f"l3-{slice_id}-patch-events.jsonl"
    )
    if not events_path.exists():
        return {"repair_rounds": 0, "auto_recovered": False, "llm_calls": 0}
    repair_rounds = 0
    verified = False
    statuses: list[str] = []
    rollback_ids: list[str] = []
    llm_call_keys: set[str] = set()
    for line in events_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        round_value = event.get("round")
        if not isinstance(round_value, int) or round_value < 1:
            continue
        status = event.get("status")
        if isinstance(status, str):
            statuses.append(status)
        rollback_id = event.get("rollback_id")
        if isinstance(rollback_id, str) and rollback_id and rollback_id not in rollback_ids:
            rollback_ids.append(rollback_id)
        ai_usage = event.get("ai_usage")
        if isinstance(ai_usage, dict) and ai_usage.get("used") is True:
            candidate_id = ai_usage.get("candidate_id")
            patch_id = event.get("patch_id")
            key = candidate_id if isinstance(candidate_id, str) and candidate_id else patch_id
            if isinstance(key, str) and key:
                llm_call_keys.add(key)
        if status == "applied":
            repair_rounds = max(repair_rounds, round_value)
        elif status == "verified":
            verified = True
            repair_rounds = max(repair_rounds, round_value)
    repair_history = {
        "patch_events_path": summary_reference_path(events_path, repo_root=repo_root, out_root=out_root),
        "patch_events_sha256": sha256(events_path),
        "statuses": statuses,
        "rollback_ids": rollback_ids,
        "verified": verified,
    }
    return {
        "repair_rounds": repair_rounds,
        "auto_recovered": repair_rounds > 0 and verified and semantic_pass,
        "repair_history": repair_history,
        "llm_calls": len(llm_call_keys),
    }


def required_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise SystemExit(f"slice spec missing required string: {key}")
    return value


def profile_id(repo_root: Path) -> str:
    profile_path = repo_root / "config" / "competition-env" / "environment.json"
    return str(json.loads(profile_path.read_text(encoding="utf-8")).get("profile_id", "unknown"))


def clang_source(repo_root: Path) -> str:
    if os.environ.get("CLANG_PATH"):
        return "CLANG_PATH"
    for candidate in ("tools/llvm/bin/clang-18", "tools/llvm/bin/clang", "tools/clang/bin/clang"):
        if (repo_root / candidate).exists():
            return "vendored"
    return "missing"


def unsafe_budget_summary(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        report = {}
    if not isinstance(report, dict):
        report = {}
    status = report.get("status") if isinstance(report.get("status"), str) else "failed"
    if status not in {"passed", "failed"}:
        status = "failed"
    unsafe_count = report.get("first_party_non_test_unsafe_count")
    unsafe_ratio = report.get("unsafe_ratio")
    return {
        "status": status if result.returncode == 0 else "failed",
        "total_first_party_non_test_unsafe": unsafe_count
        if isinstance(unsafe_count, int) and unsafe_count >= 0
        else 0,
        "ratio": unsafe_ratio if isinstance(unsafe_ratio, (int, float)) and unsafe_ratio >= 0 else 0.0,
    }


def rel_script(path: Path, repo_root: Path) -> str:
    return rel_path(path, repo_root)


def rel_path(path: Path, repo_root: Path) -> str:
    resolved = path if path.is_absolute() else repo_root / path
    try:
        return resolved.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
