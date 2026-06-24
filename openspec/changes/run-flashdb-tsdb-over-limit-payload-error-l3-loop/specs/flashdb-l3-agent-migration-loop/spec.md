## ADDED Requirements

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
