## ADDED Requirements

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
