## 1. OpenSpec

- [x] 1.1 Create proposal, design, spec, and tasks for `remediate-low-cost-l1-native-failures`.
- [x] 1.2 Validate the change with `openspec validate "remediate-low-cost-l1-native-failures" --strict`.

## 2. Catalog Remediation

- [x] 2.1 Update high-confidence command-only recipes in `validation/projects.json`.
- [x] 2.2 Record deferred projects and remediation boundaries in documentation.
- [x] 2.3 Validate catalog shape with `scripts/validate-c-project-catalog.ps1`.

## 3. Evidence Tooling

- [x] 3.1 Add or generalize aggregation tooling for remediation result files.
- [x] 3.2 Generate a remediation JSON report.
- [x] 3.3 Generate a remediation Markdown report.
- [x] 3.4 Refresh per-project evidence and `validation/evidence/l1-native-summary.json`.

## 4. Remediation Runs

- [x] 4.1 Rerun accepted first-batch projects in a fresh external work root.
- [x] 4.2 Inspect remaining failures and ensure they are not overclaimed.
- [x] 4.3 Update `validation/README.md` with remediation status and report paths.

## 5. Validation and Delivery

- [x] 5.1 Run `openspec validate "remediate-low-cost-l1-native-failures" --strict`.
- [x] 5.2 Run `openspec validate --all`.
- [x] 5.3 Run `cargo test` in `flashDB_rust`.
- [x] 5.4 Run `cargo test` in `validation/l2_slices`.
- [x] 5.5 Run `git diff --check`.
- [x] 5.6 Commit and push the branch.
