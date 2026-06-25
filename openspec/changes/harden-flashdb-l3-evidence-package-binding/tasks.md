## 1. OpenSpec Contract

- [x] 1.1 Add proposal, design, specs, and tasks for FlashDB L3 evidence package binding hardening.
- [x] 1.2 Validate the change with `openspec validate harden-flashdb-l3-evidence-package-binding --strict`.

## 2. Red Tests

- [x] 2.1 Add a unit test proving a failed positive diff report is rejected.
- [x] 2.2 Add a unit test proving failed final verification is rejected.
- [x] 2.3 Add a unit test proving a summary-declared evidence hash mismatch is rejected.
- [x] 2.4 Run the targeted test module and observe the new tests fail before implementation.

## 3. Validator Implementation

- [x] 3.1 Validate loaded positive diff content, including status and first mismatch.
- [x] 3.2 Validate loaded final verification content, including status, diff status, C oracle generation, and check results.
- [x] 3.3 Validate summary-declared evidence `sha256` values against resolved files when hashes are present.

## 4. Documentation

- [x] 4.1 Update `validation/gates.md` to document content-level FlashDB L3 package binding.

## 5. Verification

- [x] 5.1 Run targeted FlashDB L3 validator unit tests.
- [x] 5.2 Run `validate_flashdb_l3_evidence.py` against committed `validation/evidence`.
- [x] 5.3 Run OpenSpec validation and `git diff --check`.
- [x] 5.4 Run short full-regression smoke.
