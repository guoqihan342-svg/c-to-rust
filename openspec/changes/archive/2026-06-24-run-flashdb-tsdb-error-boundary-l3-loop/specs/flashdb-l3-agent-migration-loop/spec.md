## ADDED Requirements

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
The system SHALL keep TSDB error-boundary first-party non-test unsafe at 0% for this slice and SHALL use deterministic cache invalidation and bounded parallel agent roles.

系统必须将本 TSDB error-boundary 切片的一方非测试 unsafe 保持为 0%，并使用确定性缓存失效与有边界的并行智能体角色。

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
