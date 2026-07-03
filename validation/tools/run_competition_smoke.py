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
import re
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
LOCAL_HOST_PATH_UNQUOTED = (
    r"(?:"
    r"[A-Za-z]:[\\/][^\s;&|]+|"
    r"/mnt/[A-Za-z]/[^\s;&|]+|"
    r"/home/[^\s;&|]+|"
    r"/Users/[^\s;&|]+|"
    r"/tmp/[^\s;&|]+|"
    r"/var/[^\s;&|]+|"
    r"\\\\wsl\$\\[^\s;&|]+|"
    r"\\\\wsl\.localhost\\[^\s;&|]+|"
    r"//wsl\$/[^\s;&|]+|"
    r"//wsl\.localhost/[^\s;&|]+"
    r")"
)
LOCAL_HOST_PATH_DOUBLE_QUOTED = (
    r"(?:"
    r'[A-Za-z]:[\\/][^"]+|'
    r'/mnt/[A-Za-z]/[^"]+|'
    r'/home/[^"]+|'
    r'/Users/[^"]+|'
    r'/tmp/[^"]+|'
    r'/var/[^"]+|'
    r'\\\\wsl\$\\[^"]+|'
    r'\\\\wsl\.localhost\\[^"]+|'
    r'//wsl\$/[^"]+|'
    r'//wsl\.localhost/[^"]+'
    r")"
)
LOCAL_HOST_PATH_SINGLE_QUOTED = (
    r"(?:"
    r"[A-Za-z]:[\\/][^']+|"
    r"/mnt/[A-Za-z]/[^']+|"
    r"/home/[^']+|"
    r"/Users/[^']+|"
    r"/tmp/[^']+|"
    r"/var/[^']+|"
    r"\\\\wsl\$\\[^']+|"
    r"\\\\wsl\.localhost\\[^']+|"
    r"//wsl\$/[^']+|"
    r"//wsl\.localhost/[^']+"
    r")"
)
LOCAL_HOST_PATH_IN_COMMAND = re.compile(
    rf'"(?P<double_quoted_path>{LOCAL_HOST_PATH_DOUBLE_QUOTED})"|'
    rf"'(?P<single_quoted_path>{LOCAL_HOST_PATH_SINGLE_QUOTED})'|"
    rf"(?P<plain_path>{LOCAL_HOST_PATH_UNQUOTED})"
)


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
PROOF_CLASSES = ["competition-exact", "ci-approximation", "wsl-local-simulation", "local-simulation"]
DEFAULT_STEP_TIMEOUT_SECONDS = 600
REQUIRED_TOOL_MISSING_PATTERNS = (
    "gcc is not installed",
    "g++ is not installed",
    "cc is not installed",
    "c compiler is not installed",
    "c compiler missing",
    "required c compiler",
    "no acceptable c compiler",
)


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
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_STEP_TIMEOUT_SECONDS)
    args = parser.parse_args()

    result = run_competition_smoke(
        out_root=args.out_root,
        proof_class=args.proof_class,
        confirm_competition_exact=args.confirm_competition_exact,
        target_id=args.target_id,
        slice_id=args.slice_id,
        slice_spec=args.slice_spec,
        timeout_seconds=args.timeout_seconds,
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
    timeout_seconds: int = DEFAULT_STEP_TIMEOUT_SECONDS,
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
    command_log_path = logs_dir / "commands.jsonl"
    if command_log_path.exists():
        command_log_path.unlink()

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
            timeout_seconds=timeout_seconds,
        )
        timed_out = bool(getattr(result, "timed_out", False))
        failure_class = getattr(result, "failure_class", None)
        step_status_value = smoke_step_status(
            step,
            result.returncode,
            proof_class=proof_class,
            timed_out=timed_out,
            failure_class=failure_class,
        )
        proof_class_effect = None
        if (
            step == "environment-check"
            and result.returncode != 0
            and proof_class != "competition-exact"
            and not timed_out
            and failure_class != "required_c_compiler_missing"
        ):
            proof_class_effect = "exactness_blocker"
        steps.append(
            {
                "step": step,
                "status": step_status_value,
                "returncode": result.returncode,
                "log_path": summary_log_path(logs_dir / "commands.jsonl", repo_root=repo_root, out_root=out_root),
                **(
                    {
                        "timed_out": True,
                        "timeout_seconds": timeout_seconds,
                    }
                    if timed_out
                    else {}
                ),
                **({"failure_class": failure_class} if failure_class else {}),
                **({"proof_class_effect": proof_class_effect} if proof_class_effect else {}),
            }
        )

    clang_source_value = clang_source(repo_root)
    clang_lane_verified_value = (
        clang_source_value != "missing"
        and step_status(steps, "environment-check") == "passed"
        and step_status(steps, "vendored-clang-verification") == "passed"
    )
    final_gate_reasons = final_gate_reasons_for(
        proof_class=proof_class,
        steps=steps,
        deviations=deviations,
        environment=environment,
    )
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
        "timeout_policy": {
            "per_step_timeout_seconds": timeout_seconds,
            "timeout_exit_code": 124,
            "timeout_is_final_gate_failure": True,
        },
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
            "sha256": sha256_lf_stable(command_log_path),
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
    slice_spec_arg = repo_relative_path(slice_spec, repo_root, "slice_spec")
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
                slice_spec_arg,
                "--require-semantic-pass",
            ],
        ),
        (
            "evidence-governance",
            [
                sys.executable,
                rel_path(EVIDENCE_GOVERNANCE, repo_root),
                "--policy-tier",
                "ci",
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


def smoke_step_status(
    step: str,
    returncode: int,
    *,
    proof_class: str,
    timed_out: bool = False,
    failure_class: str | None = None,
) -> str:
    if timed_out:
        return "failed"
    if returncode == 0:
        return "passed"
    if failure_class == "required_c_compiler_missing":
        return "failed"
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
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    timed_out = False
    try:
        result = command_runner(
            command,
            cwd=repo_root,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        timed_out = True
        result = subprocess.CompletedProcess(
            command,
            124,
            timeout_output_text(error.output),
            timeout_output_text(error.stderr) or f"timed out after {timeout_seconds} seconds",
        )
        setattr(result, "timed_out", True)
    failure_class = smoke_step_failure_class(step, result)
    if failure_class:
        setattr(result, "failure_class", failure_class)
    entry = {
        "step": step,
        "command": command_for_log(command, repo_root=repo_root, out_root=out_root),
        "returncode": result.returncode,
        "stdout": output_text_for_log(result.stdout),
        "stderr": output_text_for_log(result.stderr),
        "log_path": summary_log_path(logs_dir / "commands.jsonl", repo_root=repo_root, out_root=out_root),
        **({"timed_out": True, "timeout_seconds": timeout_seconds} if timed_out else {}),
        **({"failure_class": failure_class} if failure_class else {}),
    }
    with (logs_dir / "commands.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
    return result


def smoke_step_failure_class(step: str, result: subprocess.CompletedProcess[str]) -> str | None:
    if step != "environment-check" or result.returncode == 0:
        return None
    output = f"{result.stdout}\n{result.stderr}".lower()
    if any(pattern in output for pattern in REQUIRED_TOOL_MISSING_PATTERNS):
        return "required_c_compiler_missing"
    return None


def timeout_output_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


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
        "competition_exact_host_attested": bool(os.environ.get("COMPETITION_EXACT_HOST")),
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
    environment: dict[str, Any],
) -> list[str]:
    reasons = [f"step_failed:{step['step']}" for step in steps if step["status"] == "failed"]
    reasons.extend(
        f"{step['failure_class']}:{step['step']}"
        for step in steps
        if step.get("status") == "failed" and step.get("failure_class")
    )
    if proof_class == "ci-approximation" and not environment.get("detected_ci"):
        reasons.append("proof_class_incompatible_with_environment")
    if proof_class == "wsl-local-simulation" and not environment.get("detected_wsl"):
        reasons.append("proof_class_incompatible_with_environment")
    if proof_class == "competition-exact" and not environment.get("competition_exact_host_attested"):
        reasons.append("proof_class_requires_exact_host_evidence")
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


def repo_relative_path(path: Path, repo_root: Path, field_name: str) -> str:
    resolved = path if path.is_absolute() else repo_root / path
    try:
        return resolved.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as error:
        raise ValueError(f"{field_name} must be repo-relative") from error


def command_for_log(command: list[str], *, repo_root: Path, out_root: Path) -> list[str]:
    return [command_argument_for_log(argument, repo_root=repo_root, out_root=out_root) for argument in command]


def command_argument_for_log(argument: str, *, repo_root: Path, out_root: Path) -> str:
    if not argument or not any(separator in argument for separator in ["/", "\\"]):
        return argument
    sanitized_argument = sanitize_host_paths_in_command_text(argument)
    if any(token in argument for token in [";", "|", "&&"]):
        return sanitized_argument
    path = Path(argument)
    resolved = path if path.is_absolute() else repo_root / path
    for root in [repo_root.resolve(), out_root.resolve()]:
        try:
            return resolved.resolve().relative_to(root).as_posix()
        except ValueError:
            continue
    return path_basename(argument)


def sanitize_host_paths_in_command_text(argument: str) -> str:
    def replace_match(match: re.Match[str]) -> str:
        if match.group("double_quoted_path") is not None:
            return f'"{path_basename(match.group("double_quoted_path"))}"'
        if match.group("single_quoted_path") is not None:
            return f"'{path_basename(match.group('single_quoted_path'))}'"
        return path_basename(match.group("plain_path"))

    return LOCAL_HOST_PATH_IN_COMMAND.sub(replace_match, argument)


def output_text_for_log(value: str) -> str:
    return sanitize_host_paths_in_command_text(value)


def path_basename(path_text: str) -> str:
    name = Path(path_text).name
    if name:
        return name
    normalized = path_text.replace("\\", "/").rstrip("/")
    return normalized.rsplit("/", 1)[-1] if normalized else path_text


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_lf_stable(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
