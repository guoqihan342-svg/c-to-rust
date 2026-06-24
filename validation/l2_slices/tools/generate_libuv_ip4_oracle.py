#!/usr/bin/env python3
"""Generate C oracle evidence for libuv uv_ip4_addr.

Run under WSL/Linux from the repository root:
  python3 validation/l2_slices/tools/generate_libuv_ip4_oracle.py \
    --libuv-root /mnt/c/Users/Administrator/Documents/c-to-rust-l1-work/remediation-l1/libs-20260624T124853/repos/libuv
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


SOURCE_COMMIT = "5e7d51a8f4734cac453db960d4b9919735bbf7c3"
SLICE_ID = "ip4-addr"
TARGET_ID = "libuv"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--libuv-root", required=True)
    parser.add_argument(
        "--input",
        default="validation/l2_slices/fixtures/libuv-ip4-addr-input.json",
    )
    parser.add_argument(
        "--fixture-output",
        default="validation/l2_slices/fixtures/libuv-ip4-addr-c-oracle.json",
    )
    parser.add_argument(
        "--evidence-output",
        default="validation/evidence/libuv/l3-ip4-addr-c-oracle.json",
    )
    parser.add_argument(
        "--producer-output",
        default="validation/evidence/libuv/l3-ip4-addr-c-oracle-producer-evidence.json",
    )
    args = parser.parse_args()

    repo_root = Path.cwd()
    libuv_root = Path(args.libuv_root)
    input_path = repo_root / args.input
    fixture_output = repo_root / args.fixture_output
    evidence_output = repo_root / args.evidence_output
    producer_output = repo_root / args.producer_output

    fixture = json.loads(input_path.read_text(encoding="utf-8"))
    cases = fixture["cases"]
    ensure_libuv_checkout(libuv_root)
    helper_result = run_c_helper(libuv_root, cases)

    report = {
        "schema_version": 1,
        "level": "L3",
        "target_id": TARGET_ID,
        "slice_id": SLICE_ID,
        "status": "passed",
        "toolchain_status": "C_ORACLE_GENERATED",
        "source_commit": SOURCE_COMMIT,
        "source_boundary": {
            "files": [
                "include/uv.h",
                "src/uv-common.c",
                "src/inet.c",
                "test/test-ip4-addr.c",
            ],
            "functions": ["uv_ip4_addr", "uv_inet_pton", "inet_pton4"],
            "signature": "int uv_ip4_addr(const char* ip, int port, struct sockaddr_in* addr)",
        },
        "input_fixture": rel(input_path, repo_root),
        "input_fixture_sha256": sha256(input_path),
        "case_count": len(helper_result["cases"]),
        "compared_fields": [
            "return_code",
            "status",
            "family",
            "port_host",
            "port_bytes_hex",
            "addr_bytes_hex",
        ],
        "cases": helper_result["cases"],
    }

    fixture_output.parent.mkdir(parents=True, exist_ok=True)
    evidence_output.parent.mkdir(parents=True, exist_ok=True)
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
        "libuv_root": str(libuv_root),
        "compile_command": helper_result["compile_command"],
        "run_command": helper_result["run_command"],
        "helper_stdout_sha256": helper_result["stdout_sha256"],
        "fixture_output": rel(fixture_output, repo_root),
        "evidence_output": rel(evidence_output, repo_root),
        "source_hashes": {
            "include/uv.h": sha256(libuv_root / "include/uv.h"),
            "src/uv-common.c": sha256(libuv_root / "src/uv-common.c"),
            "src/inet.c": sha256(libuv_root / "src/inet.c"),
            "test/test-ip4-addr.c": sha256(libuv_root / "test/test-ip4-addr.c"),
        },
    }
    write_json(producer_output, producer)

    print(json.dumps({"status": "passed", "cases": len(cases), "output": rel(evidence_output, repo_root)}))
    return 0


def ensure_libuv_checkout(libuv_root: Path) -> None:
    required = [
        libuv_root / "include/uv.h",
        libuv_root / "src/uv-common.c",
        libuv_root / "src/inet.c",
        libuv_root / "build/libuv.so",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit(f"missing libuv checkout/build files: {missing}")
    commit = subprocess.check_output(["git", "-C", str(libuv_root), "rev-parse", "HEAD"], text=True).strip()
    if commit != SOURCE_COMMIT:
        raise SystemExit(f"libuv commit mismatch: expected {SOURCE_COMMIT}, got {commit}")


def run_c_helper(libuv_root: Path, cases: list[dict]) -> dict:
    with tempfile.TemporaryDirectory(prefix="libuv-ip4-oracle-") as temp:
        temp_dir = Path(temp)
        source = temp_dir / "libuv_ip4_oracle.c"
        exe = temp_dir / "libuv_ip4_oracle"
        stdout = temp_dir / "oracle.json"
        source.write_text(render_c_helper(cases), encoding="utf-8")
        compile_cmd = [
            "gcc",
            "-std=c99",
            "-D_GNU_SOURCE",
            "-pthread",
            "-I",
            str(libuv_root / "include"),
            str(source),
            "-L",
            str(libuv_root / "build"),
            f"-Wl,-rpath,{libuv_root / 'build'}",
            "-luv",
            "-o",
            str(exe),
        ]
        subprocess.run(compile_cmd, check=True)
        with stdout.open("w", encoding="utf-8") as out:
            subprocess.run([str(exe)], check=True, stdout=out)
        text = stdout.read_text(encoding="utf-8")
        data = json.loads(text)
        data["compile_command"] = " ".join(compile_cmd)
        data["run_command"] = str(exe)
        data["stdout_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return data


def render_c_helper(cases: list[dict]) -> str:
    rows = []
    for case in cases:
        rows.append(
            '  {"%s", "%s", %d, "%s"}'
            % (
                c_escape(case["id"]),
                c_escape(case["ip"]),
                int(case["port"]),
                c_escape(case["coverage_kind"]),
            )
        )
    case_rows = ",\n".join(rows)
    return f"""
#include <arpa/inet.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "uv.h"

struct test_case {{
  const char* id;
  const char* ip;
  int port;
  const char* coverage_kind;
}};

static const struct test_case cases[] = {{
{case_rows}
}};

static void print_hex2(unsigned char byte) {{
  static const char* hex = "0123456789abcdef";
  putchar(hex[(byte >> 4) & 0x0f]);
  putchar(hex[byte & 0x0f]);
}}

int main(void) {{
  size_t i;
  printf("{{\\\"cases\\\":[");
  for (i = 0; i < sizeof(cases) / sizeof(cases[0]); i++) {{
    struct sockaddr_in addr;
    unsigned char* port_bytes;
    unsigned char* addr_bytes;
    int rc = uv_ip4_addr(cases[i].ip, cases[i].port, &addr);
    port_bytes = (unsigned char*) &addr.sin_port;
    addr_bytes = (unsigned char*) &addr.sin_addr.s_addr;
    if (i > 0) printf(",");
    printf("{{\\\"id\\\":\\\"%s\\\",", cases[i].id);
    printf("\\\"ip\\\":\\\"%s\\\",", cases[i].ip);
    printf("\\\"port\\\":%d,", cases[i].port);
    printf("\\\"coverage_kind\\\":\\\"%s\\\",", cases[i].coverage_kind);
    printf("\\\"return_code\\\":%d,", rc);
    printf("\\\"status\\\":\\\"%s\\\",", rc == 0 ? "ok" : "invalid");
    printf("\\\"family\\\":%d,", (int) addr.sin_family);
    printf("\\\"port_host\\\":%u,", (unsigned int) ntohs(addr.sin_port));
    printf("\\\"port_bytes_hex\\\":\\\"");
    print_hex2(port_bytes[0]);
    print_hex2(port_bytes[1]);
    printf("\\\",");
    printf("\\\"addr_bytes_hex\\\":\\\"");
    print_hex2(addr_bytes[0]);
    print_hex2(addr_bytes[1]);
    print_hex2(addr_bytes[2]);
    print_hex2(addr_bytes[3]);
    printf("\\\"}}");
  }}
  printf("]}}\\n");
  return 0;
}}
"""


def c_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


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
