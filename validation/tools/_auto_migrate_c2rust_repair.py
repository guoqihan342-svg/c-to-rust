from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from validation.tools.ai_candidate_harness import ProviderExecution, coordinate_repairs
from validation.tools._ai_candidate_harness_parts.context import (
    atomic_write_bytes,
    canonical_json_bytes,
    sha256_path,
)
from validation.tools._ai_candidate_harness_parts.repair import required_context_string


ProviderRunner = Callable[[list[str], int], ProviderExecution]
ValidationRunner = Callable[[Path, int], dict[str, Any]]


def repair_c2rust_candidate_after_validation(
    context_pack: dict[str, Any],
    *,
    out_dir: Path,
    baseline_candidate_path: Path,
    initial_failure_facts: dict[str, Any],
    validation_runner: ValidationRunner,
    max_rounds: int,
    opencode_command: str,
    resolved_model: str,
    agent: str,
    variant: str,
    timeout_seconds: int,
    provider_runner: ProviderRunner | None = None,
) -> tuple[dict[str, Any] | None, Path | None]:
    if max_rounds == 0 or initial_failure_facts.get("status") != "failed":
        return None, None
    slice_id = required_context_string(context_pack, "slice_id")
    out_dir.mkdir(parents=True, exist_ok=True)
    repair_input_path = out_dir / f"l3-{slice_id}-c2rust-repair-input.rs"
    atomic_write_bytes(repair_input_path, baseline_candidate_path.read_bytes())
    report = coordinate_repairs(
        context_pack,
        candidate_path=repair_input_path,
        initial_failure_facts=initial_failure_facts,
        out_dir=out_dir,
        validation_runner=validation_runner,
        max_rounds=max_rounds,
        opencode_command=opencode_command,
        resolved_model=resolved_model,
        agent=agent,
        variant=variant,
        timeout_seconds=timeout_seconds,
        runner=provider_runner,
        artifact_label="c2rust-repair",
    )
    reopened_report = reopen_c2rust_repair_report(report, out_dir=out_dir)
    return reopened_report, reopen_latest_candidate(reopened_report, out_dir=out_dir)


def reopen_c2rust_repair_report(report: dict[str, Any], *, out_dir: Path) -> dict[str, Any]:
    slice_id = report.get("slice_id")
    if not isinstance(slice_id, str) or not slice_id:
        raise ValueError("C2Rust repair report is missing slice_id")
    report_path = safe_evidence_path(out_dir, f"l3-{slice_id}-c2rust-repair-report.json")
    try:
        reopened = json.loads(report_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("C2Rust repair report is not valid JSON") from error
    if not isinstance(reopened, dict) or canonical_json_bytes(reopened) != canonical_json_bytes(report):
        raise ValueError("C2Rust repair report payload drifted")
    if reopened.get("artifact_label") != "c2rust-repair":
        raise ValueError("C2Rust repair report artifact_label drifted")
    if reopened.get("input_source") != "c2rust-baseline":
        raise ValueError("C2Rust repair report input_source drifted")
    return reopened


def reopen_latest_candidate(report: dict[str, Any], *, out_dir: Path) -> Path | None:
    refs: list[Any] = [report.get("final_candidate")]
    rounds = report.get("rounds")
    if isinstance(rounds, list):
        for round_record in reversed(rounds):
            bindings = round_record.get("bindings") if isinstance(round_record, dict) else None
            refs.append(bindings.get("candidate") if isinstance(bindings, dict) else None)
    for ref in refs:
        if not isinstance(ref, dict) or "path" not in ref:
            continue
        candidate_path = safe_evidence_path(out_dir, ref.get("path"))
        expected_sha = ref.get("sha256")
        if not isinstance(expected_sha, str) or sha256_path(candidate_path) != expected_sha:
            raise ValueError("C2Rust repair candidate sha256 drifted")
        return candidate_path
    return None


def repair_report_binding(report: dict[str, Any], *, out_dir: Path) -> dict[str, Any]:
    reopened = reopen_c2rust_repair_report(report, out_dir=out_dir)
    report_path = safe_evidence_path(
        out_dir,
        f"l3-{reopened['slice_id']}-c2rust-repair-report.json",
    )
    return {
        "path": report_path.relative_to(out_dir.resolve()).as_posix(),
        "sha256": sha256_path(report_path),
        "status": str(reopened.get("status", "unknown")),
        "semantic_pass": False,
    }


def safe_evidence_path(out_dir: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError("C2Rust repair artifact path must be evidence-relative")
    evidence_root = out_dir.resolve()
    configured_path = evidence_root / value
    if configured_path.is_symlink():
        raise ValueError("C2Rust repair artifact is not safely reopenable")
    path = configured_path.resolve()
    try:
        path.relative_to(evidence_root)
    except ValueError as error:
        raise ValueError("C2Rust repair artifact escapes evidence directory") from error
    if not path.is_file() or path.is_symlink():
        raise ValueError("C2Rust repair artifact is not safely reopenable")
    return path
