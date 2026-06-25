#!/usr/bin/env python3
"""Generate C oracle evidence for the demo call_expression_chain slice."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
from pathlib import Path


SOURCE_COMMIT = "demo-call-expression-20260625"
TARGET_ID = "demo"
SLICE_ID = "call-expression"
CALL_CONTEXTS = ["declaration_initializer", "assignment", "return"]
SOURCE_CALLS = [
    "int first = call_expression_chain(value - 1)",
    "value = call_expression_chain(first - 1)",
    "return call_expression_chain(value - 1)",
]

CASES = [
    {"id": "negative-two", "coverage_kind": "base_negative", "value": -2},
    {"id": "negative-one", "coverage_kind": "base_negative", "value": -1},
    {"id": "zero", "coverage_kind": "base_zero", "value": 0},
    {"id": "one", "coverage_kind": "recursive_single", "value": 1},
    {"id": "two", "coverage_kind": "recursive_multi", "value": 2},
    {"id": "three", "coverage_kind": "recursive_multi", "value": 3},
    {"id": "four", "coverage_kind": "recursive_multi", "value": 4},
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fixture-output",
        default="validation/l2_slices/fixtures/call-expression-c-oracle.json",
    )
    parser.add_argument(
        "--evidence-output",
        default="validation/evidence/demo/l3-call-expression-c-oracle.json",
    )
    parser.add_argument(
        "--producer-output",
        default="validation/evidence/demo/l3-call-expression-c-oracle-producer-evidence.json",
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
                "call_expression_count": len(SOURCE_CALLS),
                "call_expression_contexts": CALL_CONTEXTS,
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
            "files": ["validation/l2_slices/tools/generate_call_expression_oracle.py"],
            "functions": ["call_expression_chain"],
            "signature": "int call_expression_chain(int value)",
        },
        "case_count": len(rows),
        "compared_fields": [
            "return_value",
            "status",
            "call_expression_count",
            "call_expression_contexts",
            "source_calls",
        ],
        "cases": rows,
        "non_goals": [
            "No external callee semantic proof.",
            "No function pointer, member call, variadic call, macro call, or nested call support claim.",
            "No large recursion depth or performance claim.",
            "No signed overflow domain; fixture values stay inside the safe recursion input domain.",
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
src="$tmpdir/call_expression_oracle.c"
exe="$tmpdir/call_expression_oracle"
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
        "compile_command": "wsl sh -lc gcc -std=c99 -Wall -Wextra -Werror call_expression_oracle.c",
        "run_command": "wsl sh -lc ./call_expression_oracle",
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

static int call_expression_chain(int value) {{
  if (value <= 0) {{
    return -value;
  }}
  int first = call_expression_chain(value - 1);
  value = call_expression_chain(first - 1);
  return call_expression_chain(value - 1);
}}

static const struct test_case cases[] = {{
{rows}
}};

int main(void) {{
  size_t i;
  for (i = 0; i < sizeof(cases) / sizeof(cases[0]); i++) {{
    int ret = call_expression_chain(cases[i].value);
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
