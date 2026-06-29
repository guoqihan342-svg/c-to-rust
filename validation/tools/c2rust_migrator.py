#!/usr/bin/env python3
"""OpenCode-facing request wrapper for the competition runner."""

from __future__ import annotations

import argparse
import json
from pathlib import PurePosixPath
import subprocess
import sys
from typing import Any


RUN_COMPETITION = "validation/tools/run_competition.py"
DIRECT_REQUIRED_FIELDS = [
    "source_repo_root",
    "source_file",
    "function",
    "target_id",
    "slice_id",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True, choices=["migrate", "verify", "audit"])
    parser.add_argument("--change", default="design-c2rust-migration-agent")
    parser.add_argument("--input", required=True)
    args = parser.parse_args()

    request = load_request(args.input)
    argv = build_run_competition_argv(request)
    completed = subprocess.run(argv, check=False)
    return completed.returncode


def load_request(path: str | PurePosixPath) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        request = json.load(handle)
    if not isinstance(request, dict):
        raise SystemExit("request input must be a JSON object")
    return request


def build_run_competition_argv(request: dict[str, Any]) -> list[str]:
    argv = ["python", RUN_COMPETITION]
    worker_summaries = request.get("worker_summaries") or []
    if worker_summaries:
        for summary in expect_string_list(worker_summaries, "worker_summaries"):
            argv.extend(["--worker-summary", checked_posix_path(summary)])
    else:
        missing = [field for field in DIRECT_REQUIRED_FIELDS if not request.get(field)]
        if missing:
            raise SystemExit(f"missing required request fields: {', '.join(missing)}")
        argv.extend(
            [
                "--source-repo-root",
                checked_posix_path(str(request["source_repo_root"])),
                "--source-file",
                checked_posix_path(str(request["source_file"])),
                "--function",
                str(request["function"]),
                "--target-id",
                str(request["target_id"]),
                "--slice-id",
                str(request["slice_id"]),
            ]
        )
        if request.get("source_commit"):
            argv.extend(["--source-commit", str(request["source_commit"])])
        if request.get("compiler_command_source"):
            argv.extend(["--compiler-command-source", checked_posix_path(str(request["compiler_command_source"]))])
        for include_path in expect_string_list(request.get("include_paths") or [], "include_paths"):
            argv.extend(["--include-path", checked_posix_path(include_path)])
        for define in expect_string_list(request.get("defines") or [], "defines"):
            argv.extend(["--define", define])

    out_root = checked_posix_path(str(request.get("out_root", "target/competition-out")))
    proof_class = str(request.get("proof_class", "local-simulation"))
    argv.extend(["--out-root", out_root, "--proof-class", proof_class])
    if request.get("run_id"):
        argv.extend(["--run-id", str(request["run_id"])])
    return argv


def expect_string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SystemExit(f"{field} must be a list of strings")
    return value


def checked_posix_path(value: str) -> str:
    if not value or "\\" in value:
        raise SystemExit(f"path must be a non-empty POSIX relative path: {value}")
    if value.startswith("/") or value.startswith("~"):
        raise SystemExit(f"path must be relative: {value}")
    if len(value) >= 2 and value[1] == ":":
        raise SystemExit(f"path must not contain a drive prefix: {value}")
    if ".." in PurePosixPath(value).parts:
        raise SystemExit(f"path must not escape repository: {value}")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
