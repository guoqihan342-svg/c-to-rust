## 1. OpenSpec Version Governance

- [x] 1.1 Create and validate the `add-versioned-migration-governance` OpenSpec proposal, design, spec, and tasks.
- [x] 1.2 Record read-only agent findings for OpenSpec/version docs and Rust/toolchain/evidence version gaps.

## 2. TDD For Version Manifest CLI

- [x] 2.1 Add a failing CLI test for `flashdb-rust version-manifest --report <path>` before production code changes.
- [x] 2.2 Persist the red test output at `validation/evidence/flashdb/version-governance-red-test.log`.
- [x] 2.3 Implement the minimal `version-manifest` command in `flashDB_rust/src/cli.rs`.
- [x] 2.4 Verify the targeted CLI test passes and the command emits required version fields.

## 3. Docs And Evidence

- [x] 3.1 Update `docs/c2rust-migration-agent/agent-contract.md` to require version manifests in runtime input/output and audit phases.
- [x] 3.2 Update `docs/c2rust-migration-agent/baseline-and-versioning.md` with the per-slice manifest gate.
- [x] 3.3 Generate `validation/evidence/flashdb/version-governance-manifest.json`.
- [x] 3.4 Generate `validation/evidence/flashdb/version-governance-summary.json` and `.md`.

## 4. Verification, Archive, And Delivery

- [x] 4.1 Run `cargo fmt -- --check` in `flashDB_rust`.
- [x] 4.2 Run targeted CLI tests for version manifest.
- [x] 4.3 Run `cargo check` and `cargo test` in `flashDB_rust`.
- [x] 4.4 Run `openspec validate add-versioned-migration-governance --strict`, `openspec validate --all`, and `git diff --check`.
- [x] 4.5 Archive the OpenSpec change after all tasks are complete.
- [x] 4.6 Commit and push the verified version-governance slice.
