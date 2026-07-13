# C-to-Rust Future Vision and MVP Roadmap

This document is the English mirror of `future-vision-and-mvp.md`. The Chinese document is the canonical backlog and the only entrypoint for current status, execution order, and capability boundaries. Detailed implementation history remains in Git, the coverage matrix, and machine-readable evidence instead of being duplicated here.

Last updated: 2026-07-12.

## 1. Current Status

The goal is an auditable end-to-end pipeline:

```text
input.c + compile context
  -> ContextPack (source / headers / flags / ABI / diagnostics)
  -> GLM-5.1 primary candidate
  -> typed IR / C2Rust alternate candidates
  -> bounded verify-and-repair loop
  -> C oracle + Rust replay + diff + negative diff
  -> unsafe ledger + final verification
  -> accepted / refused / blocked
```

| Item | Current value | Exact meaning |
| --- | ---: | --- |
| `translator_generated_semantic_pass_count` | 38 | Coverage-ledger-derived count; it does not mean the current strict full regression is green or that whole-project translation is complete |
| `accepted_evidence_semantic_pass_count` | 1 | Accepted-evidence-ledger-derived count; the only slice is still blocked by historical SHA drift |
| Current AI candidate state | `GLM 0 / fixed auxiliary 6/12 + A18c8a targeted 2/4 exact` | Competition GLM still has no candidate because balance is unavailable; the fixed 12 cases have not been rerun as a full suite after A18c8a, while two of four targeted cases newly pass exact gates, all explicitly competition-ineligible |
| Active translator track | P0-A18c / P0-A10 | A18c8h4d now safely feeds hash-bound exact rustc/replay compile diagnostics into the existing AI repair loop. It retains at most eight `{code,message}` entries and excludes rendered source, spans, fixtures, and oracle values. Next exercise API repair through the AI-first exact stage and add executable callee semantics/no-escape |
| External parallel track | P0-H9 | Revalidate the exact OpenCode + GLM-5.1 contract on the real competition host |
| Latest development stage | P0-A18c8h4d | Exact compile/replay gates extract allowlisted compiler diagnostics only after candidate, target, replay, and fixture bindings match. Repair prompts receive API errors but not oracle-bearing replay source. Every repaired candidate must rerun all ten exact gates, and `semantic_pass=false` remains unchanged |
| Current strict regression | `25/33` | Run `20260711T-finite-p0-t31`; `stress_loops=0`, and eight historical evidence drifts remain |
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

### 3.1 Current Priority Board

Execute strictly from top to bottom. A successful lower-level sample cannot close a higher-level item.

| Order | Work item | State | Completion criterion for this stage |
| ---: | --- | --- | --- |
| 1 | P0-A18c7 cross-project AI-input and evidence closure | Complete | The 125-test gate passes on Windows and WSL; all 12 fixed cases generate candidates, contract failures are zero, and six pass exact gates |
| 2 | P0-A18c8 remaining exact-failure closure | In progress | A18c8h4a turns the real candidate replay API mismatch into compile-preflight evidence; A18h still needs safe API adaptation, executable callee semantics/no-escape, direct-local scalar, raw extern-boundary, and post-write initialization proofs |
| 3 | P0-A10 AI golden set | Pending | Expand with multiple projects, unfamiliar identifiers, and nearest negatives without test-case patches |
| 4 | P0-H9 competition-host verification | Externally blocked | Real-host attestation, OpenCode preflight, GLM-5.1 session, and release packet all close |
| 5 | P0-C stage closure | Pending | Repair historical evidence drift and clear the remaining all-feature Clippy items |

Checkbox rule: implementation closes only its subitem. A parent closes only after every acceptance gate and evidence binding under it closes. A targeted sample, AI prose, candidate compilation, WSL simulation, or auxiliary-model success cannot independently close P0-A18c, P0-A10, or P0-H9.

### 3.2 P0-T: Deterministic Translation Support Lane

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

- [x] **P0-T26: next-slice decision gate for `fdb_kvdb.c:1877-1883`**

  - The selected construct is line 1880, `itr->iterated_cnt++`: a statement-position postfix increment whose value is discarded and whose target is a u32 field on a direct mutable record-pointer root.
  - A focused no-clang AST fixture proves normalization to field assignment plus unsigned add. The Rust candidate uses `wrapping_add(1u32)` and runs `0 -> 1`, an ordinary value, and `u32::MAX -> 0`.
  - Existing fail-closed boundaries remain pinned for const record pointers, nested/non-direct bases, and missing mutable ownership evidence.
  - The stop boundary excludes lines 1876-1879 and 1881-1885, real `read_kv` side effects, the condition and early return, owner-interior-alias composition, the whole loop, and FlashDB ABI. Production behavior must not depend on project, function, slice, field, or fixture names.

  This stage is project-independent candidate generation only. Status remains `candidate_context_only`, and the semantic count remains 35.

- [x] **P0-T27: source-backed semantic closure for `fdb_kvdb.c:1880`**

  The line-1880 source span and normalized hash, three bounded fixtures, C oracle, generated Rust replay, schema diff, `wrapping_add` to `wrapping_sub` negative mutation, unsafe ledger, route/profile, and final verification are complete. All 12 strict binding checks pass in the WSL competition clang lane with `semantic_pass=true` and `generated_draft_semantic_pass=true`, moving the matrix-derived count from 35 to 36. The claim covers only a direct u32 field postfix increment through one mutable record root over zero, ordinary, and wrap cases; the enclosing branch/loop, whole function, layout, ABI, and FlashDB project remain excluded.

- [x] **P0-T28: generic owner-interior sibling accumulation candidate for `fdb_kvdb.c:1881`**

  - The selected construct is line 1881, `itr->iterated_obj_bytes += kv->len`. Because `kv` comes from `&itr->curr_kv`, this is one mutable owner with a scoped interior alias read and a non-overlapping sibling write, not two noalias pointer roots.
  - Generic frontend/typed-IR generation requires an explicit LP64 target ABI, a u32 source field, a `size_t`/usize target field, pointer-typedef alias provenance, non-overlapping paths, and no additional alias use or side effect before it emits `wrapping_add(kv.len as usize)`.
  - A renamed no-clang AST fixture and six focused tests pin ordinary, zero, and LP64 wrap cases plus fail-closed behavior for missing ABI, overlapping paths, a second pointer hop, alias reuse, type drift, fictional noalias, and terminal-statement drift.

  This stage is project-independent candidate generation only. Production behavior does not depend on project, function, field, slice, or fixture names, and the semantic count remains 36.

- [x] **P0-T29: source-backed semantic closure for `fdb_kvdb.c:1881`**

  The exact line-1881 source span, pointer-typedef carrier, and LP64 ABI are bound to three finite fixtures covering ordinary, zero-addend, and usize-wrap cases. The actually compiled and executed C oracle, generated Rust replay, schema diff, negative mutation, unsafe ledger, route/profile, and final verification all pass. The WSL competition clang lane reports `schema_status=passed`, `semantic_pass=true`, and `generated_draft_semantic_pass=true` across all 12 strict binding classes, moving the matrix-derived count from 36 to 37. The claim covers only one owner, one scoped interior alias, and one u32-to-usize sibling wrapping add at line 1881; lines 1882-1883, the enclosing branch/loop, complete function, real layout/whole ABI, and the FlashDB project remain excluded.

- [x] **P0-T30: generic composition candidate for `fdb_kvdb.c:1882-1883` and `:1880-1883`**

  A project-independent bounded ordered sequence now supports one direct u32 wrapping increment, two distinct u32 fields read through one scoped interior alias and added into distinct LP64 usize sibling fields, and a fixed `return true`. Production analysis checks only AST, type, ABI, alias, and effect constraints; it does not read project, function, field, slice, or fixture names. A renamed no-clang AST, runtime positives, and adjacent shape/alias/type/effect negatives pass. This remains candidate-only, so the count stays 37.

- [x] **P0-T31: source-backed semantic closure for `fdb_kvdb.c:1880-1883`**

  The exact source span, single-owner/interior-alias carrier, and LP64 ABI are bound to four finite fixtures. The compiled C oracle, generated Rust replay, schema diff, negative mutation, unsafe ledger, route/profile, and final verification pass. The WSL competition clang lane reports `schema_status=passed`, `semantic_pass=true`, and `generated_draft_semantic_pass=true` across all 12 strict binding classes, moving the matrix-derived count from 37 to 38. Line 1877, the enclosing branch/loop, complete function, real layout/whole ABI, and whole-project FlashDB translation remain excluded.

- [ ] **P0-T32: compose the `fdb_kvdb.c:1877` condition with the `:1880-1883` body**

  Pause this as the active track. Keep it as a real golden case for comparing GLM-5.1, typed IR, and C2Rust candidates. Increase the numerator only after the common gates pass, and do not recount the accepted stats body.

### 3.3 P0-A: AI-first Harness Track

Close work in executable dependency order so external model or checkout blockers do not stall local development:

| Order | Work | Current stop condition |
| ---: | --- | --- |
| 1 | P0-A11 provider admission and zero-call evidence | Complete; only regression fixes remain |
| 2 | P0-A12 file-based prompt transport | Complete; only transport/CLI compatibility regressions remain |
| 3 | P0-A13 content-addressed AI candidate cache | Complete; only cache binding/schema/validator regressions remain |
| 4 | P0-A14 bounded compile response-file expansion | Complete; only dialect/schema/binding regressions remain |
| 5 | P0-A15 recomputable AI caller/callee context | Complete; only ContextPack/prompt-scope/validator regressions remain |
| 6 | P0-A16 transparent auxiliary-model validation | Complete; auxiliary models can produce local evaluation evidence only and cannot impersonate GLM |
| 7 | P0-A17 isolated auxiliary suite and strict input binding | Complete; DeepSeek and other substitutes produce only separate auxiliary reports |
| 8 | P0-A18 replay-compatible Rust API contract | Active local track; give the model the exact function contract required by replay before invocation |
| 9 | P0-A10 fixed-suite real acceptance | Run the complete suite once after GLM resource recovery and publish reproducible metrics |
| 10 | P0-A6 / P0-H9 competition-host replay | A valid resource package and competition-exact host are available; simulation cannot substitute |

Each stage runs the finite construct set once, then expands translator/ContextPack support from observed failure frequency. Do not resume FlashDB line-number rule accumulation, and do not pause independent harness work while waiting for external resources.

- [ ] **P0-A6: real GLM-5.1 candidate generation lane**

  OpenCode `zai/glm-5.1` consumes a hash-bound ContextPack and emits one structured Rust candidate. Record provider, logical/resolved model, variant, prompt, input, raw response, parse result, and candidate SHA-256. Model output, chat text, and file writes remain `semantic_gate=false`. Missing credentials, timeout, malformed response, or missing candidate must become structured blocked results; a silent fallback must not claim that AI ran.

  Current progress: the candidate generator, schema-v7 manifest, sensitive/host-path cleanup, strict JSON parsing, candidate materialization SHA check, source-span provider readiness, balance/auth/launch/timeout classification, and `auto_migrate --ai-first-candidate` are implemented. A missing, escaping, hash-drifted, oversized, or unsupported-encoding source span becomes `context_not_provider_ready` before OpenCode starts and records `provider_invocations=0`; the summary validator reopens the hash-bound ContextPack and independently recomputes preflight and invocation count. LF/CRLF equivalence is checked by streaming full-source hashing plus span hashing. A fragment wrapper must also pass carrier, containing-function, and real upstream fragment SHA/text/claim contracts plus `verbatim_once` embedding before becoming `inline_translation_carrier_bound`, and it still makes no whole-function semantic claim. All 12 fixed cases are provider-ready on Windows and WSL in the P0-A10 input worktree that retains the three pinned checkouts; an ordinary fresh worktree without those ignored checkouts does not have that prerequisite. WSL can list and launch `zai/glm-5.1`. OpenCode writes provider errors to its bounded log and then continues internal retries, so the old harness reached its outer 30/180-second limit first and recorded an empty response as `provider_timeout`. On 2026-07-12, a new log-offset diagnostic covers nonzero exits, timeouts, and first-created logs, emits only fixed sentinels, and never stores raw logs or secrets. It reclassified one real call as `provider_insufficient_balance`. A passing DeepSeek auxiliary run cannot substitute for this evidence, so no real GLM candidate exists and this item remains open.

- [x] **P0-A7: project-level ContextPack and compile-context closure**

  Build minimal context from the real source root/span, effective includes, `compile_commands.json` or manual flags, macros, target ABI, dependency declarations, Clang AST/diagnostics, typed-IR/C2Rust baselines, and validation failures. Relative/absolute paths, generated headers, and build directories must resolve. Secrets, host absolute paths, and unrelated large files must not enter publishable artifacts.

  Completion evidence: ContextPack v3 is split by responsibility into source, compile database, compile arguments, response files, security, and deterministic-artifact modules. It supports an explicit external source root, a repository-relative source root, real span/source SHA bindings, compile-command selection, include/define/ABI summaries, a 128 KB total cap, and a 32 KB per-artifact cap. Path or symlink escape, hash drift, secrets, and host paths fail closed.

- [x] **P0-A8: validation-driven bounded AI repair loop**

  Feed only structured failure facts back to the model: rustc diagnostics, C/Rust schema diff, negative mutation, and unsafe/ABI/alias gates. Default to at most three rounds, with five as the competition hard cap; stop immediately when both input and failure hashes are unchanged. Preserve each candidate, patch, diagnostic, and hash. The model must not modify the oracle, expected output, validator, or gate configuration.

  Completion evidence: the bounded repair coordinator, one-candidate/one-file-patch contract, per-round SHA evidence, LF normalization, unchanged-input-plus-failure stop, and provider/validator fail-closed handling are implemented. A fresh C-oracle proof rechecks the harness, fixture, source span, flags, and ABI. The exact validator runs rustc, replay, schema diff, negative mutation, unsafe/ledger, alias, ABI, and final gates against the current candidate SHA and feeds ten bounded failure classes into the same repair state machine. `--ai-first-candidate` is mutually exclusive with `--accept-existing-evidence`, so old accepted reports cannot certify a new AI candidate. Independent `validate_ai_exact_evidence.py --require-semantic-pass` reopens the auto manifest, router, candidate evidence, gate index, and canonical-draft SHA bindings; the competition runner counts compile/semantic pass only when that strict result and router state both pass. Fresh demo/add-one evidence on 2026-07-12 checked 16 artifacts and returned `semantic_pass=true`.

- [x] **P0-A9: AI-primary multi-candidate router**

  The competition translation path generates a GLM-5.1 candidate first. typed IR and raw C2Rust are zero-token candidates, while C2Rust+repair is an AI-assisted alternative. The router may rank only by recomputable gate results, never by project/function/slice names or model self-assessment. Every candidate traverses the same compile/oracle/replay/diff/negative/unsafe/final gates.

  Completion evidence: the competition runner passes `--ai-first-candidate` for fresh translations, and competition-exact forbids OpenCode/GLM/agent/variant substitution. The pure router accepts at most four candidates, deduplicates by artifact SHA, schedules `opencode-ai -> typed-ir -> c2rust-repair -> c2rust-baseline`, and selects only a candidate that passes all eight candidate-bound gate groups. `auto_migrate` first validates AI, typed IR, and current-run raw C2Rust; any passing zero-token candidate suppresses repair. If all fail, it chooses exactly one repair base: repair raw C2Rust only when it passed strictly more gates than AI, otherwise repair AI, with one shared default-three/hard-five-round budget. The generic C2Rust repair state machine contains no project/function special case, permits one Rust candidate or patch, preserves independent report/round/prompt/response/candidate SHA evidence, and reruns fresh exact gates as `source=c2rust-repair`. Strict validation and competition metrics reopen unique, duplicate, and no-candidate audit states from disk. Repair rounds count toward total model invocations without inflating the initial-AI-candidate success rate. Baseline compile/status, repair reports, and historical accepted evidence never advance a candidate by themselves.

- [ ] **P0-A10: finite cross-project stability acceptance**

  Maintain at most 20 fixed cases covering at least three real C projects and ten distinct construct families. Run the finite set once per stage, with no 1,000/10,000-round or loop stress tests. Publish AI invocation, candidate generation, rustc compilation, semantic acceptance, refused/blocked, repair-round, and route-selection metrics. Repeated similar slices must not inflate success rates.

  Current progress: input and harness closure are complete. `validation/ai-finite-cross-project-suite.json` fixes 12 cases across three real projects and 12 unique construct families: eight real upstream function slices and four executable generic carriers bound to real upstream fragments, with zero synthetic or unbound provenance. `project_sources` pins repository, repository-relative checkout root, and commit. The validator verifies Git HEAD, origin, tracked-clean state, spec/fixture SHA, source file/span SHA, and line/byte alignment offline; it permits only LF/CRLF newline equivalence and rejects content drift or project-label substitution. In the P0-A10 input worktree that retains all three pinned checkouts, Windows and WSL both return `ready=12/blocked=0` under `--require-all-ready`.

  `run_ai_finite_cross_project_suite.py` now passes all 12 specs to one competition runner invocation, disables accepted-evidence shortcuts and outer retries, hash-binds the suite and summary, and refuses to copy metrics unless the lower-level summary validator passed. WSL local simulation may explicitly use an offline Cargo cache, but the summary records `bypassed_for_local_cache`, and `competition-exact` rejects that bypass. Insufficient balance, authentication failure, or provider launch failure opens the circuit on the first failure; timeout retains a two-consecutive-failure threshold, and changing kinds resets the consecutive count. Only actually invoked items enter slice, workflow, and AI-unit counts; remaining items are recorded as skipped rather than fabricated `not_invoked` units, while ContextPack-preflight refusals explicitly record zero provider calls.

  The empty-out-root WSL auxiliary run `ai-auxiliary-p0-a18c8-deepseek-wsl-20260712-02` completed all 12 fixed cases on 2026-07-12. All 12 initial candidates were generated, four evidence-driven repairs ran, and total provider calls were 16. Six cases passed exact gates and six failed; contract failures, execution failures, and provider blocks were all zero. The report SHA-256 is `dfff968ad274924b763a8cede749338f37dcca25e38b5148fbeaaef0d09c2927`. This is a DeepSeek `wsl-local-simulation` quality signal with both public numerators fixed at zero. P0-A10 remains open because the competition GLM run and real-host evidence are still missing.

- [x] **P0-A11: provider admission and zero-call evidence closure**

  Before process launch, the candidate producer reopens the ContextPack's real source/span/carrier bindings. Path escape, incomplete hashes or declarations, mid-read drift, invalid coordinates, budget overflow, encoding failure, or a fragment hidden by conditional compilation is rejected structurally with `provider_invocations=0`. The summary validator does not trust manifest self-reporting; it reopens the hash-bound ContextPack and recomputes readiness and call count. This gate decides only whether a model call is warranted and never raises semantic status.

- [x] **P0-A12: file-based prompt transport**

  Write candidate and repair prompts to repository-scoped, hash-bound files, then launch OpenCode with its file-input option plus a fixed short message so Windows/WSL argv limits cannot change behavior. The manifest must record transport, prompt path/hash, and effective command policy; logs and public artifacts must not copy the full prompt, credentials, or host paths. Completion requires large ContextPacks and repair candidates to leave argv while preserving parsing, timeout, diagnostics, and strict-gate behavior.

  Completion evidence: candidate generation and bounded repair share `opencode-file-attachment-v2`. argv fixes the short message before `--file=<prompt-path>`, correcting OpenCode 1.17.18 consuming the message as a second file; the complete prompt remains SHA-bound on disk. The schema-v7 manifest and schema-v3 repair report record file option/style, message position, fixed-message SHA, and `inline_prompt_in_argv=false`; both summary and exact-evidence validators independently reject transport drift.

- [x] **P0-A13: content-addressed AI candidate cache**

  Derive the cache key from the ContextPack payload hash, prompt schema/version, actual prompt hash, resolved model, agent name, repository-local agent-definition hash, variant, and parse contract. Cache only successfully parsed results whose candidate and raw response can both be reopened by SHA; never cache provider failures, timeouts, refusals, or unparsed responses. A hit still traverses all common gates, records `cache_hit` and zero new provider calls, and remains `semantic_gate=false`; any binding drift invalidates the hit and triggers a real model call.

  Completion evidence: caching is enabled only through explicit `--cache-root` or `--ai-candidate-cache-root`, and the competition runner accepts only repository-local roots. The schema-v4 manifest binds the eight-part content key and copies a hit's `entry.json` into current path/SHA evidence; the summary validator reopens the entry, raw response, and initial candidate, reparses the response, and recomputes the key. Same-key requests first use single-flight and recheck the cache, then publish under a cross-process lock through a unique staging directory and first-writer-wins rename; a corrupt entry is quarantined and rebuilt by one real provider call. Failures, timeouts, refusals, and parse failures are never cached. A hit records initial `provider_invocations=0` and metrics-v2 `cache_hits=1`, while later repair rounds still count as invocations; common gates and `semantic_gate=false` remain unchanged. All 124 contract tests pass on Windows; WSL passes 123 of the same 124 and platform-skips the Windows-lock-specific case.

- [x] **P0-A14: bounded compile response-file expansion**

  Expand only relative `@file` inputs inside the source root, with recursion-depth, file-count, per-file/total-byte, and cycle limits; bind every response file by logical path and SHA. Parse failure, path escape, or budget overflow must fail closed instead of silently dropping include, define, target-ABI, or other arguments. Validate this against different real C projects without project, function, or fixture special cases.

  Completion evidence: ContextPack v3 and its independent schema enable only `gnu-v1` for clang/gcc/cc families; MSVC and unknown dialects fail closed. Relative paths may normalize `..` while remaining inside the root; real escape, absolute/drive/UNC paths, cycles, links, invalid UTF-8/NUL/quoting, depth over 4, more than 16 expansions, files over 64 KiB, totals over 256 KiB, or more than 4096 arguments block before provider invocation. Successful expansion recovers defines, includes, and target ABI, records original/expanded argv SHAs, and binds every file's logical path/SHA/size/depth in both the selected entry and ContextPack inputs. Response changes invalidate the ContextPack, prompt, and AI cache key. Windows and WSL each run 149 tests and pass 148: Windows skips only unavailable symlink creation, while WSL skips only the Windows-lock-specific case.

- [x] **P0-A15: recomputable AI caller/callee context and prompt scope**

  ContextPack must give AI bounded facts for direct-callee signatures, definition status, source bindings, stub boundaries, and call-expression contracts instead of asking the model to infer cross-function semantics from caller source alone. Candidate-manifest `prompt_scope` must be computed from the actual ContextPack rather than claiming absent type-map, CFG, pointer-graph, root-cause, or caller/callee inputs.

  Completion evidence: ContextPack v3's 16 KiB C boundary now includes `external_direct_callees` and `call_expression_contract` under the common sensitive-field and host-path sanitizer, including quoted secret assignments inside ordinary strings, embedded JSON, and escaped JSON. The independent `context_scope.py` derives a stable scope only from nonempty loaded excerpts, real failure states, and named direct-callee facts; informational diagnostics under a successful status do not count as root cause. Normal generation and cache hits share this rule. Provider admission returns zero-call `required_callee_context_incomplete` when a required callee boundary is compacted or truncated by either its local budget or the 128 KiB total ContextPack budget. Current schema-v7 records scope, model identity, and the invocation receipt; the fresh-run summary validator requires v7, reopens the hash-bound ContextPack, byte-recomputes the prompt, and rejects scope, identity, receipt, or version drift. Older versions retain schema and accepted-evidence archive readability but cannot self-select downgrade for a fresh run. This adds no project, function, or fixture special case and does not increase the semantic numerator.

- [x] **P0-A16: transparent auxiliary-model validation and tool-free candidate boundary**

  When GLM balance is unavailable, an alternate model may be selected explicitly for local candidate-quality evaluation, but model identity must derive from the resolved model and propagate through generator, candidate, repair, router, and summary. Only `zai/glm-5.1` is `competition-primary`. Every alternate must record `competition_eligible=false` and `evaluation_scope=auxiliary-local-validation`; it cannot close P0-A6/A10/H9, enter competition metrics, or impersonate `opencode-glm51-1`.

  Completion evidence: a shared model identity and dynamic candidate id now feed manifests and routers. Competition summary validation independently derives identity from the resolved model and cross-checks generator/candidate fields. The exact router binds the selected id, only manifest candidate, and full model scope, while C2Rust repair generators must match the routed AI generator. Candidate generation and repair share the bounded response contract: `c2rust-candidate` is the default with `*=deny`, unknown repository-local agents are rejected before provider launch, worker/preflight retains `c2rust-migrator`, and logical probe model `GLM-5.1` is separate from candidate resolved id `zai/glm-5.1`; `opencode models` accepts both exact tokens and rejects near matches. Parsers recursively reject nested `tool` or `tool_use` events. Strict JSON and one complete JSON fence are accepted, while multiple or incomplete fences fail closed, raising the parse contract to v3. Provider responsibilities are split into 474-line orchestration, 218-line response parsing, 282-line runtime diagnostics, and 121-line receipt construction. Schema v7 binds each provider call to a minimal receipt and separate session-export identity projection. Both use dedicated `additionalProperties=false` schemas and retain only identity, prompt/response SHAs, and the SHA of the full in-memory export; the full session is never persisted. Competition-exact reopens the same live OpenCode session and checks the export SHA, actual identity, attached prompt path and ContextPack prefix, and assistant response, so an unrelated GLM session cannot replace a DeepSeek response. Under WSL OpenCode 1.17.18, omitting `--ai-agent` while using `opencode/deepseek-v4-flash-free` generated `opencode-deepseek-v4-flash-1`. The candidate passed rustc plus compile/oracle/replay/schema-diff/negative-diff/unsafe/alias-ABI/final-verification exact gates. The router preserves its full auxiliary identity and reports `semantic_pass=true`, while the overall auto manifest and candidate remain noncompetition `semantic_pass=false`. The same 203-test group passes on Windows and WSL, with one platform-specific skip on each.

- [x] **P0-A17: isolated auxiliary-model suite and strict input binding**

  When GLM balance is unavailable, run DeepSeek V4 Flash or another noncompetition model through a separate auxiliary runner over the fixed cross-project set. Auxiliary success rates must never enter competition or translator numerators. Every run requires an empty out-root, path-safe and unique project/slice identities, and slice-spec SHA checks before and after model execution. Concurrent OpenCode units receive isolated config/data/cache/state/tmp directories so SQLite, sessions, logs, and export identity cannot cross units.

  Completion evidence: `run_ai_auxiliary_cross_project_suite.py` defaults to `opencode/deepseek-v4-flash-free`, rejects competition-eligible models, accepted evidence, stale out-roots, path escape, duplicate units, and spec TOCTOU, and updates the provider circuit in batches of one to four workers. Reports hard-code `competition_success_numerator=0` and `translation_coverage_numerator=0`. Fresh-oracle full-file and function-span bindings accept only exact bytes or a provable LF/CRLF projection; byte coordinates cannot degrade into permissive line fallback. Candidate and repair prompts copy the exact C signature, parameter order, and Rust pointer/unsafe policy before the full ContextPack. A mixed-version run performed while source files were changing was discarded and contributes no published rate. Auxiliary results still cannot close P0-A6/A10/H9.

- [ ] **P0-A18: put the replay-compatible Rust API contract before the model**

  Before provider launch, generate and hash-bind the exact Rust function contract: name, visibility, parameter count and order, C-pointer to Rust reference/slice mapping, whether length parameters remain, return type, ABI, and unsafe boundary. The slice spec, Rust boundary, and replay generator must derive this contract through shared logic. Project names, function names, fixture names, and model guesses cannot drive it.

  Current root cause: the high-salience boundary summary moved DeepSeek's `fdb_is_str` output from an unrelated single-`u8` API to a semantically close safe-slice implementation, but the model still removed the `len` parameter required by replay, so the initial candidate failed with an arity mismatch. The first isolated repair round also failed to restore `len` and added unnecessary `unsafe`, so the exact gates correctly rejected it. Completion requires the provider and repair prompts to bind the exact generated-replay API and a material reduction in first-round rustc API mismatches on the fixed auxiliary suite. Only exact gates report pass rates.

  This item now has three independently verifiable stages so one improved fixture cannot be reported as generic completion:

  - [x] **P0-A18a: executable replay source contract**. `auto_migrate` generates the replay draft before provider launch. ContextPack v4 fully binds replay source, SHA, size, and real call count so validators can reopen and recompute it. The model projection no longer exposes replay source that may carry expected/actual values; it shows only the same-source ReplayCallPlan and `required_candidate_api`, once in each candidate or repair prompt. Provider readiness, manifest v8, cache, scope, and the fresh summary validator fail closed. Missing, sensitive, oversized, call-free, or drifted replay evidence results in zero provider calls or an invalid fresh run. `_auto_migrate_ai_exact.py` was also split into a 489-line compatibility facade plus routing, persistence, and validation modules.
  - [x] **P0-A18b: structured ReplayCallPlan**. Extract one structured plan from the replay generator with parameter names/order/Rust types, C mappings, retained length fields, return type, ABI, unsafe policy, and call args. The renderer and prompts consume the same plan. Dedicated legacy fallback dispatch and the readiness OR list are removed; function names are contract data only.
    - [x] **P0-A18b1: declarative plan core**. The bounded DSL, plan SHA, ContextPack nested contract v2, source marker, recomputed call arity, single prompt payload, and fresh binding are complete. `source_function_name` is distinct from Rust `api_name`; zlib/libuv now emit real calls, while `fdb_blob_make/kv_to_blob/set/del` select renderers by semantic contract. An AI draft can enter replay only when manifest v8, selected candidate, applied artifact, and draft SHA all close.
    - [x] **P0-A18b2: plan every legacy adapter**. Every inventoried scalar, record, external-sequence, record-pointer, and opaque-context adapter consumes ReplayCallPlan. Incomplete contracts fail closed instead of falling back to a dedicated renderer.
      - [x] **P0-A18b2a: plan byte-slice/CRC paths**. `readonly_byte_slice_bool_return` is normalized by contract kind into the same plan without function-name dispatch, while `fdb_calc_crc32` declares generic parameter/fixture mappings. The plan now supports canonical inline-fixture SHA binding and a `u8_array` codec; `fdb_is_str` and CRC32 both emit typed direct calls. The 141-test focused suite passes and fixed-suite preflight remains 12/12 ready with zero model calls.
      - [x] **P0-A18b2b: record/external plan v2**. All inventoried nine record-state and four scripted external/call-continue renderers are migrated.
        - [x] **P0-A18b2b1: record plan-v2 core**. Bounded `bindings`, `binding_value/borrow_mut`, recursive record initializers, `binding_path` observations, typed `u32/usize/bool` codecs, and mutable-root noalias closure are wired into ContextPack, schema, and fresh binding. Constant, field add, field-plus-scalar add, postfix increment, interior projection, stats sequence, and guarded stats have left legacy dispatch. The v2 implementation keeps a thin facade and splits bounded parts by responsibility.
        - [x] **P0-A18b2b2: remaining state/external paths**.
          - [x] **P0-A18b2b2a: record state 9/9**. Owner-interior u32-to-usize add reuses typed owner observation, while reset-add-while-continue reuses multiple `binding_path` observations. Record parameters with `direction=input` now emit `binding_borrow`/`&T`; only `inout` emits `binding_borrow_mut`/`&mut T`, while noalias still closes over every simultaneous borrow root.
          - [x] **P0-A18b2b2b: scripted external 4/4**. Generic `scripted_runtime` data declares scalar/sequence stimuli, reset channels, call count/args/order probes, scalar/tuple/array/vector/matrix codecs, and a fixture-only claim boundary. Output pointers use bounded array bindings. The plan carries only closed channel/operation values plus callee, fixture-field, and API data; the renderer maps channel/operation pairs to fixed repository helpers, preventing arbitrary Rust-helper injection. All seven real slice specs behind the four legacy renderers now enter plan v2, and the 102-test focused group passes. Of 159 `test_auto_migrate` tests, only two pre-existing CRC32 methods fail and one platform test skips; the same two methods also fail at clean baseline `26b6edce`, so they are not counted as scripted-runtime regressions.
      - [x] **P0-A18b2c: eliminate simple legacy renderers**. All 13 inventoried direct-call adapters for scalar returns, mutable out reports, record/pointer identity, and opaque contexts are migrated. Dedicated fallback dispatch and the readiness OR list are removed.
        - [x] **P0-A18b2c1: scalar-return 4/4**. Structural matching recognizes pure-u32, single-i32, signed-shift-i32, and ABI-bound u64 without reading function or project names, then emits one schema-v3 declarative contract. Fixture metadata such as `status/contract` becomes hash-bound `fixture_assertions` whose constants are checked while building the plan, and `u64` is now a first-class codec. All eight existing demo specs leave legacy rendering; 27 plan tests and three exact auto-migrate tests pass.
        - [x] **P0-A18b2c2: mutable-out/report 4/4**. Single i32 output, dynamic i32 slice output, input-buffer out0-plus-sum, and call metadata now produce generic plans from C signatures, parameter directions, length companions, the call-expression contract, and closed fixture observables. Fixed i32 arrays, bounded `Vec<i32>` initializers, `i32_slice/i32_vec` codecs capped at 4096 items, whole-binding observations, `usize/string_vec` metadata assertions, fixture relations, full symbol/field renaming, and drift refusal are covered. Call metadata explicitly declares `input_fixture_fields`, contexts, and source calls instead of guessing fields or parsing C text. The real store-add-one, copy-i32-ptr-arith, sum-i32-buffer, sum-i32-ptr-arith, and call-expression replays no longer enter their legacy renderers.
        - [x] **P0-A18b2c3: record-pointer/opaque 5/5**. Record pointer identity, record projection identity, record buffer/length identity, opaque key, and opaque key/value now use generic v2 producers. Opaque contexts use a safe Rust fixture model instead of forging a FlashDB ABI marker; old raw-pointer AI drafts fail closed at the replay compile gate. The focused gate passes 48/48 on both Windows and WSL; the 207-test WSL stage gate retains only the two CRC32 failures already present at clean baseline plus one platform skip. This is replay/harness capability only: it does not increase the translation coverage numerator or replace C oracle/Rust replay/diff semantic evidence.
    - [x] **P0-A18b3: split ReplayCallPlan by responsibility**. The former 946-line implementation is now a 48-line compatibility facade plus real dispatch, v1-builder, fixture-binding, schema, and literal-rendering modules, with no `exec` or source-fragment assembly. Commit `b28d5648` passes 87 compatibility tests with one Windows symlink condition skipped.
    - [ ] **P0-A18b4: move ReplayCallPlan v2 out of dynamic fragments**. `replay_call_plan_v2.py` still loads nine `.pyfrag` files totaling about 2,949 lines. Replace them with explicit builder/schema/fixture/scripted/identity/buffer/string modules while preserving plan JSON, plan SHA, and generated Rust byte-for-byte.
  - [ ] **P0-A18c: finite cross-project acceptance**. All fixed 12 cases must generate a real replay call, first-round rustc API mismatches must materially improve over A17, and quality remains counted only by exact gates.
    - [x] **P0-A18c1: bounded provider/repair reliability**. ContextPack replay contract v3 derives an independently recomputable `required_candidate_api` from ReplayCallPlan, including the exact signature, supporting structs, ABI, unsafe marker, and reference-return lifetime; candidate and repair prompts present one complete API copy. AI manifest v9 retries the identical prompt once only for a valid tool-free JSONL completion with no assistant text, terminal `step_finish`, and zero output/reasoning tokens. Both response/receipt/session identities are hash-bound; balance, authentication, timeout, nonzero exit, tool events, and ordinary malformed responses do not retry. Fixture-only Rust compile stubs are removed by restoring the canonical AI draft byte-for-byte after checking, preventing applied-artifact SHA drift. Repair accepts only a complete self-contained Rust candidate and is skipped with zero calls when the fresh oracle did not pass, the target contract is absent, or no structured candidate failure exists. The auxiliary aggregator reopens hash-bound repair reports and counts initial, repair, and total provider invocations separately; its default timeout is 300 seconds. The 161-test focused Windows gate passes. This closes the harness implementation slice only; P0-A18c still owns the fixed 12-item rerun result.
    - [x] **P0-A18c2: fail-closed safety-syntax rejection**. When the Rust safety contracts for call-continue, reset-add, or interior projection raise `ValueError`, `auto_migrate` no longer terminates with a traceback. The runner records `replay_safety.kind=generated_rust_safety_contract_failed`, `replay_execution.phase=safety`, failed mappings, and `semantic_gate=false`, skips rustc/replay execution, and allows later exact/repair processing to continue. The new path passes 4/4 on both Windows and WSL.
    - [x] **P0-A18c3: closed candidate source assembly**. `required_candidate_api` now carries a recomputable `candidate_source_contract`: the candidate is self-contained, nonempty `supporting_types_source` appears exactly once, the harness injects no missing types, and compiler-owned fixture types form a closed type environment. Candidate and repair prompts restate the same rule directly after the required API and forbid replacement extern/FFI/opaque types. The rule reads no project or function names. The API/prompt/provider focused gate passes 62 tests on Windows and 55 on WSL.
    - [x] **P0-A18c4: safe projection for unobserved null-pointer defaults**. In record-pointer identity contracts, fields that are absent from observables and exist only to complete a proxy record with `null/null_mut` defaults now use `Option<NonNull<c_void>>` plus a `None` initializer instead of a raw pointer. Record buffer/length and actual pointer-identity fields do not use this path. ReplayCallPlan validation, rendering, ContextPack schema, and required API all support `optional_non_null_none`. The rule reads no project or function names, and the 34-test focused gate passes.
    - [x] **P0-A18c5: separate safe `NonNull` types from raw-pointer operations**. The exact alias gate masks a `core/std::ptr::NonNull<T>` path only when the candidate contains no `unsafe` and the path appears in a generic type position. `NonNull::<T>` construction, other `ptr` APIs, `as_ptr/as_mut_ptr/from_raw/into_raw`, raw-pointer types, and every `unsafe` + `NonNull` combination still fail closed and require a current-candidate alias proof. The rule reads no project, function, or field names; the related 53-test gate passes on both Windows and WSL.
      - After commit `ecbb2ef3`, the zero-repair DeepSeek checks for `kv_to_blob` and `tsl_to_blob` both reached one-call AI exact pass. Their router SHA-256 values are `4f753f9cd00359d46ed13044f9845b9dff04702c84a4c9ede0aacfc85de31cac` and `93f7b5fe6d2f7f3d903d7042d2a78236b96b86afa491faeea5c971ed00d7a68b`. This closes the alias false positive for two record-identity candidates; it does not increase the competition numerator.
    - [x] **P0-A18c6: generic, source-backed external-callee behavior contract**. When the translated function calls outside the current slice, the model may recover behavior only from SHA-bound C definitions, macros, enums, and struct fields. Fixture expected/actual values and oracle-bearing replay source remain hidden from both candidate and repair. Project names, function names, paths, and fixed fixture values cannot select behavior.
      - [x] **P0-A18c6a: external-callee source context**. Extract bounded function definitions for declared direct callees from the source root, failing closed on path, file SHA, span, TOCTOU, count, or byte-budget violations without dispatching on target names.
      - [x] **P0-A18c6b: source behavior parsing and independent binding**. Parse negated guards, function-like macro field projections, and enum ordinals from SHA-bound source, producing an independent `behavior_sha256`. Fixture expected values are validator-only cross-checks and do not construct rules. The effective fixture SHA binds both source fixture and spec overlays.
      - [x] **P0-A18c6c: remove model oracle inputs and dedicated semantic stubs**. Candidate and repair prompts hide replay source, expected/actual/observed/mismatch, and gate values. `flashdb_kv_set_fixture_model_allowed`, `flashdb_kv_del_fixture_model_allowed`, `rust_check_harness_only_external_stub`, and the fixed `7i32` path are removed. The Windows focused contract gate passes 41 tests with one platform condition skipped.
      - [x] **P0-A18c6d: cross-platform stage gate**. Schema parsing, fresh binding, `git diff --check`, and directly affected auto-migrate paths are closed. The final focused contract group completes 96 tests on Windows (95 pass and one platform skip) and passes 96/96 on WSL; the seven auto-migrate tests for removing dedicated stubs pass 7/7 on each. Readiness recomputes rule/behavior hashes and checks every real callee plus source binding, with fail-closed negatives for commented pseudo-control-flow and `oracle_contract` feedback. The 252-test Windows stage group retains only two CRC32 failures already recorded at clean baseline plus two platform skips, so they are not stage regressions.
      - [x] **P0-A18c6e: auxiliary-model exact rerun**. Empty out-root `ai-auxiliary-p0-a18c6-kv-set-deepseek-wsl-20260712-02` used `opencode/deepseek-v4-flash-free`, one initial call, and zero repairs. The independent validator reopened 16 hash-bound artifacts and reported AI exact pass. Router SHA-256 is `3d71be46e6d8530842397547a9011c1e65b1dc500922ee0d7f69daa12f7514e2`; candidate SHA-256 is `9e9b78cac94f05e6cd23ee6aafd9e4598be415df325e8b4e77e803f75c292230`. The run retains auxiliary identity and both public numerators at zero; it cannot replace the fixed 12 cases or GLM competition verification.
      - [x] **P0-A18c6f: split implementation by responsibility**. External-callee source-block extraction/input binding and guard/macro/enum behavior parsing now live in separate 260-line and 307-line modules; generic provider readiness and callee hash/binding readiness are separate 309-line and 164-line modules. They use no `exec`, dynamic `.pyfrag` loading, or project-specific dispatch.

    - [x] **P0-A18c7: cross-project AI-input and evidence-contract closure**. Recompute eligibility after repair; admit the actual external-source/typed-IR prompt scopes and both context-boundary states in the manifest schema; do not require repository function source for fixture-only scripted callees; derive target-function guard/return rules by reopening a file-SHA-bound strict source span and resolving macro/enum dependencies; use the real translation-carrier fragment as the fresh-oracle span. Project TypeMap `mappings`, CFG `functions`, and a bounded clang typed-IR summary into prompt scope while independently truncating oversized diagnostics. Every rule is driven by structure, declarations, and source hashes rather than project, function, or fixture identifiers. The focused gate passes 125/125 on both Windows and WSL.
      - The fixed empty-directory auxiliary run generated 12/12 candidates with 12 initial and four repair calls, zero contract failures, zero execution failures, zero provider blocks, and an exact-pass increase from 3/12 to 6/12. New passes are `tsl_to_blob`, `kv_set`, and `kv_del`. Report SHA-256 is `dfff968ad274924b763a8cede749338f37dcca25e38b5148fbeaaef0d09c2927`; auxiliary identity and both public numerators remain zero.
      - The remaining failure boundary is now clean: fresh oracle passes for all four real fragments, leaving generated-replay behavior mismatches; zlib-ng and libuv still fail fresh oracle because generated include/header and whole-translation-unit link closure are incomplete. These move to A18c8 without reopening A18c7.

    - [ ] **P0-A18c8: generic semantic closure for the remaining exact failures**.
      - [x] **P0-A18c8a: carrier/scripted source behavior digest**. Derive source-backed branch, call-order, field-write, and return summaries from the real fragment, ReplayCallPlan scripted runtime, CFG/effect data, and typed IR. Fixture expected/actual values remain hidden from the model.
        - The ordered typed-IR projection preserves assignment target/RHS pairs, nested `If/While/DoWhile`, call order, `continue`, fixed returns, unsigned wrapping, and all-ones sentinels under an independent `projection_sha256`. Unknown nodes, more than 64 items, exhausted node/depth budgets, truncation, or hash drift are blocked before provider launch; partial projections are never described as exact semantics.
        - Candidate and repair share the same high-salience source-semantics contract. Scripted callees are harness-owned and already in lexical scope: the model must call but must not declare, define, mock, or inline them. Candidate-owned scripted callees now produce structured rust-check evidence instead of a traceback, and legal Rust signatures with trailing commas are no longer rejected.
        - Artifact bounding reserves the non-metadata budget for a complete clang excerpt, fixing the case where a 6.3 KiB ordered projection was rewritten by generic depth limiting and then failed its SHA binding. The focused gate passes 131/131 on both Windows and WSL, and `git diff --check` passes.
        - In a four-case DeepSeek zero-repair `wsl-local-simulation`, all cases were provider-ready and made one call each. Interior projection and stats sequence moved from replay failures to all eight gates passing; each independent validator reopened 16 artifacts and returned `semantic_pass=true`. Router SHA-256 values are `1d40a293cd63acee5a8eab1c72c155a879bf932ec5bbe68da9e15e965c394e31` and `7bfbc41e2803d72415c4035ab5068eb4b6bbe02eec5966b1e845556e941b2ae1`.
        - Zero-start and read-kv-body-call still fail exact gates after their initial candidates and one repair each: DeepSeek continues rewriting nested loop/return/sentinel behavior or required-API mutability. This evidence does not expose fixture values, add more rounds, or claim a new fixed-suite rate. The default pipeline remains protected by the generic typed-IR fallback and exact gates, so the parent item stays open.
      - [x] **P0-A18c8b: real-project fresh-C-oracle build closure**. Prefer a bound compile database, generated includes, and build-artifact/link contracts. Missing context fails closed; zlib/libuv names cannot select semantic stubs or test-only link flags.
        - A `linked_artifacts_v1` resolver and independent manifest schema now select behavior only from schema/mode/data fields, never target/project/function/slice/name identities. A closure binds the source tree, normalized compile DB, source/generated include trees, static libraries, ordered system link args, source/link symbols, CMake config, toolchain, and target ABI. Every path is repo-relative; parent traversal, absolute paths, symlinks, missing artifacts, and SHA drift are rejected.
        - Producer and validator rebuild the same ordered argv from the closure. Invalid closures produce `native_build_closure_invalid`, zero argv, and structured diagnostics. The slice spec/build profile and ContextPack carry the closure manifest path/SHA; fresh-oracle verification reopens the closure and includes compile-DB/include/library/link/symbol/config/toolchain/ABI identity in flags and the reuse key.
        - The minimal repo-owned closures live under `validation/native-build-closures/`. zlib-ng uses the `ZLIB_COMPAT=OFF` `libz-ng.a`, explicitly binding `adler32_z -> zng_adler32_z` plus generated headers. libuv uses `libuv.a` plus `-lpthread -ldl -lrt -lm`. Both compile databases are free of host absolute paths, and archive hashes match the captured `nm` symbols.
        - In WSL `runs-05`, both units reached `compile_succeeded_not_oracle` with return code 0 and `exited_zero_not_oracle`; oracle compile-contract recomputation passed, and the full libuv auto-translation schema validator passed. Fresh proof now fails only with `oracle_output_mismatch/oracle_output_unproven`, not header/link/build-profile/closure mismatch. Focused contract tests pass 61/61 on Windows and WSL, and the fixed 12-case offline preflight is 12/12 ready with zero model calls.
        - An empty zlib CFG is now represented honestly as `blocked`, and the full auto-translation schema validator passes. This proves complete refusal evidence only, not translation or semantics. The obsolete `adler32_step` AST fixture was removed and must not be restored as synthetic proof for real `adler32_z`.
      - [x] **P0-A18c8b1: hash-bound real-TU translator compile context**. Project a repo-relative source/include/define/compile-DB/ABI context from the verified closure. The compile DB must match its SHA and select exactly one target-source entry; compiler, input, output, dependency-generation, and captured include arguments are removed before closure-authoritative includes and defines are overlaid. Invalid, ambiguous, or ABI-conflicting context blocks without legacy-parser fallback.
        - Function selection binds file, lines, byte range, and normalized fragment SHA. Macro-renamed definitions resolve to the expanded `FunctionDecl` while output restores the logical name. LF-normalized offsets map to raw CRLF offsets for Windows/WSL versus Linux checkouts. Non-null pointer `BitCast` remains refused; only an already-proven null pointer may be retargeted.
        - WSL `runs-07` binds zlib-ng and libuv to commit `0a7831c1`, clang 18.1.3, and each compile-DB SHA. Both native oracle harnesses reach `compile_succeeded_not_oracle`/`exited_zero_not_oracle`, and both full schema validators pass. zlib refuses a runtime function-table member call; libuv refuses `sizeof(*addr)` without record-layout proof. Both remain `semantic_pass=false` and add no success numerator. Rust lib tests pass 253/253 and focused Python tests pass 50/50.
      - [x] **P0-A18c8c: generic executable C-oracle call plan**. Generate data-driven harness calls, input initialization, return/record-field encoding, and stdout comparison from C signatures, fixture codecs, observable outputs, and ABI. Project/function identities cannot select adapters. Fresh oracle may enter AI repair/exact only after the harness executes fixture target calls and every output gate matches.
        - [x] **P0-A18c8c1: direct-return call plan**. ReplayCallPlan v1 scalar, string, hex/byte-array, derived-length, and `null_default` inputs now render generically into C fixture storage, signature-ordered arguments, one real target invocation, and direct-return comparison. The renderer never reads project, slice, function, or fixture identity to select an adapter. Case count, ids, strings, buffers, and rendered source are bounded fail closed, and normalized case-id collisions still produce distinct variables.
        - The validator and fresh-oracle proof regenerate the call plan from the hash-bound spec and compare the plan SHA, declarations, and complete invocation/assertion statements. A marker-only or forged matched-text harness cannot pass. In WSL competition-like `runs-02`, both zlib-ng fixtures execute `adler32_z`; compile and run return codes are zero, the output gate matches, and the full schema validator passes.
        - This stage remains `semantic_pass=false` and does not increase the translation coverage numerator. libuv still refuses because its omitted C output parameter and C record-field projections are undeclared. Output initialization, record/byte-order projections, and C/Rust diff remain later A18c8c work.
        - [x] **P0-A18c8c2: strict structured C-oracle output protocol**. Each `generated` call-plan case/field emits exactly one canonical JSON record binding the ReplayCallPlan SHA, case ordinal/id, field, encoding, and canonical string actual value; total protocol output must fit the persisted stdout bound. The parser rejects missing, duplicate, extra, reordered, wrong-value/SHA, unknown-key, malformed JSON, duplicate JSON key, and non-canonical records while ignoring ordinary diagnostics.
        - Output gate v2, fresh-oracle, and the full evidence validator use the same parser to recompute the gate from persisted stdout instead of trusting producer-supplied matched/missing lists. Historical `not_used` harnesses retain the legacy gate, while a `generated` contract cannot downgrade. In WSL competition-like `runs-03`, both zlib-ng actual-value records match exactly, invalid/unexpected counts are zero, and compile, execution, and the full schema validator pass. This remains `semantic_pass=false` and adds no success numerator.
        - [x] **P0-A18c8c3: declarative output parameters and record projections**. A separate `c_oracle_contract` accepts only safe header basenames, zero-initialized single struct pointees, `address_of`, return, scalar mapping, field, BE16, and fixed object-byte enums. Raw C expressions and project/function adapters are rejected. Output bindings must exactly close omitted C parameters, observation order must exactly match ReplayCallPlan assertions and fixture observables, and the C call-plan SHA binds the replay plan, effective fixture, target ABI, and complete contract.
        - The renderer emits `_Static_assert` checks for pointer/`int`/`CHAR_BIT` and each observed field; each header must uniquely match `c_boundary.files(role=header)`. A complete target/slice/function/output-parameter rename still selects the same path. The implementation is split into a 70-line façade plus direct renderer, output renderer, output schema, and output protocol modules, all below 400 lines.
        - In WSL competition-like libuv `runs-02`, compile and execution return zero. All 12 strict records across the `loopback` and `invalid` cases match for return/status/family/host-port/port-bytes/address-bytes, invalid/unexpected counts are zero, and the full schema validator passes. This closes only the fresh C-oracle harness: the translator still fails closed at unproven `sizeof(*addr)` record layout, `semantic_pass=false`, and the translation success numerator does not increase.
      - [x] **P0-A18c8d: `sizeof(expression)` operand-type recovery**. Real clang JSON omits `argType` for expression-form traits. The frontend now recovers the type only when `inner` contains exactly one operand carrying `type.qualType`. The explicit `argType` path is unchanged; missing type or multiple operands remain `unsupported_sizeof_operand`. WSL libuv `runs-03` advances from the old operand blocker to `unsupported_sizeof_type: sizeof(struct sockaddr_in) requires explicit C layout/ABI provenance`, while the fresh C oracle still matches all 12 strict records. This stage emits no Rust and adds no success numerator.
      - [x] **P0-A18c8e: hash-bound record-layout provenance**. Only the hash-bound compile-database path runs a separate clang `-fdump-record-layouts-complete` invocation with the same sanitized compile arguments. Raw stdout, diagnostics, shared arguments, compile database, and complete target ABI are bound independently by SHA/value. `sizeof` admits only one exactly matching named `struct` layout; `_Alignof`, unions, missing/duplicate layouts, and type/ABI/hash conflicts remain fail-closed. The implementation does not select a size from project, function, or record identity.
        - WSL competition-like libuv `runs-06` captures `struct sockaddr_in` as `size=16, align=4`, derived from the clang dump rather than identity dispatch. The dump SHA is `a6c4e578f594579408d716a1cfbf48ed02169d05630167f2fbabb8c02e7c432b`; the compile-database SHA is `f81a760815fb8618d3856e9f376a89d0e9c76234d3af0dd9e7840d8319f40638`. The fresh C oracle still matches all 12 strict records and the full validator passes; the translator blocker advances to `memset destination BitCast operand struct sockaddr_in * is not mutable unsigned 8-bit pointer`.
        - This evidence proves within-run binding consistency and allows the persisted report to be reopened and checked. Without an externally supplied expected dump SHA, it does not claim to detect cross-run clang/environment drift. This stage remains candidate context with `semantic_pass=false` and adds no translation-success numerator.
      - [x] **P0-A18c8f: generic mutable record-pointer zero fill**. Admit only standard `memset` in statement position, a direct non-null mutable single-level record parameter, an exact zero byte, and complete `sizeof(record)` produced by the same hash-bound layout proof. The frontend lowers this to dedicated `IrStmt::RecordMemset`, retaining record type, size/alignment, four SHAs, and target ABI; an ordinary numerically equal `IrExpr::Call` cannot impersonate it. The typed emitter revalidates provenance and safely emits `*dest = Record { ...zero values... }` only for integers, fixed integer arrays, and recursively complete records. It never byte-slices a Rust record and emits no `unsafe`. Readonly, nullable, nonzero/partial writes, pointer fields, type/ABI/hash drift, `memcpy`, and custom calls remain refused. No project, record, or function identity selects the rule.
        - WSL `runs-09` uses clang 18.1.3 and the default Cargo cache as a local simulation. The old `memset destination BitCast operand struct sockaddr_in *` blocker is gone, while record layout remains bound to dump SHA `a6c4e578f594579408d716a1cfbf48ed02169d05630167f2fbabb8c02e7c432b` and compile-database SHA `f81a760815fb8618d3856e9f376a89d0e9c76234d3af0dd9e7840d8319f40638`. The fresh C oracle still compiles, executes, and matches all 12 strict records, and the full validator passes. The new blocker is `sa_family_t is outside the current type skeleton`; that name records the real observation but is not a future dispatch key.
        - The competition-environment repo-local Cargo mirror returned an empty response in this run, so `runs-09` is explicitly `wsl-local-simulation`, not `competition-exact`. No real libuv Rust candidate is emitted yet; `semantic_pass=false` and the success numerator is unchanged.
      - [x] **P0-A18c8g: generic typedef canonical/desugared type recovery**. Clang type-object candidates are still attempted in `qualType -> desugaredQualType -> canonicalQualType` order, but when all remain unsupported only because target ABI is not bound yet, the last and deepest canonical spelling is retained for the later ABI pass instead of preserving an unresolvable surface alias. Translation-unit `TypedefDecl` inventory now feeds both function-body AST type objects and named/anonymous record fields, including field nodes that omit desugaring when unique alias provenance exists. Alias versus explicit desugared/canonical drift, duplicate conflicts, unknown aliases, and missing target widths remain fail closed. No project, header, function, field, or typedef identity selects the rule.
        - A direct WSL translator rerun uses clang 18.1.3, the same hash-bound libuv compile database, and the `x86_64-unknown-linux-gnu` ABI. The old `sa_family_t is outside the current type skeleton` blocker is gone. The new blocker is `CallExpr: argument 2: ... mutable void * BitCast address target in_addr_t * is not a mutable record pointer`, meaning that an address of a complete mutable scalar lvalue passed as a `void *` write argument is not modeled yet. The two observed typedef names record real progress only and are not dispatch keys.
        - This probe is an unpublished WSL local-simulation diagnostic under `target/`; it contains no Rust candidate, C/Rust replay/diff, or semantic acceptance. `semantic_pass=false` and the translation-success numerator is unchanged.
      - [ ] **P0-A18c8h: generic mutable-scalar address to `void *` call argument**. Model a temporary mutable borrow only for a provably complete integer-scalar direct/record-field lvalue address, a direct external call, and an explicit mutable `void *` parameter. Alias, lifetime, alignment, width, signature, and post-call read paths must be verifiable. Const, nullable, bitfield, packed/volatile/atomic, pointer arithmetic, cross-call escape, and overlapping mutable borrows remain refused; no `in_addr_t`, libuv, or fixed-callee identity mapping is allowed.
        - [x] **P0-A18c8h1: safe-adapter candidate for a record-pointer field address**. The frontend preserves dedicated `MutableVoidPointerAddress` provenance and accepts only one direct mutable record-pointer root, one initial `->` followed only by `.`, a complete record-field path ending in a fixed-width integer, a same-width/signedness source integer pointer, a direct `FunctionDecl`, and a mutable `void *` parameter at that position. Typed IR revalidates complete field inventory, root ownership, non-nullability, overlapping borrows in the same call, and source/target types, then emits `&mut root.path` only for a compile-checked safe adapter. Ordinary `AddrOf` and numerically similar handwritten nodes cannot enter this path. A raw `*mut c_void` extern binding is not disguised as a safe interface and still fails at rustc/link gates without an adapter.
        - [x] **P0-A18c8h2: explicit noalias precondition and equivalent integer typedefs**. The legacy libuv slice spec now carries the generic `pointer_contract`: `ip` is a readonly input, `addr` is a mutable output, and `ip -> addr` is a complete noalias precondition, while `aliasing_proven=false` and the no-whole-program-alias-proof boundary remain explicit. The translator does not infer noalias from project/function identity or differing C types. The dedicated A18h check now accepts different typedef/base spellings only when constness, signedness, and width all agree; signed-32 and width-16 drift remain refused.
        - [x] **P0-A18c8h3: external direct-call compile context and pointer adaptation**. The libuv slice spec declares `__bswap_16` and `uv_inet_pton` with their real C signatures and binds normalized `inet.c` SHA; the system-header inline binds only its call site and header source instead of pretending to be a source implementation. Generic rustc-only stubs use an independent pointee type for each C pointer parameter, preserve const/mutable direction, and report `compile_only_pointer_pointee_erasure`. This applies only to `rustc_compile_only`; fixture/replay-specific models retain exact signatures.
        - The `target/a18c8h-probe-07` WSL run uses clang 18.1.3, the same hash-bound libuv compile database, and `x86_64-unknown-linux-gnu`. It emits a `GenericTypedIr` candidate with both callees marked `generated_compile_only`, `blocked_count=0`, a passing stub contract, and `rust_check.status=passed`. Replay explicitly skips with `compile_only_external_bindings_not_executable`, and this run also uses `--skip-c-oracle`; therefore `semantic_pass=false` and the success numerator remains 38.
        - [x] **P0-A18c8h4a: compile-only candidate/replay API compile preflight**. Whenever rust-check reports a `rustc_compile_only` binding, the harness combines the stub-injected candidate with generated replay and runs one `rustc --test`, persisting stdout/stderr, return code, and `candidate_replay_compile_preflight`. It keeps `execution_allowed=false` regardless of compile result, never runs the stub, and never creates replay pass. A renamed positive proves matching APIs compile but still skip execution; a renamed negative proves API mismatch saves diagnostics while semantics remain false.
        - [x] **P0-A18c8h4b: candidate-required external-callee filtering**. Rust-check first runs structured diagnostics with `--json=diagnostic-short` against the raw candidate without injected stubs, avoiding a compiler rendering crash from long rendered diagnostics when multiple calls are unresolved. It accepts only code exactly `E0425`, message exactly `cannot find function \`NAME\` in this scope`, and `NAME` in the intersection with slice-declared or blocked external callees, then builds compile-only context for only those names. A fully self-contained AI candidate is no longer unconditionally stubbed or prevented from replay merely because the original C call graph still contains external dependencies; a partially inlined candidate receives only its actually unresolved declared functions. Diagnostic-like strings, other error codes, `cannot find value`, and undeclared names cannot spoof selection. This stage does not loosen compile-only execution, does not treat rustc/replay alone as semantic acceptance, and leaves the success count at 38.
        - The `target/a18c8h-probe-10` WSL local simulation uses clang 18.1.3, Rust 1.95.0-dev, the same hash-bound libuv compile database, and the `x86_64-unknown-linux-gnu` ABI. Raw-candidate diagnostics select exactly the two declared functions `__bswap_16` and `uv_inet_pton`; rust-check passes after injecting both compile-only bindings. Candidate+replay preflight still returns 101 for the safe API shape, keeps `execution_allowed=false`, and replay skips with `compile_only_external_bindings_not_executable`. This run uses `--skip-c-oracle`, so `semantic_pass=false`, the success count is unchanged, and the evidence is not `competition-exact`.
        - [x] **P0-A18c8h4c: stable multi-diagnostic feedback for AI repair**. Generated replay and its non-executing preflight now use `--json=diagnostic-short`; this changes no compile, execution, or semantic gate and only removes long rendered snippets that can trigger a Rust diagnostic-renderer ICE. A neutral regression creates both a missing type and an argument-type mismatch in one replay and requires both structured diagnostic classes to persist. The `target/a18c8h-probe-11` WSL local simulation returns normal failure code 1, two `E0425`, two `E0061`, and `compiler unexpectedly panicked=false` for the same real candidate. These errors can feed the existing AI exact repair loop, but this run invokes no model, uses `--skip-c-oracle`, keeps `execution_allowed=false` and `semantic_pass=false`, and leaves the success count at 38.
        - [x] **P0-A18c8h4d: exact compiler diagnostics into AI repair facts**. A separate identity-neutral normalization layer extracts at most eight errors from exact rustc `errors` or replay compile JSONL, retains only bounded `code` and host/sensitive-metadata-redacted `message`, deduplicates them, and binds them to the candidate SHA. The compile gate forwards diagnostics only after candidate/target bindings match; the replay gate additionally requires matching replay/fixture bindings and an exact compile phase. SHA or contract drift never trusts runner diagnostics. Repair facts revalidate the allowlist and discard every extra field, so rendered source, spans, fixture values, and oracle values never enter the model prompt. The harness does not synthesize wrappers or rewrite candidates. OpenCode may return only a complete self-contained Rust candidate, which must rerun rustc, fresh oracle, replay, schema diff, negative mutation, unsafe, alias, ABI, and final verification. This improves repair input only and leaves the success count at 38.
        - The real `target/a18c8h-probe-08` WSL local simulation still has `rust_check.status=passed`, while preflight returns 101 and `candidate_replay_api_compile_failed`, explicitly reporting missing `Ip4AddrReport` and call-shape mismatch. Replay still skips with `compile_only_external_bindings_not_executable`. This stage improves repair diagnostics only and does not increase the success numerator.
        - The A18h parent remains open: required safe candidate API adaptation, executable external-callee semantics/no-escape, direct local/parameter scalar addresses, the raw extern boundary, and post-call field initialization remain separate work. Const, nullable, variadic, indirect-call, signedness/width drift, incomplete-record, and same-root sibling-read cases have fail-closed regressions.

      Prior failure evidence: same-profile `kv_set` router `4a6b7b99095e2c91fde2c40a9eac9ca141a9bb276d4c981dd886115350d6f6a0` passed rustc/unsafe/oracle, but the candidate implemented external-callee result `-1` while the oracle produced `7`. All three WSL worktree runs reported `repo_commit=UNKNOWN0`, so they remain local hash-bound AI-routing evidence only.

  Historical auxiliary runs retain only the decision index below. The corresponding reports and Git history remain the detailed artifact source. Every run is `wsl-local-simulation`, with both public numerators fixed at zero.

  | Stage / run id | Exact | Decision-relevant result | Bound evidence |
  | --- | ---: | --- | --- |
  | A18b2b2a / `ai-auxiliary-p0-a18b2b2a-wsl-20260712-160700` | 2/12 | 12 calls and 8 candidates; 2 contract failures, 1 execution failure, and 1 provider block prevent a generic-improvement claim | run id + unit artifacts |

  | A18b2c2 / `ai-auxiliary-p0-a18b2c2-deepseek-wsl-20260712-180000` | 1/12 | 12 calls and 8 candidates; regression from the prior run means replay planning did not yet improve success | report SHA `bc26d70321086cd5a6e27b9e5d13912aaa29c32445160536364fe9ad00f27458` |

  | A18b2c3 / `ai-auxiliary-p0-a18b2c3-deepseek-wsl-20260712-192612` | 2/12 | 12 initial + 6 repair calls; fixes old aggregate undercounting but only restores the two-pass baseline | report SHA `7e8bd77b9afd6c5883d007a47c5058d47a12d1a5d973b86e5ff042b908e2d5c0` |

  | A18c1 / `ai-auxiliary-p0-a18c1-deepseek-wsl-20260712-204206` | 2/12 | 12 initial + 4 repair calls and 11 candidates; contract failures fell to zero and first-round API mismatch fell 3 to 1, but exact success did not improve | report SHA `512641d1ece1d6dcf8b5bc20af3208da467a1c5284931d3c2a32bdb5cf8551c1` |

  | A18c3 / `kv_to_blob` targeted | 0/1 exact | rustc/replay pass, but `alias_proof_missing` keeps semantic false; a targeted sample is not fixed-suite success evidence | router SHA `0c5f8f7130f4b6b8c163f1007af130cc6016f48234a54e6dde4485a8a7b31316`; manifest SHA `16a7fa57a8038cb9c66a57c8f8a8eeb04cb171dba68a5cc9b6802aa55529f18b` |

- [x] **P0-A1: OpenCode no-progress retry suppression**

  Hash effective request/source/spec/repair-trace/launch-policy inputs as `effective_input_sha256`, and hash structured root cause/status/returncode/diagnostics as `failure_sha256`. After two identical deterministic failures with no current input change, close the repair hint before a third launch, clear its retry command, record `repair_retry_suppressed`, and fail closed as `refused/retry_input_unchanged`. Do not invoke the runner, append a synthetic attempt, or raise semantic status. Preserve retries for timeout, SQLite/OpenCode locks, preflight, credentials, contracts, missing environment, unknown causes, and missing or drifting hashes.

  This gate reduces OpenCode calls and token use that have no information gain. It does not treat AI output as semantic fact or replace the C oracle, Rust replay, or strict validator.

- [x] **P0-A2: align bare `CLANG_PATH` command names with the competition PATH contract**

  The Rust clang frontend now accepts both an existing explicit path and a bare command name resolved by the process `PATH`, such as `CLANG_PATH=clang`; an explicit path containing separators still fails closed when it does not exist. The WSL clang 18 minimum-TU smoke and three real-clang auto-migrate positive/negative tests pass. This restores candidate generation only and does not increase the semantic count.

- [x] **P0-A3: deterministic-first admission gate**

  `mode=auto` selects deterministic execution before OpenCode preflight only when every worker binds accepted evidence, an existing evidence root, a source hash, and a slice spec with no repair policy. Mixed or unbound input is refused before fanout as `auto_route_unbound`; `competition-exact`, hostless rehearsal, and explicit OpenCode attestation cannot auto-downgrade. This route only avoids model calls with no expected information gain and remains `semantic_gate=false`.

  This is historical behavior. After P0-A9, `mode=auto` becomes AI-primary for new translation work; only pure accepted-evidence revalidation retains the deterministic shortcut.

- [x] **P0-A4: compact the OpenCode worker context while preserving the exact contract**

  `.opencode/agents/c2rust-migrator.md` was reduced from 5408 bytes to 1439 bytes while preserving `opencode + GLM-5.1 + c2rust-migrator + max`, Required Preflight, the non-gating Superpowers boundary, the first-and-only exact Command line tool call, prohibitions on exploration/editing/subagents/substitute commands, hash-bound handoff/session/contract verification, and the non-semantic chat boundary. The bundle manifest and profile contract tests were updated. This only reduces model context and ambiguity; it remains `semantic_gate=false`.

- [x] **P0-A5: keep one command representation in OpenCode prompts**

  Worker and preflight prompts remove the duplicate `Command: <JSON argv>` text and retain one executable `Command line:`. Structured argv, command hashes, sessions, and handoff evidence remain unchanged. Representative prompts are 13.2%-16.1% smaller and the full harness suite passes. This only reduces token use and command ambiguity; it remains `semantic_gate=false`.

### 3.4 P0-B: Competition Host and OpenCode

- [ ] **P0-H9: exact OpenCode + GLM-5.1 competition contract revalidation**

  WSL currently resolves provider-qualified `zai/glm-5.1`, but the complete preflight/worker marker chain is not closed on the real competition host. OpenCode + GLM-5.1 is now the default competition translation path. When it is unavailable locally, record blocked/unavailable explicitly; deterministic results must not impersonate the AI competition lane.

  Completion requires `COMPETITION_EXACT_HOST=1`, an exact GLM-5.1 token from `opencode models`, preflight with `opencode` + `GLM-5.1` + `c2rust-migrator` + `max`, complete hash-bound probe/session/worker artifacts, and successful judge-bundle/public-packet revalidation.

  WSL, local, and CI results remain `wsl-local-simulation`, `local-simulation`, and `ci-approximation`; none closes H9.

- [ ] **P0-H10: publish the CRC32 competition-exact before/after**

  Depends on P0-H9. Close only after replaying the completed CRC32 C2Rust+repair before/after on the real competition host and publishing hash-bound workflow metrics.

### 3.5 P0-C: Stage Closure

- [ ] **P0-C1: historical evidence drift**. Fix the eight failures reconfirmed by run `20260711T-finite-p0-t31` in artifact-ownership batches, separate from translator behavior changes.
- [ ] **P0-C2: all-feature Clippy**. Commit `81a772d1` cleared nine low-risk warnings; eight remain: two `large_enum_variant`, one `redundant_guards`, one `needless_lifetimes`, and four `too_many_arguments`. New slices must add no warnings.
- [x] **P0-C3: first-party Rust large-file split closure**. Every Git-tracked first-party `.rs` file under `crates/c2r-translator`, `flashDB_rust`, and `validation/l2_slices` is at most 400 lines after formatting. Splits occur only at complete item/test boundaries, the single oversized report function was extracted into a dedicated helper, and the test-source self-check recursively covers split leaves. The only exceptions are the 733/704-line hash-bound historical C2Rust evidence snapshots under `validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/`; evidence content must not be rewritten merely to satisfy the line limit.

## 4. Later Backlog

### P1: Expand Generic Translation

1. Expand typed IR according to P0-A10 cross-project failure frequency instead of one-project source order; start with a complete alias/noalias, pointer-provenance, and escape model.
2. Preserve integer promotion, usual arithmetic conversion, narrowing, array/function decay, and ABI-related conversions explicitly in IR.
3. Model compound side effects as composable rules for sequence points, evaluation order, increment/decrement, dereference, index, member, and call.
4. Expand CFG support: classify and evidence `switch`/`goto` fail-closed behavior before adding a relooper or structured lowering.
5. Expand compound literals, designated initializers, function pointers, variadics, unions, bitfields, VLAs, and flexible array members.
6. Model volatile, hardware registers, RTOS/interrupts, filesystems, and power-loss boundaries; host fixtures do not replace target evidence.
7. Add real slices from different construct families across FlashDB, zlib-ng, libuv, and other projects; do not inflate coverage with many similar checksum/parser slices.

### P2: Agents, Routing, and Release

1. Maintain model/prompt upgrade and rollback policies plus offline replay; P0-A10 establishes the golden-set fact source.
2. Use a second model only for independent candidates or audit; majority voting must not replace semantic gates.
3. Publish human intervention, duration, token/evidence cost, and model-upgrade before/after differences.
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
| P0-T26 | Select and validate the `:1880` u32 mutable record-pointer postfix increment candidate | 35 -> 35 (candidate only) |
| P0-T27 | Strict source-backed acceptance for the `:1880` u32 mutable record-pointer postfix increment | 35 -> 36 |
| P0-T28 | Select and validate the `:1881` owner-interior u32-to-LP64-usize sibling accumulation candidate | 36 -> 36 (candidate only) |
| P0-T29 | Strict source-backed acceptance for the `:1881` owner-interior sibling accumulation | 36 -> 37 |
| P0-T30 | Select and validate the `:1880-1883` bounded ordered stats sequence candidate | 37 -> 37 (candidate only) |
| P0-T31 | Strict source-backed acceptance for the `:1880-1883` ordered stats sequence | 37 -> 38 |

Validation run bindings:

| Validation | Binding | Result |
| --- | --- | --- |
| P0-T31 strict validator | WSL competition clang lane, 2026-07-11 | `schema_status=passed`, `semantic_pass=true`, `generated_draft_semantic_pass=true`; all 12 semantic-binding checks passed; only four finite fixtures ran, with no stress loop or repeated rounds |
| P0-T29 strict validator | WSL competition clang lane, 2026-07-11 | `schema_status=passed`, `semantic_pass=true`, `generated_draft_semantic_pass=true`; all 12 semantic-binding checks passed; only three bounded fixtures ran, with no 1,000/10,000-round or other loop stress test |
| P0-T27 strict validator | WSL competition clang lane, 2026-07-11 | `semantic_pass=true`, `generated_draft_semantic_pass=true`; all 12 semantic-binding checks passed; only three bounded fixtures ran and no loop stress was run |
| P0-T25 strict validator | WSL competition clang lane, 2026-07-11 | `semantic_pass=true`, `generated_draft_semantic_pass=true`; all 12 semantic-binding checks passed; three bounded fixtures cover 1/2/3 ordered body/tail calls; no loop stress was run |
| P0-T24 / P0-A1 / P0-A2 stage validation | WSL local simulation, 2026-07-11 | translator library `228`, bounded `665`, and integer conversion `4` passed, with `133` real-clang opt-in tests ignored by default; three real-clang focused tests, Python auto-migrate `155`, and OpenCode harness `192` passed; no loop stress was run |
| P0-T23 strict validator | WSL competition clang lane, 2026-07-11 | `semantic_pass=true`, `generated_draft_semantic_pass=true`; all 12 semantic-binding checks passed; three bounded fixtures cover 1/2/3 calls |
| P0-T22 translator candidate | current worktree, 2026-07-11 | library `228` passed; bounded `659` passed with `133` real-clang opt-in ignores; integer conversion `4` passed; coverage matrix passed |
| P0-T21 translator candidate | commit `02067028`, 2026-07-11 | library `228` passed; bounded `657` passed with `133` real-clang opt-in ignores; integer conversion `4` passed |
| P0-T20 Python core historical snapshot | 2026-07-11 stage snapshot | `293 passed, 6 skipped`, plus `90` subtests; proves only that revision |
| Full regression | run `20260711T-finite-p0-t31` | 25 of 33 passed; P0-T31 added no failure and the same eight historical evidence drifts failed; `stress_loops=0`, `run_stress=false` |
| P0-T21 strict validator | evidence generated from commit `8a261787` | `semantic_pass=true`, `generated_draft_semantic_pass=true`, and all 12 semantic binding classes passed |
| P0-T20 strict validator | P0-T20 evidence | `semantic_pass=true` and `generated_draft_semantic_pass=true` |
| Accepted-evidence strict status | `libuv/ip4-addr` | verified-unsafe-baseline SHA drift; the ledger count is not a current strict pass |
| All-feature Clippy | commit `81a772d1` plus current test cleanup | Eight warnings remain under `--all-features --all-targets`, all in the four P0-C2 categories listed above |

## 6. Architecture Boundaries

### 6.1 Candidate Routes

| Level | Purpose | Can it claim semantic success alone? |
| --- | --- | --- |
| L0 ContextPack | Bind real source, compile context, diagnostics, and candidate baselines | No |
| L1 AI primary | OpenCode + GLM-5.1 candidate generation or repair | No |
| L2 deterministic alternates | typed IR, raw C2Rust, and C2Rust+repair candidates | No |
| L3 common verification | Compile, oracle/replay, diff/negative, and unsafe/ABI gates | Only after all pass |
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
2. New competition translation work defaults to AI-first. typed IR and C2Rust provide context, alternate candidates, and verifiable fallback; a hand-written lowering rule is not a prerequisite for invoking AI on an unfamiliar construct.
3. Start with the smallest source-backed slice and expand adjacent structure. Every relaxed rule needs a positive and nearest fail-closed negative.
4. The C oracle is ground truth only within its declared fixture, compiler, flags, ABI, and observable contract.
5. Fail-closed results must provide the source span, refusal reason, and next smallest implementation step; refusal volume is not success.
6. Unsafe counts are governance metrics, not complete proof for FFI, concurrency, volatile, ABI, or hardware semantics.
7. Evidence uses repo-relative paths, stable hashes, and explicit retention rules. Never publish secrets or host absolute paths.
8. Split large files by module responsibility. Add tests, schemas, evidence, and docs only when they produce a behavioral or acceptance benefit.
9. AI input is limited to source, compile context, type/API contracts, and failure classification. Candidate and repair must not receive fixture expected/actual values, oracle output, first mismatch, or replay source carrying those values. Validators may read complete hash-bound evidence but may not feed validation answers back to the model.

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
