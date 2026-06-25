#!/usr/bin/env python3
"""Generate C oracle evidence for the demo copy_i32_ptr_arith output-write slice."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
from pathlib import Path


SOURCE_COMMIT = "demo-copy-i32-ptr-arith-20260625"
TARGET_ID = "demo"
SLICE_ID = "copy-i32-ptr-arith"

CASES = [
    {"id": "empty", "coverage_kind": "empty", "values": []},
    {"id": "single-positive", "coverage_kind": "single", "values": [7]},
    {"id": "multi-positive", "coverage_kind": "multi", "values": [1, 2, 3, 4]},
    {"id": "mixed-negative", "coverage_kind": "negative_values", "values": [-5, 2, -3, 6]},
    {"id": "zero-values", "coverage_kind": "zero_values", "values": [0, 0, 0]},
    {"id": "boundary-safe", "coverage_kind": "boundary_safe", "values": [1073741823, -1073741824, -1]},
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fixture-output",
        default="validation/l2_slices/fixtures/copy-i32-ptr-arith-c-oracle.json",
    )
    parser.add_argument(
        "--evidence-output",
        default="validation/evidence/demo/l3-copy-i32-ptr-arith-c-oracle.json",
    )
    parser.add_argument(
        "--producer-output",
        default="validation/evidence/demo/l3-copy-i32-ptr-arith-c-oracle-producer-evidence.json",
    )
    args = parser.parse_args()

    repo_root = Path.cwd()
    fixture_output = repo_root / args.fixture_output
    evidence_output = repo_root / args.evidence_output
    producer_output = repo_root / args.producer_output

    helper = run_wsl_helper()
    rows = []
    for line in helper["stdout"].splitlines():
        case_id, coverage_kind, values_csv, length, return_code, out_csv = line.split("\t")
        values = [] if not values_csv else [int(item) for item in values_csv.split(",")]
        out_values = [] if not out_csv else [int(item) for item in out_csv.split(",")]
        rows.append(
            {
                "id": case_id,
                "coverage_kind": coverage_kind,
                "values": values,
                "len": int(length),
                "return_code": int(return_code),
                "status": "ok" if int(return_code) == 0 else "error",
                "out_values": out_values,
                "source_reads": "*(values + i) under i < len",
                "canonical_reads": "values[i]",
                "source_writes": "*(out + i) under i < len",
                "canonical_writes": "out[i]",
                "write_count": len(out_values),
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
            "files": ["validation/l2_slices/tools/generate_copy_i32_ptr_arith_oracle.py"],
            "functions": ["copy_i32_ptr_arith"],
            "signature": "int copy_i32_ptr_arith(const int* values, int len, int* out)",
        },
        "case_count": len(rows),
        "compared_fields": [
            "return_code",
            "status",
            "len",
            "values",
            "out_values",
            "source_reads",
            "canonical_reads",
            "source_writes",
            "canonical_writes",
            "write_count",
        ],
        "cases": rows,
        "non_goals": [
            "No NULL pointer execution.",
            "No negative len execution.",
            "No aliasing proof between values and out.",
            "No input/output overlap execution.",
            "No signed overflow cases.",
            "No arbitrary pointer arithmetic beyond *(values + i) reads and *(out + i) writes.",
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
src="$tmpdir/copy_i32_ptr_arith_oracle.c"
exe="$tmpdir/copy_i32_ptr_arith_oracle"
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
        "compile_command": "wsl sh -lc gcc -std=c99 -Wall -Wextra -Werror copy_i32_ptr_arith_oracle.c",
        "run_command": "wsl sh -lc ./copy_i32_ptr_arith_oracle",
    }


def render_c_helper() -> str:
    case_defs = []
    array_defs = []
    for idx, case in enumerate(CASES):
        array_name = f"case_{idx}_values"
        if case["values"]:
            values = ", ".join(str(value) for value in case["values"])
            array_defs.append(f"static const int {array_name}[] = {{{values}}};")
            values_ptr = array_name
        else:
            values_ptr = "0"
        case_defs.append(
            f'  {{"{case["id"]}", "{case["coverage_kind"]}", {values_ptr}, {len(case["values"])}}}'
        )
    arrays = "\n".join(array_defs)
    rows = ",\n".join(case_defs)
    return f"""
#include <stdio.h>

struct test_case {{
  const char* id;
  const char* coverage_kind;
  const int* values;
  int len;
}};

static int copy_i32_ptr_arith(const int* values, int len, int* out) {{
  int i;
  for (i = 0; i < len; i++) {{
    *(out + i) = *(values + i);
  }}
  return 0;
}}

{arrays}

static const struct test_case cases[] = {{
{rows}
}};

int main(void) {{
  size_t i;
  for (i = 0; i < sizeof(cases) / sizeof(cases[0]); i++) {{
    int out[16] = {{0}};
    int rc = copy_i32_ptr_arith(cases[i].values, cases[i].len, out);
    int j;
    printf("%s\\t%s\\t", cases[i].id, cases[i].coverage_kind);
    for (j = 0; j < cases[i].len; j++) {{
      if (j > 0) {{
        printf(",");
      }}
      printf("%d", cases[i].values[j]);
    }}
    printf("\\t%d\\t%d\\t", cases[i].len, rc);
    for (j = 0; j < cases[i].len; j++) {{
      if (j > 0) {{
        printf(",");
      }}
      printf("%d", out[j]);
    }}
    printf("\\n");
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
