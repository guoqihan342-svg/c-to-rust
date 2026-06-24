## ADDED Requirements

### Requirement: KVDB Compact Overwrite L3 Slice Selection
The system SHALL select `kvdb-compact-overwrite` as a FlashDB L3 migration slice and SHALL record visible-behavior boundaries before implementation.

系统必须选择 `kvdb-compact-overwrite` 作为 FlashDB L3 迁移切片，并在实现前记录可见行为边界。

#### Scenario: KVDB compact overwrite slice is declared
- **WHEN** the KVDB compact/overwrite L3 loop starts
- **THEN** it records `kvdb-compact-overwrite` as the active slice with Rust APIs `KvDb::set`, `KvDb::get`, `KvDb::entries`, `KvDb::compact`, `KvDb::open`, `KvDb::delete`, and C oracle operations `kv.set`, `kv.get`, `kv.entries`, `kv.compact`, `kv.reopen`, `kv.delete`

#### Scenario: Compact boundary is visible behavior only
- **WHEN** the slice contract is frozen
- **THEN** it states that `kv.compact` is validated through pre/post compact visible behavior and does not claim native FlashDB GC, sector movement, tombstone layout, or byte-for-byte flash image equivalence

### Requirement: KVDB Compact Overwrite Fixture Coverage
The system SHALL use a named L3 fixture that covers same-key overwrite, compact, reopen, entries, and delete behavior.

系统必须使用命名的 L3 fixture 覆盖同 key overwrite、compact、reopen、entries 与 delete 行为。

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

系统必须使用同一个 fixture 和 schema-aware diff 对比 C/Rust KVDB compact/overwrite 可见行为。

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

系统必须在 `validation/evidence/flashdb/` 下持久化 KVDB compact/overwrite L3 证据，并按从快到慢的顺序重跑验证。

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

系统必须将此 KVDB compact/overwrite 切片的 first-party non-test unsafe 保持为 0%，并使用确定性缓存失效和有边界的并行智能体角色。

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

系统必须记录 KVDB compact/overwrite 性能烟测数据，但不能用性能结果替代正确性门禁。

#### Scenario: KVDB compact overwrite performance evidence is recorded
- **WHEN** the L3 loop runs performance smoke
- **THEN** it records backend, operation counts, elapsed time, toolchain status, command, and report path

#### Scenario: KVDB compact overwrite async or threading requires design update
- **WHEN** async runtime, multithreaded replay, or internal concurrency is proposed for FlashDB Rust KVDB logic
- **THEN** the agent requires prior performance evidence, deterministic semantics, and an OpenSpec design update before implementation
