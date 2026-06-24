## 1. Scope And Context

- [x] 1.1 Record the `tsdb-payload-boundary` slice boundary and affected Rust/C/report files.
- [x] 1.2 Confirm the change is public payload visibility evidence only and does not alter TSDB storage, replay schema, or FlashDB semantics.
- [x] 1.3 Assign bounded parallel review roles for slice feasibility, C oracle behavior, and evidence review.

## 2. TDD Fixture And Rust Tests

- [x] 2.1 Add a focused Rust test that expects a `payload-boundary` fixture to show empty and 128-byte payload visibility across query/count/reopen.
- [x] 2.2 Run the focused test before adding the fixture and capture the expected failure.
- [x] 2.3 Add `l3-tsdb-payload-boundary.json` and make the focused test pass.

## 3. Diff And Oracle Evidence

- [x] 3.1 Generate Rust replay evidence for the payload-boundary fixture.
- [x] 3.2 Generate C oracle evidence with `C_ORACLE_GENERATED` for the same fixture.
- [x] 3.3 Run schema-aware diff and persist a passing diff report.
- [x] 3.4 Mutate the 128-byte payload value, empty payload value, query entries, or count and persist a negative diff proving payload regression protection.

## 4. Compile Self-Healing And Safety Evidence

- [x] 4.1 Run `cargo check --message-format=json`, summarize compiler status, and record whether patch self-healing was needed.
- [x] 4.2 Run unsafe scan and keep first-party non-test unsafe at 0%.
- [x] 4.3 Record cache metadata and performance smoke without using performance as a correctness gate.

## 5. Final Verification

- [x] 5.1 Run `cargo fmt -- --check`.
- [x] 5.2 Run focused payload-boundary replay/schema tests.
- [x] 5.3 Run `cargo test`.
- [x] 5.4 Run `openspec validate run-flashdb-tsdb-payload-boundary-l3-loop --strict`.
- [x] 5.5 Run `openspec validate --all`.
- [x] 5.6 Run `git diff --check`.
- [x] 5.7 Write bilingual summary evidence and mark all tasks complete only after verification passes.
