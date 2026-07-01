#!/usr/bin/env python3
"""Linux/WSL/CI competition smoke entrypoint.

This script proves the local runner can execute the competition environment
checks and lightweight validation gates. It is not a slice translation runner
and does not make semantic-pass claims for new slices.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPO_ROOT / "config" / "competition-env" / "environment.json"
AUTO_EVIDENCE_VALIDATOR = REPO_ROOT / "validation" / "tools" / "validate_auto_translation_evidence.py"
EVIDENCE_GOVERNANCE = REPO_ROOT / "validation" / "tools" / "evidence_governance.py"
TRANSLATOR_COVERAGE_MATRIX = REPO_ROOT / "validation" / "tools" / "translator_coverage_matrix.py"
MILESTONE_RELEASE_REPORT = REPO_ROOT / "validation" / "tools" / "milestone_release_report.py"
VERIFY_VENDORED_CLANG = REPO_ROOT / "validation" / "tools" / "verify_vendored_clang.py"
DEFAULT_SLICE_SPEC = REPO_ROOT / "validation" / "slice-specs" / "flashdb-real-fdb-calc-crc32.json"


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
PROOF_CLASSES = ["competition-exact", "ci-approximation", "wsl-local-simulation", "local-simulation"]


class CompetitionSmokeResult:
    def __init__(self, *, exit_code: int, summary_path: Path, summary: dict[str, Any]) -> None:
        self.exit_code = exit_code
        self.summary_path = summary_path
        self.summary = summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-root", type=Path, default=REPO_ROOT / "target" / "competition-smoke")
    parser.add_argument("--run-id")
    parser.add_argument("--proof-class", choices=PROOF_CLASSES, default="local-simulation")
    parser.add_argument("--confirm-competition-exact", action="store_true")
    parser.add_argument("--target-id", default="flashdb")
    parser.add_argument("--slice-id", default="real-fdb-calc-crc32")
    parser.add_argument("--slice-spec", type=Path, default=DEFAULT_SLICE_SPEC)
    args = parser.parse_args()

    result = run_competition_smoke(
        out_root=args.out_root,
        proof_class=args.proof_class,
        confirm_competition_exact=args.confirm_competition_exact,
        target_id=args.target_id,
        slice_id=args.slice_id,
        slice_spec=args.slice_spec,
        run_id=args.run_id,
        repo_root=REPO_ROOT,
    )
    print(json.dumps(result.summary, indent=2, sort_keys=True))
    return result.exit_code


def run_competition_smoke(
    *,
    out_root: Path,
    proof_class: str,
    command_runner: CommandRunner = subprocess.run,
    repo_root: Path = REPO_ROOT,
    run_id: str | None = None,
    confirm_competition_exact: bool = False,
    target_id: str = "flashdb",
    slice_id: str = "real-fdb-calc-crc32",
    slice_spec: Path = DEFAULT_SLICE_SPEC,
) -> CompetitionSmokeResult:
    if proof_class == "competition-exact" and not confirm_competition_exact:
        raise SystemExit("proof_class=competition-exact requires --confirm-competition-exact")

    repo_root = repo_root.resolve()
    out_root = out_root if out_root.is_absolute() else repo_root / out_root
    logs_dir = out_root / "logs"
    summary_dir = out_root / "summary"
    reports_dir = out_root / "reports"
    for directory in [logs_dir, summary_dir, reports_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    run_id = run_id or time.strftime("smoke-%Y%m%dT%H%M%SZ", time.gmtime())
    profile = load_profile(repo_root)
    environment = detect_execution_environment()
    deviations = environment_deviations(profile, environment, proof_class=proof_class)

    steps: list[dict[str, Any]] = []
    commands = smoke_commands(
        repo_root=repo_root,
        out_root=out_root,
        proof_class=proof_class,
        target_id=target_id,
        slice_id=slice_id,
        slice_spec=slice_spec,
    )
    for step, command in commands:
        result = run_logged_step(
            step,
            command,
            command_runner=command_runner,
            repo_root=repo_root,
            logs_dir=logs_dir,
            out_root=out_root,
        )
        step_status_value = smoke_step_status(step, result.returncode, proof_class=proof_class)
        proof_class_effect = None
        if step == "environment-check" and result.returncode != 0 and proof_class != "competition-exact":
            proof_class_effect = "exactness_blocker"
        steps.append(
            {
                "step": step,
                "status": step_status_value,
                "returncode": result.returncode,
                "log_path": summary_log_path(logs_dir / "commands.jsonl", repo_root=repo_root, out_root=out_root),
                **({"proof_class_effect": proof_class_effect} if proof_class_effect else {}),
            }
        )

    clang_source_value = clang_source(repo_root)
    clang_lane_verified_value = (
        clang_source_value != "missing"
        and step_status(steps, "environment-check") == "passed"
        and step_status(steps, "vendored-clang-verification") == "passed"
    )
    final_gate_reasons = final_gate_reasons_for(proof_class=proof_class, steps=steps, deviations=deviations)
    status = "passed" if not final_gate_reasons else "failed"
    summary = {
        "schema_version": 1,
        "report_kind": "competition-smoke-summary",
        "run_id": run_id,
        "proof_class": proof_class,
        "profile_id": str(profile.get("profile_id", "unknown")),
        "profile_sha256": sha256(profile_path(repo_root)),
        "clang_source": clang_source_value,
        "clang_lane_verified": clang_lane_verified_value,
        "execution_environment": environment,
        "competition_profile_match": competition_profile_match(
            profile,
            environment,
            profile_sha256_actual=sha256(profile_path(repo_root)),
            clang_lane_verified_value=clang_lane_verified_value,
            repo_root=repo_root,
        ),
        "environment_deviations": deviations,
        "smoke_entrypoint": {
            "name": "competition-linux-wsl-ci-smoke",
            "script": "validation/tools/run_competition_smoke.py",
            "scope": [
                "environment-check",
                "vendored-clang-verification",
                "core-auto-evidence-validator",
                "evidence-governance",
                "translator-coverage-matrix",
                "milestone-release-report",
                "lightweight-unittest",
            ],
            "semantic_acceptance_boundary": "does_not_translate_new_slices",
        },
        "claim_boundary": {
            "semantic_gate": False,
            "semantic_claim_source": "competition_environment_smoke",
            "generated_draft_semantic_pass": False,
            "translation_coverage_numerator": 0,
            "boundary": (
                "Competition smoke proves environment and lightweight evidence gates only. "
                "It does not translate new slices and does not expand semantic acceptance."
            ),
        },
        "elapsed_seconds": int(time.monotonic() - started),
        "artifact_roots": [
            summary_path(out_root / "summary", repo_root=repo_root, out_root=out_root),
            summary_path(out_root / "logs", repo_root=repo_root, out_root=out_root),
            summary_path(out_root / "reports", repo_root=repo_root, out_root=out_root),
        ],
        "command_log": {
            "path": summary_path(logs_dir / "commands.jsonl", repo_root=repo_root, out_root=out_root),
        },
        "reports": {
            "evidence_governance": {
                "path": summary_path(
                    out_root / "reports" / "evidence-governance.json",
                    repo_root=repo_root,
                    out_root=out_root,
                ),
            },
            "translator_coverage_matrix": {
                "path": summary_path(
                    out_root / "reports" / "translator-coverage-matrix.json",
                    repo_root=repo_root,
                    out_root=out_root,
                ),
            },
        },
        "vendored_clang_verification": {
            "path": summary_path(
                out_root / "summary" / "vendored-clang-verification.json",
                repo_root=repo_root,
                out_root=out_root,
            ),
            "required_for_proof_class": proof_class == "competition-exact",
        },
        "milestone_release_report": {
            "path": summary_path(
                out_root / "reports" / "milestone-release-report.json",
                repo_root=repo_root,
                out_root=out_root,
            ),
            "semantic_acceptance_claim": False,
            "boundary": "report-only milestone metrics; does not translate new slices",
        },
        "steps": steps,
        "final_gate": {
            "status": status,
            "validator": "run_competition_smoke.py",
            **({"reasons": final_gate_reasons} if final_gate_reasons else {}),
        },
    }
    summary_path_value = summary_dir / "competition-smoke-summary.json"
    summary_path_value.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return CompetitionSmokeResult(
        exit_code=0 if status == "passed" else 1,
        summary_path=summary_path_value,
        summary=summary,
    )


def smoke_commands(
    *,
    repo_root: Path,
    out_root: Path,
    proof_class: str,
    target_id: str,
    slice_id: str,
    slice_spec: Path,
) -> list[tuple[str, list[str]]]:
    vendored_clang_command = [
        sys.executable,
        rel_path(VERIFY_VENDORED_CLANG, repo_root),
        "--proof-class",
        proof_class,
        "--out",
        rel_path(out_root / "summary" / "vendored-clang-verification.json", repo_root),
    ]
    if proof_class == "competition-exact":
        vendored_clang_command.append("--require-clang")

    return [
        (
            "environment-check",
            ["bash", "-lc", "source config/competition-env/env.sh; bash config/competition-env/toolchain-check.sh"],
        ),
        ("vendored-clang-verification", vendored_clang_command),
        (
            "core-auto-evidence-validator",
            [
                sys.executable,
                rel_path(AUTO_EVIDENCE_VALIDATOR, repo_root),
                "--target-id",
                target_id,
                "--slice-id",
                slice_id,
                "--slice-spec",
                rel_path(slice_spec, repo_root),
                "--require-semantic-pass",
            ],
        ),
        (
            "evidence-governance",
            [
                sys.executable,
                rel_path(EVIDENCE_GOVERNANCE, repo_root),
                "--output",
                rel_path(out_root / "reports" / "evidence-governance.json", repo_root),
            ],
        ),
        (
            "translator-coverage-matrix",
            [
                sys.executable,
                rel_path(TRANSLATOR_COVERAGE_MATRIX, repo_root),
                "--output",
                rel_path(out_root / "reports" / "translator-coverage-matrix.json", repo_root),
            ],
        ),
        (
            "milestone-release-report",
            [
                sys.executable,
                rel_path(MILESTONE_RELEASE_REPORT, repo_root),
                "--coverage-report",
                rel_path(out_root / "reports" / "translator-coverage-matrix.json", repo_root),
                "--output",
                rel_path(out_root / "reports" / "milestone-release-report.json", repo_root),
            ],
        ),
        (
            "lightweight-unittest",
            [
                sys.executable,
                "-m",
                "unittest",
                "validation.tools.test_competition_environment_profile",
                "validation.tools.test_validate_competition_run_summary",
            ],
        ),
    ]


def smoke_step_status(step: str, returncode: int, *, proof_class: str) -> str:
    if returncode == 0:
        return "passed"
    if step == "environment-check" and proof_class != "competition-exact":
        return "degraded"
    return "failed"


def run_logged_step(
    step: str,
    command: list[str],
    *,
    command_runner: CommandRunner,
    repo_root: Path,
    logs_dir: Path,
    out_root: Path,
) -> subprocess.CompletedProcess[str]:
    result = command_runner(
        command,
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    entry = {
        "step": step,
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "log_path": summary_log_path(logs_dir / "commands.jsonl", repo_root=repo_root, out_root=out_root),
    }
    with (logs_dir / "commands.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
    return result


def detect_execution_environment() -> dict[str, Any]:
    uname = platform.uname()
    release_lower = uname.release.lower()
    detected_ci = any(os.environ.get(name) for name in ["CI", "GITHUB_ACTIONS", "BUILD_BUILDID"])
    detected_wsl = "microsoft" in release_lower or bool(os.environ.get("WSL_DISTRO_NAME"))
    if detected_ci:
        kind = "linux-ci"
    elif detected_wsl:
        kind = "wsl"
    elif platform.system() == "Linux":
        kind = "local-linux"
    elif platform.system() == "Windows":
        kind = "windows-local"
    else:
        kind = "local"
    return {
        "kind": kind,
        "detected_ci": bool(detected_ci),
        "detected_wsl": detected_wsl,
        "system": platform.system(),
        "release": uname.release,
        "version": uname.version,
        "machine": uname.machine,
        "kernel": uname.release,
        "python_version": platform.python_version(),
        "runner_name": os.environ.get("GITHUB_ACTIONS") and "github-actions" or "local",
    }


def environment_deviations(
    profile: dict[str, Any],
    environment: dict[str, Any],
    *,
    proof_class: str,
) -> list[dict[str, Any]]:
    expected_os = profile.get("os", {}) if isinstance(profile.get("os"), dict) else {}
    expected_toolchain = profile.get("toolchain", {}) if isinstance(profile.get("toolchain"), dict) else {}
    deviations = []
    append_deviation(
        deviations,
        field="os.name",
        expected=expected_os.get("name"),
        actual=environment["system"],
        limit=limit_for_environment(environment),
    )
    append_deviation(
        deviations,
        field="os.kernel",
        expected=expected_os.get("kernel"),
        actual=environment["kernel"],
        limit=limit_for_environment(environment),
    )
    append_deviation(
        deviations,
        field="python.version",
        expected=expected_toolchain.get("python"),
        actual=environment["python_version"],
        limit=limit_for_environment(environment),
    )
    if proof_class != "competition-exact":
        deviations.append(
            {
                "field": "proof_class",
                "expected": "competition-exact only on the real competition host",
                "actual": proof_class,
                "severity": "diagnostic",
                "limits_proof_class_to": proof_class,
            }
        )
    return deviations


def append_deviation(
    deviations: list[dict[str, Any]],
    *,
    field: str,
    expected: Any,
    actual: Any,
    limit: str,
) -> None:
    if expected != actual:
        deviations.append(
            {
                "field": field,
                "expected": expected,
                "actual": actual,
                "severity": "proof-class-limiting",
                "limits_proof_class_to": limit,
            }
        )


def limit_for_environment(environment: dict[str, Any]) -> str:
    if environment["detected_ci"]:
        return "ci-approximation"
    if environment["detected_wsl"]:
        return "wsl-local-simulation"
    return "local-simulation"


def competition_profile_match(
    profile: dict[str, Any],
    environment: dict[str, Any],
    *,
    profile_sha256_actual: str,
    clang_lane_verified_value: bool,
    repo_root: Path,
) -> dict[str, Any]:
    expected_os = profile.get("os", {}) if isinstance(profile.get("os"), dict) else {}
    expected_toolchain = profile.get("toolchain", {}) if isinstance(profile.get("toolchain"), dict) else {}
    return {
        "profile_id": str(profile.get("profile_id", "unknown")),
        "profile_sha256_actual": profile_sha256_actual,
        "os_name_match": expected_os.get("name") == environment["system"],
        "kernel_match": expected_os.get("kernel") == environment["kernel"],
        "python_version_match": expected_toolchain.get("python") == environment["python_version"],
        "clang_lane_verified": clang_lane_verified_value,
        "cargo_mirror_config_present": (repo_root / "config" / "competition-env" / "cargo" / "config.toml").exists(),
    }


def step_status(steps: list[dict[str, Any]], step_name: str) -> str:
    for step in steps:
        if step["step"] == step_name:
            return str(step["status"])
    return "missing"


def final_gate_reasons_for(
    *,
    proof_class: str,
    steps: list[dict[str, Any]],
    deviations: list[dict[str, Any]],
) -> list[str]:
    reasons = [f"step_failed:{step['step']}" for step in steps if step["status"] == "failed"]
    if proof_class == "competition-exact" and any(
        item.get("severity") == "proof-class-limiting" for item in deviations
    ):
        reasons.append("proof_class_limited_by_environment")
    return reasons


def load_profile(repo_root: Path) -> dict[str, Any]:
    return json.loads(profile_path(repo_root).read_text(encoding="utf-8"))


def profile_path(repo_root: Path) -> Path:
    return repo_root / "config" / "competition-env" / "environment.json"


def clang_source(repo_root: Path) -> str:
    if os.environ.get("CLANG_PATH"):
        return "CLANG_PATH"
    for candidate in (
        "tools/llvm/bin/clang-18",
        "tools/llvm/bin/clang",
        "tools/clang/bin/clang",
        "tools/llvm/bin/clang.exe",
        "tools/clang/bin/clang.exe",
    ):
        if (repo_root / candidate).exists():
            return "vendored"
    return "missing"


def summary_log_path(path: Path, *, repo_root: Path, out_root: Path) -> str:
    return summary_path(path, repo_root=repo_root, out_root=out_root)


def summary_path(path: Path, *, repo_root: Path, out_root: Path) -> str:
    resolved = path.resolve()
    for root in [repo_root.resolve(), out_root.resolve()]:
        try:
            return resolved.relative_to(root).as_posix()
        except ValueError:
            continue
    return resolved.as_posix()


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
