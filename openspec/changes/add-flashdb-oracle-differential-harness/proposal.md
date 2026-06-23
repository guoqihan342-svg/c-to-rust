## Why

`flashDB_rust` 已经具备可编译 Rust 骨架和 10000-loop 本地压力证据，但它还不能证明与原始 FlashDB C 行为等价。现在需要补上可复用 fixture、Rust replay、C oracle 生成契约和差分报告，让后续单点渐进式重构有可回放、可定位、可自愈的闭环。

English summary: the current Rust skeleton is runnable, but it lacks a reusable C/Rust oracle contract. This change adds the deterministic differential harness needed before claiming semantic equivalence.

## What Changes

- Add deterministic fixture and oracle report schemas for KVDB, TSDB, persistence/reopen, abnormal data, and corrupted-image paths.
- Add Rust CLI support for fixture replay and differential report comparison.
- Add stable Rust error codes and per-step replay output so error stacks can drive precise self-healing patches.
- Add C oracle generation contract files and scripts for environments with a C toolchain, while recording `SKIPPED_LOCAL_NO_C_TOOLCHAIN` on this native Windows host.
- Add evidence ledger output for fixture hash, Rust report hash, optional C oracle report hash, accepted differences, toolchain status, and comparison result.
- Add CI or scripted verification hooks for Rust replay/diff and long 10000-loop stress without introducing heavy dependencies.

## Capabilities

### New Capabilities

- `flashdb-oracle-fixtures`: Defines deterministic operation fixtures, expected oracle report shape, normalized comparison rules, and accepted-difference records.
- `flashdb-differential-harness`: Covers Rust fixture replay, machine-readable per-step reports, C/Rust oracle comparison, and precise mismatch output.
- `flashdb-oracle-generation-contract`: Covers the C oracle producer contract, fixed FlashDB source commit, required toolchain checks, and skip evidence when C tools are unavailable.
- `equivalence-evidence-ledger`: Covers durable evidence files that record fixture provenance, report hashes, toolchain state, comparison status, and remaining equivalence gaps.

### Modified Capabilities

- None.

## Impact

- Updates `flashDB_rust` CLI behavior and tests.
- Adds fixture and oracle evidence files under `flashDB_rust/fixtures/` and `flashDB_rust/evidence/`.
- Adds C oracle contract files under `flashDB_rust/oracle/`.
- May add CI workflow and verification script updates.
- Keeps the dependency set small and avoids async/multithreaded runtime changes in this step.
- Does not claim full byte-for-byte FlashDB layout equivalence until a real C oracle run is generated and compared.
