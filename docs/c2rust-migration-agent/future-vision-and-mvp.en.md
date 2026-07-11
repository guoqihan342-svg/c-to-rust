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
| `translator_generated_semantic_pass_count` | 35 | Coverage-ledger-derived count; it does not mean the current strict full regression is green or that whole-project translation is complete |
| `accepted_evidence_semantic_pass_count` | 1 | Accepted-evidence-ledger-derived count; the only slice is still blocked by historical SHA drift |
| Active translator track | P0-T26 | Audit and select the smallest generic slice within `fdb_kvdb.c:1877-1883` |
| External parallel track | P0-H9 | Revalidate the exact OpenCode + GLM-5.1 contract on the real competition host |
| Latest development stage | P0-T25 | The `:1876` discarded direct-call body has source-backed strict semantic closure and raises the count to 35 |
| Current strict regression | `26/34` | Run `20260711T061416Z`; eight historical evidence drifts remain |
| Current proof class | `wsl-local-simulation` | Valid for development and approximation, but not `competition-exact` |

`validation/translator-coverage-matrix.json` is the machine-readable source of truth for capability counts. A native C build, typed-IR unit test, rustc compile, C2Rust output, or LLM output alone is candidate evidence only.

## 2. Competition Environment

### 2.1 Official Target Baseline

The machine-readable source of truth is `config/competition-env/environment.json`, with profile id `huawei-competition-ubuntu-24.04` and current raw-bytes SHA-256 `8f2233e9c8c4e7676524a72bf8db919b83e89366ec3cc76d3673d07f32488160`. Development, CI, and WSL may simulate this profile, but only an attested real host may claim `competition-exact`.

| Item | Competition target |
| --- | --- |
| OS | Ubuntu `24.04.4 LTS`, codename `noble` |
| Kernel | `5.10.0-182.0.0.95.r194_123.hce2.x86_64` |
| Architecture | `x86_64` |
| Python / pip | `3.12.3` / `24.0` |
| Rust / Cargo | `1.96.0` / `1.96.0` |
| gcc / g++ / Make | `13.3.0` / `13.3.0` / `4.3` |
| Node.js / npm | `v24.13.0` / `11.6.2` |
| Java / Maven | Bisheng OpenJDK `21.0.10` / Maven `3.9.11` |
| `MAVEN_HOME` | `/usr/local/maven3` |
| Go / CMake | Unavailable: Go is not installed and CMake is not found |
| clang | Not required by default; explicitly required by the typed-IR competition clang lane |

The profile fixes these mirrors:

| Ecosystem | Mirror |
| --- | --- |
| APT | `http://mirrors.tools.huawei.com/ubuntu` |
| PyPI | `https://mirrors.tools.huawei.com/pypi/simple` |
| npm | `https://mirrors.tools.huawei.com/npm/` |
| Cargo | `sparse+http://rust.inhuawei.com/crates.io-index/` |

`source config/competition-env/env.sh` sets the profile id, mirrors, `MAVEN_HOME`, and repo-local `CARGO_HOME=config/competition-env/cargo`, avoiding dependence on a user's global Cargo configuration.

### 2.2 Competition Source, clang, and OpenCode Contracts

The FlashDB competition input is fixed to:

| Field | Fixed value |
| --- | --- |
| repository | `https://gitcode.com/xwxf/FlashDB.git` |
| branch | `competition` |
| commit | `f9d0421315c564fb890a1b14eee77b290e0d7bbe` |
| checkout | `git checkout -B competition f9d0421315c564fb890a1b14eee77b290e0d7bbe` |

Every new competition-targeted extraction must provide repository, branch, and `--require-source-commit`, and verify the checkout before generating a slice spec. Historical evidence may bind older commits, but it cannot represent new competition input.

The competition clang lane is not a default dependency. With `auto_migrate.py --competition-clang-lane`, clang must come from `CLANG_PATH` or one of these repo-local paths:

```text
tools/llvm/bin/clang-18
tools/llvm/bin/clang
tools/clang/bin/clang
```

Availability requires both `clang -print-resource-dir` and a minimum JSON AST dump including `stdint.h` and `stddef.h`. A successful `clang --version` is insufficient. `LIBCLANG_PATH` is not an input to this lane. Missing clang must produce `missing_clang_path`, not a fallback presented as typed-IR clang execution.

The competition agent contract is fixed:

| Field | Requirement |
| --- | --- |
| command | `opencode` |
| logical model | `GLM-5.1` |
| repo-owned agent | `c2rust-migrator` |
| variant | `max` |
| retry cap | At most five rounds, one minimal patch per round |
| preflight | `opencode models` in the same run/runtime environment must list exact GLM-5.1 and produce a hash-bound passed report/marker |

A provider-qualified id may be the resolved model id, but the logical model, probe output, preflight, worker argv, resume data, judge bundle, and public packet must agree. Current WSL `opencode models` prints lowercase `zai/glm-5.1`; the repository's strict probe requires a case-sensitive final token exactly equal to `GLM-5.1`, so `toolchain-check.sh` still reports "GLM-5.1 not listed." This shows that the provider exposes the corresponding model, but it does not pass the current competition OpenCode contract. OpenCode conversation text is not semantic evidence either.

### 2.3 Current WSL Versus the Competition Target

The current WSL probe on 2026-07-11 reports:

| Item | Current WSL | Competition target | Result |
| --- | --- | --- | --- |
| OS | Ubuntu `24.04.3 LTS` | `24.04.4 LTS` | Minor version differs |
| Kernel | `6.6.87.2-microsoft-standard-WSL2` | Huawei HCE `5.10.0-...` | Different; not equivalent |
| Architecture | `x86_64` | `x86_64` | Match |
| Python | `3.12.3` | `3.12.3` | Match |
| Rust / Cargo | `1.95.0` / `1.95.0` | `1.96.0` / `1.96.0` | Differ |
| gcc / g++ / Make | `13.3.0` / `13.3.0` / `4.3` | Same | Match |
| Node.js / npm | `v22.22.0` / `10.9.4` | `v24.13.0` / `11.6.2` | Differ |
| Java / Maven | Ubuntu OpenJDK `17.0.19` / Maven `3.8.7` | Bisheng OpenJDK `21.0.10` / Maven `3.9.11` | Differ |
| Go / CMake | Go absent / CMake `3.28.3` | Both unavailable | CMake does not match |
| OpenCode | `1.17.18`, models prints `zai/glm-5.1` | Binary version not pinned; strict GLM-5.1 launch contract | Strict model probe fails |
| clang | System `/usr/bin/clang` `18.1.3` | Optional, with explicit source and complete smoke | Present but not auto-selected by `env.sh` |

Running `source config/competition-env/env.sh && bash config/competition-env/toolchain-check.sh` in current WSL returns exit code 1 with ten mismatches. System clang exists, but `env.sh` auto-selects only `CLANG_PATH` or a repo-local vendored clang. With explicit `export CLANG_PATH=/usr/bin/clang`, the observed resource dir is `/usr/lib/llvm-18/lib/clang/18` and the minimum-TU JSON AST smoke passes, but the other ten environment differences still fail the overall check.

Current WSL results therefore remain `wsl-local-simulation`. They can verify Linux paths, gcc/explicit clang, the Python harness, Rust replay, FlashDB build/smoke, and most of the evidence chain. They cannot prove equivalence for the target kernel, Rust 1.96, Node 24, Java/Maven, the no-CMake baseline, the strict OpenCode/GLM host, or competition resource limits.

### 2.4 Self-Check, Simulation, and Exact Run Entrypoints

Start a competition-host or Linux/WSL session with:

```bash
source config/competition-env/env.sh
bash config/competition-env/toolchain-check.sh
```

`toolchain-check.sh` checks tool versions, mirrors, Go/CMake absence, and OpenCode model status. When clang is found, it also runs resource-dir and minimum-TU AST smoke. Missing OpenCode/GLM is informational by default; enable the competition-agent hard gate with:

```bash
REQUIRE_OPENCODE_GLM=1 bash config/competition-env/toolchain-check.sh
```

Run the current WSL simulation smoke with:

```bash
bash config/competition-env/smoke.sh \
  wsl-local-simulation \
  target/competition-smoke-wsl
```

This smoke verifies environment and lightweight evidence gates only. It does not translate a new slice or create semantic acceptance.

Run every judge entrypoint on the real competition host with:

```bash
export COMPETITION_EXACT_HOST=1
python3 -B -m validation.tools.run_judge_entrypoints \
  --config config/competition-env/judge-entrypoints/flashdb-harness.json \
  --proof-class competition-exact
```

After execution, deeply validate local artifacts:

```bash
python3 -B -m validation.tools.validate_judge_entrypoints \
  --config config/competition-env/judge-entrypoints/flashdb-harness.json \
  --require-local-artifacts
```

Use `--dry-run` for plan inspection and `--entrypoint-id` for focused debugging. Neither focused mode replaces the full competition-exact release packet.

### 2.5 Currently Proven and Unproven Boundaries

The WSL competition-like lane currently proves the P0-T20 C oracle, generated Rust replay, diff, negative mutation, unsafe gates, and strict validator. Routine full regression runs no loop stress step, and loop stress is no longer a normal acceptance condition. The runner is capped at three repeated rounds, separately approved diagnostic stress is capped at 100 loops, and 1,000/10,000-iteration runs are rejected. Volatile test counts are recorded only in section 5 with a run or commit binding.

Still unproven are the target kernel, Rust/Cargo 1.96, target Node/npm, real Huawei host package/runtime differences, competition resource limits, real-host `COMPETITION_EXACT_HOST=1` attestation, a complete OpenCode preflight marker, GLM-5.1 worker/session artifacts, and the full competition-exact judge bundle/public packet. P0-H9 therefore remains open.

## 3. Active Execution Queue

### P0-A: Translator Track

- [x] **P0-T21: compose the `:1868-:1874` zero-start and next-address branches**

  Put the `sector.addr + SECTOR_HDR_DATA_SIZE` write for `kv->addr.start == 0` in the same generic carrier as the P0-T20 assignment-call else-if, reset, traversed-length add, and `continue` path.

  The discriminating set is fixed at five cases: zero-start non-wrap, zero-start wrap, sentinel hit, zero-return miss, and ordinary miss. Zero-start must skip the external call and must not produce the P0-T20 `continue` observation.

  Preserve the owner interior alias, local sector copy, exact `db -> itr` noalias relation, mutually exclusive branches, exact-u32/wrapping behavior, and current-level `continue`.

  Explicitly out of scope: real `SECTOR_HDR_DATA_SIZE` expansion, real `get_next_kv_addr` semantics, the `read_kv` loop from line 1875, complete `fdb_kv_iterate`, whole FlashDB, and record layout/ABI.

  | Stage | Status | Completion criterion |
  | --- | --- | --- |
  | source boundary | Complete | Bind exactly `fdb_kvdb.c:1868-1874` without extending into line 1875 |
  | generic implementation | Complete | Commit the project-independent typed-IR carrier and schema-v2 reporter |
  | generic tests | Complete | Positive, adjacent fail-closed, and all-feature translator tests pass |
  | source-backed inputs | Complete | Spec, fixture, and source-fragment hash are reproducible |
  | semantic evidence | Complete | C oracle, Rust replay, diff, negative, and unsafe ledger are generated and cross-bound |
  | strict acceptance | Complete | Every section 7 gate passes and the matrix-derived count is 34 |

- [x] **P0-T22: next-slice decision gate**

  - Slice id: `real-fdb-kv-iterate-kv-tail`.
  - Real source span: `src/fdb_kvdb.c:1885` at the pinned FlashDB commit, limited to the empty-body do-while tail assignment-call.
  - Construct gap: a mutable alias derived from an owner interior projection is both the nested-u32 assignment target and the unique same-alias argument of the same direct call.
  - Nearest negative: `typed_ir_rejects_assignment_call_sibling_read_when_owner_is_mutably_borrowed`; same-owner sibling reads remain refused.
  - Stop condition: generate a generic candidate only. Lines 1876-1884, real `get_next_kv_addr`, the complete function, ABI, and the FlashDB project remain out of scope. Fail closed if function-name matching or weaker noalias evidence would be required.

  Project-independent no-clang AST lowering, Rust emission/runtime, and non-empty-body/comparison-drift negatives are complete. Status remains `candidate_context_only`, and the semantic count remains 33.

- [x] **P0-T23: source-backed semantic closure for `fdb_kvdb.c:1885`**

  The source-bound spec, fixture, C oracle, Rust replay, schema diff, negative diff, unsafe ledger, route/profile, and final verification are complete. All 12 strict semantic-binding checks pass under the WSL `--competition-clang-lane`, with `semantic_pass=true` and `generated_draft_semantic_pass=true`. The claim remains fixed to line 1885 and excludes the real `get_next_kv_addr` and whole function. The matrix-derived count moved from 33 to 34.

- [x] **P0-T24: next-slice decision gate**

  - Slice id: `real-fdb-kv-iterate-read-kv-body-call`.
  - Real source span: `src/fdb_kvdb.c:1876` at the pinned FlashDB commit; normalized-line SHA-256 is `10948836c8ce66dea9de8d52dd04882b110c70acdabd785634c9e6d2660f2940`.
  - Construct gap: exactly one ordered direct-call statement with a discarded return value in the do-while body of an owner interior alias, followed by the existing assignment-call tail.
  - Generic implementation: accept only `[Expr(direct Call), normalized tail assignment-call]`; the body-call arguments must be the proven-noalias independent call root and the same interior alias. The legacy empty-body shape remains accepted.
  - Fail closed: a second body statement, non-call expression, nested call, extra or repeated mutable root, owner sibling read, and comparison drift remain rejected.
  - Stop boundary: lines 1877-1884, real `read_kv` semantics, callee side effects, the whole loop, and FlashDB ABI remain excluded. Project names, function names, slice ids, and fixture constants must not drive behavior.

  Project-independent no-clang AST lowering, emitted-Rust runtime order checks, and adjacent negatives are complete. Status is `candidate_context_only`; the semantic count remains 34.

- [x] **P0-T25: source-backed semantic closure for `fdb_kvdb.c:1876`**

  The source-bound spec, three bounded fixtures, fixture-only `read_kv`/`get_next_kv_addr` dual-call contract, C oracle, generated Rust replay, schema diff, body-call-suppression negative diff, unsafe ledger, route/profile, and final verification are complete. All 12 strict binding checks pass in the WSL competition clang lane with `semantic_pass=true` and `generated_draft_semantic_pass=true`, moving the matrix-derived count from 34 to 35. The claim covers only the line-1876 call shape, argument forwarding, and fixture order; line 1885 is synthetic scaffold, and real callee side effects and whole-loop semantics remain excluded.

- [ ] **P0-T26: next-slice decision gate for `fdb_kvdb.c:1877-1883`**

  Audit the two-field short-circuit condition, status constant, three statistics updates, and early return. Select the smallest project-independent construct that does not depend on real `read_kv` side effects. Pin nearest positive/negative cases, alias and integer-promotion boundaries, and the source span before separating candidate generation from source-backed acceptance.

### P0-A: AI/Harness Efficiency

- [x] **P0-A1: OpenCode no-progress retry suppression**

  Hash effective request/source/spec/repair-trace/launch-policy inputs as `effective_input_sha256`, and hash structured root cause/status/returncode/diagnostics as `failure_sha256`. After two identical deterministic failures with no current input change, close the repair hint before a third launch, clear its retry command, record `repair_retry_suppressed`, and fail closed as `refused/retry_input_unchanged`. Do not invoke the runner, append a synthetic attempt, or raise semantic status. Preserve retries for timeout, SQLite/OpenCode locks, preflight, credentials, contracts, missing environment, unknown causes, and missing or drifting hashes.

  This gate reduces OpenCode calls and token use that have no information gain. It does not treat AI output as semantic fact or replace the C oracle, Rust replay, or strict validator.

- [x] **P0-A2: align bare `CLANG_PATH` command names with the competition PATH contract**

  The Rust clang frontend now accepts both an existing explicit path and a bare command name resolved by the process `PATH`, such as `CLANG_PATH=clang`; an explicit path containing separators still fails closed when it does not exist. The WSL clang 18 minimum-TU smoke and three real-clang auto-migrate positive/negative tests pass. This restores candidate generation only and does not increase the semantic count.

- [x] **P0-A3: deterministic-first admission gate**

  `mode=auto` selects deterministic execution before OpenCode preflight only when every worker binds accepted evidence, an existing evidence root, a source hash, and a slice spec with no repair policy. Mixed or unbound input is refused before fanout as `auto_route_unbound`; `competition-exact`, hostless rehearsal, and explicit OpenCode attestation cannot auto-downgrade. This route only avoids model calls with no expected information gain and remains `semantic_gate=false`.

### P0-B: Competition Host and OpenCode

- [ ] **P0-H9: exact OpenCode + GLM-5.1 competition contract revalidation**

  WSL currently resolves provider-qualified `zai/glm-5.1`, but the complete preflight/worker marker chain is not closed on the real competition host. Use OpenCode only when it shortens an independent task or performs competition-contract revalidation; it is not the default development path.

  Completion requires `COMPETITION_EXACT_HOST=1`, an exact GLM-5.1 token from `opencode models`, preflight with `opencode` + `GLM-5.1` + `c2rust-migrator` + `max`, complete hash-bound probe/session/worker artifacts, and successful judge-bundle/public-packet revalidation.

  WSL, local, and CI results remain `wsl-local-simulation`, `local-simulation`, and `ci-approximation`; none closes H9.

- [ ] **P0-H10: publish the CRC32 competition-exact before/after**

  Depends on P0-H9. Close only after replaying the completed CRC32 C2Rust+repair before/after on the real competition host and publishing hash-bound workflow metrics.

### P0-C: Stage Closure

- [ ] **P0-C1: historical evidence drift**. Fix the eight failures in run `20260711T061416Z` in artifact-ownership batches, separate from translator behavior changes.
- [ ] **P0-C2: all-feature Clippy**. Commit `81a772d1` cleared nine low-risk warnings; eight remain: two `large_enum_variant`, one `redundant_guards`, one `needless_lifetimes`, and four `too_many_arguments`. New slices must add no warnings.

## 4. Later Backlog

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

## 5. Completed Milestones

| Range | Result | Semantic count change |
| --- | --- | ---: |
| P0-T0..T3 | Ordered inc/dec, for-init comma, no-clang AST replay, and do-while assignment-call candidate foundations | Not counted |
| P0-T4..T9 | `tsl_to_blob`, `fdb_is_str`, do-while continue, and if assignment-call named-slice acceptance | 21 -> 24 |
| P0-T10..T13 | Generic record/call/alias expansion and the exact `fdb_kvdb.c:1870` fragment | 24 -> 25 |
| P0-T14..T17 | Iterator tail call, traversed length, KV reset, and sector start | 25 -> 29 |
| P0-T18 | Safe interior reborrow projection for `kv = &itr->curr_kv` | 29 -> 30 |
| P0-T19 | `:1871-:1873` reset/add/current-level continue | 30 -> 31 |
| P0-T20 | Compose the `:1870-:1873` assignment-call condition and branch body | 31 -> 32 |
| P0-T21 | Compose the `:1868-:1874` zero-start and assignment-call branches | 32 -> 33 |
| P0-T22 | Select and implement the `:1885` interior-reborrow do-while tail candidate | 33 -> 33 (candidate only) |
| P0-T23 | Strict source-backed acceptance for the `:1885` owner-interior-alias do-while tail | 33 -> 34 |
| P0-T24 | Select and implement the `:1876` discarded direct-call body candidate | 34 -> 34 (candidate only) |
| P0-T25 | Strict source-backed acceptance for the `:1876` discarded direct-call body | 34 -> 35 |

Validation run bindings:

| Validation | Binding | Result |
| --- | --- | --- |
| P0-T25 strict validator | WSL competition clang lane, 2026-07-11 | `semantic_pass=true`, `generated_draft_semantic_pass=true`; all 12 semantic-binding checks passed; three bounded fixtures cover 1/2/3 ordered body/tail calls; no loop stress was run |
| P0-T24 / P0-A1 / P0-A2 stage validation | WSL local simulation, 2026-07-11 | translator library `228`, bounded `665`, and integer conversion `4` passed, with `133` real-clang opt-in tests ignored by default; three real-clang focused tests, Python auto-migrate `155`, and OpenCode harness `192` passed; no loop stress was run |
| P0-T23 strict validator | WSL competition clang lane, 2026-07-11 | `semantic_pass=true`, `generated_draft_semantic_pass=true`; all 12 semantic-binding checks passed; three bounded fixtures cover 1/2/3 calls |
| P0-T22 translator candidate | current worktree, 2026-07-11 | library `228` passed; bounded `659` passed with `133` real-clang opt-in ignores; integer conversion `4` passed; coverage matrix passed |
| P0-T21 translator candidate | commit `02067028`, 2026-07-11 | library `228` passed; bounded `657` passed with `133` real-clang opt-in ignores; integer conversion `4` passed |
| P0-T20 Python core historical snapshot | 2026-07-11 stage snapshot | `293 passed, 6 skipped`, plus `90` subtests; proves only that revision |
| Full regression | run `20260711T061416Z` | 26 of 34 passed; P0-T21 added no failure and the same eight historical evidence drifts failed; future runner defaults omit loop stress |
| P0-T21 strict validator | evidence generated from commit `8a261787` | `semantic_pass=true`, `generated_draft_semantic_pass=true`, and all 12 semantic binding classes passed |
| P0-T20 strict validator | P0-T20 evidence | `semantic_pass=true` and `generated_draft_semantic_pass=true` |
| Accepted-evidence strict status | `libuv/ip4-addr` | verified-unsafe-baseline SHA drift; the ledger count is not a current strict pass |
| All-feature Clippy | commit `81a772d1` plus current test cleanup | Eight warnings remain under `--all-features --all-targets`, all in the four P0-C2 categories listed above |

## 6. Architecture Boundaries

### 6.1 Candidate Routes

| Level | Purpose | Can it claim semantic success alone? |
| --- | --- | --- |
| L0 deterministic | Tiny, proven mechanical rules | No |
| L1 generic typed IR | Generic AST/type/alias-driven candidates | No |
| L2 C2Rust baseline/repair | Broad unsafe baselines and safety before/after | No |
| L3 LLM/OpenCode | Candidate generation or repair | No |
| L4 refuse | Fail closed with an actionable next step | Not applicable |

A candidate becomes a semantic pass only after the shared gates in section 7 prove the declared slice boundary.

### 6.2 IR Layers

1. **Semantic IR**: C integer width/signedness, casts, lvalue/rvalue, pointer provenance, volatile/atomic, and undefined/implementation-defined boundaries.
2. **Control IR**: blocks, branches, loops, break/continue/return, and future CFG/relooper data.
3. **Typed Value IR**: scalar, record, array, pointer, function type, qualifiers, and ABI/layout provenance.
4. **Lowering**: Rust ownership, borrows, slices, wrapping/checked arithmetic, raw pointers, or refusal. IR must not invent Rust safety.

## 7. Acceptance Gates

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

## 8. Development Principles

1. FlashDB is a real test case, not a translator-specialization source. Project names, function names, paths, and fixed fixture values must not select translation behavior.
2. Start with the smallest source-backed slice and expand adjacent structure. Every relaxed rule needs a positive and nearest fail-closed negative.
3. The C oracle is ground truth only within its declared fixture, compiler, flags, ABI, and observable contract.
4. Fail-closed results must provide the source span, refusal reason, and next smallest implementation step; refusal volume is not success.
5. Unsafe counts are governance metrics, not complete proof for FFI, concurrency, volatile, ABI, or hardware semantics.
6. Evidence uses repo-relative paths, stable hashes, and explicit retention rules. Never publish secrets or host absolute paths.
7. Split large files by module responsibility. Add tests, schemas, evidence, and docs only when they produce a behavioral or acceptance benefit.

## 9. Common Validation Commands

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

## 10. Document Maintenance Rules

- Keep only current status, the unique active queue, tiered backlog, milestone summary, and stable rules here.
- When an item closes, update the status table, active queue, milestone table, and validation summary instead of appending a daily log.
- Store exact artifacts, hashes, cases, and validator results in the coverage matrix/evidence; keep only conclusions and boundaries here.
- The Chinese file is canonical and the English mirror must change in the same patch.
- Use Git history for older states. Do not create a second global TODO, handoff, or roadmap.
