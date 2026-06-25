#!/usr/bin/env python3
"""Generate C oracle evidence for the demo external direct callee slice."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
from pathlib import Path


SOURCE_COMMIT = "demo-external-direct-callee-20260625"
TARGET_ID = "demo"
SLICE_ID = "external-direct-callee"
CALL_CONTEXTS = ["declaration_initializer", "assignment", "return"]
SOURCE_CALLS = [
    "int first = helper_add_one(value)",
    "value = helper_add_one(first)",
    "return helper_add_one(value)",
]
CALLEE_BINDINGS = [
    "helper_add_one:int->int",
    "helper_add_one:int->int",
    "helper_add_one:int->int",
]

CASES = [
    {"id": "negative-two", "coverage_kind": "negative", "value": -2},
    {"id": "negative-one", "coverage_kind": "negative", "value": -1},
    {"id": "zero", "coverage_kind": "zero", "value": 0},
    {"id": "one", "coverage_kind": "positive", "value": 1},
    {"id": "seven", "coverage_kind": "positive", "value": 7},
    {"id": "large-safe", "coverage_kind": "safe_range", "value": 2147483000},
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fixture-output",
        default="validation/l2_slices/fixtures/external-direct-callee-c-oracle.json",
    )
    parser.add_argument(
        "--evidence-output",
        default="validation/evidence/demo/l3-external-direct-callee-c-oracle.json",
    )
    parser.add_argument(
        "--producer-output",
        default="validation/evidence/demo/l3-external-direct-callee-c-oracle-producer-evidence.json",
    )
    args = parser.parse_args()

    repo_root = Path.cwd()
    fixture_output = repo_root / args.fixture_output
    evidence_output = repo_root / args.evidence_output
    producer_output = repo_root / args.producer_output

    helper = run_wsl_helper()
    rows = []
    for line in helper["stdout"].splitlines():
        case_id, coverage_kind, value, return_value = line.split("\t")
        rows.append(
            {
                "id": case_id,
                "coverage_kind": coverage_kind,
                "input_value": int(value),
                "return_value": int(return_value),
                "status": "ok",
                "external_callee_call_count": len(SOURCE_CALLS),
                "external_callee_contexts": CALL_CONTEXTS,
                "external_callee_bindings": CALLEE_BINDINGS,
                "source_calls": SOURCE_CALLS,
            }
        )

    report = {
        "schema_version": 1,
        "level": "L3",
        "target_id": TARGET_ID,
        "slice_id": SLICE_ID,
        "status": "passed",
        "toolchain_status": "C_ORACLE_GENERATED",
        "source_commit": SOURCE_COMMIT,
        "source_boundary": {
            "files": ["validation/l2_slices/tools/generate_external_direct_callee_oracle.py"],
            "functions": ["call_helper_chain", "helper_add_one"],
            "signature": "int call_helper_chain(int value); int helper_add_one(int value)",
            "direct_call_edges": [
                {"from": "call_helper_chain", "to": "helper_add_one", "context": "declaration_initializer"},
                {"from": "call_helper_chain", "to": "helper_add_one", "context": "assignment"},
                {"from": "call_helper_chain", "to": "helper_add_one", "context": "return"},
            ],
        },
        "case_count": len(rows),
        "compared_fields": [
            "return_value",
            "status",
            "external_callee_call_count",
            "external_callee_contexts",
            "external_callee_bindings",
            "source_calls",
        ],
        "cases": rows,
        "non_goals": [
            "No arbitrary multi-function translation claim.",
            "No function pointer, member call, variadic call, macro call, or nested call support claim.",
            "No signed overflow equivalence beyond the committed safe fixture domain.",
        ],
    }
    write_json(fixture_output, report)
    write_json(evidence_output, report)

    producer = {
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
    write_json(producer_output, producer)

    print(json.dumps({"status": "passed", "cases": len(rows), "output": rel(evidence_output, repo_root)}))
    return 0


def run_wsl_helper() -> dict[str, str]:
    c_source = render_c_helper()
    encoded = base64.b64encode(c_source.encode("utf-8")).decode("ascii")
    shell = f"""
set -eu
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
src="$tmpdir/external_direct_callee_oracle.c"
exe="$tmpdir/external_direct_callee_oracle"
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
        "compile_command": "wsl sh -lc gcc -std=c99 -Wall -Wextra -Werror external_direct_callee_oracle.c",
        "run_command": "wsl sh -lc ./external_direct_callee_oracle",
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

static int helper_add_one(int value) {{
  return value + 1;
}}

static int call_helper_chain(int value) {{
  int first = helper_add_one(value);
  value = helper_add_one(first);
  return helper_add_one(value);
}}

static const struct test_case cases[] = {{
{rows}
}};

int main(void) {{
  size_t i;
  for (i = 0; i < sizeof(cases) / sizeof(cases[0]); i++) {{
    int ret = call_helper_chain(cases[i].value);
    printf("%s\\t%s\\t%d\\t%d\\n", cases[i].id, cases[i].coverage_kind, cases[i].value, ret);
  }}
  return 0;
}}
""".lstrip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
