#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
CRATE = REPO / "validation" / "l2_slices"
FIXTURES = CRATE / "fixtures"
EVIDENCE = REPO / "validation" / "evidence" / "l2-slices"
WORK = Path("/mnt/c/Users/Administrator/Documents/c-to-rust-l2-work")

SQLITE = Path("/mnt/c/Users/Administrator/Documents/c-to-rust-l1-work/storage-runtime/runs/run-20260624T011503Z/sqlite")
ZLIB_NG = Path("/mnt/c/Users/Administrator/Documents/c-to-rust-l1-work/compression-image/run-20260624-091638/zlib-ng")
ZSTD = Path("/mnt/c/Users/Administrator/Documents/c-to-rust-l1-work/compression-image/run-20260624-091638/zstd")


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def require_path(path: Path, description: str) -> None:
    if not path.exists():
        raise RuntimeError(f"missing {description}: {path}")


def preflight() -> None:
    if os.name == "nt":
        raise RuntimeError("generate_oracles.py must run under WSL/Linux because oracle paths use /mnt/c")
    if shutil.which("cc") is None:
        raise RuntimeError("missing C compiler: cc")
    require_path(SQLITE / "sqlite3.c", "SQLite amalgamation")
    require_path(ZLIB_NG / "build" / "libz.a", "zlib-ng static library")
    require_path(ZLIB_NG / "build" / "zlib.h", "zlib-ng generated header")
    require_path(ZSTD / "lib" / "common" / "xxhash.c", "zstd xxhash source")
    require_path(ZSTD / "lib" / "common" / "xxhash.h", "zstd xxhash header")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def hex_bytes(data: bytes) -> str:
    return data.hex()


def generate_sqlite() -> dict:
    work = WORK / "sqlite-varint"
    work.mkdir(parents=True, exist_ok=True)
    c_path = work / "sqlite_varint_oracle.c"
    out_path = work / "sqlite_varint_oracle"
    values = [0, 1, 2, 10, 63, 64, 65, 126, 127, 128, 129]
    for k in range(1, 9):
        base = (1 << (7 * k))
        values.extend([base - 1, base, base + 1])
    values.extend([
        4_294_967_295,
        4_294_967_296,
        9_223_372_036_854_775_807,
        9_223_372_036_854_775_808,
        18_446_744_073_709_551_614,
        18_446_744_073_709_551_615,
    ])
    values = sorted(set(values))
    value_list = ", ".join(f"{v}ULL" for v in values)
    write(
        c_path,
        f"""
#include <stdio.h>
#include <stdint.h>
#include "sqlite3.h"

extern int sqlite3PutVarint(unsigned char*, sqlite3_uint64);
extern unsigned char sqlite3GetVarint(const unsigned char*, sqlite3_uint64*);

static void print_hex(const unsigned char *p, int n) {{
  for (int i = 0; i < n; i++) printf("%02x", p[i]);
}}

int main(void) {{
  sqlite3_uint64 values[] = {{ {value_list} }};
  int n = (int)(sizeof(values) / sizeof(values[0]));
  printf("[\\n");
  for (int i = 0; i < n; i++) {{
    unsigned char buf[16] = {{0}};
    sqlite3_uint64 decoded = 0;
    int used = sqlite3PutVarint(buf, values[i]);
    unsigned char decoded_used = sqlite3GetVarint(buf, &decoded);
    printf("  {{\\"id\\":\\"sqlite-varint-%d\\",\\"value\\":%llu,\\"encoded_hex\\":\\"", i, (unsigned long long)values[i]);
    print_hex(buf, used);
    printf("\\",\\"bytes_used\\":%d,\\"decoded_value\\":%llu,\\"decoded_bytes\\":%u}}%s\\n",
      used, (unsigned long long)decoded, (unsigned)decoded_used, i + 1 == n ? "" : ",");
  }}
  printf("]\\n");
  return 0;
}}
""".strip()
        + "\n",
    )
    compile_cmd = [
        "cc",
        "-std=c99",
        "-O2",
        "-DSQLITE_PRIVATE=",
        "-DSQLITE_THREADSAFE=0",
        "-DSQLITE_OMIT_LOAD_EXTENSION",
        "-I",
        str(SQLITE),
        str(SQLITE / "sqlite3.c"),
        str(c_path),
        "-o",
        str(out_path),
    ]
    compiled = run(compile_cmd)
    if compiled.returncode != 0:
        raise RuntimeError(compiled.stderr)
    executed = run([str(out_path)])
    if executed.returncode != 0:
        raise RuntimeError(executed.stderr)
    fixture = FIXTURES / "sqlite-varint-c-oracle.json"
    write(fixture, executed.stdout)
    return {
        "schema_version": 1,
        "project_id": "sqlite",
        "slice_id": "sqlite-varint",
        "source_commit": "99a92ee66d80d519851015cf27def1c54e7a2037",
        "c_source_boundary": "sqlite3PutVarint/sqlite3GetVarint from sqlite3.c",
        "compile_command": " ".join(compile_cmd),
        "execution_environment": "WSL/Linux C toolchain",
        "fixture": str(fixture.relative_to(REPO)).replace("\\", "/"),
        "case_count": len(json.loads(executed.stdout)),
        "status": "passed",
        "toolchain_status": "C_ORACLE_GENERATED",
    }


def make_pattern(kind: str, length: int) -> bytes:
    if kind == "empty":
        return b""
    if kind == "ascii":
        return b"zlib checksum fixture"[:length]
    if kind == "zero":
        return bytes([0]) * length
    if kind == "ff":
        return bytes([0xFF]) * length
    if kind == "inc":
        return bytes((i % 256 for i in range(length)))
    if kind == "lcg":
        value = 0x12345678
        out = []
        for _ in range(length):
            value = (1103515245 * value + 12345) & 0xFFFFFFFF
            out.append((value >> 16) & 0xFF)
        return bytes(out)
    raise ValueError(kind)


def make_lcg_pattern(seed: int, length: int) -> bytes:
    value = seed & 0xFFFFFFFF
    out = []
    for _ in range(length):
        value = (1103515245 * value + 12345) & 0xFFFFFFFF
        out.append((value >> 16) & 0xFF)
    return bytes(out)


def generate_zlib() -> dict:
    work = WORK / "zlib-adler32"
    work.mkdir(parents=True, exist_ok=True)
    c_path = work / "zlib_adler32_oracle.c"
    out_path = work / "zlib_adler32_oracle"
    vectors = [
        ("empty", "empty", 0),
        ("ascii", "ascii", 21),
        ("inc_256", "inc", 256),
        ("nmax_5552", "inc", 5552),
        ("nmax_plus_1", "inc", 5553),
        ("lcg_32768", "lcg", 32768),
        ("ff_128", "ff", 128),
    ]
    deterministic_lengths = [
        0, 1, 2, 3, 4, 15, 16, 31, 32, 63, 64, 127, 128,
        255, 256, 511, 512, 1023, 1024, 2047, 2048,
        5551, 5552, 5553, 8191, 8192,
    ]
    deterministic_seeds = [
        0x00000001,
        0x12345678,
        0x5A5A5A5A,
        0xC0FFEE00,
        0xFFFFFFFF,
    ]
    for seed in deterministic_seeds:
        for length in deterministic_lengths:
            vectors.append((f"lcg_{seed:08x}_{length}", "lcg_seeded", length, seed))
    static_rows = []
    for vector in vectors:
        if len(vector) == 3:
            case_id, kind, length = vector
            data = make_pattern(kind, length)
        elif len(vector) == 4:
            case_id, kind, length, seed = vector
            if kind != "lcg_seeded":
                raise ValueError(kind)
            data = make_lcg_pattern(seed, length)
        else:
            raise ValueError(f"unsupported zlib vector shape: {vector}")
        static_rows.append((case_id, hex_bytes(data)))
    if len(static_rows) != 137:
        raise RuntimeError(f"zlib-adler32 corpus must contain 137 cases, got {len(static_rows)}")
    ids = [case_id for case_id, _ in static_rows]
    if len(ids) != len(set(ids)):
        raise RuntimeError("zlib-adler32 corpus case ids must be unique")
    rows = "\n".join(
        f'  {{"{case_id}", "{hex_data}"}},' for case_id, hex_data in static_rows
    )
    write(
        c_path,
        f"""
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "zlib.h"

struct row {{ const char *id; const char *hex; }};
static struct row rows[] = {{
{rows}
}};

static unsigned char hex_nibble(char c) {{
  if (c >= '0' && c <= '9') return (unsigned char)(c - '0');
  if (c >= 'a' && c <= 'f') return (unsigned char)(10 + c - 'a');
  if (c >= 'A' && c <= 'F') return (unsigned char)(10 + c - 'A');
  return 0;
}}

int main(void) {{
  int n = (int)(sizeof(rows) / sizeof(rows[0]));
  printf("[\\n");
  for (int i = 0; i < n; i++) {{
    size_t hex_len = strlen(rows[i].hex);
    size_t len = hex_len / 2;
    unsigned char *buf = malloc(len ? len : 1);
    for (size_t j = 0; j < len; j++) buf[j] = (hex_nibble(rows[i].hex[j*2]) << 4) | hex_nibble(rows[i].hex[j*2+1]);
    unsigned long init = adler32(0L, Z_NULL, 0);
    unsigned long value = adler32_z(init, buf, len);
    printf("  {{\\"id\\":\\"%s\\",\\"input_hex\\":\\"%s\\",\\"seed\\":null,\\"value\\":%lu,\\"value_hex\\":\\"0x%08lx\\"}}%s\\n",
      rows[i].id, rows[i].hex, value, value, i + 1 == n ? "" : ",");
    free(buf);
  }}
  printf("]\\n");
  return 0;
}}
""".strip()
        + "\n",
    )
    compile_cmd = [
        "cc",
        str(c_path),
        "-std=c11",
        "-O2",
        "-I",
        str(ZLIB_NG / "build"),
        "-I",
        str(ZLIB_NG),
        str(ZLIB_NG / "build" / "libz.a"),
        "-o",
        str(out_path),
    ]
    compiled = run(compile_cmd)
    if compiled.returncode != 0:
        raise RuntimeError(compiled.stderr)
    executed = run([str(out_path)])
    if executed.returncode != 0:
        raise RuntimeError(executed.stderr)
    fixture = FIXTURES / "zlib-adler32-c-oracle.json"
    write(fixture, executed.stdout)
    return {
        "schema_version": 1,
        "project_id": "zlib-ng",
        "slice_id": "zlib-adler32",
        "source_commit": "d40f29fd42ed9158e3eb3e221dca50e4b627f7a8",
        "c_source_boundary": "adler32_z from zlib-ng build/libz.a",
        "compile_command": " ".join(compile_cmd),
        "execution_environment": "WSL/Linux C toolchain",
        "fixture": str(fixture.relative_to(REPO)).replace("\\", "/"),
        "case_count": len(json.loads(executed.stdout)),
        "status": "passed",
        "toolchain_status": "C_ORACLE_GENERATED",
    }


def generate_zstd() -> dict:
    work = WORK / "zstd-xxh32"
    work.mkdir(parents=True, exist_ok=True)
    c_path = work / "zstd_xxh32_oracle.c"
    out_path = work / "zstd_xxh32_oracle"
    cases = []
    for case_id, kind, length in [
        ("empty", "empty", 0),
        ("one", "inc", 1),
        ("fifteen", "inc", 15),
        ("sixteen", "inc", 16),
        ("seventeen", "inc", 17),
        ("ascii", "ascii", 22),
        ("inc_128", "inc", 128),
        ("lcg_1024", "lcg", 1024),
    ]:
        data = make_pattern(kind, length)
        for seed in [0, 1, 0x9E3779B1, 0xFFFFFFFF]:
            cases.append((f"{case_id}_seed_{seed:08x}", hex_bytes(data), seed))
    rows = "\n".join(
        f'  {{"{case_id}", "{hex_data}", {seed}U}},' for case_id, hex_data, seed in cases
    )
    write(
        c_path,
        f"""
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "xxhash.h"

struct row {{ const char *id; const char *hex; uint32_t seed; }};
static struct row rows[] = {{
{rows}
}};

static unsigned char hex_nibble(char c) {{
  if (c >= '0' && c <= '9') return (unsigned char)(c - '0');
  if (c >= 'a' && c <= 'f') return (unsigned char)(10 + c - 'a');
  if (c >= 'A' && c <= 'F') return (unsigned char)(10 + c - 'A');
  return 0;
}}

int main(void) {{
  int n = (int)(sizeof(rows) / sizeof(rows[0]));
  printf("[\\n");
  for (int i = 0; i < n; i++) {{
    size_t hex_len = strlen(rows[i].hex);
    size_t len = hex_len / 2;
    unsigned char *buf = malloc(len ? len : 1);
    for (size_t j = 0; j < len; j++) buf[j] = (hex_nibble(rows[i].hex[j*2]) << 4) | hex_nibble(rows[i].hex[j*2+1]);
    uint32_t value = XXH32(buf, len, rows[i].seed);
    printf("  {{\\"id\\":\\"%s\\",\\"input_hex\\":\\"%s\\",\\"seed\\":%u,\\"value\\":%u,\\"value_hex\\":\\"0x%08x\\"}}%s\\n",
      rows[i].id, rows[i].hex, rows[i].seed, value, value, i + 1 == n ? "" : ",");
    free(buf);
  }}
  printf("]\\n");
  return 0;
}}
""".strip()
        + "\n",
    )
    compile_cmd = [
        "cc",
        "-std=c99",
        "-O2",
        "-Wall",
        "-Wextra",
        "-DXXH_NAMESPACE=ZSTD_",
        "-I",
        str(ZSTD / "lib" / "common"),
        str(c_path),
        str(ZSTD / "lib" / "common" / "xxhash.c"),
        "-o",
        str(out_path),
    ]
    compiled = run(compile_cmd)
    if compiled.returncode != 0:
        raise RuntimeError(compiled.stderr)
    executed = run([str(out_path)])
    if executed.returncode != 0:
        raise RuntimeError(executed.stderr)
    fixture = FIXTURES / "zstd-xxh32-c-oracle.json"
    write(fixture, executed.stdout)
    return {
        "schema_version": 1,
        "project_id": "zstd",
        "slice_id": "zstd-xxh32",
        "source_commit": "5233c58e6ca0b1c4c6b353ad79649191ed195bdc",
        "c_source_boundary": "XXH32 from zstd lib/common/xxhash.c",
        "compile_command": " ".join(compile_cmd),
        "execution_environment": "WSL/Linux C toolchain",
        "fixture": str(fixture.relative_to(REPO)).replace("\\", "/"),
        "case_count": len(json.loads(executed.stdout)),
        "status": "passed",
        "toolchain_status": "C_ORACLE_GENERATED",
    }


def main() -> None:
    preflight()
    FIXTURES.mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    results = [generate_sqlite(), generate_zlib(), generate_zstd()]
    for result in results:
        path = EVIDENCE / f"{result['slice_id']}-oracle.json"
        write(path, json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    summary = {
        "schema_version": 1,
        "command": "generate-l2-c-oracles",
        "status": "passed",
        "slice_count": len(results),
        "slices": results,
        "reporting_boundary": "C oracle fixtures cover only the named slice functions and generated input corpus.",
    }
    write(EVIDENCE / "c-oracle-summary.json", json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
