## Purpose

Define the bounded L3 FlashDB migration loop for selecting one C-to-Rust slice, preserving cross-file module relationships, validating C/Rust semantic equivalence, constraining automatic compile self-healing, and recording reusable evidence for future FlashDB or larger C project migrations.

定义 FlashDB 有边界的 L3 迁移闭环：选择一个 C 到 Rust 的单点切片，保持跨文件模块调用关系，验证 C/Rust 语义等价，约束编译自愈自动补丁，并为后续 FlashDB 或更复杂 C 项目迁移沉淀可复用证据。

## Requirements

### Requirement: Bounded L3 Slice Selection
The system SHALL select one named FlashDB migration slice before implementation and SHALL record the C and Rust boundaries required to preserve cross-file module relationships.

系统必须在实现前选择一个命名的 FlashDB L3 迁移切片，并记录 C/Rust 边界，确保单点渐进式重构不破坏跨文件调用关系。

#### Scenario: KVDB lifecycle slice is declared
- **WHEN** the L3 loop starts for FlashDB
- **THEN** it records `kvdb-lifecycle` as the active slice with C APIs `fdb_kvdb_init`, `fdb_kv_set`, `fdb_kv_get`, `fdb_kv_del`, and deinit/reopen boundaries

#### Scenario: Cross-file context is captured before patching
- **WHEN** the agent prepares to change Rust code for the slice
- **THEN** it produces a ContextPack containing direct C callers/callees, relevant Rust modules, public APIs, tests, fixture paths, unsafe ledger status, accepted differences, and rollback id

### Requirement: C Oracle And Rust Replay Diff
The system SHALL compare C and Rust behavior for the selected slice using the same fixture input and a schema-aware diff.

系统必须使用同一个 fixture 输入生成 C oracle report 与 Rust replay report，并通过 schema-aware diff 判断行为等价。

#### Scenario: Reports use the same fixture
- **WHEN** L3 evidence is generated for `kvdb-lifecycle`
- **THEN** `l3-kvdb-lifecycle-c-oracle.json` and `l3-kvdb-lifecycle-rust-report.json` reference the same fixture hash and source commit

#### Scenario: Behavior fields cannot be accepted differences
- **WHEN** the schema-aware diff compares C and Rust reports
- **THEN** differences in value, status, count, operation success, or error semantics fail the L3 gate

#### Scenario: Layout metadata can be explicitly accepted
- **WHEN** the diff finds flash image hash or layout metadata differences caused by the current Rust seed layout
- **THEN** those differences are allowed only when they are listed in accepted differences and do not alter behavior fields

### Requirement: Compile Self-Healing Loop
The system SHALL run compile validation with rustc JSON error stacks and SHALL produce bounded PatchPlan evidence for every automatic repair attempt.

系统必须使用 rustc JSON error stack 驱动编译自愈，并为每次自动修复生成有边界的 PatchPlan 证据。

#### Scenario: Rust compiler errors are classified
- **WHEN** `cargo check --message-format=json` returns errors
- **THEN** the agent stores error code, primary span, related spans, rendered message, root cause key, affected items, and suggested rerun command

#### Scenario: PatchPlan is generated before automatic repair
- **WHEN** an error is eligible for automatic repair
- **THEN** the agent records patch id, files, spans, reason, expected error delta, risk, rollback id, forbidden changes, AI usage, and verification commands before applying the patch

#### Scenario: Unsafe or semantic contract changes stop automation
- **WHEN** a candidate repair adds first-party non-test unsafe, changes public API outside the impact set, edits C oracle contract, changes golden fixture results, or broadens accepted differences
- **THEN** the agent stops automatic patching and records a blocked repair requiring human approval

### Requirement: Verification Escalation And Evidence
The system SHALL rerun validation in escalating order and SHALL persist L3 evidence under a stable FlashDB evidence root.

系统必须按从快到慢的顺序重跑验证，并在稳定 evidence 目录下保存 L3 证据。

#### Scenario: Validation reruns are staged
- **WHEN** a patch is applied
- **THEN** the agent runs `cargo check --message-format=json` first, then targeted Rust tests, then `cargo test`, then replay/diff, then unsafe scan and performance smoke

#### Scenario: L3 evidence files are written
- **WHEN** the selected slice reaches an evidence checkpoint
- **THEN** the agent writes machine-readable reports under `validation/evidence/flashdb/` including C oracle, Rust report, diff, performance smoke, patch events, self-healing summary, and L3 summary

#### Scenario: Local Windows C oracle skip is not a pass
- **WHEN** the local host cannot build the C oracle
- **THEN** the agent records `SKIPPED_LOCAL_NO_C_TOOLCHAIN` and does not mark the C oracle or L3 semantic gate as passed until Linux/WSL/CI produces `C_ORACLE_GENERATED`

### Requirement: Unsafe Budget And Ledger
The system SHALL keep first-party non-test unsafe below 10% and SHALL prefer 0% unsafe for the initial L3 slice.

系统必须将 first-party non-test unsafe 控制在 10% 以下，首个 L3 切片默认目标为 0% unsafe。

#### Scenario: Unsafe scan is part of the L3 gate
- **WHEN** L3 verification runs
- **THEN** the agent reports unsafe count, unsafe ratio, scanned files, ignored generated or vendor paths, and any ledger entries

#### Scenario: New unsafe requires ledger evidence
- **WHEN** implementation introduces an unsafe block, unsafe function, raw pointer cast, `extern "C"`, `transmute`, or `repr(C)` boundary
- **THEN** the agent records file, span, category, reason, alternative considered, tests covering it, and C source evidence before the change can pass

### Requirement: Token, Cache, And Parallel Agent Boundaries
The system SHALL minimize token usage with structured context, cache invalidation, and bounded parallel agent roles.

系统必须通过结构化上下文、缓存失效键和有边界的并行智能体角色降低 token 与运行成本。

#### Scenario: Context sent to AI is sliced
- **WHEN** AI assistance is used for a repair or analysis
- **THEN** the prompt contains only the root cause summary, primary span context, directly related public types, direct caller/callee facts, and current verification delta unless a controlled 2-hop expansion is justified

#### Scenario: Cached context is invalidated deterministically
- **WHEN** source commit, file hashes, Cargo.lock, command args, rustc version, feature/env, or context schema changes
- **THEN** cached ContextPack, error classification, and PatchPlan suggestions for the affected slice are invalidated

#### Scenario: Parallel agents do not perform conflicting edits
- **WHEN** multiple agents are used for the L3 loop
- **THEN** their default roles are read-only analysis, independent validation, evidence audit, or patch review, while code edits are applied serially by one writer

### Requirement: Performance Smoke Is Secondary To Correctness
The system SHALL record performance smoke data for the selected slice without using it to replace correctness gates.

系统必须记录所选切片的性能烟测数据，但性能结果不能替代 C/Rust 行为等价和测试门禁。

#### Scenario: Performance evidence is recorded
- **WHEN** the L3 loop runs performance smoke for `kvdb-lifecycle`
- **THEN** it records backend, operation counts, elapsed time, toolchain status, command, and report path

#### Scenario: Async or threading requires measurement
- **WHEN** async runtime, multithreaded replay, or internal concurrency is proposed for FlashDB Rust logic
- **THEN** the agent requires prior performance evidence, deterministic semantics, and a design update before implementation
