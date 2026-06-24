## 1. Scope And Context

- [x] 1.1 Record the `tsdb-over-limit-payload-error` slice boundary and affected Rust/C/report files.
- [x] 1.2 Confirm the change is 129-byte payload length error evidence only and not capacity, rollover, binary/NUL, larger payload, or layout evidence.
- [x] 1.3 Assign bounded parallel review roles for feasibility, C oracle behavior, and evidence audit.

## 2. TDD Fixture And Rust Tests

- [x] 2.1 Add a focused Rust test expecting 129-byte append rejection, no visible rejected entry, post-error valid append, and reopen stability.
- [x] 2.2 Run the focused test before implementation and capture the expected failure.
- [x] 2.3 Add `l3-tsdb-over-limit-payload-error.json` and align Rust replay behavior so the focused test passes.

## 3. Diff And Oracle Evidence

- [x] 3.1 Generate Rust replay evidence for the over-limit payload fixture.
- [x] 3.2 Generate C oracle evidence with `C_ORACLE_GENERATED` for the same fixture.
- [x] 3.3 Run schema-aware diff and persist a passing diff report.
- [x] 3.4 Mutate the over-limit error code, operation success, query entries, or count and persist a negative diff.

## 4. Compile Self-Healing And Safety Evidence

- [x] 4.1 Run `cargo check --message-format=json`, summarize compiler status, and record whether patch self-healing was needed.
- [x] 4.2 Run unsafe scan and keep first-party non-test unsafe at 0%.
- [x] 4.3 Record cache metadata and performance smoke without using performance as a correctness gate.

## 5. Final Verification

- [x] 5.1 Run `cargo fmt -- --check`.
- [x] 5.2 Run focused over-limit payload replay/schema tests.
- [x] 5.3 Run `cargo test`.
- [x] 5.4 Run `openspec validate run-flashdb-tsdb-over-limit-payload-error-l3-loop --strict`.
- [x] 5.5 Run `openspec validate --all`.
- [x] 5.6 Run `git diff --check`.
- [x] 5.7 Write bilingual summary evidence and mark all tasks complete only after verification passes.
