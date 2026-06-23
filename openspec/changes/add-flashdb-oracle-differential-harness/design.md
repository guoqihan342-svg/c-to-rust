## Context

当前 `flashDB_rust` 已经有 Rust library、CLI、KVDB/TSDB seed 行为、file/memory backend、10000-loop stress 证据和 0 unsafe 证据。缺口是 C/Rust 等价验证还没有可回放的共同输入，也没有逐步输出、错误码、fixture hash、oracle hash 和 accepted differences 的统一台账。

Current state: the Rust project is host-verifiable, but it is not yet a semantic-equivalence harness. The next step is a small deterministic differential layer, not a full FlashDB byte layout rewrite.

约束：

- 本机 native Windows 只有 Rust/Cargo/OpenSpec 可用，缺少 `gcc`, `clang`, `cl`, `make`, `cmake`, `c2rust`。
- 原 FlashDB C oracle 必须绑定固定源版本 `93d175549da579b8abac07bd175ce4c3f9dde829`。
- `flashDB_rust` 继续保持小依赖集，优先标准库手写 schema/reporter，不引入 async runtime 或重型测试框架。
- 本 change 允许生成“C oracle producer 契约和脚本”，但本机不能把未运行的 C oracle 冒充为通过。

## Goals / Non-Goals

**Goals:**

- Define deterministic fixture files shared by C oracle producer and Rust replay consumer.
- Implement Rust replay and differential comparison so local Windows can validate Rust behavior against checked-in or externally generated oracle reports.
- Emit stable per-step result objects with operation id, operation name, status code, value/entries/hash where applicable, and error code when failed.
- Record evidence ledger files with fixture hash, Rust report hash, optional C report hash, toolchain status, comparison status, and accepted differences.
- Add C oracle generation contract files for a Linux/CI environment with a C compiler.
- Preserve 0 first-party unsafe in Rust sources unless later changes explicitly register and justify unsafe.

**Non-Goals:**

- This change does not complete byte-for-byte FlashDB storage layout equivalence.
- This change does not require native Windows C compilation to pass.
- This change does not add async, multithreaded replay, or caching infrastructure beyond deterministic fixture/report reuse.
- This change does not migrate FAL, RTOS, hardware flash, or full C ABI compatibility.

## Decisions

### Decision 1: Behavior-level fixture first

Use fixture JSON as the shared operation trace. It covers KVDB set/get/delete/entries/compact/reopen, TSDB append/query/count/status/reopen, and abnormal operations. This gives both C and Rust the same ordered input without requiring Rust to parse C test code or C to understand Rust internals.

Alternative considered: compare random stress output only. Rejected because a mismatch would not identify the first failing operation and would be hard for an agent to self-heal from an error stack.

### Decision 2: Stable report schema without new runtime dependencies

Keep report generation dependency-free. The initial fixture parser and reporter use a deliberately small supported JSON subset and deterministic string output. This fits the current project style and keeps the binary small.

Alternative considered: add `serde` and `serde_json` immediately. Deferred because current CLI is dependency-free and the first fixture set can stay simple. A later change can add serde if schema breadth becomes the actual bottleneck.

### Decision 3: Rust consumer is a required local gate; C producer is conditional

The Rust replay/diff consumer MUST run on this Windows host. The C oracle producer MUST be present as a contract and runnable in CI/Linux, but local execution MAY be skipped only with explicit `SKIPPED_LOCAL_NO_C_TOOLCHAIN` evidence.

Rationale: we can still validate the most important local loop, while avoiding false claims about C equivalence when no C compiler exists.

### Decision 4: Accepted differences are data, not comments

Known deltas such as Rust seed image layout not matching C FlashDB byte layout MUST be recorded in an accepted-differences section of the comparison/evidence report. A passing comparison can only pass fields that are either equal or explicitly accepted by id.

This prevents future agents from hiding mismatches inside prose summaries.

### Decision 5: CI runs expensive checks; local script keeps fast checks

Local verification keeps `cargo fmt`, `cargo check`, `cargo test`, replay/diff smoke, unsafe scan, and OpenSpec validation. CI can additionally run release 10000-loop stress and C oracle producer when toolchain setup succeeds.

No async or multithreaded replay is added in this step because fixture replay is I/O-light, deterministic, and easier to debug sequentially.

## Risks / Trade-offs

- [Risk] The Rust seed format still differs from FlashDB C image layout. -> Mitigation: compare behavior fields first and record image-layout mismatch as an accepted difference until a later layout-compatible slice lands.
- [Risk] Hand-written JSON parsing is narrower than general JSON. -> Mitigation: keep fixture schema intentionally constrained and validate fixtures through integration tests.
- [Risk] Checked-in sample oracle reports can become stale. -> Mitigation: record fixture hash and source commit in every report and fail comparison when fixture identity changes unexpectedly.
- [Risk] CI C oracle can pass while local Windows skips it. -> Mitigation: local evidence must say `SKIPPED_LOCAL_NO_C_TOOLCHAIN`; final summaries must distinguish local Rust consumer pass from C oracle pass.
- [Risk] Differential output becomes too large. -> Mitigation: include full per-step report for small fixtures and first mismatch summary for failures.

## Migration Plan

1. Add OpenSpec specs and tasks for fixture schema, Rust differential harness, C oracle producer contract, and evidence ledger.
2. Add Rust error codes and fixture replay/diff CLI commands.
3. Add a small set of deterministic fixtures and matching Rust-produced oracle smoke reports.
4. Add tests for fixture replay, diff pass, diff failure, and stable error code output.
5. Add C oracle contract files and CI/script hooks without making native Windows C compilation a hard gate.
6. Run local verification: `cargo fmt -- --check`, `cargo check`, `cargo test`, replay/diff smoke, unsafe scan, OpenSpec validation, and `git diff --check`.
7. Run or preserve the release 10000-loop command and record evidence if it completes.

Rollback strategy: each step keeps the existing `smoke`, `stress`, `inspect-image`, and `unsafe-scan` commands intact. If replay/diff breaks compilation, revert only the new replay/diff module or CLI branch while keeping the existing skeleton.

## Open Questions

- Whether a later change should replace the hand-written fixture parser with `serde_json` once fixture complexity grows.
- Whether C oracle reports should be checked in for small canonical fixtures or only generated in CI and stored as build artifacts.
- Which later slice should tackle FlashDB byte-for-byte sector layout compatibility.
