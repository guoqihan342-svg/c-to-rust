#!/usr/bin/env python3
"""Generate C oracle evidence for the demo add_i32_pair_ptr_arith alias slice."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
from pathlib import Path


SOURCE_COMMIT = "demo-add-i32-pair-ptr-arith-20260625"
TARGET_ID = "demo"
SLICE_ID = "add-i32-pair-ptr-arith"
SOURCE_READS = "*(lhs + i), *(rhs + i) under i < len"
CANONICAL_READS = "lhs[i], rhs[i]"
SOURCE_WRITES = "*(out + i) under i < len"
CANONICAL_WRITES = "out[i]"

CASES = [
    {
        "id": "empty-disjoint",
        "coverage_kind": "empty",
        "lhs": [],
        "rhs": [],
        "alias_case": "disjoint",
        "execute": True,
    },
    {
        "id": "single-disjoint",
        "coverage_kind": "single",
        "lhs": [7],
        "rhs": [5],
        "alias_case": "disjoint",
        "execute": True,
    },
    {
        "id": "multi-disjoint",
        "coverage_kind": "multi",
        "lhs": [1, 2, 3, 4],
        "rhs": [10, 20, 30, 40],
        "alias_case": "disjoint",
        "execute": True,
    },
    {
        "id": "mixed-negative",
        "coverage_kind": "negative_values",
        "lhs": [-5, 2, -3, 6],
        "rhs": [4, -7, 3, -1],
        "alias_case": "disjoint",
        "execute": True,
    },
    {
        "id": "lhs-rhs-read-alias",
        "coverage_kind": "read_read_alias",
        "lhs": [3, -1, 8],
        "rhs": [3, -1, 8],
        "alias_case": "lhs_rhs_read_alias",
        "execute": True,
    },
    {
        "id": "lhs-out-overlap-risk",
        "coverage_kind": "input_output_overlap_risk",
        "lhs": [1, 2, 3],
        "rhs": [4, 5, 6],
        "alias_case": "lhs_out_overlap_risk",
        "execute": False,
    },
    {
        "id": "rhs-out-overlap-risk",
        "coverage_kind": "input_output_overlap_risk",
        "lhs": [1, 2, 3],
        "rhs": [4, 5, 6],
        "alias_case": "rhs_out_overlap_risk",
        "execute": False,
    },
    {
        "id": "boundary-safe",
        "coverage_kind": "boundary_safe",
        "lhs": [1073741823, -1073741824, -1],
        "rhs": [1, -1, 1],
        "alias_case": "disjoint",
        "execute": True,
    },
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fixture-output",
        default="validation/l2_slices/fixtures/add-i32-pair-ptr-arith-c-oracle.json",
    )
    parser.add_argument(
        "--evidence-output",
        default="validation/evidence/demo/l3-add-i32-pair-ptr-arith-c-oracle.json",
    )
    parser.add_argument(
        "--producer-output",
        default="validation/evidence/demo/l3-add-i32-pair-ptr-arith-c-oracle-producer-evidence.json",
    )
    args = parser.parse_args()

    repo_root = Path.cwd()
    fixture_output = repo_root / args.fixture_output
    evidence_output = repo_root / args.evidence_output
    producer_output = repo_root / args.producer_output

    helper = run_wsl_helper()
    rows = []
    for line in helper["stdout"].splitlines():
        (
            case_id,
            coverage_kind,
            lhs_csv,
            rhs_csv,
            length,
            return_code,
            status,
            out_csv,
            safe_noalias,
            alias_case,
            alias_matrix_csv,
        ) = line.split("\t")
        lhs = [] if not lhs_csv else [int(item) for item in lhs_csv.split(",")]
        rhs = [] if not rhs_csv else [int(item) for item in rhs_csv.split(",")]
        out_values = [] if not out_csv else [int(item) for item in out_csv.split(",")]
        alias_matrix = [] if not alias_matrix_csv else alias_matrix_csv.split("|")
        rows.append(
            {
                "id": case_id,
                "coverage_kind": coverage_kind,
                "lhs": lhs,
                "rhs": rhs,
                "len": int(length),
                "return_code": int(return_code),
                "status": status,
                "out_values": out_values,
                "source_reads": SOURCE_READS,
                "canonical_reads": CANONICAL_READS,
                "source_writes": SOURCE_WRITES,
                "canonical_writes": CANONICAL_WRITES,
                "write_count": len(out_values),
                "safe_noalias_precondition": safe_noalias == "true",
                "alias_case": alias_case,
                "alias_matrix": alias_matrix,
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
            "files": ["validation/l2_slices/tools/generate_add_i32_pair_ptr_arith_oracle.py"],
            "functions": ["add_i32_pair_ptr_arith"],
            "signature": "int add_i32_pair_ptr_arith(const int* lhs, const int* rhs, int len, int* out)",
        },
        "case_count": len(rows),
        "compared_fields": [
            "return_code",
            "status",
            "len",
            "lhs",
            "rhs",
            "out_values",
            "source_reads",
            "canonical_reads",
            "source_writes",
            "canonical_writes",
            "write_count",
            "safe_noalias_precondition",
            "alias_case",
            "alias_matrix",
        ],
        "cases": rows,
        "non_goals": [
            "No NULL pointer execution.",
            "No negative len execution.",
            "No signed overflow cases.",
            "No claim that input/output overlap can be represented by safe Rust references.",
            "Rejected overlap-risk cases are boundary metadata, not accepted safe replay executions.",
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
src="$tmpdir/add_i32_pair_ptr_arith_oracle.c"
exe="$tmpdir/add_i32_pair_ptr_arith_oracle"
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
        "compile_command": "wsl sh -lc gcc -std=c99 -Wall -Wextra -Werror add_i32_pair_ptr_arith_oracle.c",
        "run_command": "wsl sh -lc ./add_i32_pair_ptr_arith_oracle",
    }


def render_c_helper() -> str:
    array_defs = []
    case_defs = []
    for idx, case in enumerate(CASES):
        lhs_name = f"case_{idx}_lhs"
        rhs_name = f"case_{idx}_rhs"
        if case["lhs"]:
            lhs_values = ", ".join(str(value) for value in case["lhs"])
            array_defs.append(f"static const int {lhs_name}[] = {{{lhs_values}}};")
            lhs_ptr = lhs_name
        else:
            lhs_ptr = "0"
        if case["alias_case"] == "lhs_rhs_read_alias":
            rhs_ptr = lhs_ptr
        elif case["rhs"]:
            rhs_values = ", ".join(str(value) for value in case["rhs"])
            array_defs.append(f"static const int {rhs_name}[] = {{{rhs_values}}};")
            rhs_ptr = rhs_name
        else:
            rhs_ptr = "0"
        execute = 1 if case["execute"] else 0
        case_defs.append(
            f'  {{"{case["id"]}", "{case["coverage_kind"]}", {lhs_ptr}, {rhs_ptr}, '
            f'{len(case["lhs"])}, "{case["alias_case"]}", {execute}}}'
        )
    return C_HELPER_TEMPLATE.replace("__ARRAYS__", "\n".join(array_defs)).replace(
        "__ROWS__", ",\n".join(case_defs)
    )


C_HELPER_TEMPLATE = r"""
#include <stdio.h>

struct test_case {
  const char* id;
  const char* coverage_kind;
  const int* lhs;
  const int* rhs;
  int len;
  const char* alias_case;
  int execute;
};

static int add_i32_pair_ptr_arith(const int* lhs, const int* rhs, int len, int* out) {
  int i;
  for (i = 0; i < len; i++) {
    *(out + i) = *(lhs + i) + *(rhs + i);
  }
  return 0;
}

__ARRAYS__

static const struct test_case cases[] = {
__ROWS__
};

static void print_values(const int* values, int len) {
  int i;
  for (i = 0; i < len; i++) {
    if (i > 0) {
      printf(",");
    }
    printf("%d", values[i]);
  }
}

static const char* alias_matrix(const char* alias_case) {
  if (alias_case[0] == 'l' && alias_case[4] == 'r') {
    return "lhs-rhs:read_read_alias_allowed|lhs-out:disjoint|rhs-out:disjoint";
  }
  if (alias_case[0] == 'l' && alias_case[4] == 'o') {
    return "lhs-rhs:disjoint|lhs-out:overlap_risk_rejected|rhs-out:disjoint";
  }
  if (alias_case[0] == 'r') {
    return "lhs-rhs:disjoint|lhs-out:disjoint|rhs-out:overlap_risk_rejected";
  }
  return "lhs-rhs:disjoint|lhs-out:disjoint|rhs-out:disjoint";
}

int main(void) {
  size_t i;
  for (i = 0; i < sizeof(cases) / sizeof(cases[0]); i++) {
    int out[16] = {0};
    int rc = -1;
    const char* status = "rejected_overlap_risk";
    if (cases[i].execute) {
      rc = add_i32_pair_ptr_arith(cases[i].lhs, cases[i].rhs, cases[i].len, out);
      status = rc == 0 ? "ok" : "error";
    }
    printf("%s\t%s\t", cases[i].id, cases[i].coverage_kind);
    print_values(cases[i].lhs, cases[i].len);
    printf("\t");
    print_values(cases[i].rhs, cases[i].len);
    printf("\t%d\t%d\t%s\t", cases[i].len, rc, status);
    if (cases[i].execute) {
      print_values(out, cases[i].len);
    }
    printf("\t%s\t%s\t%s\n",
      cases[i].execute ? "true" : "false",
      cases[i].alias_case,
      alias_matrix(cases[i].alias_case));
  }
  return 0;
}
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
