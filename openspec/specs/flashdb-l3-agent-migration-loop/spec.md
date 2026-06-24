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

### Requirement: KVDB Compact Overwrite L3 Slice Selection
The system SHALL select `kvdb-compact-overwrite` as a FlashDB L3 migration slice and SHALL record visible-behavior boundaries before implementation.

#### Scenario: KVDB compact overwrite slice is declared
- **WHEN** the KVDB compact/overwrite L3 loop starts
- **THEN** it records `kvdb-compact-overwrite` as the active slice with Rust APIs `KvDb::set`, `KvDb::get`, `KvDb::entries`, `KvDb::compact`, `KvDb::open`, `KvDb::delete`, and C oracle operations `kv.set`, `kv.get`, `kv.entries`, `kv.compact`, `kv.reopen`, `kv.delete`

#### Scenario: Compact boundary is visible behavior only
- **WHEN** the slice contract is frozen
- **THEN** it states that `kv.compact` is validated through pre/post compact visible behavior and does not claim native FlashDB GC, sector movement, tombstone layout, or byte-for-byte flash image equivalence

### Requirement: KVDB Compact Overwrite Fixture Coverage
The system SHALL use a named L3 fixture that covers same-key overwrite, compact, reopen, entries, and delete behavior.

#### Scenario: KVDB overwrite main path is covered
- **WHEN** `l3-kvdb-compact-overwrite.json` is replayed
- **THEN** it covers initial set, same-key overwrite, latest-value get, entries after overwrite, compact, reopen, latest-value get after reopen, delete, and missing get

#### Scenario: KVDB entries after overwrite are covered
- **WHEN** the fixture checks entries after overwrite
- **THEN** the report contains only live keys with the latest value for overwritten keys

#### Scenario: KVDB negative behavior regression is covered
- **WHEN** a report mutation changes latest value, entries, operation status, code, or delete/missing-get behavior
- **THEN** the schema-aware diff rejects the mutation and records the first mismatch path

### Requirement: KVDB Compact Overwrite C Oracle And Rust Replay Diff
The system SHALL compare C and Rust KVDB compact/overwrite visible behavior using the same fixture and schema-aware diff.

#### Scenario: KVDB compact overwrite reports use the same fixture
- **WHEN** L3 evidence is generated for `kvdb-compact-overwrite`
- **THEN** `l3-kvdb-compact-overwrite-c-oracle.json` and `l3-kvdb-compact-overwrite-rust-report.json` reference the same fixture hash, fixture path, and source commit

#### Scenario: KVDB compact metadata can differ
- **WHEN** the diff compares `kv.compact`, `kv.reopen`, or image layout metadata
- **THEN** image hash, backend, source, fixture, fixture hash, report path, and local toolchain metadata may differ only when listed as accepted differences

#### Scenario: KVDB behavior fields cannot be accepted differences
- **WHEN** the schema-aware diff compares KVDB C and Rust reports
- **THEN** differences in value, entries, status, code, operation success, or error semantics fail the L3 gate

### Requirement: KVDB Compact Overwrite Verification Evidence
The system SHALL persist KVDB compact/overwrite L3 evidence under `validation/evidence/flashdb/` and SHALL rerun validation in escalating order.

#### Scenario: KVDB compact overwrite evidence files are written
- **WHEN** the slice reaches an evidence checkpoint
- **THEN** the agent writes machine-readable ContextPack, slice contract, Rust report, C oracle report, diff, negative diff, compile check, error events, patch events, unsafe scan, unsafe ledger, cache metadata, performance smoke, and bilingual summary files

#### Scenario: KVDB compact overwrite validation reruns are staged
- **WHEN** a patch is applied
- **THEN** the agent runs `cargo check --message-format=json`, targeted Rust tests, `cargo test`, replay/diff, unsafe scan, performance smoke, and OpenSpec validation unless a failed earlier gate blocks later gates

#### Scenario: Local Windows C oracle skip is not a KVDB compact overwrite pass
- **WHEN** the local host cannot build the C oracle
- **THEN** the agent records `SKIPPED_LOCAL_NO_C_TOOLCHAIN` and does not mark L3 semantic evidence as passed until Linux, WSL, or CI produces `C_ORACLE_GENERATED`

### Requirement: KVDB Compact Overwrite Unsafe Cache And Parallel Boundaries
The system SHALL keep KVDB compact/overwrite first-party non-test unsafe at 0% for this slice and SHALL use deterministic cache invalidation and bounded parallel agent roles.

#### Scenario: KVDB compact overwrite unsafe scan is part of the gate
- **WHEN** L3 verification runs
- **THEN** the agent reports unsafe count, unsafe ratio, scanned files, ignored generated or vendor paths, and ledger entries

#### Scenario: KVDB compact overwrite cache is invalidated deterministically
- **WHEN** source commit, KVDB/replay/oracle fixture file hashes, Cargo.lock, command args, rustc version, feature/env, or context schema changes
- **THEN** cached ContextPack, error classification, and PatchPlan suggestions for `kvdb-compact-overwrite` are invalidated

#### Scenario: KVDB compact overwrite parallel agents do not perform conflicting edits
- **WHEN** multiple agents are used for the KVDB compact/overwrite L3 loop
- **THEN** their default roles are read-only analysis, independent validation, evidence audit, or patch review, while code edits are applied serially by one writer

### Requirement: KVDB Compact Overwrite Performance Smoke Is Secondary
The system SHALL record KVDB compact/overwrite performance smoke data without using it to replace correctness gates.

#### Scenario: KVDB compact overwrite performance evidence is recorded
- **WHEN** the L3 loop runs performance smoke
- **THEN** it records backend, operation counts, elapsed time, toolchain status, command, and report path

#### Scenario: KVDB compact overwrite async or threading requires design update
- **WHEN** async runtime, multithreaded replay, or internal concurrency is proposed for FlashDB Rust KVDB logic
- **THEN** the agent requires prior performance evidence, deterministic semantics, and an OpenSpec design update before implementation

### Requirement: KVDB Error Boundary L3 Slice Selection
The system SHALL select `kvdb-error-boundary` as a FlashDB L3 migration slice and SHALL record visible error-semantics boundaries before implementation.

系统必须选择 `kvdb-error-boundary` 作为 FlashDB L3 迁移切片，并在实现前记录可见错误语义边界。

#### Scenario: KVDB error boundary slice is declared
- **WHEN** the KVDB error-boundary L3 loop starts
- **THEN** it records `kvdb-error-boundary` as the active slice with Rust APIs `KvDb::set` and `KvDb::get`, replay operations `kv.set` and `kv.get`, and C oracle operations `kv.set` and `kv.get`

#### Scenario: Error boundary is public visible behavior only
- **WHEN** the slice contract is frozen
- **THEN** it states that missing-key, empty-key, and overlong-key behavior are validated as public visible API semantics and does not claim native FlashDB storage-layout, GC, sector movement, power-loss, or capacity-pressure behavior

### Requirement: KVDB Error Boundary Fixture Coverage
The system SHALL use a named L3 fixture that covers missing-key get, invalid-key set, overlong-key set, and valid post-error set/get behavior.

系统必须使用命名 L3 fixture 覆盖 missing-key get、invalid-key set、overlong-key set，以及错误路径后的有效 set/get 行为。

#### Scenario: KVDB missing and invalid key paths are covered
- **WHEN** `l3-kvdb-error-boundary.json` is replayed
- **THEN** it covers missing-key get returning `status: ok`, `code: OK`, and `value: null`, empty-key set returning `status: error` and `code: INVALID_KEY`, and overlong-key set returning `status: error` and `code: KEY_TOO_LONG`

#### Scenario: KVDB valid behavior after errors is covered
- **WHEN** the fixture continues after invalid-key errors
- **THEN** it covers a valid `kv.set` and `kv.get` pair returning `status: ok`, `code: OK`, and the expected value

#### Scenario: KVDB error negative regression is covered
- **WHEN** a report mutation changes `status`, `code`, `value`, key identity, step id, operation name, or operation success
- **THEN** the schema-aware diff rejects the mutation and records the first mismatch path

### Requirement: KVDB Error Boundary C Oracle And Rust Replay Diff
The system SHALL compare C and Rust KVDB error-boundary behavior using the same fixture and schema-aware diff.

系统必须使用同一个 fixture 和 schema-aware diff 对比 C/Rust KVDB 错误边界可见行为。

#### Scenario: KVDB error boundary reports use the same fixture
- **WHEN** L3 evidence is generated for `kvdb-error-boundary`
- **THEN** `l3-kvdb-error-boundary-c-oracle.json` and `l3-kvdb-error-boundary-rust-report.json` reference the same fixture hash, fixture path, and source commit

#### Scenario: KVDB error metadata can differ only outside behavior fields
- **WHEN** the diff compares error-boundary reports
- **THEN** image hash, backend, source, fixture, fixture hash, report path, local toolchain metadata, and message text may differ only when listed as accepted differences

#### Scenario: KVDB error behavior fields cannot be accepted differences
- **WHEN** the schema-aware diff compares KVDB C and Rust reports
- **THEN** differences in `status`, `code`, `value`, key identity, step id, operation name, operation success, or error semantics fail the L3 gate

### Requirement: KVDB Error Boundary Verification Evidence
The system SHALL persist KVDB error-boundary L3 evidence under `validation/evidence/flashdb/` and SHALL rerun validation in escalating order.

系统必须在 `validation/evidence/flashdb/` 下持久化 KVDB error-boundary L3 证据，并按从快到慢的顺序重新验证。

#### Scenario: KVDB error boundary evidence files are written
- **WHEN** the slice reaches an evidence checkpoint
- **THEN** the agent writes machine-readable ContextPack, slice contract, Rust report, C oracle report, diff, negative diff, compile check, error events, patch events, unsafe scan, unsafe ledger, cache metadata, performance smoke, and bilingual summary files

#### Scenario: KVDB error boundary validation reruns are staged
- **WHEN** a patch is applied
- **THEN** the agent runs `cargo check --message-format=json`, targeted Rust tests, `cargo test`, replay/diff, unsafe scan, performance smoke, and OpenSpec validation unless a failed earlier gate blocks later gates

#### Scenario: Local Windows C oracle skip is not a KVDB error boundary pass
- **WHEN** the local host cannot build the C oracle
- **THEN** the agent records `SKIPPED_LOCAL_NO_C_TOOLCHAIN` and does not mark L3 semantic evidence as passed until Linux, WSL, or CI produces `C_ORACLE_GENERATED`

### Requirement: KVDB Error Boundary Unsafe Cache And Parallel Boundaries
The system SHALL keep KVDB error-boundary first-party non-test unsafe at 0% for this slice and SHALL use deterministic cache invalidation and bounded parallel agent roles.

系统必须将此 KVDB error-boundary 切片的 first-party non-test unsafe 保持为 0%，并使用确定性缓存失效和有边界的并行智能体角色。

#### Scenario: KVDB error boundary unsafe scan is part of the gate
- **WHEN** L3 verification runs
- **THEN** the agent reports unsafe count, unsafe ratio, scanned files, ignored generated or vendor paths, and ledger entries

#### Scenario: KVDB error boundary cache is invalidated deterministically
- **WHEN** source commit, KVDB/replay/oracle fixture file hashes, Cargo.lock, command args, rustc version, feature/env, or context schema changes
- **THEN** cached ContextPack, error classification, and PatchPlan suggestions for `kvdb-error-boundary` are invalidated

#### Scenario: KVDB error boundary parallel agents do not perform conflicting edits
- **WHEN** multiple agents are used for the KVDB error-boundary L3 loop
- **THEN** their default roles are read-only analysis, independent validation, evidence audit, or patch review, while code edits are applied serially by one writer

### Requirement: KVDB Error Boundary Performance Smoke Is Secondary
The system SHALL record KVDB error-boundary performance smoke data without using it to replace correctness gates.

系统必须记录 KVDB error-boundary 性能烟测数据，但不能用性能结果替代正确性门禁。

#### Scenario: KVDB error boundary performance evidence is recorded
- **WHEN** the L3 loop runs performance smoke
- **THEN** it records backend, operation counters, elapsed time, toolchain status, command, and report path

#### Scenario: KVDB error boundary async or threading requires design update
- **WHEN** async runtime, multithreaded replay, or internal concurrency is proposed for FlashDB Rust KVDB logic
- **THEN** the agent requires prior performance evidence, deterministic semantics, and an OpenSpec design update before implementation

### Requirement: TSDB Deleted Status Reopen L3 Slice Selection
The system SHALL select `tsdb-deleted-status-reopen` as a FlashDB L3 migration slice and SHALL record visible status-count and reopen boundaries before implementation.

系统必须选择 `tsdb-deleted-status-reopen` 作为 FlashDB L3 迁移切片，并在实现前记录可见状态计数与 reopen 边界。

#### Scenario: TSDB deleted status slice is declared
- **WHEN** the TSDB deleted-status L3 loop starts
- **THEN** it records `tsdb-deleted-status-reopen` as the active slice with Rust APIs `TsDb::append`, `TsDb::set_status`, `TsDb::count_by_status`, `TsDb::open`, replay operations `ts.append`, `ts.set_status`, `ts.count_status`, `ts.reopen`, and C oracle operations `ts.append`, `ts.set_status`, `ts.count_status`, `ts.reopen`

#### Scenario: Deleted status boundary is public visible behavior only
- **WHEN** the slice contract is frozen
- **THEN** it states that deleted status count and reopen persistence are validated as public visible API semantics and does not claim `fdb_tsl_clean`, physical deletion, sector rollover, power-loss, or byte-for-byte layout behavior

### Requirement: TSDB Deleted Status Fixture Coverage
The system SHALL use a named L3 fixture that covers append, deleted status update, count-by-status, reopen, and recount behavior.

系统必须使用命名 L3 fixture 覆盖 append、deleted 状态更新、按状态计数、reopen 和 reopen 后重新计数行为。

#### Scenario: TSDB deleted and written counts are covered
- **WHEN** `l3-tsdb-deleted-status-reopen.json` is replayed
- **THEN** it covers two appends, setting entry 1 to `deleted`, counting `deleted` as 1, and counting remaining `written` as 1

#### Scenario: TSDB deleted status persists after reopen
- **WHEN** the fixture reopens the TSDB after setting entry 1 to `deleted`
- **THEN** it recounts `deleted` as 1 after reopen

#### Scenario: TSDB deleted status negative regression is covered
- **WHEN** a report mutation changes `count`, `status`, `entry_id`, step status, step code, operation id, operation name, or operation success
- **THEN** the schema-aware diff rejects the mutation and records the first mismatch path

### Requirement: TSDB Deleted Status C Oracle And Rust Replay Diff
The system SHALL compare C and Rust TSDB deleted-status behavior using the same fixture and schema-aware diff.

系统必须使用同一 fixture 和 schema-aware diff 对比 C/Rust TSDB deleted-status 可见行为。

#### Scenario: TSDB deleted status reports use the same fixture
- **WHEN** L3 evidence is generated for `tsdb-deleted-status-reopen`
- **THEN** `l3-tsdb-deleted-status-reopen-c-oracle.json` and `l3-tsdb-deleted-status-reopen-rust-report.json` reference the same fixture hash, fixture path, and source commit

#### Scenario: TSDB deleted status metadata can differ only outside behavior fields
- **WHEN** the diff compares deleted-status reports
- **THEN** image hash, backend, source, fixture, fixture hash, report path, and local toolchain metadata may differ only when listed as accepted differences

#### Scenario: TSDB deleted status behavior fields cannot be accepted differences
- **WHEN** the schema-aware diff compares TSDB C and Rust reports
- **THEN** differences in `entry_id`, `timestamp`, `status`, `value`, `count`, step status, step code, operation success, operation id, operation name, or error semantics fail the L3 gate

### Requirement: TSDB Deleted Status Verification Evidence
The system SHALL persist TSDB deleted-status L3 evidence under `validation/evidence/flashdb/` and SHALL rerun validation in escalating order.

系统必须在 `validation/evidence/flashdb/` 下持久化 TSDB deleted-status L3 证据，并按由快到慢的顺序重新验证。

#### Scenario: TSDB deleted status evidence files are written
- **WHEN** the slice reaches an evidence checkpoint
- **THEN** the agent writes machine-readable ContextPack, slice contract, Rust report, C oracle report, diff, negative diff, compile check, error events, patch events, unsafe scan, unsafe ledger, cache metadata, performance smoke, and bilingual summary files

#### Scenario: TSDB deleted status validation reruns are staged
- **WHEN** a patch is applied
- **THEN** the agent runs `cargo check --message-format=json`, targeted Rust tests, `cargo test`, replay/diff, unsafe scan, performance smoke, and OpenSpec validation unless a failed earlier gate blocks later gates

#### Scenario: Local Windows C oracle skip is not a TSDB deleted status pass
- **WHEN** the local host cannot build the C oracle
- **THEN** the agent records `SKIPPED_LOCAL_NO_C_TOOLCHAIN` and does not mark L3 semantic evidence as passed until Linux, WSL, or CI produces `C_ORACLE_GENERATED`

### Requirement: TSDB Deleted Status Unsafe Cache And Parallel Boundaries
The system SHALL keep TSDB deleted-status first-party non-test unsafe at 0% for this slice and SHALL use deterministic cache invalidation and bounded parallel agent roles.

系统必须将本 TSDB deleted-status 切片的一方非测试 unsafe 保持为 0%，并使用确定性缓存失效与有边界的并行智能体角色。

#### Scenario: TSDB deleted status unsafe scan is part of the gate
- **WHEN** L3 verification runs
- **THEN** the agent reports unsafe count, unsafe ratio, scanned files, ignored generated or vendor paths, and ledger entries

#### Scenario: TSDB deleted status cache is invalidated deterministically
- **WHEN** source commit, TSDB/replay/oracle fixture file hashes, Cargo.lock, command args, rustc version, feature/env, or context schema changes
- **THEN** cached ContextPack, error classification, and PatchPlan suggestions for `tsdb-deleted-status-reopen` are invalidated

#### Scenario: TSDB deleted status parallel agents do not perform conflicting edits
- **WHEN** multiple agents are used for the TSDB deleted-status L3 loop
- **THEN** their default roles are read-only analysis, independent validation, evidence audit, or patch review, while code edits are applied serially by one writer

### Requirement: TSDB Deleted Status Performance Smoke Is Secondary
The system SHALL record TSDB deleted-status performance smoke data without using it to replace correctness gates.

系统必须记录 TSDB deleted-status 性能烟测数据，但不能用性能结果替代正确性门禁。

#### Scenario: TSDB deleted status performance evidence is recorded
- **WHEN** the L3 loop runs performance smoke
- **THEN** it records backend, operation counters, elapsed time, toolchain status, command, and report path

#### Scenario: TSDB deleted status async or threading requires design update
- **WHEN** async runtime, multithreaded replay, or internal concurrency is proposed for FlashDB Rust TSDB logic
- **THEN** the agent requires prior performance evidence, deterministic semantics, and an OpenSpec design update before implementation
