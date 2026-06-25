## 1. OpenSpec Contract

- [x] 1.1 Validate proposal, design, spec deltas, and tasks with `openspec validate add-bounded-pointer-arithmetic-input-read --strict`

## 2. Translator TDD

- [x] 2.1 Add failing translator tests for proven `*(values + i)` safe lowering, unbounded pointer arithmetic read rejection, and `*(out + i)` write guard
- [x] 2.2 Implement bounded pointer arithmetic input-read detection, canonical read evidence, Rust expression lowering, and unsupported event handling
- [x] 2.3 Verify `cargo test --manifest-path crates/c2r-translator/Cargo.toml --test bounded_translation` passes and existing `values[i]` behavior remains unchanged

## 3. Auto-Migrate Evidence

- [x] 3.1 Update auto_migrate normalization and tests so CFG, pointer graph, type map, plan, and manifest accept `bounded-pointer-arithmetic-input-read`
- [x] 3.2 Verify targeted Python tests for auto_migrate and evidence summary behavior

## 4. L3 Demo Slice

- [x] 4.1 Add `sum_i32_ptr_arith` Rust replay implementation, C oracle generator, fixture, Rust tests, and slice spec
- [x] 4.2 Wire `sum_i32_ptr_arith` into report emission, negative diff, performance smoke, safety evidence, L3 manifest, and evidence summary
- [x] 4.3 Add L3 evidence tests covering semantic gate, raw/canonical pointer read evidence, manifest keys, unsafe scan, and summary acceptance

## 5. Regression And Delivery

- [x] 5.1 Add `demo/sum-i32-ptr-arith` semantic smoke to `scripts/run-full-regression.ps1`
- [x] 5.2 Run formatting, Rust tests, Python tests, OpenSpec strict/all validation, git diff check, and short full-regression smoke
- [x] 5.3 Commit and push the completed change branch
