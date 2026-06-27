# Build Capture and C2Rust Baseline

中文说明：C2Rust 在本项目中只作为 baseline/oracle，不作为最终 `flashDB_rust` 交付代码。最终代码必须走 Rust crate 骨架、安全 API、Rust 测试、差分验证和 unsafe 审计。

English summary: C2Rust is used only as a baseline/oracle. The final Rust project must be produced through skeleton-first migration, safe APIs, tests, differential verification, and unsafe audit.

## FlashDB Source

- Clone command: `git clone https://gitcode.com/xwxf/FlashDB.git`
- Local path: `sources/FlashDB`
- Recorded commit: `93d175549da579b8abac07bd175ce4c3f9dde829`
- Main source areas: `inc`, `src`, `tests`, `samples`, `demos`

## Feature Matrix for First Run

The first verified FlashDB test profile is based on `tests/fdb_cfg.h`:

- `FDB_USING_KVDB`: enabled
- `FDB_USING_TSDB`: enabled
- `FDB_USING_FILE_POSIX_MODE`: enabled
- `FDB_WRITE_GRAN`: `1`

Relevant public APIs observed from `inc/flashdb.h`:

- KVDB: `fdb_kvdb_init`, `fdb_kv_set`, `fdb_kv_get`, `fdb_kv_set_blob`, `fdb_kv_get_blob`, `fdb_kv_del`, iterator APIs
- TSDB: `fdb_tsl_append`, `fdb_tsl_iter`, `fdb_tsl_iter_by_time`, `fdb_tsl_query_count`, `fdb_tsl_set_status`, `fdb_tsl_clean`

## Expected `compile_commands.json` Workflow

Preferred Linux or WSL workflow:

```bash
git clone https://gitcode.com/xwxf/FlashDB.git
cd FlashDB/tests
bear -- make clean all
```

Competition environment profile:

- Profile: `config/competition-env/environment.json`
- Ubuntu 24.04.4, gcc/g++ 13.3.0, GNU Make 4.3.
- Go is not installed.
- CMake is not found, so default competition build capture and C oracle paths must not require CMake.
- Package-manager access should use the Huawei mirrors recorded in the profile.

If CMake is introduced later, treat it as a non-default path outside the current competition profile:

```bash
cmake -S . -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
cmake --build build
```

Acceptance criteria:

- `compile_commands.json` must include every C file used by the selected profile.
- Macro definitions and include paths must match the selected `fdb_cfg.h`.
- The generated file must be stored with a hash and command log.

## C2Rust Baseline Command

Preferred command:

```bash
c2rust transpile --emit-build-files path/to/compile_commands.json
```

The baseline record must store:

- C2Rust executable version or source-tree hashes
- `compile_commands.json` hash
- exact command line
- generated file hashes
- transpiler warnings
- skipped files/functions
- environment variables relevant to clang/libclang

## Current Host Constraint

Native Windows PATH currently does not expose `cmake`, `clang`, `bear`, `intercept-build`, or `c2rust`. Therefore C2Rust generation is not reproducible on the native host yet. The valid fallback is:

1. Use WSL/Linux for C2Rust baseline generation, or
2. Use the original C FlashDB implementation as the semantic oracle until the baseline is available.

This is an engineering limitation, not a design failure. The migration remains valid only when C/Rust differential tests run against a recorded oracle.

## C Oracle Fallback

When C2Rust cannot run:

- Compile the original FlashDB test profile.
- Drive C and Rust with the same operation sequence.
- Compare return codes, values, error mappings, iteration order where defined, GC effects, reopen behavior, and flash/file image bytes.
- Record every accepted mapping explicitly.

LLM summaries, manual inspection, and cached C2Rust-like output are not equivalence evidence.
