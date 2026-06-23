## Context

`design-c2rust-migration-agent` 已完成设计与任务闭环，但当前仓库还没有 `flashDB_rust` 目录，也没有任何 Rust 构建、测试或长循环验证入口。本 change 把设计落到第一份可运行工程上。

FlashDB 当前基线：

- Source path: `sources/FlashDB`
- Source commit: `93d175549da579b8abac07bd175ce4c3f9dde829`
- Test Makefile compiles `src/fdb.c`, `src/fdb_file.c`, `src/fdb_kvdb.c`, `src/fdb_tsdb.c`, and `src/fdb_utils.c`
- Test profile enables `FDB_USING_KVDB`, `FDB_USING_TSDB`, `FDB_USING_FILE_POSIX_MODE`, and `FDB_WRITE_GRAN 1`
- Public C APIs include KVDB set/get/blob/delete/iterate and TSDB append/query/count/status operations

当前 Windows host 可用 Rust stable 工具，但缺少 native `c2rust`, `clang`, `cmake`, `bear`, `nextest`, `llvm-cov`, `cargo-fuzz`, `cargo-geiger`。因此本 change 的基础门禁必须只依赖 `cargo check`, `cargo test`, `cargo run`, PowerShell/Rust 标准库；扩展工具只作为后续增强。

## Goals / Non-Goals

**Goals:**

- Create a compilable `flashDB_rust` Rust project with library and CLI binary.
- Provide safe Rust-native APIs for host-verifiable KVDB and basic TSDB behavior.
- Implement memory and file-mode storage backends with deterministic behavior.
- Implement small format helpers for CRC32, alignment, header/blob encoding, and status/error modeling.
- Add Rust unit/integration tests for normal, abnormal, persistence, and branch-oriented scenarios.
- Add a verification/stress runner that can execute configurable loop counts, including a 10000-iteration mode.
- Keep first-party unsafe at 0% in this skeleton.
- Keep dependencies small and auditable.

**Non-Goals:**

- This change does not claim full FlashDB semantic equivalence.
- This change does not run a real C2Rust baseline because native C2Rust dependencies are missing.
- This change does not migrate hardware flash, FAL, RTOS, Zephyr, full macro matrix, or full C ABI compatibility.
- This change does not add async/multithreaded storage semantics.
- This change does not require external fuzz/coverage tools for baseline verification.

## Decisions

### Decision 1: Rust crate stays dependency-light

Use a simple Cargo project with `clap` for the CLI and `serde`/`serde_json` only if structured fixture/report IO is needed. Do not introduce async runtimes, database crates, or heavy test frameworks in the first skeleton.

Alternative considered: add `tokio`, `proptest`, `criterion`, and fuzz harness immediately. Rejected for the first pass because optional tools are not installed and the user asked for a small, fast, safe project. The skeleton can expose hooks for those tools without depending on them immediately.

### Decision 2: Host-verifiable FlashDevice abstraction

Define a `FlashDevice` trait with read/write/erase/flush and operation counters. Provide:

- `MemoryFlash`: deterministic in-memory backend.
- `FileFlash`: file-backed backend for persistence and reopen smoke tests.

This keeps future C/Rust differential tests focused on storage semantics and flash images.

### Decision 3: Safe Rust API first

Expose Rust-native `KvDb` and `TsDb` types with `Result`, `Option`, slices, owned values, and iterators. No raw pointers appear in public Rust APIs. The `ffi` module exists as an explicit boundary but remains empty or minimal until a separate compatibility change.

### Decision 4: Simple but persistent seed implementation

The first implementation may use a compact deterministic record log rather than a full byte-for-byte FlashDB on-disk layout. It must still prove reopen behavior, delete behavior, corruption detection, capacity handling, CRC checks, and deterministic image hashing. Full FlashDB layout equivalence is deferred to later migration slices.

Alternative considered: copy the full FlashDB sector layout immediately. Rejected because the current goal needs a stable Rust project and verification loop first; full layout migration should happen slice by slice with differential fixtures.

### Decision 5: Verification runner is first-class

Add a CLI command or script that runs scenarios repeatedly with a seed and loop count. The same runner supports fast local checks and long 10000-iteration checks:

- normal production-like operation sequences
- abnormal/corrupt data sequences
- persistence/reopen sequences
- branch-oriented option combinations
- performance smoke counters

The runner must write a machine-readable report so future agents can compare evidence across runs.

## Risks / Trade-offs

- [Risk] Initial Rust persistence layout differs from C FlashDB. -> Mitigation: document it as seed behavior, not full equivalence; add later differential changes for C-compatible format.
- [Risk] 10000 loops may take too long on every turn. -> Mitigation: provide `--loops` and run a smaller verified sample locally, while preserving the exact 10000-loop command for long-run execution.
- [Risk] File-backed tests can be flaky if paths are reused. -> Mitigation: use isolated temp directories and deterministic cleanup.
- [Risk] The skeleton can become a toy unrelated to FlashDB. -> Mitigation: mirror FlashDB concepts: KVDB, TSDB, flash erase value, write granularity, sectors, CRC, reopen, status/error mapping.
- [Risk] Future agents may overuse unsafe or AI patches. -> Mitigation: keep unsafe at 0% and keep AI outside correctness evidence.

## Migration Plan

1. Create `flashDB_rust` Cargo project and module skeleton.
2. Implement core types, config, CRC/alignment helpers, memory flash, and file flash.
3. Implement seed KVDB and TSDB behavior with deterministic serialization.
4. Add CLI smoke/stress/report commands.
5. Add unit and integration tests.
6. Add verification script or documented command set.
7. Run `cargo fmt -- --check`, `cargo check`, `cargo test`, CLI smoke, stress sample, OpenSpec validation, and diff checks.

Rollback strategy: each implementation step must keep `cargo check` recoverable. If a change breaks compile or tests, revert only the current slice and keep earlier passing modules intact.

## Open Questions

- Whether the later full FlashDB-compatible persistent layout should be implemented directly in `format` or behind a versioned layout adapter.
- Whether 10000-loop validation should be run locally before GitHub push every time, or through CI/overnight workflow once the branch exists.
