## Context

FlashDB Rust already has strong test assets:

- L3 fixtures under `flashDB_rust/fixtures/`.
- Rust integration tests in `flashDB_rust/tests/differential_replay.rs` for replaying fixtures and negative diff regressions.
- Main-path tests such as `kvdb_main_paths.rs`, `tsdb_basic_paths.rs`, `persistence.rs`, and `abnormal_data.rs`.
- C oracle reports and schema-aware diffs under `validation/evidence/flashdb/`.

The missing layer is a machine-readable manifest proving how those C-side fixtures and oracle expectations map to Rust tests and coverage claims. This is a process/evidence gap, not a runtime gap.

中文：现有测试已经不少，缺的是机器可读映射：哪个 C oracle/fixture 来源，对应哪个 Rust test，覆盖哪些主路径、错误路径和负向回归。

## Goals / Non-Goals

**Goals:**

- Define a small reusable test-translation manifest shape.
- Require evidence links from C tests/fixtures/oracles to Rust test files and test names.
- Require explicit main-path, error-path, and negative-case coverage entries before L2/L3 success claims.
- Bind test translation evidence to source commit, repo commit, fixture hashes, test files, toolchain/profile inputs, and cache invalidation keys.

**Non-Goals:**

- Do not implement an automatic C test translator.
- Do not rewrite historical FlashDB evidence.
- Do not add Rust runtime code, dependencies, or CI jobs.
- Do not claim full branch/path coverage from the manifest alone.
- Do not replace C oracle, Rust replay, schema diff, negative diff, unsafe ledger, or pointer/config gates.

## Decisions

- Use a template and schema, not a generator.
  - Rationale: the immediate gap is traceability. A schema lets agents and reviewers audit coverage without committing to one generator.
  - Alternative considered: implement a C-test-to-Rust-test generator. Deferred because generator quality should be evaluated after the evidence contract stabilizes.

- Keep the gate applicable to both L2 and L3.
  - Rationale: L2 already has migrated Rust slices and oracle fixtures, while L3 has richer semantic evidence. Both benefit from code-test synchronization.
  - Alternative considered: only update L3. Rejected because code-only L2 success is also a risk.

- Make not-applicable explicit.
  - Rationale: some pure infrastructure or documentation-only changes may have no translatable C test. Silent absence would be ambiguous.
  - Alternative considered: always require C test mapping. Rejected because some future slices may rely on generated oracle fixtures instead of upstream C test names.

## Risks / Trade-offs

- [Risk] A manifest could be filled without enough tests. -> Mitigation: require explicit coverage entries, negative cases, and known gaps.
- [Risk] Agents may treat mapped tests as full semantic proof. -> Mitigation: state that test translation evidence complements but does not replace differential evidence.
- [Risk] Schema becomes too detailed. -> Mitigation: required fields stay focused on mapping, coverage, evidence links, and invalidation keys.
- [Risk] Historical evidence lacks this artifact. -> Mitigation: apply to future slices and preserve historical evidence unchanged.
