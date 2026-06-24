## 1. Scope And Context

- [x] 1.1 Record the `tsdb-user2-status` slice boundary and affected Rust/C/report files.
- [x] 1.2 Confirm the change is public status evidence only and does not alter TSDB storage or FlashDB semantics.
- [x] 1.3 Assign bounded parallel review roles for Rust/C feasibility and OpenSpec/evidence review.

## 2. TDD Fixture And Rust Tests

- [x] 2.1 Add a focused Rust test that expects a `user2` fixture to emit `ts_status:"user2"` and stable `user2` counts.
- [x] 2.2 Run the focused test before adding the fixture and capture the expected failure.
- [x] 2.3 Add `l3-tsdb-user2-status.json` and make the focused test pass.

## 3. Diff And Oracle Evidence

- [x] 3.1 Generate repaired Rust replay evidence for the `user2` fixture.
- [x] 3.2 Generate C oracle evidence with `C_ORACLE_GENERATED` for the same fixture.
- [x] 3.3 Run schema-aware diff and persist a passing diff report.
- [x] 3.4 Mutate `ts_status` or `count` and persist a negative diff proving behavior-field protection.

## 4. Compile Self-Healing And Safety Evidence

- [x] 4.1 Run `cargo check --message-format=json`, summarize compiler status, and record whether patch self-healing was needed.
- [x] 4.2 Run unsafe scan and keep first-party non-test unsafe at 0%.
- [x] 4.3 Record cache metadata and performance smoke without using performance as a correctness gate.

## 5. Final Verification

- [x] 5.1 Run `cargo fmt -- --check`.
- [x] 5.2 Run focused user2 replay/schema tests.
- [x] 5.3 Run `cargo test`.
- [x] 5.4 Run `openspec validate run-flashdb-tsdb-user2-status-l3-loop --strict`.
- [x] 5.5 Run `openspec validate --all`.
- [x] 5.6 Run `git diff --check`.
- [x] 5.7 Write bilingual summary evidence and mark all tasks complete only after verification passes.
