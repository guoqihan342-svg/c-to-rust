## 1. OpenSpec Contract

- [x] 1.1 Add proposal, design, specs, and tasks for the explicit evidence cleanliness gate.
- [x] 1.2 Validate the change with `openspec validate add-evidence-cleanliness-gate --strict`.

## 2. Full Regression Integration

- [x] 2.1 Add a full-regression parameter that explicitly enables committed evidence cleanliness checking.
- [x] 2.2 Add a conditional per-round step that lists and fails on tracked `validation/evidence` content drift.
- [x] 2.3 Keep default local full-regression behavior unchanged when the parameter is not supplied.

## 3. Documentation

- [x] 3.1 Update `validation/gates.md` to document the evidence cleanliness gate, usage, and non-goals.

## 4. Verification

- [x] 4.1 Run OpenSpec validation and `git diff --check`.
- [x] 4.2 Run short full-regression smoke without the cleanliness option.
- [x] 4.3 Run short full-regression smoke with the cleanliness option after committed evidence is clean.
