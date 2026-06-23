## Why

上一轮 CI 已经变绿，但 `FLASHDB_C_ORACLE_PRODUCER` 没有配置，C oracle producer 实际没有运行。这会让分支看起来验证完整，却仍缺少真实 C oracle 证据；现在必须把 CI 从“可选入口”推进到“Ubuntu 有工具链时真实生成 oracle，失败就失败”的门禁。

English summary: CI currently proves Rust replay/diff and long stress, but not real C oracle generation. This change makes C oracle generation an enforced CI path when the Ubuntu toolchain is available.

## What Changes

- Configure GitHub Actions to run the repository C oracle producer script by default.
- Change CI script behavior so configured C oracle producer failures fail the job instead of being ignored.
- Keep only true missing-toolchain cases as explicit skip evidence.
- Add evidence that distinguishes `C_ORACLE_PRODUCER_PASSED`, `SKIPPED_C_ORACLE_NO_GCC`, and actual producer failure.
- Keep local native Windows behavior unchanged: no C compiler still records `SKIPPED_LOCAL_NO_C_TOOLCHAIN`.

## Capabilities

### New Capabilities

- `ci-c-oracle-verification`: Covers CI behavior for real C oracle generation, producer configuration, failure propagation, and evidence recording.

### Modified Capabilities

- None.

## Impact

- Updates `.github/workflows/flashdb-rust-ci.yml`.
- Updates `flashDB_rust/scripts/verify-ci.sh`.
- May update `flashDB_rust/oracle/` scripts if CLI argument handling or evidence output needs tightening.
- Adds OpenSpec artifacts under `openspec/changes/require-ci-c-oracle-generation/`.
- Does not claim full C/Rust semantic equivalence; it only proves the C oracle producer is actually built and run in CI.
