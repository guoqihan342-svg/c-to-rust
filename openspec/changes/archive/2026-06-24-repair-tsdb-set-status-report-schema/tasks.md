## 1. Scope And Context

- [x] 1.1 Record the `tsdb-set-status-schema` slice boundary and affected Rust/C/report files.
- [x] 1.2 Confirm the change is schema-only and does not alter TSDB storage or FlashDB semantics.
- [x] 1.3 Assign bounded parallel review roles for Rust emitter/schema diff and OpenSpec/evidence review.

## 2. TDD Red Test

- [x] 2.1 Add a focused Rust test that expects successful `ts.set_status` to use `ts_status` and have no duplicate business `status` key.
- [x] 2.2 Run the focused test before production edits and capture the expected failure.

## 3. Schema Repair Implementation

- [x] 3.1 Update Rust replay successful `ts.set_status` output to use `ts_status`.
- [x] 3.2 Update C oracle successful `ts.set_status` output to use `ts_status`.
- [x] 3.3 Update checked-in expected fixtures and tests that assert the old status field shape.

## 4. Diff And Oracle Evidence

- [x] 4.1 Generate repaired Rust replay evidence for a fixture containing successful `ts.set_status`.
- [x] 4.2 Generate C oracle evidence with `C_ORACLE_GENERATED` for the same fixture.
- [x] 4.3 Run schema-aware diff and persist a passing diff report.
- [x] 4.4 Mutate `ts_status` and persist a negative diff proving behavior-field protection.

## 5. Compile Self-Healing And Safety Evidence

- [x] 5.1 Run `cargo check --message-format=json`, summarize compiler status, and record whether patch self-healing was needed.
- [x] 5.2 Run unsafe scan and keep first-party non-test unsafe at 0%.
- [x] 5.3 Record cache metadata and performance smoke without using performance as a correctness gate.

## 6. Final Verification

- [x] 6.1 Run `cargo fmt -- --check`.
- [x] 6.2 Run focused replay/schema tests.
- [x] 6.3 Run `cargo test`.
- [x] 6.4 Run `openspec validate repair-tsdb-set-status-report-schema --strict`.
- [x] 6.5 Run `openspec validate --all`.
- [x] 6.6 Run `git diff --check`.
- [x] 6.7 Write bilingual summary evidence and mark all tasks complete only after verification passes.
