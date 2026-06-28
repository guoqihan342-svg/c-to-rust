英文镜像见 `spec.en.md`。

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
The system SHALL keep first-party non-test unsafe below 10%.

系统必须将 first-party non-test unsafe 控制在 10% 以下。

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
The system SHALL keep TSDB first-party non-test unsafe below 10% for this slice and SHALL use deterministic cache invalidation and bounded parallel agent roles.

系统必须将此 TSDB 切片的 first-party non-test unsafe 控制在 10% 以下，并使用确定性缓存失效和有边界的并行智能体角色。

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
The system SHALL keep KVDB compact/overwrite first-party non-test unsafe below 10% for this slice and SHALL use deterministic cache invalidation and bounded parallel agent roles.

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
The system SHALL keep KVDB error-boundary first-party non-test unsafe below 10% for this slice and SHALL use deterministic cache invalidation and bounded parallel agent roles.

系统必须将此 KVDB error-boundary 切片的 first-party non-test unsafe 控制在 10% 以下，并使用确定性缓存失效和有边界的并行智能体角色。

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
The system SHALL keep TSDB deleted-status first-party non-test unsafe below 10% for this slice and SHALL use deterministic cache invalidation and bounded parallel agent roles.

系统必须将本 TSDB deleted-status 切片的一方非测试 unsafe 控制在 10% 以下，并使用确定性缓存失效与有边界的并行智能体角色。

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

### Requirement: TSDB Error Boundary L3 Slice Selection
The system SHALL select `tsdb-error-boundary` as a FlashDB L3 migration slice and SHALL record public TSDB error-semantics boundaries before implementation.

系统必须选择 `tsdb-error-boundary` 作为 FlashDB L3 迁移切片，并在实现前记录公开可见的 TSDB 错误语义边界。

#### Scenario: TSDB error boundary slice is declared
- **WHEN** the TSDB error-boundary L3 loop starts
- **THEN** it records `tsdb-error-boundary` as the active slice with Rust APIs `TsDb::append`, `TsDb::set_status`, `TsDb::count_by_status`, `TsDb::query`, replay operations `ts.append`, `ts.set_status`, `ts.count_status`, `ts.query`, and C oracle operations `ts.append`, `ts.set_status`, `ts.count_status`, `ts.query`

#### Scenario: TSDB error boundary is public visible behavior only
- **WHEN** the slice contract is frozen
- **THEN** it states that replay-visible TSDB input errors and post-error valid behavior are validated as public visible semantics and does not claim capacity exhaustion, sector full, clean, GC, corrupt image, power-loss, payload limit, or byte-for-byte layout behavior

### Requirement: TSDB Error Boundary Fixture Coverage
The system SHALL use a named L3 fixture that covers TSDB public input errors and valid behavior after those errors.

系统必须使用命名 L3 fixture 覆盖 TSDB 公开输入错误，以及这些错误之后的有效行为。

#### Scenario: TSDB stable error codes are covered
- **WHEN** `l3-tsdb-error-boundary.json` is replayed
- **THEN** it covers unknown `entry_id` for `ts.set_status` as `INVALID_RANGE`, unknown status for `ts.set_status` and `ts.count_status` as `PARSE`, invalid timestamp for `ts.append` as `PARSE`, and missing range field for `ts.query` as `PARSE`

#### Scenario: TSDB remains usable after error steps
- **WHEN** the fixture continues after TSDB error steps
- **THEN** it covers a valid empty-payload `ts.append` and a valid `ts.query` returning the expected entries

#### Scenario: TSDB error negative regression is covered
- **WHEN** a report mutation changes step `status`, step `code`, operation id, operation name, operation success, `entry_id`, `timestamp`, `value`, `count`, or `entries`
- **THEN** the schema-aware diff rejects the mutation and records the first mismatch path

### Requirement: TSDB Error Boundary C Oracle And Rust Replay Diff
The system SHALL compare C and Rust TSDB error-boundary behavior using the same fixture and schema-aware diff.

系统必须使用同一 fixture 和 schema-aware diff 对比 C/Rust TSDB 错误边界可见行为。

#### Scenario: TSDB error boundary reports use the same fixture
- **WHEN** L3 evidence is generated for `tsdb-error-boundary`
- **THEN** `l3-tsdb-error-boundary-c-oracle.json` and `l3-tsdb-error-boundary-rust-report.json` reference the same fixture hash, fixture path, and source commit

#### Scenario: TSDB error message text can differ only outside behavior gates
- **WHEN** the diff compares error-boundary reports
- **THEN** image hash, backend, source, fixture, fixture hash, report path, local toolchain metadata, and diagnostic message text may differ only when listed as accepted differences

#### Scenario: TSDB error behavior fields cannot be accepted differences
- **WHEN** the schema-aware diff compares TSDB C and Rust reports
- **THEN** differences in step `status`, step `code`, operation success, operation id, operation name, `entry_id`, `timestamp`, `status`, `value`, `count`, `entries`, or error semantics fail the L3 gate

### Requirement: TSDB Error Boundary Verification Evidence
The system SHALL persist TSDB error-boundary L3 evidence under `validation/evidence/flashdb/` and SHALL rerun validation in escalating order.

系统必须在 `validation/evidence/flashdb/` 下持久化 TSDB error-boundary L3 证据，并按由快到慢的顺序重新验证。

#### Scenario: TSDB error boundary evidence files are written
- **WHEN** the slice reaches an evidence checkpoint
- **THEN** the agent writes machine-readable ContextPack, slice contract, impact set, Rust report, C oracle report, diff, negative diff, compile check, error events, patch events, unsafe scan, unsafe ledger, cache metadata, performance smoke, and bilingual summary files

#### Scenario: TSDB error boundary validation reruns are staged
- **WHEN** a patch is applied
- **THEN** the agent runs `cargo check --message-format=json`, targeted Rust tests, `cargo test`, replay/diff, unsafe scan, performance smoke, and OpenSpec validation unless a failed earlier gate blocks later gates

#### Scenario: Local Windows C oracle skip is not a TSDB error boundary pass
- **WHEN** the local host cannot build the C oracle
- **THEN** the agent records `SKIPPED_LOCAL_NO_C_TOOLCHAIN` and does not mark L3 semantic evidence as passed until Linux, WSL, or CI produces `C_ORACLE_GENERATED`

### Requirement: TSDB Error Boundary Unsafe Cache And Parallel Boundaries
The system SHALL keep TSDB error-boundary first-party non-test unsafe below 10% for this slice and SHALL use deterministic cache invalidation and bounded parallel agent roles.

系统必须将本 TSDB error-boundary 切片的一方非测试 unsafe 控制在 10% 以下，并使用确定性缓存失效与有边界的并行智能体角色。

#### Scenario: TSDB error boundary unsafe scan is part of the gate
- **WHEN** L3 verification runs
- **THEN** the agent reports unsafe count, unsafe ratio, scanned files, ignored generated or vendor paths, and ledger entries

#### Scenario: TSDB error boundary cache is invalidated deterministically
- **WHEN** source commit, TSDB/replay/oracle fixture file hashes, Cargo.lock, command args, rustc version, feature/env, or context schema changes
- **THEN** cached ContextPack, error classification, and PatchPlan suggestions for `tsdb-error-boundary` are invalidated

#### Scenario: TSDB error boundary parallel agents do not perform conflicting edits
- **WHEN** multiple agents are used for the TSDB error-boundary L3 loop
- **THEN** their default roles are read-only analysis, independent validation, evidence audit, or patch review, while code edits are applied serially by one writer

### Requirement: TSDB Error Boundary Performance Smoke Is Secondary
The system SHALL record TSDB error-boundary performance smoke data without using it to replace correctness gates.

系统必须记录 TSDB error-boundary 性能烟测数据，但不能用性能结果替代正确性门禁。

#### Scenario: TSDB error boundary performance evidence is recorded
- **WHEN** the L3 loop runs performance smoke
- **THEN** it records backend, operation counters, elapsed time, toolchain status, command, and report path

#### Scenario: TSDB error boundary async or threading requires design update
- **WHEN** async runtime, multithreaded replay, or internal concurrency is proposed for FlashDB Rust TSDB logic
- **THEN** the agent requires prior performance evidence, deterministic semantics, and an OpenSpec design update before implementation

### Requirement: TSDB Set Status Report Schema Repair
The system SHALL emit unambiguous replay report fields for successful TSDB `ts.set_status` operations.

系统必须为成功的 TSDB `ts.set_status` 操作输出无歧义的 replay 报告字段。

#### Scenario: Successful set status separates step and TS status
- **WHEN** a replay fixture executes a successful `ts.set_status` operation
- **THEN** the step execution status is reported as `status:"ok"` and the requested TS business status is reported as `ts_status`

#### Scenario: Successful set status report has no duplicate status key
- **WHEN** Rust replay or the C oracle emits a successful `ts.set_status` step
- **THEN** the emitted step JSON contains exactly one step-level `status` key and does not use a second `status` key for the TS business status

### Requirement: TSDB Set Status Schema Diff Parity
The system SHALL compare repaired Rust and C oracle `ts.set_status` reports using the same schema-aware diff gate.

系统必须使用同一个 schema-aware diff 门禁比较修复后的 Rust 与 C oracle `ts.set_status` 报告。

#### Scenario: Repaired schema participates in behavior diff
- **WHEN** Rust and C oracle reports include a successful `ts.set_status` step
- **THEN** `ts_status` is treated as a behavior field and is not hidden by accepted metadata differences

#### Scenario: Mutated TS status is rejected
- **WHEN** a report mutates a successful `ts.set_status` step from one `ts_status` value to another
- **THEN** schema-aware diff fails at the mutated `ts_status` field path

### Requirement: TSDB Set Status Schema Repair Evidence
The system SHALL persist evidence for the TSDB `ts.set_status` report-schema repair.

系统必须持久化 TSDB `ts.set_status` report-schema 修复证据。

#### Scenario: Evidence records repair scope and validation
- **WHEN** the schema repair is implemented
- **THEN** evidence under `validation/evidence/flashdb/` records TDD red/green results, Rust replay output, C oracle output, schema diff, negative diff, unsafe scan, performance smoke, OpenSpec validation, and git whitespace validation

### Requirement: TSDB User2 Status L3 Slice Selection
The system SHALL select `tsdb-user2-status` as a focused FlashDB L3 migration slice and SHALL record its public visible status boundary before implementation.

系统必须选择 `tsdb-user2-status` 作为聚焦的 FlashDB L3 迁移切片，并在实现前记录其公开可见状态边界。

#### Scenario: TSDB user2 slice is declared
- **WHEN** the TSDB user2-status L3 loop starts
- **THEN** it records `tsdb-user2-status` as the active slice with Rust APIs `TsDb::append`, `TsDb::set_status`, `TsDb::count_by_status`, `TsDb::open`, replay operations `ts.append`, `ts.set_status`, `ts.count_status`, `ts.reopen`, and C oracle operations `ts.append`, `ts.set_status`, `ts.count_status`, `ts.reopen`

#### Scenario: TSDB user2 scope is public visible behavior only
- **WHEN** the slice contract is frozen
- **THEN** it states that `user2` set/count/reopen behavior is validated as public visible API semantics and does not claim clean, GC, physical deletion, sector rollover/full, capacity pressure, corrupt-image reopen, byte-for-byte layout, payload limits, or power-loss behavior

### Requirement: TSDB User2 Status Fixture Coverage
The system SHALL use a named L3 fixture that covers TSDB `user2` status behavior before and after reopen.

系统必须使用命名 L3 fixture 覆盖 TSDB `user2` 状态在 reopen 前后的行为。

#### Scenario: TSDB user2 status is set and counted
- **WHEN** `l3-tsdb-user2-status.json` is replayed
- **THEN** it appends at least two records, sets one entry to `user2`, emits `ts_status:"user2"`, counts `user2` as 1, and counts remaining `written` entries as 1

#### Scenario: TSDB user2 status persists after reopen
- **WHEN** the fixture reopens the TSDB after setting one entry to `user2`
- **THEN** it recounts `user2` as 1 after reopen

#### Scenario: TSDB user2 negative regression is covered
- **WHEN** a report mutation changes `ts_status`, `count`, `entry_id`, step status, step code, operation id, operation name, or operation success
- **THEN** the schema-aware diff rejects the mutation and records the first mismatch path

### Requirement: TSDB User2 C Oracle And Rust Replay Diff
The system SHALL compare C and Rust TSDB user2-status behavior using the same fixture and schema-aware diff.

系统必须使用同一个 fixture 和 schema-aware diff 对比 C/Rust TSDB user2-status 可见行为。

#### Scenario: TSDB user2 reports use the same fixture
- **WHEN** L3 evidence is generated for `tsdb-user2-status`
- **THEN** `l3-tsdb-user2-status-c-oracle.json` and `l3-tsdb-user2-status-rust-report.json` reference the same fixture hash, fixture path, and source commit

#### Scenario: TSDB user2 behavior fields cannot be accepted differences
- **WHEN** the schema-aware diff compares TSDB user2 C and Rust reports
- **THEN** differences in `entry_id`, `timestamp`, `ts_status`, `count`, step status, step code, operation success, operation id, operation name, or error semantics fail the L3 gate

### Requirement: TSDB User2 Verification Evidence
The system SHALL persist TSDB user2-status L3 evidence under `validation/evidence/flashdb/` and SHALL rerun validation in escalating order.

系统必须在 `validation/evidence/flashdb/` 下持久化 TSDB user2-status L3 证据，并按由快到慢的顺序重新验证。

#### Scenario: TSDB user2 evidence files are written
- **WHEN** the slice reaches an evidence checkpoint
- **THEN** the agent writes machine-readable ContextPack, slice contract, impact set, Rust report, C oracle report, diff, negative diff, compile check, unsafe scan, unsafe ledger, cache metadata, performance smoke, and bilingual summary files

#### Scenario: TSDB user2 final verification is complete
- **WHEN** the TSDB user2-status slice is ready to close
- **THEN** `cargo fmt -- --check`, targeted Rust tests, `cargo test`, replay/diff, unsafe scan, `openspec validate run-flashdb-tsdb-user2-status-l3-loop --strict`, `openspec validate --all`, and `git diff --check` have durable evidence

### Requirement: TSDB Status Transition L3 Slice Selection
The system SHALL select `tsdb-status-transition` as a focused FlashDB L3 migration slice and SHALL record the public visible repeated-status boundary before implementation.

系统必须选择 `tsdb-status-transition` 作为聚焦的 FlashDB L3 迁移切片，并在实现前记录连续状态转换的公共可见边界。

#### Scenario: TSDB status transition slice is declared
- **WHEN** the TSDB status-transition L3 loop starts
- **THEN** it records `tsdb-status-transition` as the active slice with Rust APIs `TsDb::append`, `TsDb::set_status`, `TsDb::count_by_status`, `TsDb::query`, `TsDb::open`, replay operations `ts.append`, `ts.set_status`, `ts.count_status`, `ts.query`, `ts.reopen`, and C oracle operations `ts.append`, `ts.set_status`, `ts.count_status`, `ts.query`, `ts.reopen`

#### Scenario: TSDB status transition scope is public visible behavior only
- **WHEN** the slice contract is frozen
- **THEN** it states that latest-status query/count/reopen behavior is validated as public visible API semantics and does not claim clean, GC, physical deletion, sector rollover/full, capacity pressure, corrupt-image reopen, byte-for-byte layout, payload limits, or power-loss behavior

### Requirement: TSDB Status Transition Fixture Coverage
The system SHALL use a named L3 fixture that covers repeated TSDB status transitions on one entry and stable visibility after reopen.

系统必须使用命名 L3 fixture 覆盖同一条 TS entry 的连续状态转换，并验证 reopen 后可见性保持稳定。

#### Scenario: TSDB latest status wins after repeated updates
- **WHEN** `l3-tsdb-status-transition.json` is replayed
- **THEN** it appends two records, changes one entry through `user1`, `user2`, and `deleted`, counts final `deleted` as 1, counts final `written` as 1, and counts intermediate `user1` and `user2` as 0 after the final transition

#### Scenario: TSDB query reports final status only
- **WHEN** the fixture queries the covered time range after repeated status updates
- **THEN** the transitioned entry is reported with `status:"deleted"` and the untouched entry is reported with `status:"written"`

#### Scenario: TSDB latest status persists after reopen
- **WHEN** the fixture reopens the TSDB after repeated status updates
- **THEN** it recounts `deleted` as 1, recounts `written` as 1, and queries the same final visible statuses

### Requirement: TSDB Status Transition C Oracle And Rust Replay Diff
The system SHALL compare C and Rust TSDB status-transition behavior using the same fixture and schema-aware diff.

系统必须使用同一 fixture 和 schema-aware diff 对比 C/Rust TSDB 状态转换的可见行为。

#### Scenario: TSDB status transition reports use the same fixture
- **WHEN** L3 evidence is generated for `tsdb-status-transition`
- **THEN** `l3-tsdb-status-transition-c-oracle.json` and `l3-tsdb-status-transition-rust-report.json` reference the same fixture hash, fixture path, and source commit

#### Scenario: TSDB stale intermediate statuses cannot be accepted differences
- **WHEN** the schema-aware diff compares TSDB status-transition C and Rust reports
- **THEN** differences in `entry_id`, `timestamp`, query entry `status`, `value`, `ts_status`, `count`, step status, step code, operation success, operation id, operation name, or error semantics fail the L3 gate

#### Scenario: TSDB status transition negative regression is covered
- **WHEN** a report mutation changes the final query status or final count
- **THEN** the schema-aware diff rejects the mutation and records the first mismatch path

### Requirement: TSDB Status Transition Verification Evidence
The system SHALL persist TSDB status-transition L3 evidence under `validation/evidence/flashdb/` and SHALL rerun validation in escalating order.

系统必须在 `validation/evidence/flashdb/` 下持久化 TSDB 状态转换 L3 证据，并按由快到慢的顺序重新验证。

#### Scenario: TSDB status transition evidence files are written
- **WHEN** the slice reaches an evidence checkpoint
- **THEN** the agent writes machine-readable ContextPack, slice contract, impact set, Rust report, C oracle report, diff, negative diff, compile check, unsafe scan, unsafe ledger, cache metadata, performance smoke, and bilingual summary files

#### Scenario: TSDB status transition final verification is complete
- **WHEN** the TSDB status-transition slice is ready to close
- **THEN** `cargo fmt -- --check`, targeted Rust tests, `cargo test`, replay/diff, unsafe scan, `openspec validate run-flashdb-tsdb-status-transition-l3-loop --strict`, `openspec validate --all`, and `git diff --check` have durable evidence

### Requirement: TSDB Payload Boundary L3 Slice Selection
The system SHALL select `tsdb-payload-boundary` as a focused FlashDB L3 migration slice and SHALL record the public visible payload boundary before implementation.

系统必须选择 `tsdb-payload-boundary` 作为聚焦的 FlashDB L3 迁移切片，并在实现前记录公开可见 payload 边界。

#### Scenario: TSDB payload boundary slice is declared
- **WHEN** the TSDB payload-boundary L3 loop starts
- **THEN** it records `tsdb-payload-boundary` as the active slice with Rust APIs `TsDb::append`, `TsDb::query`, `TsDb::count_by_status`, `TsDb::open`, replay operations `ts.append`, `ts.query`, `ts.count_status`, `ts.reopen`, and C oracle operations `ts.append`, `ts.query`, `ts.count_status`, `ts.reopen`

#### Scenario: TSDB payload boundary scope is public visible behavior only
- **WHEN** the slice contract is frozen
- **THEN** it states that empty payload, exactly 128-byte ASCII payload, query visibility, count visibility, and reopen persistence are validated as public visible API semantics and does not claim over-limit rejection, binary or NUL payload handling, capacity pressure, sector rollover/full, clean/GC, physical deletion, corrupt-image reopen, byte-for-byte layout, non-monotonic timestamps, or power-loss behavior

### Requirement: TSDB Payload Boundary Fixture Coverage
The system SHALL use a named L3 fixture that covers empty payload and exactly 128-byte ASCII payload visibility before and after reopen.

系统必须使用命名 L3 fixture 覆盖空 payload 和刚好 128 字节 ASCII payload 在 reopen 前后的可见性。

#### Scenario: TSDB boundary payloads are appended and queried
- **WHEN** `l3-tsdb-payload-boundary.json` is replayed
- **THEN** it appends one empty payload record, appends one exactly 128-byte ASCII payload record, queries the full covered time range, and reports both payload values without truncation or substitution

#### Scenario: TSDB exact timestamp and empty range payload behavior is covered
- **WHEN** the fixture queries the exact timestamp of the 128-byte payload and an empty time range between the two records
- **THEN** the exact timestamp query reports only the 128-byte payload record and the empty range query reports no entries with written count 0

#### Scenario: TSDB payload boundary persists after reopen
- **WHEN** the fixture reopens the TSDB after appending boundary payloads
- **THEN** it queries the covered time range again and reports the same empty payload and 128-byte payload values

### Requirement: TSDB Payload Boundary C Oracle And Rust Replay Diff
The system SHALL compare C and Rust TSDB payload-boundary behavior using the same fixture and schema-aware diff.

系统必须使用同一 fixture 和 schema-aware diff 对比 C/Rust TSDB payload-boundary 可见行为。

#### Scenario: TSDB payload boundary reports use the same fixture
- **WHEN** L3 evidence is generated for `tsdb-payload-boundary`
- **THEN** `l3-tsdb-payload-boundary-c-oracle.json` and `l3-tsdb-payload-boundary-rust-report.json` reference the same fixture hash, fixture path, and source commit

#### Scenario: TSDB payload values cannot be accepted differences
- **WHEN** the schema-aware diff compares TSDB payload-boundary C and Rust reports
- **THEN** differences in `entry_id`, `timestamp`, query entry `status`, query entry `value`, append `value`, `count`, step status, step code, operation success, operation id, operation name, or error semantics fail the L3 gate

#### Scenario: TSDB payload boundary negative regression is covered
- **WHEN** a report mutation changes the 128-byte payload value, empty payload value, final query entries, or count
- **THEN** the schema-aware diff rejects the mutation and records the first mismatch path

### Requirement: TSDB Payload Boundary Verification Evidence
The system SHALL persist TSDB payload-boundary L3 evidence under `validation/evidence/flashdb/` and SHALL rerun validation in escalating order.

系统必须在 `validation/evidence/flashdb/` 下持久化 TSDB payload-boundary L3 证据，并按由快到慢的顺序重新验证。

#### Scenario: TSDB payload boundary evidence files are written
- **WHEN** the slice reaches an evidence checkpoint
- **THEN** the agent writes machine-readable ContextPack, slice contract, impact set, Rust report, C oracle report, diff, negative diff, compile check, unsafe scan, unsafe ledger, cache metadata, performance smoke, and bilingual summary files

#### Scenario: TSDB payload boundary final verification is complete
- **WHEN** the TSDB payload-boundary slice is ready to close
- **THEN** `cargo fmt -- --check`, targeted Rust tests, `cargo test`, replay/diff, unsafe scan, `openspec validate run-flashdb-tsdb-payload-boundary-l3-loop --strict`, `openspec validate --all`, and `git diff --check` have durable evidence

### Requirement: TSDB Reverse Query Reopen L3 Slice Selection
The system SHALL select `tsdb-reverse-query-reopen` as a focused FlashDB L3 migration slice and SHALL record the public visible reverse-query-after-reopen boundary before implementation.

系统必须选择 `tsdb-reverse-query-reopen` 作为聚焦的 FlashDB L3 迁移切片，并在实现前记录 reopen 后反向 query 的公开可见边界。

#### Scenario: TSDB reverse query reopen slice is declared
- **WHEN** the TSDB reverse-query-reopen L3 loop starts
- **THEN** it records `tsdb-reverse-query-reopen` as the active slice with Rust APIs `TsDb::append`, `TsDb::set_status`, `TsDb::query`, `TsDb::open`, replay operations `ts.append`, `ts.set_status`, `ts.query`, `ts.reopen`, and C oracle operations `ts.append`, `ts.set_status`, `ts.query`, `ts.reopen`

#### Scenario: TSDB reverse query reopen scope is public visible behavior only
- **WHEN** the slice contract is frozen
- **THEN** it states that reverse query entry ordering, entry id, timestamp, status, value, and reopen persistence are validated as public visible API semantics and does not claim reverse `count_status`, capacity pressure, sector rollover/full, clean/GC, physical deletion, corrupt-image reopen, byte-for-byte layout, payload limits, non-monotonic timestamps, async/threading, or power-loss behavior

### Requirement: TSDB Reverse Query Reopen Fixture Coverage
The system SHALL use a named L3 fixture that covers reverse TSDB query ordering before and after reopen.

系统必须使用命名 L3 fixture 覆盖 reopen 前后的 TSDB 反向 query 顺序。

#### Scenario: TSDB reverse query is covered before reopen
- **WHEN** `l3-tsdb-reverse-query-reopen.json` is replayed before reopen
- **THEN** it appends three records with timestamps 10, 20, and 30, sets the middle entry to `user1`, and queries `from:30` to `to:10` with entries ordered by timestamps 30, 20, and 10

#### Scenario: TSDB reverse query persists after reopen
- **WHEN** the fixture reopens the TSDB and queries `from:30` to `to:10` again
- **THEN** it reports the same reverse ordering with the middle entry still carrying status `user1`

### Requirement: TSDB Reverse Query Reopen C Oracle And Rust Replay Diff
The system SHALL compare C and Rust TSDB reverse-query-after-reopen behavior using the same fixture and schema-aware diff.

系统必须使用同一 fixture 和 schema-aware diff 对比 C/Rust TSDB reopen 后反向 query 可见行为。

#### Scenario: TSDB reverse query reopen reports use the same fixture
- **WHEN** L3 evidence is generated for `tsdb-reverse-query-reopen`
- **THEN** `l3-tsdb-reverse-query-reopen-c-oracle.json` and `l3-tsdb-reverse-query-reopen-rust-report.json` reference the same fixture hash, fixture path, and source commit

#### Scenario: TSDB reverse query ordering cannot be an accepted difference
- **WHEN** the schema-aware diff compares TSDB reverse-query-reopen C and Rust reports
- **THEN** differences in query entry order, `entry_id`, `timestamp`, query entry `status`, `value`, step status, step code, operation success, operation id, operation name, or error semantics fail the L3 gate

#### Scenario: TSDB reverse query reopen negative regression is covered
- **WHEN** a report mutation changes the after-reopen reverse query order, status, timestamp, entry id, value, operation id, operation name, or operation success
- **THEN** the schema-aware diff rejects the mutation and records the first mismatch path

### Requirement: TSDB Reverse Query Reopen Verification Evidence
The system SHALL persist TSDB reverse-query-reopen L3 evidence under `validation/evidence/flashdb/` and SHALL rerun validation in escalating order.

系统必须在 `validation/evidence/flashdb/` 下持久化 TSDB reverse-query-reopen L3 证据，并按由快到慢的顺序重新验证。

#### Scenario: TSDB reverse query reopen evidence files are written
- **WHEN** the slice reaches an evidence checkpoint
- **THEN** the agent writes machine-readable ContextPack, slice contract, impact set, Rust report, C oracle report, diff, negative diff, compile check, unsafe scan, unsafe ledger, cache metadata, performance smoke, and bilingual summary files

#### Scenario: TSDB reverse query reopen final verification is complete
- **WHEN** the TSDB reverse-query-reopen slice is ready to close
- **THEN** `cargo fmt -- --check`, targeted Rust tests, `cargo test`, replay/diff, unsafe scan, `openspec validate run-flashdb-tsdb-reverse-query-reopen-l3-loop --strict`, `openspec validate --all`, and `git diff --check` have durable evidence

### Requirement: TSDB Over-Limit Payload Error L3 Slice Selection
The system SHALL select `tsdb-over-limit-payload-error` as a focused FlashDB L3 migration slice and SHALL record the public visible over-limit payload error boundary before implementation.

系统必须选择 `tsdb-over-limit-payload-error` 作为聚焦的 FlashDB L3 迁移切片，并在实现前记录超限 payload 错误的公开可见边界。

#### Scenario: TSDB over-limit payload error slice is declared
- **WHEN** the TSDB over-limit-payload-error L3 loop starts
- **THEN** it records `tsdb-over-limit-payload-error` as the active slice with Rust APIs `TsDb::append`, `TsDb::query`, `TsDb::count_by_status`, `TsDb::open`, replay operations `ts.append`, `ts.query`, `ts.count_status`, `ts.reopen`, and C oracle operations `ts.append`, `ts.query`, `ts.count_status`, `ts.reopen`

#### Scenario: TSDB over-limit scope is public visible error behavior only
- **WHEN** the slice contract is frozen
- **THEN** it states that 129-byte ASCII payload rejection, non-visibility of the rejected entry, post-error valid append, count/query visibility, and reopen persistence are validated, and does not claim binary or NUL payload handling, payloads larger than 129 bytes, capacity pressure, sector rollover/full, clean/GC, physical deletion, corrupt-image reopen, byte-for-byte layout, non-monotonic timestamps, async/threading, or power-loss behavior

### Requirement: TSDB Over-Limit Payload Error Fixture Coverage
The system SHALL use `l3-tsdb-over-limit-payload-error.json` to cover a 129-byte TSDB payload rejection and stable state after the failed append.

系统必须使用 `l3-tsdb-over-limit-payload-error.json` 覆盖 129 字节 TSDB payload 拒绝行为，以及失败 append 之后的稳定状态。

#### Scenario: Over-limit append is rejected
- **WHEN** `l3-tsdb-over-limit-payload-error.json` is replayed
- **THEN** it appends a valid control record, attempts one 129-byte ASCII `ts.append`, and reports `status:"error"` with `code:"FDB_WRITE_ERR"` for the over-limit append

#### Scenario: Failed append does not create visible state
- **WHEN** the fixture queries and counts the covered range after the failed append
- **THEN** the rejected payload is absent from query entries, written count excludes it, and the next successful append uses the next contiguous successful `entry_id`

#### Scenario: Post-error state persists after reopen
- **WHEN** the fixture reopens the TSDB after the failed append and a later valid append
- **THEN** query/count results still include only the successful records

### Requirement: TSDB Over-Limit Payload Error C Oracle And Rust Replay Diff
The system SHALL compare C and Rust TSDB over-limit payload error behavior using the same fixture and schema-aware diff.

系统必须使用同一个 fixture 与 schema-aware diff 对比 C/Rust TSDB 超限 payload 错误行为。

#### Scenario: TSDB over-limit reports use the same fixture
- **WHEN** L3 evidence is generated for `tsdb-over-limit-payload-error`
- **THEN** `l3-tsdb-over-limit-payload-error-c-oracle.json` and `l3-tsdb-over-limit-payload-error-rust-report.json` reference the same fixture hash, fixture path, and source commit

#### Scenario: Over-limit error fields cannot be accepted differences
- **WHEN** the schema-aware diff compares C and Rust reports
- **THEN** differences in step status, step code, operation success, operation id, operation name, entry id, timestamp, query entries, count, or error semantics fail the L3 gate; diagnostic message text may differ only as an accepted metadata difference

#### Scenario: Over-limit negative regression is covered
- **WHEN** a report mutation changes the failed append into success, changes `FDB_WRITE_ERR`, or makes the rejected payload visible
- **THEN** the schema-aware diff rejects the mutation and records the first mismatch path

### Requirement: TSDB Over-Limit Payload Error Verification Evidence
The system SHALL persist TSDB over-limit-payload-error L3 evidence under `validation/evidence/flashdb/` and SHALL rerun validation in escalating order.

系统必须在 `validation/evidence/flashdb/` 下持久化 TSDB over-limit-payload-error L3 证据，并按由快到慢的顺序重新验证。

#### Scenario: TSDB over-limit evidence files are written
- **WHEN** the slice reaches an evidence checkpoint
- **THEN** the agent writes machine-readable ContextPack, slice contract, impact set, Rust report, C oracle report, diff, negative diff, compile check, unsafe scan, unsafe ledger, cache metadata, performance smoke, and bilingual summary files

#### Scenario: TSDB over-limit final verification is complete
- **WHEN** the slice is ready to close
- **THEN** `cargo fmt -- --check`, targeted Rust tests, `cargo test`, replay/diff, unsafe scan, `openspec validate run-flashdb-tsdb-over-limit-payload-error-l3-loop --strict`, `openspec validate --all`, and `git diff --check` have durable evidence

### Requirement: TSDB Non-Monotonic Timestamp L3 Slice Selection
The system SHALL select `tsdb-non-monotonic-timestamp` as a focused FlashDB L3 migration slice and SHALL record the public visible strict-increasing timestamp boundary before implementation.

系统必须选择 `tsdb-non-monotonic-timestamp` 作为聚焦的 FlashDB L3 迁移切片，并在实现前记录 timestamp 严格递增的公开可见边界。

#### Scenario: TSDB non-monotonic timestamp slice is declared
- **WHEN** the TSDB non-monotonic-timestamp L3 loop starts
- **THEN** it records `tsdb-non-monotonic-timestamp` as the active slice with Rust APIs `TsDb::append`, `TsDb::query`, `TsDb::count_by_status`, `TsDb::open`, replay operations `ts.append`, `ts.query`, `ts.count_status`, `ts.reopen`, and C oracle operations `ts.append`, `ts.query`, `ts.count_status`, `ts.reopen`

#### Scenario: TSDB timestamp-order scope is public visible error behavior only
- **WHEN** the slice contract is frozen
- **THEN** it states that duplicate timestamp rejection, decreasing timestamp rejection, non-visibility of rejected entries, post-error valid append, count/query visibility, and reopen persistence are validated, and does not claim timestamp overflow, negative timestamp policy, 64-bit timestamp builds, capacity pressure, sector rollover/full, clean/GC, physical deletion, corrupt-image reopen, byte-for-byte layout, payload-size behavior, async/threading, or power-loss behavior

### Requirement: TSDB Non-Monotonic Timestamp Fixture Coverage
The system SHALL use `l3-tsdb-non-monotonic-timestamp.json` to cover duplicate and decreasing TSDB timestamp rejection and stable state after failed appends.

系统必须使用 `l3-tsdb-non-monotonic-timestamp.json` 覆盖重复 timestamp 与倒退 timestamp 的 TSDB append 拒绝行为，以及失败 append 之后的稳定状态。

#### Scenario: Duplicate timestamp append is rejected
- **WHEN** `l3-tsdb-non-monotonic-timestamp.json` is replayed
- **THEN** it appends one valid control record, attempts another `ts.append` with the same timestamp, and reports `status:"error"` with `code:"FDB_WRITE_ERR"` for the duplicate timestamp append

#### Scenario: Decreasing timestamp append is rejected
- **WHEN** the same fixture attempts a later `ts.append` whose timestamp is less than the last successful append timestamp
- **THEN** it reports `status:"error"` with `code:"FDB_WRITE_ERR"` for the decreasing timestamp append

#### Scenario: Failed timestamp-order appends do not create visible state
- **WHEN** the fixture queries and counts the covered range after both failed appends
- **THEN** the rejected values are absent from query entries, written count excludes them, and the next successful append uses the next contiguous successful `entry_id`

#### Scenario: Post-error state persists after reopen
- **WHEN** the fixture reopens the TSDB after failed timestamp-order appends and a later valid append
- **THEN** query/count results still include only the successful records

### Requirement: TSDB Non-Monotonic Timestamp C Oracle And Rust Replay Diff
The system SHALL compare C and Rust TSDB timestamp-order error behavior using the same fixture and schema-aware diff.

系统必须使用同一个 fixture 与 schema-aware diff 对比 C/Rust TSDB timestamp 顺序错误行为。

#### Scenario: TSDB timestamp-order reports use the same fixture
- **WHEN** L3 evidence is generated for `tsdb-non-monotonic-timestamp`
- **THEN** `l3-tsdb-non-monotonic-timestamp-c-oracle.json` and `l3-tsdb-non-monotonic-timestamp-rust-report.json` reference the same fixture hash, fixture path, and source commit

#### Scenario: Timestamp-order error fields cannot be accepted differences
- **WHEN** the schema-aware diff compares C and Rust reports
- **THEN** differences in step status, step code, operation success, operation id, operation name, successful entry id, timestamp, query entries, count, or error semantics fail the L3 gate; diagnostic message text may differ only as an accepted metadata difference

#### Scenario: Timestamp-order negative regression is covered
- **WHEN** a report mutation changes a duplicate or decreasing timestamp append into success, changes `FDB_WRITE_ERR`, or makes a rejected value visible
- **THEN** the schema-aware diff rejects the mutation and records the first mismatch path

### Requirement: TSDB Non-Monotonic Timestamp Verification Evidence
The system SHALL persist TSDB non-monotonic-timestamp L3 evidence under `validation/evidence/flashdb/` and SHALL rerun validation in escalating order.

系统必须在 `validation/evidence/flashdb/` 下持久化 TSDB non-monotonic-timestamp L3 证据，并按由快到慢的顺序重新验证。

#### Scenario: TSDB timestamp-order evidence files are written
- **WHEN** the slice reaches an evidence checkpoint
- **THEN** the agent writes machine-readable ContextPack, slice contract, impact set, Rust report, C oracle report, diff, negative diff, compile check, unsafe scan, unsafe ledger, cache metadata, performance smoke, and bilingual summary files

#### Scenario: TSDB timestamp-order final verification is complete
- **WHEN** the slice is ready to close
- **THEN** `cargo fmt -- --check`, targeted Rust tests, `cargo test`, replay/diff, unsafe scan, `openspec validate run-flashdb-tsdb-non-monotonic-timestamp-l3-loop --strict`, `openspec validate --all`, and `git diff --check` have durable evidence

### Requirement: KVDB Delete Missing Key L3 Slice Selection
The system SHALL select `kvdb-delete-missing-key` as a FlashDB L3 migration slice and SHALL record public visible error-semantics boundaries before implementation.

系统必须选择 `kvdb-delete-missing-key` 作为 FlashDB L3 迁移切片，并在实现前记录公开可见的错误语义边界。

#### Scenario: KVDB delete missing key slice is declared
- **WHEN** the KVDB delete-missing-key L3 loop starts
- **THEN** it records `kvdb-delete-missing-key` as the active slice with Rust APIs `KvDb::delete`, `KvDb::set`, `KvDb::get`, `KvDb::entries`, `KvDb::open`, and C oracle operations `kv.delete`, `kv.set`, `kv.get`, `kv.entries`, `kv.reopen`

#### Scenario: Missing delete is the only new behavior
- **WHEN** the slice contract is frozen
- **THEN** it states that valid but absent-key `kv.delete` returns `FDB_KV_NAME_ERR`, while missing `kv.get` remains `OK` with `null`

### Requirement: KVDB Delete Missing Key Fixture Coverage
The system SHALL use a named L3 fixture that covers never-existing delete, delete-after-delete, recovery state, reopen, and live entries without mutating older fixture hashes.

系统必须使用命名 L3 fixture 覆盖从未存在 key 的 delete、已删除 key 的再次 delete、恢复状态、reopen 和 live entries，并且不得修改旧 fixture hash。

#### Scenario: Never-existing delete is covered
- **WHEN** `l3-kvdb-delete-missing-key.json` is replayed
- **THEN** the first delete of a valid key that never existed returns `status:"error"` and `code:"FDB_KV_NAME_ERR"`

#### Scenario: Delete-after-delete is covered
- **WHEN** the fixture deletes an existing key and then deletes the same key again
- **THEN** the first delete returns `OK`, the second delete returns `FDB_KV_NAME_ERR`, and a later get of that key returns `OK` with `null`

#### Scenario: Recovery after missing delete is covered
- **WHEN** a missing delete occurs before or after live-key operations
- **THEN** unrelated set, get, entries, reopen, and post-reopen reads remain visible and correct

#### Scenario: KVDB negative behavior regression is covered
- **WHEN** a report mutation changes missing-delete status, code, operation success, value, entries, or live-key state
- **THEN** the schema-aware diff rejects the mutation and records the first mismatch path

### Requirement: KVDB Delete Missing Key C Oracle And Rust Replay Diff
The system SHALL compare C and Rust KVDB delete-missing-key visible behavior using the same fixture and schema-aware diff.

系统必须使用同一个 fixture 和 schema-aware diff 对比 C/Rust KVDB delete-missing-key 可见行为。

#### Scenario: KVDB delete missing key reports use the same fixture
- **WHEN** L3 evidence is generated for `kvdb-delete-missing-key`
- **THEN** `l3-kvdb-delete-missing-key-c-oracle.json` and `l3-kvdb-delete-missing-key-rust-report.json` reference the same fixture hash, fixture path, and FlashDB source commit

#### Scenario: Missing delete behavior fields cannot be accepted differences
- **WHEN** the schema-aware diff compares KVDB C and Rust reports
- **THEN** differences in missing-delete status, code, operation success, live-key value, entries, step id, or operation id fail the L3 gate

#### Scenario: Diagnostic message text can differ
- **WHEN** C and Rust report different diagnostic message text for the same missing-delete error code
- **THEN** the difference may be accepted only as `message` metadata while `status` and `code` remain strict

### Requirement: KVDB Delete Missing Key Verification Evidence
The system SHALL persist KVDB delete-missing-key L3 evidence under `validation/evidence/flashdb/` and SHALL rerun validation in escalating order.

系统必须在 `validation/evidence/flashdb/` 下持久化 KVDB delete-missing-key L3 证据，并按从快到慢的顺序重新验证。

#### Scenario: KVDB delete missing key evidence files are written
- **WHEN** the slice reaches an evidence checkpoint
- **THEN** the agent writes machine-readable ContextPack, slice contract, impact set, agent roles, Rust report, C oracle report, diff, negative diff, compile check, error events, patch events, unsafe scan, unsafe ledger, cache metadata, performance smoke, final verification, and bilingual summary files

#### Scenario: KVDB delete missing key validation reruns are staged
- **WHEN** a patch is applied
- **THEN** the agent runs `cargo check --message-format=json`, targeted Rust tests, `cargo test`, replay/diff, unsafe scan, performance smoke, and OpenSpec validation unless a failed earlier gate blocks later gates

#### Scenario: Local Windows C oracle skip is not a KVDB delete missing key pass
- **WHEN** the local host cannot build the C oracle
- **THEN** the agent records `SKIPPED_LOCAL_NO_C_TOOLCHAIN` and does not mark L3 semantic evidence as passed until Linux, WSL, or CI produces `C_ORACLE_GENERATED`

### Requirement: KVDB Delete Missing Key Unsafe Cache And Parallel Boundaries
The system SHALL keep KVDB delete-missing-key first-party non-test unsafe below 10% for this slice and SHALL use deterministic cache invalidation and bounded parallel agent roles.

系统必须将此 KVDB delete-missing-key 切片的 first-party non-test unsafe 控制在 10% 以下，并使用确定性缓存失效和有边界的并行智能体角色。

#### Scenario: KVDB delete missing key unsafe scan is part of the gate
- **WHEN** L3 verification runs
- **THEN** the agent reports unsafe count, unsafe ratio, scanned files, ignored generated or vendor paths, and ledger entries

#### Scenario: KVDB delete missing key cache is invalidated deterministically
- **WHEN** source commit, KVDB/replay/oracle fixture file hashes, Cargo.lock, command args, rustc version, feature/env, or context schema changes
- **THEN** cached ContextPack, error classification, and PatchPlan suggestions for `kvdb-delete-missing-key` are invalidated

#### Scenario: KVDB delete missing key parallel agents do not perform conflicting edits
- **WHEN** multiple agents are used for the KVDB delete-missing-key L3 loop
- **THEN** their default roles are read-only analysis, independent validation, evidence audit, or patch review, while code edits are applied serially by one writer

### Requirement: KVDB Delete Missing Key Performance Smoke Is Secondary
The system SHALL record KVDB delete-missing-key performance smoke data without using it to replace correctness gates.

系统必须记录 KVDB delete-missing-key 性能烟测数据，但不能用性能结果替代正确性门禁。

#### Scenario: KVDB delete missing key performance evidence is recorded
- **WHEN** the L3 loop runs performance smoke
- **THEN** it records backend, operation counts, elapsed time, toolchain status, command, and report path

#### Scenario: KVDB delete missing key async or threading requires design update
- **WHEN** async runtime, multithreaded replay, or internal concurrency is proposed for FlashDB Rust KVDB logic
- **THEN** the agent requires prior performance evidence, deterministic semantics, and an OpenSpec design update before implementation

### Requirement: L3 Version Manifest
The system SHALL generate a machine-readable version manifest for every FlashDB L3 migration slice before implementation edits or cache reuse.

系统必须在每个 FlashDB L3 迁移切片开始实现或复用缓存前，生成机器可读的 version manifest。

#### Scenario: Version manifest contains required version dimensions
- **WHEN** an L3 slice starts
- **THEN** the manifest records agent contract version, context schema version, PatchPlan schema version, output crate name and version, FlashDB source clone URL and commit, OpenSpec version, rustc version, cargo version, git version, fixture schema version, evidence schema version, Cargo.lock hash, host OS, and cache key inputs

#### Scenario: Missing optional tool versions are explicit
- **WHEN** a tool version cannot be detected
- **THEN** the manifest records `NOT_FOUND` for that tool and the affected gate decides whether the slice can continue

### Requirement: L3 Version Compatibility Gate
The system SHALL treat version drift as a cache invalidation and evidence review trigger before compile self-healing, C/Rust diff claims, or archive.

系统必须把版本漂移作为缓存失效和证据复核触发条件，且该检查必须发生在编译自愈、C/Rust diff 声明或归档之前。

#### Scenario: Version drift invalidates reusable artifacts
- **WHEN** FlashDB source commit, Rust crate version, Cargo.lock hash, fixture schema version, evidence schema version, agent contract version, context schema version, PatchPlan schema version, rustc version, cargo version, OpenSpec version, feature matrix, or command arguments change
- **THEN** cached ContextPack, PatchPlan suggestions, AI candidate patches, C oracle reports, and schema-aware diff conclusions are not reused without regeneration or explicit evidence review

#### Scenario: Version manifest is part of final evidence
- **WHEN** an L3 slice reaches final verification
- **THEN** the final verification evidence references the version manifest path and hash

### Requirement: Version Manifest CLI
The system SHALL expose a small Rust CLI command that emits the current migration version manifest without introducing new runtime dependencies or unsafe code.

系统必须暴露一个小型 Rust CLI 命令用于输出当前迁移 version manifest，且不得引入新的运行时依赖或 unsafe 代码。

#### Scenario: Version manifest command writes a report
- **WHEN** `flashdb-rust version-manifest --report <path>` is executed
- **THEN** it writes JSON containing `command:"version-manifest"`, `schema_version:1`, crate version, source commit, tool versions, schema versions, and cache key inputs to the requested report path

#### Scenario: Version manifest command prints JSON
- **WHEN** `flashdb-rust version-manifest` is executed without `--report`
- **THEN** it prints the same JSON to stdout

#### Scenario: Version command does not affect storage semantics
- **WHEN** the version manifest command runs
- **THEN** it does not create KVDB/TSDB flash images, does not run replay/diff, and does not change public database behavior

### Requirement: L3 Bilingual OpenSpec Text Integrity
The system SHALL keep FlashDB L3 OpenSpec artifact prose readable as UTF-8 text while preserving parser-required English anchors.

系统必须保持 FlashDB L3 OpenSpec 文档说明文本为可读 UTF-8，同时保留 parser 需要的英文结构锚点。

#### Scenario: Bilingual prose remains readable
- **WHEN** the agent writes or repairs FlashDB L3 OpenSpec proposal, design, specs, tasks, summary, or evidence prose
- **THEN** Chinese explanatory text remains readable UTF-8 and does not contain known mojibake markers from encoding drift

#### Scenario: Parser anchors are preserved
- **WHEN** bilingual prose is repaired
- **THEN** OpenSpec anchors such as `## ADDED Requirements`, `### Requirement:`, `#### Scenario:`, `WHEN`, and `THEN` remain unchanged

### Requirement: TSDB Reverse Query Reopen Test Evidence Hardening
The system SHALL assert that the `tsdb-reverse-query-reopen` Rust replay test validates the reopen operation report as an explicit successful step.

系统必须确保 `tsdb-reverse-query-reopen` Rust replay 测试把 reopen 操作报告校验为明确成功的 step。

#### Scenario: Reopen step report fields are asserted
- **WHEN** `l3-tsdb-reverse-query-reopen.json` is replayed by the Rust test
- **THEN** step `ts-rqr-006` is asserted to contain `op:"ts.reopen"`, `status:"ok"`, `code:"OK"`, and an `image_hash` field

#### Scenario: Reopen hash remains metadata
- **WHEN** the test checks `ts-rqr-006`
- **THEN** it asserts the presence of `image_hash` without pinning a concrete hash value

### Requirement: FlashDB Evidence Trace Search CLI
The system SHALL expose a small Rust CLI command that searches local FlashDB migration evidence and returns traceable match metadata without AI calls, unsafe code, or new runtime dependencies.

系统必须提供一个小型 Rust CLI 命令，用于检索本地 FlashDB 迁移证据，并返回可追溯的命中元数据；该命令不得调用 AI，不得引入 unsafe，也不得新增运行时依赖。

#### Scenario: Search returns traceable matches
- **WHEN** `flashdb-rust evidence-search --evidence-dir <dir> --query <text>` is executed against supported evidence files
- **THEN** it prints JSON containing `command:"evidence-search"`, `schema_version:1`, the evidence directory, the query, `match_count`, and a `matches` array with each match's `path`, `line`, and `snippet`

#### Scenario: Search writes an optional report
- **WHEN** `flashdb-rust evidence-search --evidence-dir <dir> --query <text> --report <path>` is executed
- **THEN** it writes the same JSON emitted to stdout to the requested report path and creates the parent directory when needed

#### Scenario: Search report does not match itself
- **WHEN** the requested `--report` path already exists inside the evidence directory and contains the query text
- **THEN** the search excludes that report path from matching before writing the new report

#### Scenario: Search only scans supported evidence text files
- **WHEN** the evidence directory contains `.json`, `.jsonl`, `.log`, `.md`, and unsupported files
- **THEN** only `.json`, `.jsonl`, `.log`, and `.md` files are scanned for matches

#### Scenario: Search is deterministic and bounded
- **WHEN** `--limit <N>` is provided
- **THEN** matches are returned in deterministic path and line order and no more than `N` matches are emitted

#### Scenario: Search rejects invalid limits
- **WHEN** `--limit` is `0` or greater than the maximum supported evidence search limit
- **THEN** the command fails with a CLI error explaining the accepted limit range

#### Scenario: Search snippets are bounded
- **WHEN** a matching evidence line is longer than the snippet budget
- **THEN** the emitted `snippet` is truncated to a bounded excerpt instead of copying the full line

#### Scenario: Search emits valid JSON for control characters
- **WHEN** the query or matching snippet contains tab, carriage return, or other JSON control characters
- **THEN** those characters are escaped in the JSON output

#### Scenario: Search reports missing query input
- **WHEN** `evidence-search` is executed without `--query`
- **THEN** the command fails with a CLI error explaining that `evidence-search` requires `--query`

#### Scenario: Search rejects empty query input
- **WHEN** `evidence-search` is executed with an empty `--query`
- **THEN** the command fails with a CLI error explaining that `evidence-search` requires a non-empty query

### Requirement: Auto-Translated Slice Evidence Source
The system SHALL allow FlashDB or non-FlashDB L3 migration loops to consume auto-translated Rust draft artifacts only as evidence-bound candidates, not as accepted implementation by default.

系统可以让 FlashDB 或非 FlashDB 的 L3 迁移循环消费自动翻译生成的 Rust draft，但这些生成物默认只能作为绑定证据的候选，不能自动视为已接受实现。

#### Scenario: Auto-generated draft is marked as candidate
- **WHEN** an L3 migration slice uses artifacts from the bounded automatic translation pipeline
- **THEN** the slice evidence records generated source paths, generator version, input slice spec hash, build profile hash, translation rule ids, AI candidate manifest if any, and candidate status before validation

#### Scenario: L3 gate remains authoritative
- **WHEN** an auto-generated Rust draft compiles
- **THEN** the L3 migration loop still requires C oracle, Rust replay, schema-aware diff, negative diff, unsafe scan, version manifest, cache metadata, and final verification evidence before accepting the slice

### Requirement: Auto-Translation Evidence Manifest Binding
The system SHALL bind auto-translation artifacts into the existing L3 evidence manifest without weakening existing FlashDB L3 gates.

系统必须把自动翻译产物绑定进现有 L3 evidence manifest，并且不得削弱现有 FlashDB L3 门禁。

#### Scenario: Manifest includes translator-specific artifacts
- **WHEN** an L3 evidence manifest is emitted for an auto-translated slice
- **THEN** it includes or references `l3-<slice>-auto-translation-plan.json`, `l3-<slice>-auto-translation-events.jsonl`, `l3-<slice>-type-map.json`, `l3-<slice>-cfg.json`, `l3-<slice>-patch-events.jsonl` or equivalent PatchPlan evidence, and `l3-<slice>-blocked-repairs.json`

#### Scenario: Missing translator artifacts fail the auto-translation claim
- **WHEN** an L3 manifest claims that a slice was produced by the automatic translation pipeline
- **THEN** the claim fails if context pack, type map, CFG, pointer graph decision, Rust draft provenance, C oracle evidence, Rust replay evidence, diff evidence, unsafe evidence, and version/config binding are not all present

### Requirement: Auto-Translation Repair Boundaries
The system SHALL preserve existing FlashDB slice contracts during automatic compile self-healing.

系统在自动编译自愈过程中必须保留现有 FlashDB slice contract，不得为了通过编译而扩大语义边界。

#### Scenario: Forbidden L3 edits block self-healing
- **WHEN** compile self-healing proposes to edit FlashDB fixture expected results, C oracle contracts, accepted differences, public behavior fields, source slice boundaries, or unsafe budget policy
- **THEN** the L3 loop records a blocked repair requiring human approval and refuses to apply the patch automatically

#### Scenario: Patch verification is staged
- **WHEN** an automatic self-healing patch is applied to a generated or migrated Rust artifact
- **THEN** the L3 loop reruns compile check first, targeted Rust replay tests second, full relevant Rust tests third, then C/Rust diff, negative diff, unsafe scan, version/config checks, and OpenSpec validation unless an earlier gate blocks
