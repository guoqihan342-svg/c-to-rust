## ADDED Requirements

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
