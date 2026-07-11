#!/usr/bin/env python3
"""Run the bounded AI finite cross-project suite through run_competition."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SUITE = Path("validation/ai-finite-cross-project-suite.json")
DEFAULT_OUT_ROOT = Path("target/ai-finite-cross-project-suite")
REPORT_NAME = "ai-finite-cross-project-suite-run-report.json"
PROOF_CLASSES = (
    "competition-exact",
    "ci-approximation",
    "wsl-local-simulation",
    "local-simulation",
)


PreflightValidator = Callable[[Path | str, Path | str | None], dict[str, Any]]
CompetitionRunner = Callable[..., Any]


def _default_preflight_validator(
    suite_path: Path | str,
    repo_root: Path | str | None = None,
) -> dict[str, Any]:
    from validation.tools.validate_ai_finite_cross_project_suite import validate_suite

    return validate_suite(suite_path, repo_root)


def _default_competition_runner(**kwargs: Any) -> Any:
    from validation.tools.run_competition import run_competition

    return run_competition(**kwargs)


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("utf-8")
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _resolve(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _portable_ref(path: Path, *, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.name


def _read_suite_snapshot(path: Path) -> tuple[bytes, dict[str, Any]]:
    raw = path.read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("suite must be a JSON object")
    return raw, payload


def _suite_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 20:
        raise ValueError("suite.items must contain 1..20 entries")
    checked: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"suite.items[{index}] must be an object")
        spec = item.get("slice_spec")
        if not isinstance(spec, dict) or not isinstance(spec.get("path"), str):
            raise ValueError(f"suite.items[{index}].slice_spec.path must be a string")
        if not isinstance(spec.get("sha256"), str):
            raise ValueError(f"suite.items[{index}].slice_spec.sha256 must be a string")
        checked.append(item)
    return checked


def _preflight_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract_status": report.get("contract_status"),
        "status": report.get("status"),
        "summary": report.get("summary"),
    }


def _claim_boundary(*, dry_run: bool) -> dict[str, Any]:
    return {
        "accepted_evidence_shortcut": False,
        "fresh_execution_only": True,
        "outer_retry_count": 0,
        "semantic_claim_source": "hash_bound_run_competition_final_summary",
        "semantic_numbers_copied_only": True,
        "suite_report_is_independent_semantic_evidence": False,
        "dry_run_creates_success_claim": False,
        "dry_run": dry_run,
    }


def _base_report(
    *,
    suite_path: Path,
    repo_root: Path,
    suite_sha256: str | None,
    suite_id: Any,
    run_id: str | None,
    proof_class: str,
    preflight: dict[str, Any],
    dry_run: bool,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "proof_class": proof_class,
        "dry_run": dry_run,
        "suite": {
            "id": suite_id if isinstance(suite_id, str) else None,
            "path": _portable_ref(suite_path, base=repo_root),
            "sha256": suite_sha256,
        },
        "preflight": preflight,
        "claim_boundary": _claim_boundary(dry_run=dry_run),
    }


def _blocked_report(
    base: dict[str, Any],
    *,
    reason: str,
    report_path: Path,
) -> tuple[int, dict[str, Any], Path]:
    report = {
        **base,
        "status": "blocked",
        "exit_code": 2,
        "blocked_reasons": [reason],
        "runs": [],
        "slices": [],
        "ai_translation_metrics": [],
    }
    _atomic_write_json(report_path, report)
    return 2, report, report_path


def _plan(
    base: dict[str, Any],
    *,
    items: list[dict[str, Any]],
    out_root: Path,
    repo_root: Path,
    ai_options: dict[str, Any],
) -> dict[str, Any]:
    suite_items = [
        {
            "index": index,
            "item_id": item.get("id"),
            "project_id": item.get("project_id"),
            "slice_id": item.get("slice_id"),
            "slice_spec": {
                "path": item["slice_spec"]["path"],
                "sha256": item["slice_spec"]["sha256"],
            },
        }
        for index, item in enumerate(items)
    ]
    return {
        **base,
        "status": "planned",
        "exit_code": 0,
        "plan": {
            "out_root": _portable_ref(out_root, base=repo_root),
            "competition_run": {
                "out_root": "competition",
                "suite_items": suite_items,
                "reuse_accepted_evidence": False,
                "outer_attempts": 1,
                "ai": ai_options,
            },
            "competition_runner_invocations": 0,
            "model_invocations": 0,
            "translations_executed": 0,
            "success_claim_created": False,
        },
    }


def _load_bound_competition_summary(
    *,
    result: Any,
    expected_path: Path,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    result_path = getattr(result, "summary_path", None)
    if not isinstance(result_path, Path) or result_path.resolve() != expected_path.resolve():
        return None, None, "unexpected_competition_summary_path"
    if not expected_path.is_file():
        return None, None, "competition_summary_missing"

    first_sha = _sha256_path(expected_path)
    raw = expected_path.read_bytes()
    if _sha256_bytes(raw) != first_sha or _sha256_path(expected_path) != first_sha:
        return None, None, "competition_summary_sha256_drift"
    try:
        summary = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, None, "competition_summary_invalid_json"
    if not isinstance(summary, dict):
        return None, None, "competition_summary_not_object"
    if getattr(result, "summary", None) != summary:
        return None, None, "competition_summary_result_mismatch"
    if getattr(result, "summary_validated", None) is not True:
        return None, None, "competition_summary_validation_failed"
    if not isinstance(summary.get("slices"), dict):
        return None, None, "competition_summary_slices_missing"
    if not isinstance(summary.get("ai_translation_metrics"), dict):
        return None, None, "competition_summary_ai_translation_metrics_missing"
    return summary, first_sha, None


def run_suite(
    *,
    suite: Path = DEFAULT_SUITE,
    out_root: Path = DEFAULT_OUT_ROOT,
    proof_class: str = "local-simulation",
    run_id: str | None = None,
    ai_model: str | None = None,
    ai_agent: str | None = None,
    ai_variant: str | None = None,
    ai_timeout_seconds: int | None = None,
    ai_opencode_command: str | None = None,
    dry_run: bool = False,
    repo_root: Path = REPO_ROOT,
    preflight_validator: PreflightValidator = _default_preflight_validator,
    competition_runner: CompetitionRunner = _default_competition_runner,
) -> tuple[int, dict[str, Any], Path | None]:
    root = repo_root.resolve()
    suite_path = _resolve(root, suite)
    output_root = _resolve(root, out_root)
    report_path = output_root / "summary" / REPORT_NAME

    try:
        before_raw, suite_payload = _read_suite_snapshot(suite_path)
        suite_sha256 = _sha256_bytes(before_raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        base = _base_report(
            suite_path=suite_path,
            repo_root=root,
            suite_sha256=None,
            suite_id=None,
            run_id=run_id,
            proof_class=proof_class,
            preflight={"contract_status": "failed", "status": "blocked", "error": str(exc)},
            dry_run=dry_run,
        )
        if dry_run:
            return 2, {**base, "status": "blocked", "exit_code": 2, "blocked_reasons": ["suite_unreadable"]}, None
        return _blocked_report(base, reason="suite_unreadable", report_path=report_path)

    try:
        preflight = preflight_validator(suite_path, root)
    except Exception as exc:
        preflight = {"contract_status": "failed", "status": "blocked", "error": str(exc)}
    base = _base_report(
        suite_path=suite_path,
        repo_root=root,
        suite_sha256=suite_sha256,
        suite_id=suite_payload.get("suite_id"),
        run_id=run_id,
        proof_class=proof_class,
        preflight=_preflight_summary(preflight),
        dry_run=dry_run,
    )

    try:
        after_raw, suite_payload = _read_suite_snapshot(suite_path)
        items = _suite_items(suite_payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        base["preflight"]["postflight_error"] = str(exc)
        if dry_run:
            return 2, {**base, "status": "blocked", "exit_code": 2, "blocked_reasons": ["suite_postflight_invalid"]}, None
        return _blocked_report(base, reason="suite_postflight_invalid", report_path=report_path)

    if _sha256_bytes(after_raw) != suite_sha256:
        if dry_run:
            return 2, {**base, "status": "blocked", "exit_code": 2, "blocked_reasons": ["suite_sha256_drift"]}, None
        return _blocked_report(base, reason="suite_sha256_drift", report_path=report_path)
    if preflight.get("contract_status") != "passed" or preflight.get("status") != "ready":
        if dry_run:
            return 2, {**base, "status": "blocked", "exit_code": 2, "blocked_reasons": ["suite_preflight_not_ready"]}, None
        return _blocked_report(base, reason="suite_preflight_not_ready", report_path=report_path)

    ai_options = {
        "model": ai_model,
        "agent": ai_agent,
        "variant": ai_variant,
        "timeout_seconds": ai_timeout_seconds,
        "opencode_command": ai_opencode_command,
    }
    if dry_run:
        return 0, _plan(
            base,
            items=items,
            out_root=output_root,
            repo_root=root,
            ai_options=ai_options,
        ), None

    competition_out_root = output_root / "competition"
    expected_summary = competition_out_root / "summary" / "competition-run-summary.json"
    suite_items = [
        {
            "index": index,
            "item_id": item.get("id"),
            "project_id": item.get("project_id"),
            "slice_id": item.get("slice_id"),
            "slice_spec": {
                "path": item["slice_spec"]["path"],
                "sha256": item["slice_spec"]["sha256"],
            },
        }
        for index, item in enumerate(items)
    ]
    run_record: dict[str, Any] = {
        "suite_items": suite_items,
        "fresh_execution": True,
        "outer_attempts": 1,
    }
    copied_slices: list[dict[str, Any]] = []
    copied_ai_metrics: list[dict[str, Any]] = []
    try:
        result = competition_runner(
            slice_specs=[Path(item["slice_spec"]["path"]) for item in items],
            out_root=competition_out_root,
            proof_class=proof_class,
            repo_root=root,
            run_id=run_id,
            reuse_accepted_evidence=False,
            ai_model=ai_model,
            ai_agent=ai_agent,
            ai_variant=ai_variant,
            ai_timeout_seconds=ai_timeout_seconds,
            ai_opencode_command=ai_opencode_command,
        )
    except (Exception, SystemExit) as exc:
        run_record.update(status="failed", exit_code=1, error=f"competition_runner_failed: {exc}")
    else:
        summary, summary_sha, error = _load_bound_competition_summary(
            result=result,
            expected_path=expected_summary,
        )
        runner_exit = getattr(result, "exit_code", 1)
        if error is not None or summary is None or summary_sha is None:
            run_record.update(status="failed", exit_code=runner_exit, error=error)
        else:
            slices = summary["slices"]
            ai_metrics = summary["ai_translation_metrics"]
            attempted = slices.get("attempted")
            circuit = summary.get("provider_circuit_breaker")
            circuit_blocked = (
                isinstance(attempted, int)
                and isinstance(circuit, dict)
                and circuit.get("status") == "open"
                and circuit.get("requested_slice_specs") == len(items)
                and circuit.get("attempted_slice_specs") == attempted
                and circuit.get("skipped_slice_specs") == len(items) - attempted
                and 0 <= attempted < len(items)
            )
            if attempted != len(items) and not circuit_blocked:
                run_record.update(
                    status="failed",
                    exit_code=runner_exit,
                    error="competition_summary_attempted_count_mismatch",
                )
            else:
                final_gate = summary.get("final_gate")
                passed = runner_exit == 0 and isinstance(final_gate, dict) and final_gate.get("status") == "passed"
                summary_ref = {
                    "path": _portable_ref(expected_summary, base=output_root),
                    "sha256": summary_sha,
                }
                run_record.update(
                    status="blocked" if circuit_blocked else "passed" if passed else "failed",
                    exit_code=runner_exit,
                    competition_summary=summary_ref,
                    slices=slices,
                    ai_translation_metrics=ai_metrics,
                )
                if circuit_blocked:
                    run_record.update(
                        error="provider_circuit_breaker_open",
                        provider_circuit_breaker=circuit,
                    )
                copied_slices.append({"competition_summary": summary_ref, "value": slices})
                copied_ai_metrics.append({"competition_summary": summary_ref, "value": ai_metrics})

    runs = [run_record]
    passed = run_record.get("status") == "passed"
    blocked = run_record.get("status") == "blocked"
    report = {
        **base,
        "status": "passed" if passed else "blocked" if blocked else "failed",
        "exit_code": 0 if passed else 2 if blocked else 1,
        "runs": runs,
        "slices": copied_slices,
        "ai_translation_metrics": copied_ai_metrics,
    }
    _atomic_write_json(report_path, report)
    return report["exit_code"], report, report_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--proof-class", choices=PROOF_CLASSES, default="local-simulation")
    parser.add_argument("--run-id")
    parser.add_argument("--ai-model")
    parser.add_argument("--ai-agent")
    parser.add_argument("--ai-variant")
    parser.add_argument("--ai-timeout-seconds", type=int)
    parser.add_argument("--ai-opencode-command")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(
    argv: list[str] | None = None,
    *,
    preflight_validator: PreflightValidator = _default_preflight_validator,
    competition_runner: CompetitionRunner = _default_competition_runner,
    repo_root: Path = REPO_ROOT,
) -> int:
    args = build_parser().parse_args(argv)
    exit_code, payload, _ = run_suite(
        suite=args.suite,
        out_root=args.out_root,
        proof_class=args.proof_class,
        run_id=args.run_id,
        ai_model=args.ai_model,
        ai_agent=args.ai_agent,
        ai_variant=args.ai_variant,
        ai_timeout_seconds=args.ai_timeout_seconds,
        ai_opencode_command=args.ai_opencode_command,
        dry_run=args.dry_run,
        repo_root=repo_root,
        preflight_validator=preflight_validator,
        competition_runner=competition_runner,
    )
    print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
