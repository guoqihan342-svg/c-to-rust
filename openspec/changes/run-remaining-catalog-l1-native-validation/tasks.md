## 1. OpenSpec

- [x] 1.1 Create proposal, design, spec, and tasks for `run-remaining-catalog-l1-native-validation`.
- [x] 1.2 Validate the change with `openspec validate "run-remaining-catalog-l1-native-validation" --strict`.

## 2. Parallel L1 Execution

- [x] 2.1 Run FFmpeg worker in an external work root.
- [x] 2.2 Run MicroPython worker in an external work root.
- [x] 2.3 Run Zephyr worker in an external work root.
- [x] 2.4 Run FreeRTOS Kernel worker in an external work root.

## 3. Evidence Aggregation

- [x] 3.1 Aggregate worker `results.json` files into per-project L1 evidence.
- [x] 3.2 Add `validation/evidence/remaining-l1-native-summary.json`.
- [x] 3.3 Update `validation/evidence/l1-native-summary.json`.
- [x] 3.4 Update README with 40/40 L1 attempt status.

## 4. Validation and Delivery

- [x] 4.1 Run `powershell -ExecutionPolicy Bypass -File .\scripts\validate-c-project-catalog.ps1`.
- [x] 4.2 Run `openspec validate "run-remaining-catalog-l1-native-validation" --strict`.
- [x] 4.3 Run `openspec validate --all`.
- [x] 4.4 Run `cargo test` in `flashDB_rust`.
- [x] 4.5 Run `cargo test` in `validation/l2_slices`.
- [x] 4.6 Run `git diff --check`.
- [x] 4.7 Commit and push the branch.
