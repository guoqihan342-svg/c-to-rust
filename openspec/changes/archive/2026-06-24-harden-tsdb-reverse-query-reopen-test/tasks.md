## 1. Scope

- [x] 1.1 Create and validate `harden-tsdb-reverse-query-reopen-test`.
- [x] 1.2 Confirm the change is test-only and does not modify production code, fixtures, C oracle, replay, or public behavior.
- [x] 1.3 Generate the per-slice version manifest before final verification evidence.

## 2. Test Hardening

- [x] 2.1 Add a focused assertion helper or local assertion for `ts-rqr-006`.
- [x] 2.2 Assert `ts-rqr-006` includes `op:"ts.reopen"`, `status:"ok"`, `code:"OK"`, and `image_hash`.
- [x] 2.3 Persist targeted test output under `validation/evidence/flashdb/`.

## 3. Verification And Delivery

- [x] 3.1 Run targeted reverse-query-reopen replay tests.
- [x] 3.2 Run `cargo fmt -- --check`.
- [x] 3.3 Run `cargo check` and `cargo test`.
- [x] 3.4 Run `openspec validate harden-tsdb-reverse-query-reopen-test --strict`, `openspec validate --all`, and `git diff --check`.
- [x] 3.5 Archive the OpenSpec change.
- [x] 3.6 Commit and push the verified test-hardening slice.
