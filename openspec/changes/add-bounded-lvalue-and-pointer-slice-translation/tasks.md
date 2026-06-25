## 1. OpenSpec Contract

- [x] 1.1 Add proposal, design, specs, and tasks for bounded lvalue and pointer slice translation.
- [x] 1.2 Validate the change with `openspec validate add-bounded-lvalue-and-pointer-slice-translation --strict`.

## 2. Red Tests

- [x] 2.1 Add translator test for multiple pointer field writes preserving safe wrapper and pointer write effects.
- [x] 2.2 Add translator test for bounded `out[0]` pointer index write.
- [x] 2.3 Add translator test for bounded `out[0]` compound assignment or explicitly block it with recorded reason.
- [x] 2.4 Add negative translator tests for unsupported `arr[i]`, `s.field`, and `*(out + i)` lvalues.
- [x] 2.5 Run translator tests and observe new lvalue tests fail before implementation.

## 3. Translator Implementation

- [x] 3.1 Add a small lvalue classifier for simple identifier, pointer field, dereference identifier, pointer index, and unsupported complex lvalue.
- [x] 3.2 Route assignment, compound assignment, mutation analysis, and pointer-write classification through the lvalue classifier.
- [x] 3.3 Record lvalue kinds and pointer boundary decisions in CFG, pointer graph, and translation rule ids.
- [x] 3.4 Preserve safe public Rust boundary for pointer-bearing functions and block unsupported complex lvalues before emitting Rust.

## 4. Auto-Migrate Evidence

- [x] 4.1 Preserve lvalue kinds and pointer boundary decisions in normalized `cfg.json` and `pointer-graph.json`.
- [x] 4.2 Add auto_migrate unit test for bounded pointer/lvalue decision evidence.
- [x] 4.3 Ensure unsupported lvalue runs remain candidate/blocked evidence and do not claim semantic pass.

## 5. Verification

- [x] 5.1 Run `cargo fmt --manifest-path crates/c2r-translator/Cargo.toml -- --check`.
- [x] 5.2 Run `cargo test --manifest-path crates/c2r-translator/Cargo.toml`.
- [x] 5.3 Run `cargo clippy --manifest-path crates/c2r-translator/Cargo.toml --all-targets -- -D warnings`.
- [x] 5.4 Run `python -B -m unittest validation.tools.test_auto_migrate -v`.
- [x] 5.5 Run OpenSpec validation and `git diff --check`.
- [x] 5.6 Run short full-regression smoke with clean evidence required.
