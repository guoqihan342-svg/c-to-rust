## 1. OpenSpec Artifacts

- [x] 1.1 Create proposal, design, spec, and tasks for `add-multi-project-validation-catalog`.
- [x] 1.2 Validate the new change with `openspec validate "add-multi-project-validation-catalog" --strict`.

## 2. Catalog and Documentation

- [x] 2.1 Add `validation/projects.json` with at least 12 complex C/C-major targets.
- [x] 2.2 Add `validation/README.md` explaining scope and non-equivalence boundaries.
- [x] 2.3 Add `validation/gates.md` defining L0-L3 gates and evidence requirements.

## 3. Verifier and Evidence

- [x] 3.1 Add `scripts/validate-c-project-catalog.ps1`.
- [x] 3.2 Run offline catalog validation and write evidence.
- [x] 3.3 Run optional remote probe and write evidence.
- [x] 3.4 Ensure remote probe evidence records default branch and HEAD SHA or failure detail.

## 4. Validation and Delivery

- [x] 4.1 Run `powershell -ExecutionPolicy Bypass -File .\scripts\validate-c-project-catalog.ps1`.
- [x] 4.2 Run `powershell -ExecutionPolicy Bypass -File .\scripts\validate-c-project-catalog.ps1 -ProbeRemote`.
- [x] 4.3 Run `openspec validate "add-multi-project-validation-catalog" --strict`.
- [x] 4.4 Run `openspec validate --all`.
- [x] 4.5 Run `git diff --check`.
- [ ] 4.6 Commit and push the branch.
