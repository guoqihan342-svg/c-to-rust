## Why

`design-c2rust-migration-agent` 已经完成 Agent 设计，但仓库里还没有实际可编译的 `flashDB_rust` 工程。继续推进迁移前，必须先落地一个小而精、可编译、可测试、可循环验证的 Rust 骨架，作为后续 KVDB/TSDB 渐进迁移和 10000 轮压力验证的承载点。

English summary: the design change is complete, but there is still no compilable `flashDB_rust` project. This change creates the first runnable Rust skeleton and verification loop foundation.

## What Changes

- Create `flashDB_rust` as a Rust library-first project with a small CLI executable.
- Add core modules for `config`, `types`, `flash`, `format`, `kvdb`, `tsdb`, `ffi`, and CLI entrypoints.
- Implement safe host-verifiable foundations: memory backend, file-mode backend, core error types, address wrappers, CRC/alignment helpers, simple KVDB and basic TSDB behavior.
- Add Rust unit and integration tests covering format helpers, memory/file backends, KVDB main paths, TSDB basic paths, persistence/reopen behavior, and abnormal/corruption scenarios.
- Add a verification runner that can execute deterministic loop tests, abnormal data tests, persistence/reliability tests, branch-oriented scenario tests, and performance smoke tests.
- Keep first-party unsafe at 0% for this skeleton unless a later task explicitly justifies and registers unsafe.
- Add documentation and scripts so later agents can run fast checks, extended checks, and long 10000-iteration stress runs.

## Capabilities

### New Capabilities

- `flashdb-rust-skeleton`: Covers the initial `flashDB_rust` crate layout, safe API, host storage backends, KVDB/TSDB seed behavior, CLI smoke executable, and unsafe boundary.
- `verification-loop`: Covers Rust tests, deterministic stress loops, abnormal data cases, persistence/reliability checks, performance smoke, and commands for long verification runs.

### Modified Capabilities

- None.

## Impact

- Adds a new Rust project under `flashDB_rust/`.
- Adds OpenSpec implementation artifacts under `openspec/changes/build-flashdb-rust-skeleton/`.
- Adds verification scripts or CLI commands for repeatable local validation.
- Uses Rust stable tooling available on this host (`rustc 1.95.0`, `cargo 1.95.0`).
- Does not require C2Rust, clang, cmake, nextest, llvm-cov, cargo-fuzz, or cargo-geiger for the first pass, because those optional tools are not currently installed on native Windows.
- Does not claim full FlashDB equivalence yet; this change establishes the executable Rust foundation and local verification loop required for subsequent deeper migration changes.
