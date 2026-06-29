#!/usr/bin/env python3
"""Thin repo-local C2Rust verifier MCP scaffold.

This module intentionally registers a small tool contract and delegates to
existing validation helpers. It is not a full verifier runtime.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import sys
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from validation.tools import c2rust_migrator
from validation.tools import translator_coverage_matrix


CLAIM_BOUNDARY = (
    "C2Rust verifier MCP scaffold: repo-confined planning and evidence reads only; "
    "not a full verifier/runtime completion and not semantic acceptance evidence."
)


def tool_metadata() -> list[dict[str, Any]]:
    return [
        {
            "name": "translate_slice",
            "description": (
                "repo-confined command planner for a C2Rust migration slice; "
                "returns the existing run_competition argv without executing it."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "slice_spec": {"type": "string"},
                    "slice_specs": {"type": "array", "items": {"type": "string"}},
                    "out_root": {"type": "string"},
                    "reuse_accepted_evidence": {"type": "boolean"},
                    "accepted_evidence_root": {"type": "string"},
                },
            },
        },
        {
            "name": "run_oracle",
            "description": (
                "repo-confined verifier/oracle command planner; returns argv for "
                "existing validation scripts without executing it."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "slice_spec": {"type": "string"},
                    "slice_specs": {"type": "array", "items": {"type": "string"}},
                    "out_root": {"type": "string"},
                    "proof_class": {"type": "string"},
                },
            },
        },
        {
            "name": "read_evidence",
            "description": "repo-confined JSON evidence reader for existing validation artifacts.",
            "input_schema": {
                "type": "object",
                "required": ["path"],
                "properties": {"path": {"type": "string"}},
            },
        },
        {
            "name": "coverage_matrix",
            "description": "repo-confined wrapper around the existing translator coverage matrix report.",
            "input_schema": {
                "type": "object",
                "properties": {"matrix": {"type": "string"}},
            },
        },
    ]


def translate_slice(request: dict[str, Any], *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    normalized = _confine_request_paths(request, repo_root=repo_root)
    argv = c2rust_migrator.build_run_competition_argv(normalized)
    return {
        "schema_version": 1,
        "status": "planned",
        "tool": "translate_slice",
        "executed": False,
        "argv": argv,
        "claim_boundary": CLAIM_BOUNDARY,
    }


def run_oracle(request: dict[str, Any], *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    normalized = _confine_request_paths(request, repo_root=repo_root)
    normalized.setdefault("proof_class", "local-simulation")
    argv = c2rust_migrator.build_run_competition_argv(normalized)
    return {
        "schema_version": 1,
        "status": "planned",
        "tool": "run_oracle",
        "phase": "verify",
        "executed": False,
        "argv": argv,
        "claim_boundary": CLAIM_BOUNDARY,
    }


def read_evidence(request: dict[str, Any], *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    path_text = _require_string(request, "path")
    path = _repo_path(path_text, repo_root=repo_root)
    if not path.exists() or not path.is_file():
        raise SystemExit(f"evidence file not found: {path_text}")
    return {
        "schema_version": 1,
        "status": "recorded",
        "path": _rel(repo_root, path),
        "payload": json.loads(path.read_text(encoding="utf-8-sig")),
        "claim_boundary": CLAIM_BOUNDARY,
    }


def coverage_matrix(request: dict[str, Any], *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    matrix_path = None
    if request.get("matrix"):
        matrix_path = _repo_path(_require_string(request, "matrix"), repo_root=repo_root)
    report = translator_coverage_matrix.build_report(repo_root, matrix_path=matrix_path)
    report["claim_boundary"] = f"{report['claim_boundary']}; {CLAIM_BOUNDARY}"
    return report


def handle_call(name: str, arguments: dict[str, Any], *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
        "translate_slice": lambda args: translate_slice(args, repo_root=repo_root),
        "run_oracle": lambda args: run_oracle(args, repo_root=repo_root),
        "read_evidence": lambda args: read_evidence(args, repo_root=repo_root),
        "coverage_matrix": lambda args: coverage_matrix(args, repo_root=repo_root),
    }
    if name not in handlers:
        raise SystemExit(f"unknown tool: {name}")
    if not isinstance(arguments, dict):
        raise SystemExit("tool arguments must be a JSON object")
    return handlers[name](arguments)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-tools", action="store_true")
    parser.add_argument("--call", choices=[tool["name"] for tool in tool_metadata()])
    parser.add_argument("--arguments", default="{}")
    args = parser.parse_args(argv)

    if args.list_tools:
        print(json.dumps({"tools": tool_metadata(), "claim_boundary": CLAIM_BOUNDARY}, indent=2))
        return 0
    if args.call:
        arguments = json.loads(args.arguments)
        print(json.dumps(handle_call(args.call, arguments), indent=2, sort_keys=True))
        return 0
    parser.print_help()
    return 0


def _confine_request_paths(request: dict[str, Any], *, repo_root: Path) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise SystemExit("request must be a JSON object")
    normalized = dict(request)
    for key in (
        "source_repo_root",
        "source_file",
        "compiler_command_source",
        "out_root",
        "accepted_evidence_root",
        "slice_spec",
    ):
        if key in normalized and normalized[key] is not None:
            normalized[key] = _repo_relative(_require_string(normalized, key), repo_root=repo_root)
    for key in ("slice_specs", "worker_summaries", "include_paths"):
        if key in normalized and normalized[key] is not None:
            values = normalized[key]
            if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
                raise SystemExit(f"{key} must be a list of strings")
            normalized[key] = [_repo_relative(item, repo_root=repo_root) for item in values]
    return normalized


def _repo_path(path_text: str, *, repo_root: Path) -> Path:
    relative = _repo_relative(path_text, repo_root=repo_root)
    root = repo_root.resolve()
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise SystemExit(f"path must not escape repository: {path_text}") from exc
    return path


def _repo_relative(path_text: str, *, repo_root: Path) -> str:
    if not path_text or "\\" in path_text:
        raise SystemExit(f"path must be a non-empty POSIX relative path: {path_text}")
    if path_text.startswith("/") or path_text.startswith("~"):
        raise SystemExit(f"path must be relative: {path_text}")
    if len(path_text) >= 2 and path_text[1] == ":":
        raise SystemExit(f"path must not contain a drive prefix: {path_text}")
    if ".." in PurePosixPath(path_text).parts:
        raise SystemExit(f"path must not escape repository: {path_text}")
    path = _repo_path_without_recursing(path_text, repo_root=repo_root)
    return _rel(repo_root, path)


def _repo_path_without_recursing(path_text: str, *, repo_root: Path) -> Path:
    root = repo_root.resolve()
    path = (root / path_text).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise SystemExit(f"path must not escape repository: {path_text}") from exc
    return path


def _require_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise SystemExit(f"{key} must be a non-empty string")
    return value


def _rel(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    sys.exit(main())
