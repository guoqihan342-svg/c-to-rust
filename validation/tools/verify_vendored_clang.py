#!/usr/bin/env python3
"""Verify project-local clang availability for the competition clang lane."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
PROOF_CLASSES = ["competition-exact", "ci-approximation", "wsl-local-simulation", "local-simulation"]
VENDORED_CLANG_CANDIDATES = [
    Path("tools/llvm/bin/clang-18"),
    Path("tools/llvm/bin/clang"),
    Path("tools/clang/bin/clang"),
    Path("tools/llvm/bin/clang.exe"),
    Path("tools/clang/bin/clang.exe"),
]
MINIMUM_TU = """#include <stdint.h>
#include <stddef.h>
int c2r_clang_smoke(uint32_t value) {
  return (int)(value + sizeof(size_t));
}
"""


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


class InvalidClangPath(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ResolvedClang:
    def __init__(self, *, executable: Path, command: str, display_path: str, source: str) -> None:
        self.executable = executable
        self.command = command
        self.display_path = display_path
        self.source = source


class VendoredClangResult:
    def __init__(self, *, exit_code: int, summary_path: Path, summary: dict[str, Any]) -> None:
        self.exit_code = exit_code
        self.summary_path = summary_path
        self.summary = summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "target" / "competition-smoke" / "summary" / "vendored-clang-verification.json",
    )
    parser.add_argument("--proof-class", choices=PROOF_CLASSES, default="local-simulation")
    parser.add_argument("--require-clang", action="store_true")
    args = parser.parse_args()

    result = verify_vendored_clang(
        repo_root=REPO_ROOT,
        out=args.out,
        proof_class=args.proof_class,
        require_clang=args.require_clang,
    )
    print(json.dumps(result.summary, indent=2, sort_keys=True))
    return result.exit_code


def verify_vendored_clang(
    *,
    repo_root: Path,
    out: Path,
    proof_class: str,
    require_clang: bool = False,
    environment: dict[str, str] | None = None,
    command_runner: CommandRunner = subprocess.run,
) -> VendoredClangResult:
    repo_root = repo_root.resolve()
    out = out if out.is_absolute() else repo_root / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out_root = out.parent.parent if out.parent.name == "summary" else out.parent
    logs_dir = out_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ if environment is None else environment)
    profile = load_profile(repo_root)
    started = time.monotonic()
    clang_required = require_clang or proof_class == "competition-exact"

    try:
        resolved = resolve_clang(repo_root=repo_root, environment=environment)
    except InvalidClangPath as error:
        summary = base_summary(
            repo_root=repo_root,
            out_root=out_root,
            profile=profile,
            proof_class=proof_class,
            started=started,
        )
        summary.update(
            {
                "status": "failed",
                "reason": error.reason,
                "clang": {"source": "CLANG_PATH", "path": None, "version": None},
                "clang_required": clang_required,
                "clang_lane_verified": False,
                "checks": {},
                "command_logs": [],
                "final_gate": {
                    "status": "failed",
                    "reasons": [error.reason],
                },
            }
        )
        write_summary(out, summary)
        return VendoredClangResult(exit_code=1, summary_path=out, summary=summary)
    if resolved is None:
        final_status = "failed" if clang_required else "passed"
        summary = base_summary(
            repo_root=repo_root,
            out_root=out_root,
            profile=profile,
            proof_class=proof_class,
            started=started,
        )
        summary.update(
            {
                "status": "missing",
                "reason": "missing_clang_path",
                "clang": {"source": "missing", "path": None, "version": None},
                "clang_required": clang_required,
                "clang_lane_verified": False,
                "checks": {},
                "command_logs": [],
                "final_gate": {
                    "status": final_status,
                    **({"reasons": ["missing_clang_path"]} if clang_required else {}),
                },
            }
        )
        write_summary(out, summary)
        return VendoredClangResult(exit_code=1 if clang_required else 0, summary_path=out, summary=summary)

    command_logs: list[dict[str, Any]] = []
    minimum_tu_path = out.parent / "vendored-clang-minimum-tu.c"
    minimum_tu_path.write_text(MINIMUM_TU, encoding="utf-8")

    version_result = run_logged_step(
        "clang-version",
        [resolved.command, "--version"],
        command_runner=command_runner,
        repo_root=repo_root,
        out_root=out_root,
        logs_dir=logs_dir,
        command_logs=command_logs,
    )
    resource_result = run_logged_step(
        "resource-dir",
        [resolved.command, "-print-resource-dir"],
        command_runner=command_runner,
        repo_root=repo_root,
        out_root=out_root,
        logs_dir=logs_dir,
        command_logs=command_logs,
    )
    include_result = run_logged_step(
        "include-search-paths",
        [resolved.command, "-E", "-v", str(minimum_tu_path)],
        command_runner=command_runner,
        repo_root=repo_root,
        out_root=out_root,
        logs_dir=logs_dir,
        command_logs=command_logs,
    )
    ast_result = run_logged_step(
        "minimum-tu-ast-dump",
        [resolved.command, "-fsyntax-only", "-Xclang", "-ast-dump=json", str(minimum_tu_path)],
        command_runner=command_runner,
        repo_root=repo_root,
        out_root=out_root,
        logs_dir=logs_dir,
        command_logs=command_logs,
    )

    version = first_line(version_result.stdout)
    resource_dir = resource_result.stdout.strip()
    include_paths = parse_include_search_paths(include_result.stdout + "\n" + include_result.stderr)
    ast_output_path = out.parent / "vendored-clang-minimum-tu-ast.json"
    ast_output_path.write_text(ast_result.stdout, encoding="utf-8")
    contains_translation_unit = "TranslationUnitDecl" in ast_result.stdout
    checks = {
        "binary_exists": {
            "status": "passed" if resolved.executable.exists() else "failed",
            "path": resolved.display_path,
        },
        "resource_dir": {
            "status": "passed" if resource_result.returncode == 0 and bool(resource_dir) else "failed",
            "resource_dir": resource_dir,
        },
        "include_search_paths": {
            "status": "passed" if include_result.returncode == 0 and bool(include_paths) else "failed",
            "paths": include_paths,
        },
        "minimum_tu_ast_dump": {
            "status": "passed" if ast_result.returncode == 0 and contains_translation_unit else "failed",
            "minimum_tu_path": summary_path(minimum_tu_path, repo_root=repo_root, out_root=out_root),
            "ast_dump_path": summary_path(ast_output_path, repo_root=repo_root, out_root=out_root),
            "contains_translation_unit": contains_translation_unit,
        },
    }
    failure_reasons = [
        f"check_failed:{name}" for name, check in checks.items() if check["status"] != "passed"
    ]
    if version_result.returncode != 0:
        failure_reasons.append("check_failed:clang-version")
    status = "passed" if not failure_reasons else "failed"

    summary = base_summary(
        repo_root=repo_root,
        out_root=out_root,
        profile=profile,
        proof_class=proof_class,
        started=started,
    )
    summary.update(
        {
            "status": status,
            **({"reason": ";".join(failure_reasons)} if failure_reasons else {}),
            "clang": {
                "source": resolved.source,
                "path": resolved.display_path,
                "version": version,
            },
            "clang_required": clang_required,
            "clang_lane_verified": status == "passed",
            "minimum_tu": {
                "path": summary_path(minimum_tu_path, repo_root=repo_root, out_root=out_root),
                "required_headers": ["stdint.h", "stddef.h"],
            },
            "checks": checks,
            "command_logs": command_logs,
            "final_gate": {
                "status": status,
                **({"reasons": failure_reasons} if failure_reasons else {}),
            },
        }
    )
    write_summary(out, summary)
    return VendoredClangResult(exit_code=0 if status == "passed" else 1, summary_path=out, summary=summary)


def resolve_clang(*, repo_root: Path, environment: dict[str, str]) -> ResolvedClang | None:
    repo_root = repo_root.resolve()
    configured = environment.get("CLANG_PATH")
    if configured:
        configured_path = Path(configured)
        has_path_separator = any(separator in configured for separator in ["/", "\\"])
        if configured_path.is_absolute() or has_path_separator:
            executable = configured_path if configured_path.is_absolute() else repo_root / configured_path
            executable = executable.resolve()
            if not is_within_repo(executable, repo_root=repo_root):
                raise InvalidClangPath("invalid_clang_path_outside_repo")
            if executable.exists():
                return ResolvedClang(
                    executable=executable,
                    command=str(executable),
                    display_path=display_clang_path(executable, repo_root=repo_root),
                    source="CLANG_PATH",
                )
        else:
            resolved_command = shutil.which(configured, path=environment.get("PATH"))
            executable = Path(resolved_command).resolve() if resolved_command else repo_root / configured
            if executable.exists():
                display_path = (
                    display_clang_path(executable, repo_root=repo_root)
                    if is_within_repo(executable, repo_root=repo_root)
                    else configured
                )
                return ResolvedClang(
                    executable=executable,
                    command=configured,
                    display_path=display_path,
                    source="CLANG_PATH",
                )
    for candidate in VENDORED_CLANG_CANDIDATES:
        path = repo_root / candidate
        if path.exists():
            resolved_path = path.resolve()
            return ResolvedClang(
                executable=resolved_path,
                command=str(resolved_path),
                display_path=candidate.as_posix(),
                source=f"vendored:{candidate.as_posix()}",
            )
    return None


def run_logged_step(
    step: str,
    command: list[str],
    *,
    command_runner: CommandRunner,
    repo_root: Path,
    out_root: Path,
    logs_dir: Path,
    command_logs: list[dict[str, Any]],
) -> subprocess.CompletedProcess[str]:
    result = command_runner(
        command,
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    log_path = logs_dir / "vendored-clang-commands.jsonl"
    entry = {
        "step": step,
        "command": command_for_log(command, repo_root=repo_root, out_root=out_root),
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
    command_logs.append(
        {
            "step": step,
            "status": "passed" if result.returncode == 0 else "failed",
            "returncode": result.returncode,
            "log_path": summary_path(log_path, repo_root=repo_root, out_root=out_root),
        }
    )
    return result


def parse_include_search_paths(output: str) -> list[str]:
    paths: list[str] = []
    in_search_list = False
    for line in output.splitlines():
        stripped = line.strip()
        if stripped == "#include <...> search starts here:":
            in_search_list = True
            continue
        if in_search_list and stripped == "End of search list.":
            break
        if in_search_list and stripped:
            paths.append(stripped)
    return paths


def base_summary(
    *,
    repo_root: Path,
    out_root: Path,
    profile: dict[str, Any],
    proof_class: str,
    started: float,
) -> dict[str, Any]:
    profile_path_value = profile_path(repo_root)
    return {
        "schema_version": 1,
        "artifact_kind": "vendored-clang-verification",
        "proof_class": proof_class,
        "profile_id": str(profile.get("profile_id", "unknown")),
        "profile_path": summary_path(profile_path_value, repo_root=repo_root, out_root=out_root),
        "profile_sha256": sha256(profile_path_value),
        "elapsed_seconds": int(time.monotonic() - started),
        "validator": "validation/tools/verify_vendored_clang.py",
    }


def load_profile(repo_root: Path) -> dict[str, Any]:
    return json.loads(profile_path(repo_root).read_text(encoding="utf-8"))


def profile_path(repo_root: Path) -> Path:
    return repo_root / "config" / "competition-env" / "environment.json"


def first_line(value: str) -> str | None:
    lines = value.splitlines()
    return lines[0].strip() if lines else None


def display_clang_path(path: Path, *, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(repo_root.resolve()).as_posix()
    except ValueError as error:
        raise InvalidClangPath("invalid_clang_path_outside_repo") from error


def is_within_repo(path: Path, *, repo_root: Path) -> bool:
    try:
        path.resolve().relative_to(repo_root.resolve())
        return True
    except ValueError:
        return False


def command_for_log(command: list[str], *, repo_root: Path, out_root: Path) -> list[str]:
    return [command_argument_for_log(argument, repo_root=repo_root, out_root=out_root) for argument in command]


def command_argument_for_log(argument: str, *, repo_root: Path, out_root: Path) -> str:
    if not argument or not any(separator in argument for separator in ["/", "\\"]):
        return argument
    path = Path(argument)
    resolved = path if path.is_absolute() else repo_root / path
    return summary_path(resolved, repo_root=repo_root, out_root=out_root)


def summary_path(path: Path, *, repo_root: Path, out_root: Path) -> str:
    resolved = path.resolve()
    for root in [repo_root.resolve(), out_root.resolve()]:
        try:
            return resolved.relative_to(root).as_posix()
        except ValueError:
            continue
    return resolved.as_posix()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_summary(out: Path, summary: dict[str, Any]) -> None:
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
