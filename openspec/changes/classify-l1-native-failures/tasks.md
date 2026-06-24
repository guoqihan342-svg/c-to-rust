## 1. OpenSpec

- [x] 1.1 Create proposal, design, spec, and tasks for `classify-l1-native-failures`.
- [x] 1.2 Validate the change with `openspec validate "classify-l1-native-failures" --strict`.

## 2. Classifier

- [x] 2.1 Add a deterministic classifier under `validation/tools`.
- [x] 2.2 Smoke-check the classifier against current L1 evidence.

## 3. Evidence

- [x] 3.1 Generate `validation/evidence/l1-failure-classification.json`.
- [x] 3.2 Generate `validation/evidence/l1-failure-classification.md`.
- [x] 3.3 Update README with classification status and report paths.

## 4. Validation and Delivery

- [x] 4.1 Run `powershell -ExecutionPolicy Bypass -File .\scripts\validate-c-project-catalog.ps1`.
- [x] 4.2 Run `openspec validate "classify-l1-native-failures" --strict`.
- [x] 4.3 Run `openspec validate --all`.
- [x] 4.4 Run `cargo test` in `flashDB_rust`.
- [x] 4.5 Run `cargo test` in `validation/l2_slices`.
- [x] 4.6 Run `git diff --check`.
- [x] 4.7 Commit and push the branch.
