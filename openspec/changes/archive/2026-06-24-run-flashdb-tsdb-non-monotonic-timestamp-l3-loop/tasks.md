## 1. Scope And Context

- [x] 1.1 Record the `tsdb-non-monotonic-timestamp` slice boundary and affected Rust/C/report files.
- [x] 1.2 Confirm the change is strict timestamp-order error evidence only and not capacity, rollover, integer-width, payload, or layout evidence.
- [x] 1.3 Assign bounded parallel review roles for feasibility, C oracle behavior, and follow-up slice recommendations.

## 2. TDD Fixture And Rust Tests

- [x] 2.1 Add a focused Rust test expecting duplicate timestamp rejection, decreasing timestamp rejection, no visible rejected entries, post-error valid append, and reopen stability.
- [x] 2.2 Run the focused test before implementation and capture the expected failure.
- [x] 2.3 Add `l3-tsdb-non-monotonic-timestamp.json` and align Rust replay behavior so the focused test passes.

## 3. Diff And Oracle Evidence

- [x] 3.1 Generate Rust replay evidence for the timestamp-order fixture.
- [x] 3.2 Generate C oracle evidence with `C_ORACLE_GENERATED` for the same fixture.
- [x] 3.3 Run schema-aware diff and persist a passing diff report.
- [x] 3.4 Mutate timestamp-order error code, operation success, query entries, or count and persist a negative diff.

## 4. Compile Self-Healing And Safety Evidence

- [x] 4.1 Run `cargo check --message-format=json`, summarize compiler status, and record whether patch self-healing was needed.
- [x] 4.2 Run unsafe scan and keep first-party non-test unsafe at 0%.
- [x] 4.3 Record cache metadata and performance smoke without using performance as a correctness gate.

## 5. Final Verification

- [x] 5.1 Run `cargo fmt -- --check`.
- [x] 5.2 Run focused timestamp-order replay/schema tests.
- [x] 5.3 Run `cargo test`.
- [x] 5.4 Run `openspec validate run-flashdb-tsdb-non-monotonic-timestamp-l3-loop --strict`.
- [x] 5.5 Run `openspec validate --all`.
- [x] 5.6 Run `git diff --check`.
- [x] 5.7 Write bilingual summary evidence and mark all tasks complete only after verification passes.
