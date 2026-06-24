## ADDED Requirements

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
