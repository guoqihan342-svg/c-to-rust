# FlashDB C Oracle Contract

This directory contains the C-side oracle producer for the later Rust/C differential harness. It is intentionally small: one deterministic C runner, one build file, and one Linux/CI shell entrypoint.

## Source Pin

- Clone URL: `https://gitcode.com/xwxf/FlashDB.git`
- Fixed commit: `93d175549da579b8abac07bd175ce4c3f9dde829`
- Flash profile: POSIX file mode, `FDB_USING_KVDB`, `FDB_USING_TSDB`, `FDB_WRITE_GRAN 1`
- Storage geometry: file mode `sec_size 4096`

## Local Status

This native Windows host does not currently have the required C toolchain on PATH. The expected local status for this change is:

```text
SKIPPED_LOCAL_NO_C_TOOLCHAIN
```

Do not treat this repository state as having generated or verified a real C oracle. A real oracle JSON must be produced on Linux/WSL/CI with `git`, `gcc`, and `make`.

## Linux/CI Usage

From the repository root:

```sh
sh flashDB_rust/oracle/generate_c_oracle.sh
```

Optional environment overrides:

```sh
CC=clang OUT_FILE=/tmp/flashdb_c_oracle.json sh flashDB_rust/oracle/generate_c_oracle.sh
```

The script clones FlashDB at the fixed commit, builds `flashdb_c_oracle.c` against the public FlashDB sources, runs it in a clean work directory, and writes deterministic JSON.

## Covered Public APIs

KVDB coverage:

- `fdb_kvdb_init`
- `fdb_kv_set`
- `fdb_kv_get`
- `fdb_kv_set_blob`
- `fdb_kv_get_blob`
- `fdb_kv_del`
- `fdb_kv_iterator_init`
- `fdb_kv_iterate`

TSDB coverage:

- `fdb_tsdb_init`
- `fdb_tsl_append`
- `fdb_tsl_append_with_ts`
- `fdb_tsl_iter_by_time`
- `fdb_tsl_query_count`
- `fdb_tsl_set_status`

The runner writes FlashDB diagnostics to stderr and oracle JSON to stdout. The JSON reports `toolchain_status: "C_ORACLE_GENERATED"` only when the C executable actually runs.
