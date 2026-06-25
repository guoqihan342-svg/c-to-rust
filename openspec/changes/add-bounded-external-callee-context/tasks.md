## 1. OpenSpec Contract

- [x] 1.1 Validate proposal, design, spec deltas, and tasks with `openspec validate add-bounded-external-callee-context --strict`

## 2. Red Tests

- [x] 2.1 Add failing `auto_migrate` unit test proving a declared external helper callee gets compile-only Rust stub context and rust-check passes
- [x] 2.2 Add failing `auto_migrate` or validator test proving an undeclared helper callee cannot be silently stubbed
- [x] 2.3 Add failing semantic validator test proving external callee context must bind real helper signature/source metadata
- [x] 2.4 Add failing L3 demo evidence test for `demo-external-direct-callee` plan/context/manifest/direct call edge coverage

## 3. Auto Pipeline Implementation

- [x] 3.1 Extend slice spec parsing helpers in `auto_migrate.py` to read `c_boundary.external_direct_callees[]` and helper signatures
- [x] 3.2 Generate compile-only Rust helper stubs for declared primitive external direct callees before rust-check
- [x] 3.3 Record `external_direct_callees`, callee signature binding, source refs, `stub_kind`, and `semantics_verified` in normalized plan and context pack
- [x] 3.4 Block missing or unsupported helper callees with explicit blocked repairs/events instead of silent stub injection
- [x] 3.5 Extend `validate_auto_translation_evidence.py` semantic pass checks for external direct callee context

## 4. L3 Demo Slice

- [x] 4.1 Add safe Rust replay module and public report API for `external_direct_callee`
- [x] 4.2 Add C oracle generator and committed fixture for caller/helper corpus
- [x] 4.3 Wire module export and Rust replay test
- [x] 4.4 Extend `emit_reports.rs` to emit direct L3 evidence, negative diff, unsafe scan/ledger, final verification, summary, and manifest for `demo-external-direct-callee`
- [x] 4.5 Add `validation/slice-specs/demo-external-direct-callee.json` with entry signature first and helper signature/context metadata
- [x] 4.6 Extend `validate_l2_evidence_summary.py` mapping for `demo-external-direct-callee`
- [x] 4.7 Generate accepted evidence and auto evidence with `auto_migrate --accept-existing-evidence`
- [x] 4.8 Add full-regression semantic gate step for `demo-external-direct-callee`

## 5. Validation And Delivery

- [x] 5.1 Run `cargo fmt --manifest-path validation/l2_slices/Cargo.toml -- --check`
- [x] 5.2 Run `cargo test --manifest-path validation/l2_slices/Cargo.toml`
- [x] 5.3 Run `python -B -m unittest validation.tools.test_auto_migrate validation.tools.test_validate_auto_translation_evidence -v`
- [x] 5.4 Run external-callee L3 evidence tests and auto evidence validator
- [x] 5.5 Run `python -B validation/tools/validate_l2_evidence_summary.py --evidence-root validation/evidence`
- [x] 5.6 Run `openspec validate add-bounded-external-callee-context --strict` and `openspec validate --all`
- [x] 5.7 Run `git diff --check`
