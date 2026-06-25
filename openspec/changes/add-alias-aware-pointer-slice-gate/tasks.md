## 1. OpenSpec Contract

- [x] 1.1 Validate proposal, design, spec deltas, and tasks with `openspec validate add-alias-aware-pointer-slice-gate --strict`

## 2. Alias Gate TDD

- [x] 2.1 Add failing `auto_migrate` tests for input/read + output/write slices requiring `alias_risks`, `alias_contract`, `safe_boundary_preconditions`, and `alias_gate` plan output
- [x] 2.2 Add a regression test showing output-only pointer writes do not trigger input/output alias risk
- [x] 2.3 Add a validator test that a pointer-bearing L3 package with read/write effects fails when alias gate fields are missing

## 3. Alias Gate Implementation

- [x] 3.1 Extend `auto_migrate` pointer graph normalization to emit `alias_sets`, `alias_risks`, `alias_contract`, `safe_boundary_preconditions`, and `alias_sensitive_state` triggers
- [x] 3.2 Extend translation plan, final verification, manifest, and cache invalidation keys with alias gate status
- [x] 3.3 Enforce conservative decisions: unknown input/output aliasing is `requires_noalias_contract` or `candidate_only`, not alias-safe success
- [x] 3.4 Verify targeted Python tests for alias gate behavior and existing pointer graph tests remain green

## 4. Add I32 Pair Alias Demo

- [x] 4.1 Add `add_i32_pair_ptr_arith` Rust replay implementation, C oracle generator, fixture, Rust tests, and slice spec
- [x] 4.2 Include disjoint input cases, `lhs == rhs` read/read alias case, and rejected input/output overlap-risk case metadata
- [x] 4.3 Wire the demo into report emission, diff, negative diff, unsafe scan, unsafe ledger, performance smoke, final verification, and evidence summary
- [x] 4.4 Add L3 evidence tests covering alias matrix, noalias preconditions, manifest keys, unsafe scan, negative diff, and summary acceptance

## 5. Regression And Delivery

- [x] 5.1 Add `demo/add-i32-pair-ptr-arith` alias semantic/risk gate to `scripts/run-full-regression.ps1`
- [x] 5.2 Run formatting, Rust tests, Python tests, OpenSpec strict/all validation, git diff check, and short full-regression smoke
- [x] 5.3 Commit and push the completed change branch
