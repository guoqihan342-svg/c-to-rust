# flashDB_rust

中文：这是 FlashDB C-to-Rust 迁移的第一阶段 Rust 骨架。当前目标是可编译、可测试、host-verifiable，而不是声明完整 FlashDB 语义等价。

English: this is the first Rust skeleton for the FlashDB C-to-Rust migration. The current goal is a compilable and testable host-verifiable foundation, not full FlashDB semantic equivalence.

## Scope

- Rust-native safe API
- 0% first-party non-test unsafe
- Memory flash backend
- File-backed flash backend
- KVDB seed behavior: set/get/delete/iterate/compact/reopen
- TSDB seed behavior: append/query/count/status/reopen
- CLI smoke/stress/inspect-image/unsafe-scan
- Deterministic stress loop with configurable seed and loop count

Deferred:

- C ABI compatibility
- Byte-for-byte FlashDB on-disk layout equivalence
- C2Rust baseline generation
- FAL, RTOS, Zephyr, and hardware ports
- async or multithreaded storage semantics

## Fast Verification

```powershell
cargo fmt -- --check
cargo check
cargo test
cargo run -- smoke --backend memory --report target/verification/smoke-memory.json
cargo run -- stress --loops 20 --seed 1 --backend memory --scenario all --report target/verification/stress-smoke.json
cargo run -- replay --fixture fixtures/ci-smoke.json --report target/verification/rust-fixture-replay.json
cargo run -- diff --rust-report target/verification/rust-fixture-replay.json --oracle-report fixtures/ci-smoke.expected.json --report target/verification/rust-fixture-diff.json
cargo run -- unsafe-scan
```

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\flashDB_rust\scripts\verify.ps1
```

## Long Run Command

This command is the required 10000-loop entrypoint. Do not claim it passed unless it has actually completed and the report exists.

```powershell
cargo run --release -- stress --loops 10000 --seed 1 --backend file --scenario all --report target/verification/stress-10000.json
```

By default `FileFlash::flush` records logical flush operations and relies on normal file close/reopen behavior for fast host verification. Set `FLASHDB_RUST_SYNC_ON_FLUSH=1` when a run must force OS-level `sync_all` on every flush.

## Tool Fallbacks

- No `cargo-nextest`: use `cargo test`.
- No `cargo-llvm-cov`: use scenario matrix and test names; do not claim coverage percentage.
- No `cargo-fuzz`: use abnormal/corrupt fixtures and deterministic stress loops.
- No `cargo-geiger`: use `cargo run -- unsafe-scan` and `rg "\bunsafe\b" src`.
- No native C2Rust/clang/cmake/bear: keep C oracle and C2Rust baseline for later WSL/Linux verification.

## CI Verification

GitHub Actions runs `.github/workflows/flashdb-rust-ci.yml` on Ubuntu. The workflow calls:

```bash
bash scripts/verify-ci.sh
```

The CI script performs:

- `cargo fmt -- --check`
- `cargo check`
- `cargo test`
- CLI smoke and short stress reports
- `cargo run -- unsafe-scan`
- Rust fixture replay and Rust report diff through the mainline fixture CLI contract
- optional C oracle producer execution only when `gcc` is available and `FLASHDB_C_ORACLE_PRODUCER` is configured
- `cargo run --release -- stress --loops 10000 --seed 1 --backend file --scenario all --report target/verification/ci/stress-10000.json`

Evidence is written under `target/verification/ci/` and uploaded as a workflow artifact. The C oracle path never substitutes Rust-only results for C equivalence. If `gcc` is missing, the CI script writes `SKIPPED_C_ORACLE_NO_GCC`. If `gcc` exists but no producer is configured, it writes `SKIPPED_C_ORACLE_PRODUCER_NOT_CONFIGURED`.

## Native Windows Verification

This host does not have a native C compiler installed. The PowerShell verification script records that fact explicitly:

```powershell
powershell -ExecutionPolicy Bypass -File .\flashDB_rust\scripts\verify.ps1
```

Expected local C-oracle evidence marker:

```text
SKIPPED_LOCAL_NO_C_TOOLCHAIN
```

That marker means the local run did not execute the C oracle producer and must not be treated as C/Rust equivalence evidence. Use Ubuntu CI, WSL, or another Linux environment with `gcc` and a configured `FLASHDB_C_ORACLE_PRODUCER` for real C oracle production.

Run the long local stress check only when you intentionally want the full 10000-loop release run:

```powershell
powershell -ExecutionPolicy Bypass -File .\flashDB_rust\scripts\verify.ps1 -LongStress
```

## Fixture Replay and Diff

The Rust CLI provides deterministic fixture replay and report comparison:

- `cargo run -- replay --fixture <path> --report <path>`
- `cargo run -- diff --rust-report <path> --oracle-report <path> --report <path>`

CI-compatible aliases are also supported:

- `cargo run -- fixture-replay --fixture <path> --report <path>`
- `cargo run -- diff-report --expected <path> --actual <path> --report <path>`

Default fixture inputs are:

- `fixtures/ci-smoke.json`
- `fixtures/ci-smoke.expected.json`

Override them in CI with `FLASHDB_RUST_FIXTURE` and `FLASHDB_RUST_EXPECTED_REPORT` if the mainline fixture assets use different names.
