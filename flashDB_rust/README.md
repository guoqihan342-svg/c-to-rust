英文镜像见 `README.en.md`。

# flashDB_rust

中文：这是 FlashDB C-to-Rust 迁移的第一阶段 Rust 骨架。当前目标是可编译、可测试、host-verifiable，而不是声明完整 FlashDB 语义等价。

English: this is the first Rust skeleton for the FlashDB C-to-Rust migration. The current goal is a compilable and testable host-verifiable foundation, not full FlashDB semantic equivalence.

## Scope

- Rust-native safe API
- 当前 unsafe-scan 结果：当前 host-verifiable skeleton 中 0 个 first-party non-test `unsafe` findings。
- English: current unsafe-scan result is 0 first-party non-test `unsafe` findings in the present host-verifiable skeleton.
- 项目政策：first-party non-test `unsafe` 必须低于 repo budget；未来任何 FFI、C ABI、硬件、volatile、RTOS 或并发 unsafe 边界都必须先进入 ledger，再声明支持。
- English: project policy is to keep first-party non-test `unsafe` below the repo budget and ledger any future FFI, C ABI, hardware, volatile, RTOS, or concurrency unsafe boundary before claiming it is supported.
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

Boundary note / 边界说明:

- 0 finding 的 unsafe scan 不是生产级 FlashDB 安全性、硬件安全性、C ABI 兼容性或完整语义等价证明。
- The zero-finding unsafe scan is not a proof of production FlashDB safety, hardware safety, C ABI compatibility, or full semantic equivalence.
- Rust skeleton 是手写 seed code 和验证脚手架；除非某个函数切片绑定 translator-generated candidate 和 accepted evidence，否则不能算自动翻译产物。
- The Rust skeleton is handwritten seed code plus validation scaffolding. It is not counted as automatic translator output unless a specific function slice is tied to a translator-generated candidate and accepted evidence.

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
- C oracle producer execution through `FLASHDB_C_ORACLE_PRODUCER=./oracle/generate_c_oracle.sh` on Ubuntu CI
- Rust-vs-C schema-aware diff for `fixtures/c-rust-smoke.json`
- `cargo run --release -- stress --loops 10000 --seed 1 --backend file --scenario all --report target/verification/ci/stress-10000.json`

Evidence is written under `target/verification/ci/` and uploaded as a workflow artifact. The C oracle path never substitutes Rust-only results for C equivalence. If `gcc` is missing, the CI script writes `SKIPPED_C_ORACLE_NO_GCC`. In GitHub Actions the producer is configured by default, so a C oracle producer build, runtime failure, or Rust-vs-C behavior mismatch fails the job and leaves failure evidence. A manually run local Linux script without `FLASHDB_C_ORACLE_PRODUCER` still writes `SKIPPED_C_ORACLE_PRODUCER_NOT_CONFIGURED`.

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
