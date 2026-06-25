## 1. OpenSpec Contract

- [x] 1.1 Validate proposal, design, spec deltas, and tasks with `openspec validate add-call-expression-l3-demo-slice --strict`

## 2. Red Tests

- [x] 2.1 Add failing Rust replay test for `call_expression_chain` against a committed C oracle fixture
- [x] 2.2 Add failing L3 evidence tests for call expression diff, negative diff, unsafe scan, summary acceptance, and auto evidence call edges

## 3. Slice Implementation

- [x] 3.1 Add safe Rust replay module and public report API for `call_expression_chain`
- [x] 3.2 Add C oracle generator and committed fixture for small recursive input corpus
- [x] 3.3 Wire module export and Rust replay test

## 4. Evidence Pipeline

- [x] 4.1 Extend `emit_reports.rs` to emit C oracle, Rust report, schema diff, negative diff, performance smoke, unsafe scan/ledger, final verification, summary, and static L3 manifest for `demo-call-expression`
- [x] 4.2 Add `validation/slice-specs/demo-call-expression.json`
- [x] 4.3 Extend `validate_l2_evidence_summary.py` mapping for `demo-call-expression`
- [x] 4.4 Generate accepted evidence and auto evidence with `auto_migrate --accept-existing-evidence`
- [x] 4.5 Add full-regression semantic gate step for `demo-call-expression`

## 5. Validation And Delivery

- [x] 5.1 Run `cargo fmt --manifest-path validation/l2_slices/Cargo.toml -- --check`
- [x] 5.2 Run `cargo test --manifest-path validation/l2_slices/Cargo.toml`
- [x] 5.3 Run call-expression L3 evidence tests and auto evidence validator
- [x] 5.4 Run `python -B validation/tools/validate_l2_evidence_summary.py --evidence-root validation/evidence`
- [x] 5.5 Run `openspec validate add-call-expression-l3-demo-slice --strict` and `openspec validate --all`
- [x] 5.6 Run `git diff --check`
