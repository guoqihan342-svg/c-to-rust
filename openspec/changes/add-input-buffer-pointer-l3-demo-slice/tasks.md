## 1. OpenSpec Contract

- [x] 1.1 Add proposal, design, specs, and tasks for `add-input-buffer-pointer-l3-demo-slice`.
- [x] 1.2 Validate the change with `openspec validate add-input-buffer-pointer-l3-demo-slice --type change --strict`.

## 2. Test-First Translator Coverage

- [x] 2.1 Add failing translator tests for bounded `const int* values + len` input buffer reads and `out[0]` result writes.
- [x] 2.2 Add failing auto_migrate/evidence tests for input-buffer pointer graph, CFG, type map, and safe boundary decisions.
- [x] 2.3 Run targeted tests and record the expected red failures before implementation.

## 3. Bounded Input Buffer Translation

- [x] 3.1 Implement the minimal translator support needed for `values[i]` reads under a proven `i < len` loop.
- [x] 3.2 Record bounded input-buffer read, length companion, and aliasing boundary decisions in CFG and pointer graph evidence.
- [x] 3.3 Ensure unsupported buffer reads, pointer arithmetic, and unproven indexes remain blocked without Rust draft false success.

## 4. SumI32Buffer L3 Slice

- [x] 4.1 Add the `sum_i32_buffer` slice spec and deterministic C oracle fixture generator.
- [x] 4.2 Add safe Rust replay code and report emission for empty, single-item, multi-item, negative, and boundary-safe cases.
- [x] 4.3 Add schema diff, negative diff, unsafe scan, context pack, CFG, pointer graph, type map, test translation, summary, cache, and version evidence.
- [x] 4.4 Ensure auto_migrate accepted evidence records generated-draft boundary, input-buffer decisions, and semantic gate bindings.

## 5. Regression Gate

- [x] 5.1 Wire the `sum_i32_buffer` semantic evidence validation into the cheap smoke/full-regression path.
- [x] 5.2 Keep the new gate deterministic and independent of network or long-running stress.
- [x] 5.3 Ensure `-RequireCleanEvidence` passes after the new evidence is committed.

## 6. Verification

- [x] 6.1 Run targeted Python/Rust tests for translator, auto_migrate, replay, and evidence validators.
- [x] 6.2 Run `cargo fmt`, `cargo test`, and `cargo clippy` for affected Rust crates.
- [x] 6.3 Run `openspec validate add-input-buffer-pointer-l3-demo-slice --type change --strict` and `openspec validate --all`.
- [x] 6.4 Run `git diff --check`.
- [x] 6.5 Run one short full-regression smoke with clean evidence required.
- [x] 6.6 Commit and push the verified change.
