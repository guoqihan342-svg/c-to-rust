#!/usr/bin/env python3
"""Validate the OpenCode competition run summary contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
from typing import Any

import jsonschema


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "validation" / "competition-run-summary.schema.json"
REQUIRED_ARTIFACT_ROOTS = {
    "target/competition-out/evidence",
    "target/competition-out/summary",
    "target/competition-out/logs",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--summary",
        type=Path,
        default=REPO_ROOT / "target" / "competition-out" / "summary" / "competition-run-summary.json",
    )
    args = parser.parse_args()

    result = validate_summary(args.summary, repo_root=REPO_ROOT)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_summary(summary_path: Path, *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    summary = load_json(summary_path)
    schema = load_json(SCHEMA_PATH)
    try:
        jsonschema.validate(summary, schema)
    except jsonschema.ValidationError as error:
        path = ".".join(str(part) for part in error.absolute_path) or "<root>"
        raise SystemExit(f"competition run summary schema error at {path}: {error.message}") from error

    validate_artifact_roots(summary.get("artifact_roots", []), repo_root=repo_root)
    validate_final_gate(summary)
    validate_slice_counts(summary)
    validate_workers(summary)

    return {
        "status": "passed",
        "summary": repo_relative(summary_path, repo_root),
        "proof_class": summary["proof_class"],
        "profile_id": summary["profile_id"],
        "semantic_pass": summary["slices"]["semantic_pass"],
        "final_gate": summary["final_gate"]["status"],
    }


def validate_artifact_roots(artifact_roots: list[str], *, repo_root: Path) -> None:
    roots = set(artifact_roots)
    missing = sorted(REQUIRED_ARTIFACT_ROOTS - roots)
    if missing:
        raise SystemExit(f"competition run summary artifact_roots missing required roots: {', '.join(missing)}")

    for root in artifact_roots:
        if not is_repo_relative_posix_path(root):
            raise SystemExit(f"competition run summary artifact_roots must be repo-relative POSIX paths: {root}")
        resolved = (repo_root / root).resolve()
        try:
            resolved.relative_to(repo_root.resolve())
        except ValueError as error:
            raise SystemExit(f"competition run summary artifact_roots escapes repository: {root}") from error


def is_repo_relative_posix_path(value: str) -> bool:
    if not value or "\\" in value:
        return False
    if value.startswith("/") or value.startswith("~"):
        return False
    if len(value) >= 2 and value[1] == ":":
        return False
    parts = PurePosixPath(value).parts
    return ".." not in parts


def validate_final_gate(summary: dict[str, Any]) -> None:
    status = summary["final_gate"]["status"]
    semantic_pass = int(summary["slices"]["semantic_pass"])
    if status == "passed" and semantic_pass < 1:
        raise SystemExit("competition run summary final_gate passed requires slices.semantic_pass >= 1")
    validator = summary["final_gate"]["validator"]
    if status == "passed" and "--require-semantic-pass" not in validator:
        raise SystemExit("competition run summary final_gate passed requires --require-semantic-pass validator")


def validate_slice_counts(summary: dict[str, Any]) -> None:
    slices = summary["slices"]
    attempted = int(slices["attempted"])
    terminal = int(slices["semantic_pass"]) + int(slices["refused"]) + int(slices["blocked"]) + int(slices["failed"])
    if terminal > attempted:
        raise SystemExit("competition run summary terminal slice counts exceed slices.attempted")
    if int(slices["compiled"]) > int(slices["typed_ir_generated"]):
        raise SystemExit("competition run summary slices.compiled exceeds slices.typed_ir_generated")
    if int(slices["typed_ir_generated"]) > attempted:
        raise SystemExit("competition run summary slices.typed_ir_generated exceeds slices.attempted")


def validate_workers(summary: dict[str, Any]) -> None:
    workers = summary.get("workers")
    if workers is None:
        return
    summaries = workers["summaries"]
    if int(workers["count"]) != len(summaries):
        raise SystemExit("competition run summary workers.count does not match workers.summaries length")
    for index, worker in enumerate(summaries):
        slices = worker["slices"]
        for key in ["attempted", "semantic_pass", "failed"]:
            if int(worker[key]) != int(slices[key]):
                raise SystemExit(f"competition run summary workers.summaries[{index}].{key} does not match slices.{key}")
        if worker["status"] != "passed" and summary["final_gate"]["status"] == "passed":
            raise SystemExit("competition run summary final_gate passed with failed worker summary")


def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
