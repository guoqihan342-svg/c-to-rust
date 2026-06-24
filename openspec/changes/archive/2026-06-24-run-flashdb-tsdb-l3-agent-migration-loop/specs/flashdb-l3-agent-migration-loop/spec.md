## ADDED Requirements

### Requirement: TSDB L3 Slice Selection
The system SHALL select `tsdb-append-query-status` as the second FlashDB L3 migration slice and SHALL record the C and Rust boundaries before implementation.

系统必须选择 `tsdb-append-query-status` 作为第二个 FlashDB L3 迁移切片，并在实现前记录 C/Rust 边界。

#### Scenario: TSDB slice is declared
- **WHEN** the second FlashDB L3 loop starts
- **THEN** it records `tsdb-append-query-status` as the active slice with Rust APIs `TsDb::append`, `TsDb::query`, `TsDb::set_status`, `TsDb::count_by_status`, `TsDb::open`, and C oracle operations `ts.append`, `ts.query`, `ts.set_status`, `ts.count_status`, `ts.reopen`

#### Scenario: TSDB cross-file context is captured
- **WHEN** the agent prepares to change Rust code or replay behavior for the TSDB slice
- **THEN** it produces a ContextPack containing direct Rust modules, public APIs, tests, fixture path, C oracle functions, evidence paths, accepted differences, unsafe ledger status, cache key, and rollback id

### Requirement: TSDB C Oracle And Rust Replay Diff
The system SHALL compare C and Rust TSDB behavior using the same deterministic L3 fixture and a schema-aware diff.

系统必须使用同一个确定性的 L3 fixture 对比 C/Rust TSDB 行为，并通过 schema-aware diff 判断语义等价。

#### Scenario: TSDB reports use the same fixture
- **WHEN** L3 evidence is generated for `tsdb-append-query-status`
- **THEN** `l3-tsdb-append-query-status-c-oracle.json` and `l3-tsdb-append-query-status-rust-report.json` reference the same fixture hash, fixture path, and source commit

#### Scenario: TSDB behavior fields cannot be accepted differences
- **WHEN** the schema-aware diff compares TSDB C and Rust reports
- **THEN** differences in entries, entry id, timestamp, status, value, count, operation success, code, or error semantics fail the L3 gate

#### Scenario: TSDB metadata differences are bounded
- **WHEN** the diff finds image hash, backend, source, fixture, fixture hash, report path, or local toolchain metadata differences
- **THEN** those differences are allowed only when listed in accepted differences and do not alter TSDB behavior fields

### Requirement: TSDB Fixture Coverage
The system SHALL use a named L3 TSDB fixture that covers append, query, status update, count, reopen, and ordering behavior.

系统必须使用命名的 L3 TSDB fixture 覆盖 append、query、status update、count、reopen 和排序行为。

#### Scenario: TSDB main path is covered
- **WHEN** the fixture `l3-tsdb-append-query-status.json` is replayed
- **THEN** it covers at least three appends, forward query, reversed query, status update, count-by-status, reopen, and query-after-reopen

#### Scenario: TSDB negative behavior regression is covered
- **WHEN** a report mutation changes TSDB value, status, count, entry id, timestamp, or query ordering
- **THEN** the schema-aware diff rejects the mutation and records the first mismatch path

### Requirement: TSDB Compile Self-Healing Evidence
The system SHALL run compile validation with rustc JSON error stacks and SHALL record bounded PatchPlan evidence for TSDB repairs.

系统必须使用 rustc JSON error stack 进行编译验证，并为 TSDB 修复记录有边界的 PatchPlan 证据。

#### Scenario: TSDB compile errors are classified
- **WHEN** `cargo check --message-format=json` returns errors while implementing the TSDB slice
- **THEN** the agent stores error code, primary span, related spans, rendered message, root cause key, affected TSDB or replay item, and rerun command

#### Scenario: TSDB automatic repair is bounded
- **WHEN** an error is eligible for automatic repair
- **THEN** the agent records patch id, files, spans, reason, expected error delta, risk, rollback id, forbidden changes, AI usage, and verification commands before applying the patch

#### Scenario: TSDB semantic or unsafe widening stops automation
- **WHEN** a candidate repair adds first-party non-test unsafe, changes public API outside the TSDB impact set, edits the C oracle contract, changes fixture expected behavior, or broadens accepted differences
- **THEN** the agent stops automatic patching and records a blocked repair requiring human approval

### Requirement: TSDB Verification Evidence
The system SHALL persist TSDB L3 evidence under `validation/evidence/flashdb/` and SHALL rerun validation in escalating order.

系统必须在 `validation/evidence/flashdb/` 下持久化 TSDB L3 证据，并按从快到慢的顺序重跑验证。

#### Scenario: TSDB evidence files are written
- **WHEN** the TSDB L3 slice reaches an evidence checkpoint
- **THEN** the agent writes machine-readable ContextPack, slice contract, Rust report, C oracle report, diff, compile check, error events, patch events, unsafe scan, unsafe ledger, performance smoke, and bilingual summary files

#### Scenario: TSDB validation reruns are staged
- **WHEN** a TSDB patch is applied
- **THEN** the agent runs `cargo check --message-format=json`, targeted Rust tests, `cargo test`, replay/diff, unsafe scan, performance smoke, and OpenSpec validation in that order unless a failed earlier gate blocks later gates

#### Scenario: Local Windows C oracle skip is not a TSDB pass
- **WHEN** the local host cannot build the C oracle
- **THEN** the agent records `SKIPPED_LOCAL_NO_C_TOOLCHAIN` and does not mark TSDB L3 semantic evidence as passed until Linux, WSL, or CI produces `C_ORACLE_GENERATED`

### Requirement: TSDB Unsafe, Cache, And Parallel Boundaries
The system SHALL keep TSDB first-party non-test unsafe at 0% for this slice and SHALL use deterministic cache invalidation and bounded parallel agent roles.

系统必须将此 TSDB 切片的 first-party non-test unsafe 保持为 0%，并使用确定性缓存失效和有边界的并行智能体角色。

#### Scenario: TSDB unsafe scan is part of the gate
- **WHEN** TSDB L3 verification runs
- **THEN** the agent reports unsafe count, unsafe ratio, scanned files, ignored generated or vendor paths, and ledger entries

#### Scenario: TSDB cache is invalidated deterministically
- **WHEN** source commit, TSDB/replay/oracle fixture file hashes, Cargo.lock, command args, rustc version, feature/env, or context schema changes
- **THEN** cached ContextPack, error classification, and PatchPlan suggestions for `tsdb-append-query-status` are invalidated

#### Scenario: TSDB parallel agents do not perform conflicting edits
- **WHEN** multiple agents are used for the TSDB L3 loop
- **THEN** their default roles are read-only analysis, independent validation, evidence audit, or patch review, while code edits are applied serially by one writer

### Requirement: TSDB Performance Smoke Is Secondary
The system SHALL record TSDB performance smoke data without using it to replace correctness gates.

系统必须记录 TSDB 性能烟测数据，但不能用性能结果替代正确性门禁。

#### Scenario: TSDB performance evidence is recorded
- **WHEN** the TSDB L3 loop runs performance smoke
- **THEN** it records backend, operation counts, elapsed time, toolchain status, command, and report path

#### Scenario: TSDB async or threading requires design update
- **WHEN** async runtime, multithreaded replay, or internal concurrency is proposed for FlashDB Rust TSDB logic
- **THEN** the agent requires prior performance evidence, deterministic semantics, and an OpenSpec design update before implementation
