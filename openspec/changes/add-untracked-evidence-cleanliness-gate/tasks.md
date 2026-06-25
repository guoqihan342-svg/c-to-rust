## 1. OpenSpec Contract

- [x] 1.1 Add proposal, design, specs, and tasks for untracked evidence cleanliness.
- [x] 1.2 Validate the change with `openspec validate add-untracked-evidence-cleanliness-gate --strict`.

## 2. Red Verification

- [x] 2.1 Add a temporary untracked file under `validation/evidence/**` and confirm the current cleanliness command does not fail.
- [x] 2.2 Remove the temporary untracked file after the red verification.

## 3. Full Regression Integration

- [x] 3.1 Update `evidence-cleanliness-check` to list untracked files under `validation/evidence/**`.
- [x] 3.2 Make the step fail when untracked evidence files are present.
- [x] 3.3 Preserve default behavior when `-RequireCleanEvidence` is not supplied.

## 4. Documentation

- [x] 4.1 Update `validation/gates.md` to document tracked and untracked evidence cleanliness.

## 5. Verification

- [x] 5.1 Run OpenSpec validation and `git diff --check`.
- [x] 5.2 Run a negative check proving untracked evidence fails the cleanliness command.
- [x] 5.3 Run short full-regression smoke without the cleanliness option.
- [x] 5.4 Run short full-regression smoke with the cleanliness option after evidence is clean.
