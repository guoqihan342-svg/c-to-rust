## 1. OpenSpec And Gate Contract

- [x] 1.1 Add OpenSpec proposal, design, specs, and tasks for evidence-aware full regression.
- [x] 1.2 Validate the change with `openspec validate add-full-regression-evidence-gates --strict`.

## 2. L2 Evidence Gates

- [x] 2.1 Add validator tests for missing L2 negative diff, unsafe ledger, and test translation evidence.
- [x] 2.2 Implement L2 evidence summary validation and report output.
- [x] 2.3 Update L2 report generation so every accepted L2 slice has negative diff and test translation evidence.

## 3. FlashDB L3 And Negative Control Gates

- [x] 3.1 Add validator tests for invalid FlashDB L3 evidence manifests and missing negative mutation detection.
- [x] 3.2 Implement FlashDB L3 evidence manifest validation.
- [x] 3.3 Add an executable FlashDB fixture negative diff gate that expects a deliberate mismatch to fail.

## 4. Unsafe, Version, And Coverage Gates

- [x] 4.1 Add tests for expanded unsafe scan report categories and report writing.
- [x] 4.2 Implement FlashDB unsafe scan JSON report output and expanded category detection.
- [x] 4.3 Add version/config binding validator tests and implementation.
- [x] 4.4 Add coverage/test-translation validator tests and implementation.

## 5. Full Regression Integration

- [x] 5.1 Wire new evidence gates into `scripts/run-full-regression.ps1` with per-round report paths.
- [x] 5.2 Update `validation/gates.md` to document the new executable gate requirements and boundaries.

## 6. Verification

- [x] 6.1 Run targeted Python and Rust tests for new validators and unsafe scan behavior.
- [x] 6.2 Run OpenSpec validation and `git diff --check`.
- [x] 6.3 Run a short full-regression smoke round with long stress disabled.
