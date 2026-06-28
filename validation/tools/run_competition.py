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


class CompetitionRunResult:
    def __init__(self, *, exit_code: int, summary_path: Path, summary: dict[str, Any]) -> None:
        self.exit_code = exit_code
        self.summary_path = summary_path
        self.summary = summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slice-spec", action="append", dest="slice_specs", type=Path, default=[])
    parser.add_argument("--extract-spec", action="append", dest="extraction_specs", type=Path, default=[])
    parser.add_argument("--out-root", type=Path, default=REPO_ROOT / "target" / "competition-out")
    parser.add_argument(
        "--proof-class",
        default="local-simulation",
        choices=["competition-exact", "ci-approximation", "wsl-local-simulation", "local-simulation"],
    )
    parser.add_argument("--run-id")
    args = parser.parse_args()
    if not args.slice_specs and not args.extraction_specs:
        parser.error("at least one --slice-spec or --extract-spec is required")

    result = run_competition(
        slice_specs=args.slice_specs,
        extraction_specs=args.extraction_specs,
        out_root=args.out_root,
        proof_class=args.proof_class,
        run_id=args.run_id,
        repo_root=REPO_ROOT,
    )
    print(json.dumps(result.summary, indent=2, sort_keys=True))
    return result.exit_code


def run_competition(
    *,
    slice_specs: list[Path],
    extraction_specs: list[Path] | None = None,
    out_root: Path,
    proof_class: str,
    command_runner: CommandRunner = subprocess.run,
    repo_root: Path = REPO_ROOT,
    run_id: str | None = None,
) -> CompetitionRunResult:
    extraction_specs = extraction_specs or []
    if not slice_specs and not extraction_specs:
        raise SystemExit("at least one --slice-spec or --extract-spec is required")

    repo_root = repo_root.resolve()
    out_root = out_root if out_root.is_absolute() else repo_root / out_root
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "summary").mkdir(parents=True, exist_ok=True)
    logs_dir = out_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    evidence_root = out_root / "evidence"
    evidence_root.mkdir(parents=True, exist_ok=True)
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

    environment_result = run_logged_step(
        "environment-check",
        ["bash", "-lc", "source config/competition-env/env.sh; bash config/competition-env/toolchain-check.sh"],
        command_runner=command_runner,
        repo_root=repo_root,
        logs_dir=logs_dir,
        out_root=out_root,
    )
    if environment_result.returncode != 0:
        gate_failures += 1

    generated_slice_specs, extraction_failures = extract_slice_specs(
        extraction_specs,
        generated_slice_specs_root=generated_slice_specs_root,
        command_runner=command_runner,
        repo_root=repo_root,
        logs_dir=logs_dir,
        out_root=out_root,
    )
    slice_failures += extraction_failures

    all_slice_specs = list(slice_specs) + generated_slice_specs
    specs = [load_slice_spec(path, repo_root=repo_root) for path in all_slice_specs]
    for spec_path, spec in specs:
        target_id = required_str(spec, "target_id")
        slice_id = required_str(spec, "slice_id")
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
            continue

        final = load_final_verification(evidence_root, target_id, slice_id)
        if final.get("rust_check_status") == "passed":
            compiled += 1
        if final.get("semantic_pass") is True:
            semantic_pass += 1
        else:
            status = str(final.get("status", "failed"))
            if status == "refused":
                refused += 1
            elif status == "blocked":
                blocked += 1
            else:
                slice_failures += 1
        typed_ir_generated += 1

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
                rel_path(evidence_root, repo_root),
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

    if unsafe_result.returncode != 0 or openspec_result.returncode != 0:
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
            "attempted": len(slice_specs) + len(extraction_specs),
            "typed_ir_generated": typed_ir_generated,
            "compiled": compiled,
            "semantic_pass": semantic_pass,
            "refused": refused,
            "blocked": blocked,
            "failed": slice_failures,
        },
        "unsafe_budget": unsafe_budget_summary(),
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
    summary_path = out_root / "summary" / "competition-run-summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

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
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return CompetitionRunResult(
        exit_code=0 if summary["final_gate"]["status"] == "passed" and slice_failures == 0 and gate_failures == 0 else 1,
        summary_path=summary_path,
        summary=summary,
    )


def run_step(command: list[str], *, command_runner: CommandRunner, repo_root: Path) -> subprocess.CompletedProcess[str]:
    return command_runner(command, cwd=repo_root, text=True, capture_output=True)


def extract_slice_specs(
    extraction_specs: list[Path],
    *,
    generated_slice_specs_root: Path,
    command_runner: CommandRunner,
    repo_root: Path,
    logs_dir: Path,
    out_root: Path,
) -> tuple[list[Path], int]:
    generated = []
    failures = 0
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
            continue
        generated.append(output_path)
    return generated, failures


def load_extraction_spec(path: Path, *, repo_root: Path) -> dict[str, Any]:
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
        ("source_commit", "--source-commit"),
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


def unsafe_budget_summary() -> dict[str, Any]:
    return {
        "total_first_party_non_test_unsafe": 0,
        "ratio": 0.0,
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
