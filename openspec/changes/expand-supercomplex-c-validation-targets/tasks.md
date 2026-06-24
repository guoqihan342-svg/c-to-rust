## 1. OpenSpec

- [x] 1.1 Create proposal, design, spec, and tasks for `expand-supercomplex-c-validation-targets`.
- [x] 1.2 Validate the new change with `openspec validate "expand-supercomplex-c-validation-targets" --strict`.

## 2. Catalog Expansion

- [x] 2.1 Raise catalog `minimum_targets` to 20.
- [x] 2.2 Add Valkey, zstd, libjpeg-turbo, MicroPython, tmux, Zephyr, and FreeRTOS-Kernel.
- [x] 2.3 Update validation README target count and scope wording.

## 3. Verification Hardening

- [x] 3.1 Make remote probe fail on default-branch mismatch.
- [x] 3.2 Add `validation/l1-l2-project-cards.md`.
- [x] 3.3 Regenerate offline L0 evidence.
- [x] 3.4 Regenerate remote L0 evidence with default branch checks.

## 4. Validation and Delivery

- [x] 4.1 Run `powershell -ExecutionPolicy Bypass -File .\scripts\validate-c-project-catalog.ps1`.
- [x] 4.2 Run `powershell -ExecutionPolicy Bypass -File .\scripts\validate-c-project-catalog.ps1 -ProbeRemote`.
- [x] 4.3 Run `openspec validate "expand-supercomplex-c-validation-targets" --strict`.
- [x] 4.4 Run `openspec validate --all`.
- [x] 4.5 Run `cargo test` for the FlashDB Rust crate.
- [x] 4.6 Run `git diff --check`.
- [x] 4.7 Commit and push the branch.
