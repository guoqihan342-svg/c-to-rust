## 1. OpenSpec And Scope

- [x] 1.1 Validate `add-flashdb-evidence-search` with `openspec validate add-flashdb-evidence-search --strict`.
- [x] 1.2 Confirm the first slice is a local text evidence search command, not a persistent evidence index or AI retrieval service.

## 2. TDD Tests

- [x] 2.1 Add a failing unit test for `evidence-search` returning `path`, `line`, and `snippet` metadata from supported evidence files.
- [x] 2.2 Add a failing unit test for `--limit` and supported extension filtering.
- [x] 2.3 Add a failing binary smoke test for stdout/report parity.
- [x] 2.4 Add boundary tests for empty queries, invalid limits, report self-exclusion, non-UTF-8 evidence, long snippets, and JSON control-character escaping.

## 3. CLI Implementation

- [x] 3.1 Extend CLI options and argument parsing for `--evidence-dir`, `--query`, and `--limit`.
- [x] 3.2 Implement deterministic recursive scanning for `.json`, `.jsonl`, `.log`, and `.md` files.
- [x] 3.3 Emit compact JSON with `command`, `schema_version`, `evidence_dir`, `query`, `limit`, `match_count`, and `matches`.
- [x] 3.4 Write optional reports through the existing `--report` behavior.
- [x] 3.5 Update help text without changing existing command behavior.
- [x] 3.6 Harden resource bounds with a maximum limit, line-by-line file scanning, symlink-directory skipping, recursion/file-count caps, and complete JSON control-character escaping.

## 4. Evidence And Verification

- [x] 4.1 Generate `validation/evidence/flashdb/evidence-search-red-test.log`.
- [x] 4.2 Generate `validation/evidence/flashdb/evidence-search-green-test.log`.
- [x] 4.3 Generate `validation/evidence/flashdb/evidence-search-report.json`.
- [x] 4.4 Run `cargo fmt -- --check`, `cargo test`, `openspec validate add-flashdb-evidence-search --strict`, `openspec validate --all`, and `git diff --check`.
- [x] 4.5 Archive the OpenSpec change after verification.
