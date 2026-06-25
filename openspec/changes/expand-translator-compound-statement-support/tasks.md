## 1. OpenSpec Contract

- [x] 1.1 Add proposal, design, specs, and tasks for compound statement support.
- [x] 1.2 Validate the change with `openspec validate expand-translator-compound-statement-support --strict`.

## 2. Red Tests

- [x] 2.1 Add translator tests for standalone compound assignment.
- [x] 2.2 Add translator tests for standalone increment and decrement statements.
- [x] 2.3 Update the unsupported-expression test to keep a real unsupported syntax case.
- [x] 2.4 Run translator tests and observe the new support tests fail before implementation.

## 3. Translator Implementation

- [x] 3.1 Add statement classification for compound assignment.
- [x] 3.2 Add statement classification for standalone pre/post increment and decrement.
- [x] 3.3 Emit Rust for supported compound assignment and inc/dec statements.
- [x] 3.4 Record CFG statement kinds and translation rule ids for the new statement types.

## 4. Verification

- [x] 4.1 Run `cargo test` for `crates/c2r-translator`.
- [x] 4.2 Run `python -B -m unittest validation.tools.test_auto_migrate -v`.
- [x] 4.3 Run OpenSpec validation and `git diff --check`.
- [x] 4.4 Run short full-regression smoke.
