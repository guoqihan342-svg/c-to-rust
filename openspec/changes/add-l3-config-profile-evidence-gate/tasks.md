## 1. OpenSpec

- [x] 1.1 Add change proposal, design, specs, and tasks for the config-profile evidence gate.
- [x] 1.2 Scope the spec delta to the existing `l3-validation-template` capability.
- [x] 1.3 Validate `add-l3-config-profile-evidence-gate` with OpenSpec strict mode.

## 2. L3 Template

- [x] 2.1 Add `validation/l3-template/config-profile.schema.json`.
- [x] 2.2 Add `validation/l3-template/config-profile.example.json` using the current FlashDB oracle config as the example profile.
- [x] 2.3 Extend `validation/l3-template/evidence-manifest.schema.json` and example manifest with config-profile references.
- [x] 2.4 Update the L3 template README, checklist, validation README, and gates with config-profile pass semantics and non-goals.

## 3. Verification

- [x] 3.1 Verify JSON files parse successfully.
- [x] 3.2 Run OpenSpec validation and whitespace validation.
- [x] 3.3 Run focused Rust verification as a conservative smoke check because the repository already has a fast Rust test path.
