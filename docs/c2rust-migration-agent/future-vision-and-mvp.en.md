# C-to-Rust Future Vision and MVP Roadmap

This document is the English mirror of `future-vision-and-mvp.md`. The Chinese document is the canonical backlog and the only entrypoint for current status, execution order, and capability boundaries. Detailed implementation history remains in Git, the coverage matrix, and machine-readable evidence instead of being duplicated here.

Last updated: 2026-07-11.

## 1. Current Status

The goal is an auditable end-to-end pipeline:

```text
input.c
  -> clang / C2Rust / LLM candidate
  -> typed IR or verified unsafe baseline
  -> Rust candidate
  -> C oracle + Rust replay + diff + negative diff
  -> unsafe ledger + final verification
  -> accepted / refused / blocked
```

| Item | Current value | Exact meaning |
| --- | ---: | --- |
| `translator_generated_semantic_pass_count` | 32 | 32 translator-generated named slices pass the complete semantic gates; this is not whole-project translation |
| `accepted_evidence_semantic_pass_count` | 1 | Independent authoritative accepted-evidence slices; excluded from the translator-generated numerator |
| Active translator track | P0-T21 | Compose the zero-start and next-address branches at `fdb_kvdb.c:1868-1874` |
| External parallel track | P0-H9 | Revalidate the exact OpenCode + GLM-5.1 contract on the real competition host |
| Latest completed stage | P0-T20 | The `:1870-:1873` assignment-call, reset/add, and current-level `continue` slice is semantically accepted |
| Current proof class | `wsl-local-simulation` | Valid for development and approximation, but not `competition-exact` |

`validation/translator-coverage-matrix.json` is the machine-readable source of truth for capability counts. A native C build, typed-IR unit test, rustc compile, C2Rust output, or LLM output alone is candidate evidence only.

## 2. Active Execution Queue

### P0-A: Translator Track

- [ ] **P0-T21: compose the `:1868-:1874` zero-start and next-address branches**

  Put the `sector.addr + SECTOR_HDR_DATA_SIZE` write for `kv->addr.start == 0` in the same generic carrier as the P0-T20 assignment-call else-if, reset, traversed-length add, and `continue` path.

  Minimum accepted states: zero-start, sentinel hit, zero miss, and ordinary miss.

  Preserve the owner interior alias, local sector copy, exact `db -> itr` noalias relation, mutually exclusive branches, exact-u32/wrapping behavior, and current-level `continue`.

  Explicitly out of scope: real `SECTOR_HDR_DATA_SIZE` expansion, real `get_next_kv_addr` semantics, the `read_kv` loop from line 1875, complete `fdb_kv_iterate`, whole FlashDB, and record layout/ABI.

  Completion requires a project-independent implementation, positive and adjacent negative tests, C oracle, generated Rust replay, schema diff, executed negative mutation, unsafe/raw-pointer ledger, route/profile/final verification, strict validator, coverage matrix, and synchronized bilingual docs.

- [ ] **P0-T22: select the next smallest real source-backed gap**

  Select it only after P0-T21 closes. Prefer adjacent `fdb_kv_iterate` control flow or a generic construct family from another real project. Do not pre-claim whole-function or whole-project translation.

### P0-B: Competition Host and OpenCode

- [ ] **P0-H9: exact OpenCode + GLM-5.1 competition contract revalidation**

  WSL currently resolves provider-qualified `zai/glm-5.1`, but the complete preflight/worker marker chain is not closed on the real competition host. Use OpenCode only when it shortens an independent task or performs competition-contract revalidation; it is not the default development path.

  Completion requires `COMPETITION_EXACT_HOST=1`, an exact GLM-5.1 token from `opencode models`, preflight with `opencode` + `GLM-5.1` + `c2rust-migrator` + `max`, complete hash-bound probe/session/worker artifacts, and successful judge-bundle/public-packet revalidation.

  WSL, local, and CI results remain `wsl-local-simulation`, `local-simulation`, and `ci-approximation`; none closes H9.

### P0-C: Stage Closure

- [ ] Fix the eight historical evidence-drift failures in the full regression in ownership-scoped batches, separate from translator behavior changes.
- [ ] Clear the 17 historical feature-gated warnings from `cargo clippy --all-features --all-targets -- -D warnings`; default Clippy passes and new slices must add no warnings.
- [ ] Replay the completed CRC32 C2Rust+repair before/after on the real competition host and publish competition-exact workflow metrics.

## 3. Later Backlog

### P1: Expand Generic Translation

1. Build a complete alias/noalias, pointer-provenance, and escape model for readonly, mutable-out, inout, nullable, cross-call, and multi-pointer cases.
2. Preserve integer promotion, usual arithmetic conversion, narrowing, array/function decay, and ABI-related conversions explicitly in IR.
3. Model compound side effects as composable rules for sequence points, evaluation order, increment/decrement, dereference, index, member, and call.
4. Expand CFG support: classify and evidence `switch`/`goto` fail-closed behavior before adding a relooper or structured lowering.
5. Expand compound literals, designated initializers, function pointers, variadics, unions, bitfields, VLAs, and flexible array members.
6. Model volatile, hardware registers, RTOS/interrupts, filesystems, and power-loss boundaries; host fixtures do not replace target evidence.
7. Add real slices from different construct families across FlashDB, zlib-ng, libuv, and other projects; do not inflate coverage with many similar checksum/parser slices.

### P2: Agents, Routing, and Release

1. Combine raw C2Rust, C2Rust+repair, typed IR, LLM candidates, and refusal in an auditable multi-candidate router without bypassing shared semantic gates.
2. Maintain a small golden-slice set with model, prompt, input, and output hashes to measure model-upgrade effects.
3. Publish generation, compilation, accepted/refused/blocked, unsafe delta, repair rounds, human intervention, duration, and evidence-cost metrics.
4. Complete a formal tag/release, external review, CONTRIBUTING guidance, ownership, and release checklist.
5. Keep CFG/SSA/MIR/LLVM/self-hosting as long-term research until P0/P1 are stable.

## 4. Completed Milestones

| Range | Result | Semantic count change |
| --- | --- | ---: |
| P0-T0..T3 | Ordered inc/dec, for-init comma, no-clang AST replay, and do-while assignment-call candidate foundations | Not counted |
| P0-T4..T9 | `tsl_to_blob`, `fdb_is_str`, do-while continue, and if assignment-call named-slice acceptance | 21 -> 24 |
| P0-T10..T13 | Generic record/call/alias expansion and the exact `fdb_kvdb.c:1870` fragment | 24 -> 25 |
| P0-T14..T17 | Iterator tail call, traversed length, KV reset, and sector start | 25 -> 29 |
| P0-T18 | Safe interior reborrow projection for `kv = &itr->curr_kv` | 29 -> 30 |
| P0-T19 | `:1871-:1873` reset/add/current-level continue | 30 -> 31 |
| P0-T20 | Compose the `:1870-:1873` assignment-call condition and branch body | 31 -> 32 |

Latest stage validation:

- Translator `cargo test --all-features` passed.
- WSL competition-like Python core suite: `293 passed, 6 skipped`, plus `90` passing subtests.
- The stage full regression ran 35 checks and passed 27. All FlashDB code gates and the file-backend 10,000-loop stress test passed; eight failures are historical evidence drift.
- P0-T20 strict validator reports `semantic_pass=true` and `generated_draft_semantic_pass=true`.
- All-feature Clippy still reports 17 historical warnings; none is on a P0-T20-added line.

## 5. Architecture Boundaries

### 5.1 Candidate Routes

| Level | Purpose | Can it claim semantic success alone? |
| --- | --- | --- |
| L0 deterministic | Tiny, proven mechanical rules | No |
| L1 generic typed IR | Generic AST/type/alias-driven candidates | No |
| L2 C2Rust baseline/repair | Broad unsafe baselines and safety before/after | No |
| L3 LLM/OpenCode | Candidate generation or repair | No |
| L4 refuse | Fail closed with an actionable next step | Not applicable |

A candidate becomes a semantic pass only after the shared gates in section 6 prove the declared slice boundary.

### 5.2 IR Layers

1. **Semantic IR**: C integer width/signedness, casts, lvalue/rvalue, pointer provenance, volatile/atomic, and undefined/implementation-defined boundaries.
2. **Control IR**: blocks, branches, loops, break/continue/return, and future CFG/relooper data.
3. **Typed Value IR**: scalar, record, array, pointer, function type, qualifiers, and ABI/layout provenance.
4. **Lowering**: Rust ownership, borrows, slices, wrapping/checked arithmetic, raw pointers, or refusal. IR must not invent Rust safety.

## 6. Acceptance Gates

A named slice may increase the translator semantic numerator only when all of these hold:

1. Real source span, commit, fixture, carrier, and generated-candidate hashes agree.
2. The C oracle and Rust replay both compile and execute.
3. Schema-aware diff passes and at least one discriminating negative mutation executes and is detected.
4. Unsafe scan/ledger, route decision, validation profile, and final verification are cross-bound.
5. The independent validator passes with `--require-semantic-pass`.
6. The coverage matrix derives the updated count; manual percentages are not evidence.

Native C builds, rustc compile-only, typed-IR unit tests, no-clang fixtures, C2Rust output, LLM text, route metadata, zero unsafe findings, or agent prose cannot increase the numerator alone.

Proof classes are fixed:

| Proof class | Allowed source | Can close competition-exact work? |
| --- | --- | --- |
| `local-simulation` | Windows/local host | No |
| `wsl-local-simulation` | WSL | No |
| `ci-approximation` | Linux CI | No |
| `competition-exact` | Real competition host with explicit attestation | Yes |

## 7. Development Principles

1. FlashDB is a real test case, not a translator-specialization source. Project names, function names, paths, and fixed fixture values must not select translation behavior.
2. Start with the smallest source-backed slice and expand adjacent structure. Every relaxed rule needs a positive and nearest fail-closed negative.
3. The C oracle is ground truth only within its declared fixture, compiler, flags, ABI, and observable contract.
4. Fail-closed results must provide the source span, refusal reason, and next smallest implementation step; refusal volume is not success.
5. Unsafe counts are governance metrics, not complete proof for FFI, concurrency, volatile, ABI, or hardware semantics.
6. Evidence uses repo-relative paths, stable hashes, and explicit retention rules. Never publish secrets or host absolute paths.
7. Split large files by module responsibility. Add tests, schemas, evidence, and docs only when they produce a behavioral or acceptance benefit.

## 8. Common Validation Commands

```bash
cargo fmt --all --check
cargo test --manifest-path crates/c2r-translator/Cargo.toml --all-features
python3 -B validation/tools/translator_coverage_matrix.py --matrix validation/translator-coverage-matrix.json
python3 -B -m unittest validation.tools.test_doc_mirror_contract
python3 -B -m unittest validation.tools.test_validate_test_translation_coverage
git diff --check
```

Competition config and judge-chain changes also require:

```bash
python3 -B -m validation.tools.resync_sha_bindings --scan-root config/competition-env --dry-run --check
python3 -B -m validation.tools.resync_sha_bindings --scope judge-chain --dry-run --check
```

## 9. Document Maintenance Rules

- Keep only current status, the unique active queue, tiered backlog, milestone summary, and stable rules here.
- When an item closes, update the status table, active queue, milestone table, and validation summary instead of appending a daily log.
- Store exact artifacts, hashes, cases, and validator results in the coverage matrix/evidence; keep only conclusions and boundaries here.
- The Chinese file is canonical and the English mirror must change in the same patch.
- Use Git history for older states. Do not create a second global TODO, handoff, or roadmap.
