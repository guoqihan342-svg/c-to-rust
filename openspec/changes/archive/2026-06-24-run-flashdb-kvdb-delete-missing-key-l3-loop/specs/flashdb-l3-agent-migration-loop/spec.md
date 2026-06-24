## ADDED Requirements

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
The system SHALL keep KVDB delete-missing-key first-party non-test unsafe at 0% for this slice and SHALL use deterministic cache invalidation and bounded parallel agent roles.

系统必须将此 KVDB delete-missing-key 切片的 first-party non-test unsafe 保持为 0%，并使用确定性缓存失效和有边界的并行智能体角色。

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
