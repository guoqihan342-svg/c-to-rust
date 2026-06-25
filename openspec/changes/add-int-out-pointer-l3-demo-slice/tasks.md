## 1. OpenSpec Contract

- [x] 1.1 Add proposal, design, specs, and tasks for `add-int-out-pointer-l3-demo-slice`.
- [x] 1.2 Validate the change with `openspec validate add-int-out-pointer-l3-demo-slice --type change --strict`.

## 2. Test-First Evidence

- [x] 2.1 Add failing tests for `store_add_one` Rust replay equivalence, unsafe scan evidence, and required manifest bindings.
- [x] 2.2 Run targeted tests and record the expected red failure before implementation.

## 3. StoreAddOne L3 Slice

- [x] 3.1 Add the `store_add_one` slice spec and deterministic C oracle fixture.
- [x] 3.2 Add safe Rust replay code and report emission for nominal, boundary, and negative integer cases.
- [x] 3.3 Add schema diff, negative diff, unsafe scan, context pack, CFG, pointer graph, type map, and summary evidence.
- [x] 3.4 Ensure auto_migrate evidence records bounded lvalue and pointer decisions for the `out[0]` slice.

## 4. Regression Gate

- [x] 4.1 Wire the `store_add_one` evidence validation into the cheap smoke/full-regression path.
- [x] 4.2 Keep the new gate deterministic and independent of network or long-running stress.

## 5. Verification

- [x] 5.1 Run targeted Python/Rust tests for the new slice and evidence validators.
- [x] 5.2 Run `cargo fmt`, `cargo test`, and `cargo clippy` for affected Rust crates.
- [x] 5.3 Run `openspec validate add-int-out-pointer-l3-demo-slice --type change --strict` and `openspec validate --all`.
- [x] 5.4 Run `git diff --check`.
- [x] 5.5 Run one short full-regression smoke with clean evidence required.
- [x] 5.6 Commit and push the verified change.
