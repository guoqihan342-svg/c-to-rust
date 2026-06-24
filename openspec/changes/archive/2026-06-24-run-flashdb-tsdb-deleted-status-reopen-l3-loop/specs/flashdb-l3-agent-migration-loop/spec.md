## ADDED Requirements

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
