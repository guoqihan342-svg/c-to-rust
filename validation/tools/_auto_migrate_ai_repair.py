from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from validation.tools.ai_candidate_harness import (
    ProviderExecution,
    apply_generated_candidate,
    coordinate_repairs,
)


CompileRunner = Callable[[Path], dict[str, Any]]
ProviderRunner = Callable[[list[str], int], ProviderExecution]
ValidationRunner = Callable[[Path, int], dict[str, Any]]


def repair_ai_candidate_after_compile(
    context_pack: dict[str, Any],
    manifest: dict[str, Any],
    *,
    out_dir: Path,
    canonical_draft_path: Path,
    compile_runner: CompileRunner,
    max_rounds: int,
    opencode_command: str,
    resolved_model: str,
    agent: str,
    variant: str,
    timeout_seconds: int,
    provider_runner: ProviderRunner | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if manifest.get("status") != "generated" or max_rounds == 0:
        return manifest, None
    initial_compile = compile_runner(canonical_draft_path)
    if initial_compile.get("returncode") == 0:
        return manifest, None

    report = coordinate_repairs(
        context_pack,
        candidate_path=canonical_draft_path,
        initial_failure_facts=compile_failure_facts(initial_compile),
        out_dir=out_dir,
        validation_runner=lambda path, _round: compile_validation_result(compile_runner(path)),
        max_rounds=max_rounds,
        opencode_command=opencode_command,
        resolved_model=resolved_model,
        agent=agent,
        variant=variant,
        timeout_seconds=timeout_seconds,
        runner=provider_runner,
    )
    return apply_ai_repair_report(
        manifest,
        report,
        out_dir=out_dir,
        canonical_draft_path=canonical_draft_path,
    )


def repair_ai_candidate_after_validation(
    context_pack: dict[str, Any],
    manifest: dict[str, Any],
    *,
    out_dir: Path,
    canonical_draft_path: Path,
    initial_failure_facts: dict[str, Any],
    validation_runner: ValidationRunner,
    max_rounds: int,
    opencode_command: str,
    resolved_model: str,
    agent: str,
    variant: str,
    timeout_seconds: int,
    provider_runner: ProviderRunner | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if manifest.get("status") != "generated" or max_rounds == 0:
        return manifest, None
    if initial_failure_facts.get("status") != "failed":
        return manifest, None
    report = coordinate_repairs(
        context_pack,
        candidate_path=canonical_draft_path,
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
    )
    return apply_ai_repair_report(
        manifest,
        report,
        out_dir=out_dir,
        canonical_draft_path=canonical_draft_path,
    )


def apply_ai_repair_report(
    manifest: dict[str, Any],
    report: dict[str, Any],
    *,
    out_dir: Path,
    canonical_draft_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if report.get("status") != "candidate_ready_for_common_validation":
        manifest["repair"] = repair_report_binding(report, out_dir)
        apply_generated_candidate(
            manifest,
            out_dir=out_dir,
            canonical_draft_path=canonical_draft_path,
        )
        return manifest, report

    candidates = manifest.get("candidates")
    final_ref = report.get("final_candidate")
    if not isinstance(candidates, list) or len(candidates) != 1 or not isinstance(candidates[0], dict):
        raise ValueError("AI repair requires exactly one generated candidate")
    if not isinstance(final_ref, dict):
        raise ValueError("AI repair report is missing final_candidate")
    final_path = safe_out_path(out_dir, final_ref.get("path"))
    final_sha = final_ref.get("sha256")
    if not isinstance(final_sha, str) or sha256_path(final_path) != final_sha:
        raise ValueError("AI repair final candidate sha256 drifted")

    candidate = candidates[0]
    candidate["initial_artifact"] = candidate.get("artifact")
    candidate["initial_output_hash"] = candidate.get("output_hash")
    candidate["artifact"] = {"path": final_path.name, "sha256": final_sha}
    candidate["output_hash"] = final_sha
    candidate["repair"] = repair_report_binding(report, out_dir)
    candidate["repair_rounds"] = len(report.get("rounds", []))
    candidate["applied"] = False
    candidate.pop("applied_artifact", None)
    candidate.pop("rust_draft_sha256", None)
    apply_generated_candidate(
        manifest,
        out_dir=out_dir,
        canonical_draft_path=canonical_draft_path,
    )
    return manifest, report


def compile_validation_result(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("returncode") == 0:
        return {"schema_version": 1, "status": "passed", "failures": []}
    return compile_failure_facts(result)


def compile_failure_facts(result: dict[str, Any]) -> dict[str, Any]:
    errors = result.get("errors")
    failures: list[dict[str, Any]] = []
    if isinstance(errors, list):
        for error in errors[:8]:
            if not isinstance(error, dict):
                continue
            message = error.get("message")
            code = error.get("code")
            rendered = error.get("rendered")
            failures.append(
                {
                    "gate": "rustc",
                    "kind": str(code.get("code")) if isinstance(code, dict) and code.get("code") else "compile_error",
                    "message": str(message or "Rust candidate did not compile")[:4_096],
                    **({"details": {"rendered": str(rendered)[:8_192]}} if rendered else {}),
                }
            )
    if not failures:
        failures.append(
            {
                "gate": "rustc",
                "kind": "compile_error",
                "message": "Rust candidate did not compile",
                "details": {"returncode": result.get("returncode")},
            }
        )
    return {"schema_version": 1, "status": "failed", "failures": failures}


def repair_report_binding(report: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    slice_id = report.get("slice_id")
    report_path = out_dir / f"l3-{slice_id}-ai-repair-report.json"
    if not report_path.is_file():
        raise ValueError("AI repair report artifact is missing")
    return {
        "path": report_path.name,
        "sha256": sha256_path(report_path),
        "status": str(report.get("status", "unknown")),
        "semantic_pass": False,
    }


def safe_out_path(out_dir: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError("AI repair final candidate path must be output-relative")
    path = (out_dir / value).resolve()
    try:
        path.relative_to(out_dir.resolve())
    except ValueError as error:
        raise ValueError("AI repair final candidate escapes output directory") from error
    if not path.is_file():
        raise ValueError("AI repair final candidate is missing")
    return path


def sha256_path(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()
