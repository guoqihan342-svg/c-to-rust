## 1. OpenSpec

- [x] 1.1 Create proposal, design, spec, and tasks for `run-supercomplex-l2-slice-validation`.
- [x] 1.2 Validate the change with `openspec validate "run-supercomplex-l2-slice-validation" --strict`.

## 2. Test-First Rust Slice Crate

- [x] 2.1 Create `validation/l2_slices` Rust crate skeleton.
- [x] 2.2 Add failing fixture-driven tests for SQLite varint, zlib-ng Adler-32, and zstd xxHash32.
- [x] 2.3 Run the tests and capture the expected red failure.
- [x] 2.4 Implement the minimal safe Rust slice code until the tests pass.

## 3. C Oracle and Diff Evidence

- [x] 3.1 Generate SQLite varint C oracle fixtures from the pinned L1 checkout.
- [x] 3.2 Generate zlib-ng Adler-32 C oracle fixtures from the pinned L1 checkout.
- [x] 3.3 Generate zstd xxHash32 C oracle fixtures from the pinned L1 checkout.
- [x] 3.4 Generate Rust slice reports and schema-aware C/Rust diff evidence.
- [x] 3.5 Record L2/L3 summary evidence and unsafe scan result.

## 4. Validation and Delivery

- [x] 4.1 Run `cargo test` in `validation/l2_slices`.
- [x] 4.2 Run `cargo test` in `flashDB_rust`.
- [x] 4.3 Run `openspec validate "run-supercomplex-l2-slice-validation" --strict`.
- [x] 4.4 Run `openspec validate --all`.
- [x] 4.5 Run `git diff --check`.
- [x] 4.6 Commit and push the branch.
