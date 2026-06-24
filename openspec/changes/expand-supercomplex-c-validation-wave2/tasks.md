## 1. OpenSpec

- [x] 1.1 Create proposal, design, spec, and tasks for `expand-supercomplex-c-validation-wave2`.
- [x] 1.2 Validate the change with `openspec validate "expand-supercomplex-c-validation-wave2" --strict`.

## 2. Catalog Expansion

- [x] 2.1 Add at least 18 wave2 super-complex C/C-major targets to `validation/projects.json`.
- [x] 2.2 Raise catalog `minimum_targets` to at least 40.
- [x] 2.3 Update `validation/README.md` target count and reporting boundary.
- [x] 2.4 Update `validation/l1-l2-project-cards.md` with wave2 priority and target cards.
- [x] 2.5 Update `validation/evidence/l1-native-summary.json` catalog count and not-attempted list.

## 3. Evidence

- [x] 3.1 Run offline catalog validation and regenerate `validation/evidence/catalog-validation.json`.
- [x] 3.2 Run remote HEAD/default-branch probe and regenerate `validation/evidence/catalog-remote-probe.json`.
- [x] 3.3 Record wave2 summary evidence without overclaiming L1/L2/L3.

## 4. Validation and Delivery

- [x] 4.1 Run `openspec validate "expand-supercomplex-c-validation-wave2" --strict`.
- [x] 4.2 Run `openspec validate --all`.
- [x] 4.3 Run `cargo test` in `flashDB_rust`.
- [x] 4.4 Run `cargo test` in `validation/l2_slices`.
- [x] 4.5 Run `git diff --check`.
- [x] 4.6 Commit and push the branch.
