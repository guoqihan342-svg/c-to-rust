#!/usr/bin/env python3
"""Run a FlashDB fixture negative diff by mutating expected behavior."""

from __future__ import annotations

import argparse
import json
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
BEHAVIOR_FIELDS = ("value", "code", "status", "count", "ts_status", "entries")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected", required=True, type=Path)
    parser.add_argument("--actual", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--mutated-expected", type=Path)
    parser.add_argument("--diff-report", type=Path)
    args = parser.parse_args()

    mutated_path = args.mutated_expected or args.report.with_name(args.report.stem + "-mutated-expected.json")
    diff_report = args.diff_report or args.report.with_name(args.report.stem + "-diff.json")
    expected = load_json(args.expected)
    mutated, mutation = mutate_expected_report(expected)
    write_json(mutated_path, mutated)

    command = [
        "cargo",
        "run",
        "--manifest-path",
        str(REPO_ROOT / "flashDB_rust" / "Cargo.toml"),
        "--",
        "diff-report",
        "--expected",
        str(mutated_path),
        "--actual",
        str(args.actual),
        "--report",
        str(diff_report),
    ]
    result = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True)
    diff_payload = load_json(diff_report) if diff_report.exists() else {}
    summary = validate_negative_diff_result(result.returncode, diff_payload)
    summary.update(
        {
            "schema_version": 1,
            "command": command,
            "mutation": mutation,
            "expected": rel(args.expected),
            "actual": rel(args.actual),
            "mutated_expected": rel(mutated_path),
            "diff_report": rel(diff_report),
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    )
    write_json(args.report, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def mutate_expected_report(report: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    mutated = deepcopy(report)
    steps = mutated.get("steps")
    if not isinstance(steps, list):
        raise SystemExit("expected report must contain a steps array")
    for step_index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        for field in BEHAVIOR_FIELDS:
            if field in step:
                original = step[field]
                step[field] = mutated_value(original)
                return mutated, {
                    "step_index": step_index,
                    "step_id": step.get("id", f"step-{step_index}"),
                    "field": field,
                    "original": original,
                    "mutated": step[field],
                }
    raise SystemExit("expected report has no mutable behavior field")


def mutated_value(value: Any) -> Any:
    if value is None:
        return "__negative_control__"
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, str):
        return value + "__negative_control"
    if isinstance(value, list):
        changed = list(reversed(value)) if value else []
        changed.append({"__negative_control__": True})
        return changed
    if isinstance(value, dict):
        changed = dict(value)
        changed["__negative_control__"] = True
        return changed
    return "__negative_control__"


def validate_negative_diff_result(exit_code: int, diff_report: dict[str, Any]) -> dict[str, Any]:
    if exit_code == 0:
        raise SystemExit("FlashDB fixture negative diff unexpectedly passed")
    mismatch = diff_report.get("first_mismatch")
    if not mismatch:
        raise SystemExit("FlashDB fixture negative diff failed without first_mismatch evidence")
    return {
        "schema_version": 1,
        "status": "passed",
        "diff_status": "expected_failed",
        "first_mismatch": mismatch.get("field_path") or mismatch.get("field") or mismatch,
    }


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
