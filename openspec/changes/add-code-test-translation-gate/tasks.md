## 1. OpenSpec

- [x] 1.1 Add proposal, design, specs, and tasks for the code-test translation gate.
- [x] 1.2 Add `code-test-translation-gate` requirements.
- [x] 1.3 Add `l3-validation-template` delta requirements for test translation references.
- [x] 1.4 Validate `add-code-test-translation-gate` with OpenSpec strict mode.

## 2. Test Translation Template

- [x] 2.1 Add `validation/test-translation-template/README.md`.
- [x] 2.2 Add `validation/test-translation-template/checklist.md`.
- [x] 2.3 Add `validation/test-translation-template/test-translation.schema.json`.
- [x] 2.4 Add `validation/test-translation-template/test-translation.example.json`.

## 3. Validation Templates

- [x] 3.1 Update `validation/gates.md` with L2/L3 code-test translation pass semantics.
- [x] 3.2 Update `validation/README.md` to list the test translation template.
- [x] 3.3 Update `validation/l3-template/README.md`, `checklist.md`, `evidence-manifest.json`, `evidence-manifest.schema.json`, and `evidence-manifest.example.json`.

## 4. Verification

- [x] 4.1 Verify all new and changed JSON files parse successfully.
- [x] 4.2 Run OpenSpec validation and whitespace validation.
- [x] 4.3 Run focused Rust verification as a conservative smoke check because the repository has fast Rust tests.
