## ADDED Requirements

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
