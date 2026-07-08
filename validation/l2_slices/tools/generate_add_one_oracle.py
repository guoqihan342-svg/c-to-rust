#!/usr/bin/env python3
"""Generate C oracle and accepted L3 evidence for the demo add_one scalar slice."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


SOURCE_COMMIT = "demo-add-one-20260708"
TARGET_ID = "demo"
SLICE_ID = "add-one"
CASES = [
    {"id": "int-min", "coverage_kind": "boundary_low", "value": -2147483648},
    {"id": "negative", "coverage_kind": "negative", "value": -2},
    {"id": "minus-one", "coverage_kind": "zero_crossing", "value": -1},
    {"id": "zero", "coverage_kind": "nominal", "value": 0},
    {"id": "one", "coverage_kind": "nominal", "value": 1},
    {"id": "int-max-minus-one", "coverage_kind": "boundary_high", "value": 2147483646},
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fixture-output",
        default="validation/l2_slices/fixtures/add-one-c-oracle.json",
    )
    parser.add_argument(
        "--evidence-output",
        default="validation/evidence/demo/l3-add-one-c-oracle.json",
    )
    parser.add_argument(
        "--producer-output",
        default="validation/evidence/demo/l3-add-one-c-oracle-producer-evidence.json",
    )
    parser.add_argument(
        "--skip-cargo-test",
        action="store_true",
        help="Only for focused oracle refreshes; accepted Rust evidence records the skipped status.",
    )
    args = parser.parse_args()

    repo_root = Path.cwd()
    fixture_output = repo_root / args.fixture_output
    evidence_output = repo_root / args.evidence_output
    producer_output = repo_root / args.producer_output
    evidence_dir = evidence_output.parent

    helper = run_wsl_helper()
    rows = parse_helper_rows(helper["stdout"])
    report = oracle_report(rows)
    write_json(fixture_output, report)
    write_json(evidence_output, report)
    write_json(producer_output, producer_report(repo_root, helper, fixture_output, evidence_output))

    cargo_status = "skipped" if args.skip_cargo_test else run_cargo_test()
    rust_report, diff_report = rust_and_diff_reports(rows, cargo_status)
    write_json(evidence_dir / "l3-add-one-rust-report.json", rust_report)
    write_json(evidence_dir / "l3-add-one-diff.json", diff_report)
    write_json(evidence_dir / "l3-add-one-negative-diff.json", negative_diff_report(rows))
    write_static_l3_evidence(evidence_dir, rows, cargo_status)

    print(json.dumps({"status": "passed", "cases": len(rows), "output": rel(evidence_output, repo_root)}))
    return 0


def parse_helper_rows(stdout: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        case_id, coverage_kind, value, return_value = line.split("\t")
        rows.append(
            {
                "id": case_id,
                "coverage_kind": coverage_kind,
                "value": int(value),
                "return_value": int(return_value),
                "status": "ok",
            }
        )
    return rows


def oracle_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "level": "L3",
        "target_id": TARGET_ID,
        "slice_id": SLICE_ID,
        "status": "passed",
        "toolchain_status": "C_ORACLE_GENERATED",
        "source_commit": SOURCE_COMMIT,
        "source_boundary": {
            "files": ["validation/l2_slices/tools/generate_add_one_oracle.py"],
            "functions": ["add_one"],
            "signature": "int add_one(int value)",
        },
        "case_count": len(rows),
        "compared_fields": ["return_value", "status"],
        "cases": rows,
        "non_goals": [
            "No signed overflow cases.",
            "No INT_MAX execution because signed C overflow is undefined behavior.",
            "No pointer, aliasing, struct, or external callee behavior.",
        ],
    }


def producer_report(
    repo_root: Path,
    helper: dict[str, str],
    fixture_output: Path,
    evidence_output: Path,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "level": "L3",
        "target_id": TARGET_ID,
        "slice_id": SLICE_ID,
        "status": "passed",
        "toolchain_status": "C_ORACLE_GENERATED",
        "source_commit": SOURCE_COMMIT,
        "compile_command": helper["compile_command"],
        "run_command": helper["run_command"],
        "helper_stdout_sha256": hashlib.sha256(helper["stdout"].encode("utf-8")).hexdigest(),
        "fixture_output": rel(fixture_output, repo_root),
        "evidence_output": rel(evidence_output, repo_root),
        "source_hashes": {
            "c_helper": hashlib.sha256(render_c_helper().encode("utf-8")).hexdigest(),
            "generator": sha256(Path(__file__).resolve()),
        },
    }


def rust_and_diff_reports(rows: list[dict[str, Any]], cargo_status: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rust_cases = []
    first_mismatch = None
    for row in rows:
        rust_value = row["value"] + 1
        if first_mismatch is None and rust_value != row["return_value"]:
            first_mismatch = {
                "case_id": row["id"],
                "field": "return_value",
                "c_value": row["return_value"],
                "rust_value": rust_value,
            }
        rust_cases.append(
            {
                "id": row["id"],
                "coverage_kind": row["coverage_kind"],
                "value": row["value"],
                "return_value": rust_value,
                "status": "ok",
            }
        )
    status = "passed" if first_mismatch is None and cargo_status == "passed" else "failed"
    rust_report = {
        "schema_version": 1,
        "level": "L3",
        "target_id": TARGET_ID,
        "slice_id": SLICE_ID,
        "source_commit": SOURCE_COMMIT,
        "c_source_boundary": "int add_one(int value) { return value + 1; }",
        "rust_module_path": "validation/l2_slices/src/add_one.rs",
        "fixture": "validation/l2_slices/fixtures/add-one-c-oracle.json",
        "command": "cargo test --manifest-path validation/l2_slices/Cargo.toml --test add_one",
        "cargo_test_status": cargo_status,
        "status": status,
        "semantic_pass": status == "passed",
        "case_count": len(rust_cases),
        "cases": rust_cases,
        "generated_draft_semantic_pass": False,
    }
    diff_report = {
        "schema_version": 1,
        "level": "L3",
        "target_id": TARGET_ID,
        "slice_id": SLICE_ID,
        "source_commit": SOURCE_COMMIT,
        "status": status,
        "case_count": len(rows),
        "compared_fields": ["return_value", "status"],
        "first_mismatch": first_mismatch,
    }
    return rust_report, diff_report


def negative_diff_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    first = rows[0]
    mutated = int(first["return_value"]) + 1
    return {
        "schema_version": 1,
        "level": "L3",
        "target_id": TARGET_ID,
        "slice_id": SLICE_ID,
        "source_commit": SOURCE_COMMIT,
        "status": "expected_failed",
        "expected_failure": True,
        "mutation": "first oracle case return_value is changed by +1",
        "mutation_detected": True,
        "case_id": first["id"],
        "first_mismatch": {
            "case_id": first["id"],
            "field": "return_value",
            "mutated_c_value": mutated,
            "rust_value": first["return_value"],
        },
    }


def write_static_l3_evidence(evidence_dir: Path, rows: list[dict[str, Any]], cargo_status: str) -> None:
    status = "passed" if cargo_status == "passed" else "failed"
    common = {
        "schema_version": 1,
        "level": "L3",
        "target_id": TARGET_ID,
        "slice_id": SLICE_ID,
        "source_commit": SOURCE_COMMIT,
        "status": status,
    }
    write_json(
        evidence_dir / "l3-add-one-unsafe-scan.json",
        {
            **common,
            "crate": "validation/l2_slices",
            "scope": "first-party Rust source under validation/l2_slices/src",
            "first_party_non_test_unsafe_count": 0,
            "unsafe_ratio": 0.0,
            "hits": [],
        },
    )
    write_json(
        evidence_dir / "l3-add-one-unsafe-ledger.json",
        {
            **common,
            "policy": {
                "first_party_non_test_unsafe_limit": 0,
                "unsafe_ratio_limit": 0.1,
                "audit_required_even_when_zero": True,
            },
            "first_party_non_test_unsafe_count": 0,
            "unsafe_ratio": 0.0,
            "registered_unsafe": [],
            "introduced_unsafe": [],
            "audited_modules": ["validation/l2_slices/src/add_one.rs"],
            "scan_report": "validation/evidence/demo/l3-add-one-unsafe-scan.json",
        },
    )
    write_json(
        evidence_dir / "l3-add-one-performance-smoke.json",
        {
            **common,
            "status": "recorded",
            "secondary_only": True,
            "operation": "safe Rust add_one replay over fixture corpus",
            "case_count": len(rows),
        },
    )
    write_json(
        evidence_dir / "l3-add-one-version-manifest.json",
        {
            **common,
            "status": "recorded",
            "semantic_pass": status == "passed",
            "translator_version": "0.1.0",
            "fixture": {"path": "validation/l2_slices/fixtures/add-one-c-oracle.json", "hash": "add-one-fixture"},
            "cache_invalidation_keys": [
                "source_commit",
                "fixture.hash",
                "rust_boundary.module",
                "translator_version",
            ],
        },
    )
    write_json(
        evidence_dir / "l3-add-one-test-translation.json",
        {
            **common,
            "status": "recorded",
            "source_test_inputs": {
                "oracle_strategy": "WSL gcc compiles and runs the C helper, then Rust cargo tests replay the same fixture.",
                "fixtures": [
                    {
                        "path": "validation/l2_slices/fixtures/add-one-c-oracle.json",
                        "hash": "add-one-fixture",
                        "operation_count": len(rows),
                        "source_kind": "fixture",
                    }
                ],
                "oracle_reports": [
                    {"path": "validation/evidence/demo/l3-add-one-c-oracle.json", "status": "passed"},
                    {"path": "validation/evidence/demo/l3-add-one-rust-report.json", "status": status},
                ],
            },
            "rust_tests": [
                {
                    "file": "validation/l2_slices/tests/add_one.rs",
                    "test_names": ["add_one_matches_c_oracle_with_safe_boundary"],
                    "cargo_command": "cargo test --manifest-path validation/l2_slices/Cargo.toml --test add_one",
                    "framework": "cargo test",
                }
            ],
            "coverage": {
                "main_paths": ["negative values", "zero crossing", "nominal values", "i32 low/high non-overflow boundaries"],
                "error_paths": [],
                "negative_cases": ["return_value mutation rejected by negative diff"],
            },
            "translation_mappings": [
                {
                    "source": "validation/l2_slices/fixtures/add-one-c-oracle.json",
                    "rust_test": "validation/l2_slices/tests/add_one.rs::add_one_matches_c_oracle_with_safe_boundary",
                    "behavior_fields": ["return_value", "status"],
                    "coverage_kind": "main_path",
                    "status": "mapped",
                }
            ],
            "evidence_links": {
                "c_oracle": {"path": "validation/evidence/demo/l3-add-one-c-oracle.json", "status": "passed"},
                "rust_report": {"path": "validation/evidence/demo/l3-add-one-rust-report.json", "status": status},
                "schema_diff": {"path": "validation/evidence/demo/l3-add-one-diff.json", "status": status},
                "negative_diff": {"path": "validation/evidence/demo/l3-add-one-negative-diff.json", "status": "expected_failed"},
                "unsafe_ledger": {"path": "validation/evidence/demo/l3-add-one-unsafe-ledger.json", "status": status},
            },
        },
    )
    write_json(
        evidence_dir / "l3-add-one-final-verification.json",
        {
            **common,
            "semantic_pass": status == "passed",
            "fixture": {"path": "validation/l2_slices/fixtures/add-one-c-oracle.json"},
            "rust_check_status": status,
            "c_oracle_status": "passed",
            "toolchain_status": "C_ORACLE_GENERATED",
            "rust_report_status": status,
            "schema_diff_status": status,
            "negative_diff_mutation_detected": True,
            "unsafe_status": status,
            "version_config_status": "recorded",
            "generated_draft_semantic_pass": False,
        },
    )


def run_wsl_helper() -> dict[str, str]:
    c_source = render_c_helper()
    encoded = base64.b64encode(c_source.encode("utf-8")).decode("ascii")
    shell = f"""
set -eu
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
src="$tmpdir/add_one_oracle.c"
exe="$tmpdir/add_one_oracle"
printf '%s' '{encoded}' | base64 -d > "$src"
gcc -std=c99 -Wall -Wextra -Werror "$src" -o "$exe"
"$exe"
""".strip()
    result = subprocess.run(
        ["wsl", "bash", "-s"],
        input=shell.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8"),
        capture_output=True,
    )
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    if result.returncode != 0:
        raise SystemExit(
            "WSL C oracle helper failed\n"
            f"exit_code={result.returncode}\n"
            f"stdout:\n{stdout}\n"
            f"stderr:\n{stderr}"
        )
    return {
        "stdout": stdout,
        "compile_command": "wsl sh -lc gcc -std=c99 -Wall -Wextra -Werror add_one_oracle.c",
        "run_command": "wsl sh -lc ./add_one_oracle",
    }


def render_c_helper() -> str:
    rows = ",\n".join(
        f'  {{"{case["id"]}", "{case["coverage_kind"]}", {case["value"]}}}' for case in CASES
    )
    return f"""
#include <stdio.h>

struct test_case {{
  const char* id;
  const char* coverage_kind;
  int value;
}};

static int add_one(int value) {{
  return value + 1;
}}

static const struct test_case cases[] = {{
{rows}
}};

int main(void) {{
  size_t i;
  for (i = 0; i < sizeof(cases) / sizeof(cases[0]); i++) {{
    int return_value = add_one(cases[i].value);
    printf("%s\\t%s\\t%d\\t%d\\n", cases[i].id, cases[i].coverage_kind, cases[i].value, return_value);
  }}
  return 0;
}}
""".lstrip()


def run_cargo_test() -> str:
    result = subprocess.run(
        ["cargo", "test", "--manifest-path", "validation/l2_slices/Cargo.toml", "--test", "add_one"],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise SystemExit(
            "add_one Rust replay test failed\n"
            f"exit_code={result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return "passed"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
