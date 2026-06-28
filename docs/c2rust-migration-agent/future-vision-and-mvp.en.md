# Future Vision and MVP Roadmap

Chinese original: `future-vision-and-mvp.md`.

## 1. Goal

Build an end-to-end MVP pipeline: `input.c` → `c2rust-migrator` → `output.rs`. Phase 1 proof is complete in the code path sense (the FlashDB `real-fdb-calc-crc32` named slice can generate a compilable Rust candidate through real clang AST dump lowering + typed IR + generic emitter and bind it to semantic gates through accepted evidence), and committed evidence now includes a durable real-clang lowering artifact. Generated drafts remain candidates, and significant gaps remain before reaching an industrial-grade C→Rust translator.

The boundary must stay explicit: `validation/evidence/*/l1-native-build.json` only proves the original C project builds or smoke-tests in a pinned environment. It does not prove Rust translation success. Current real auto-translation capability is still concentrated in curated function slices; the large-project evidence catalogue is an input pool and baseline, not proof that real large projects can already be translated.

## 1.1. Todo Execution Rules

From the Chinese original and this synchronized mirror onward, core translation work defaults to the P0/P1/P2 backlog mirrored here. Unless a blocking bug appears, temporary demos or a single project should not reorder the main work. **The Chinese original `future-vision-and-mvp.md` is the authoritative global roadmap/backlog source; this English file is a synchronized mirror and must not define a separate backlog**. Checklists, tasks, Next sections, or P0/P1/P2 wording elsewhere may only be local validation templates, OpenSpec change tasks, historical implementation plans, or analysis notes, and must not override the Chinese original's priorities.

Phase 2/3/4 describe capability maturity stages. P0/P1/P2 is the default execution queue. When actual work starts, follow P0/P1/P2; if a Phase item overlaps a P-queue item, split that capability into the smallest verifiable implementation slice.

- **Expand translation capability before expanding ceremony**: before adding a schema, manifest, or gate, explain which concrete translation risk, validation false positive, or reproducibility gap it solves.
- **FlashDB is only a use case**: FlashDB remains useful as a regression sample, but the project must not add FlashDB-specific recognizers, templates, or special-case routes.
- **Candidate generation is not semantic acceptance**: typed IR, C2Rust, LLMs, and handwritten rules are only candidate sources. Semantic pass is owned by the C oracle, Rust replay, diff, negative diff, unsafe ledger, and final verification.
- **The C oracle has boundaries too**: an oracle only proves behavior for a pinned source commit, fixture set, compiler/flags, target ABI, platform model, and observable-output contract. Undefined behavior, implementation-defined behavior, hardware/RTOS/volatile effects, and insufficient test coverage must be recorded explicitly instead of being hidden behind "tests passed."
- **Fail-closed must not become a dead end**: every refusal must include an actionable next step: source span, unsupported construct, missing IR/lowering rule, oracle/fixture gap, candidate sources worth trying, and human-review input. Otherwise it is only blocked, not a governance success.
- **Evidence cost must be governed**: release-required evidence, developer smoke evidence, diagnostic logs, and historical archives need separate classes. New evidence-producing paths must record runtime, file size, retention/compression/prune policy, so metadata growth does not consume translation-development capacity.
- **Unsafe numbers are not safety proof**: the unsafe budget is a governance metric, not proof that FFI, hardware, volatile, ABI, or concurrency semantics have been safely modeled. Zero findings only means no first-party non-test `unsafe` was found in the current scan scope.
- **C2Rust baseline must stay traceable**: the route/profile C2Rust candidate is only `candidate_context_only` and must bind the baseline manifest. When the baseline actually generates output, it must also bind output path/status/sha256, and the validator must reject drift.
- **C2Rust skipped must not count as candidate success**: when the baseline is `skipped`, `blocked`, or has no output, it must record reason, toolchain/env, input hash, and `output_ref=null`; skipped baselines must not count as generated, compiled, accepted, or semantic pass.
- **Competition environment config is an adaptation reference and evidence profile**: `config/competition-env/environment.json` is the current default competition environment entrypoint. Development should follow its Ubuntu, Rust, Python, Node, gcc, mirror, and missing-tool constraints. The local machine does not need to replicate that environment exactly, but new default build, test, and validation paths must not violate it; `validation/environment-profiles/...` is compatibility-only.
- **Public reproduction paths default to Linux/CI**: PowerShell/Windows commands may remain as local convenience entrypoints, but externally assessable quickstarts, verification, and evidence generation must provide competition Linux/CI equivalents. When no equivalent path exists, mark the command as local-only.
- **Evidence must be portable**: new evidence, manifests, cache metadata, and log references should prefer repo-relative paths, profile ids/hashes, and artifact hashes. Local `C:\...`, `F:\...`, or `/mnt/c/...` paths may appear only as diagnostic host metadata, not as reproducible entrypoints or cross-machine claim anchors.
- **Default paths must expose real capability**: no-clang default CI or competition paths must not present a legacy string translator success as typed-IR success. When typed IR did not run because `CLANG_PATH` or another tool is missing, evidence, metrics, and public claims must mark it as unavailable or compatibility fallback.
- **Handoff docs must stay short and auditable**: `CONTEXT.md` is only for current state, latest verification, and next-step handoff. Long session logs should be split or archived under `docs/c2rust-migration-agent/archive/`, and must not become release documentation, an external evaluation entrypoint, or capability proof.
- **Docs must stay bilingual**: update the Chinese original `future-vision-and-mvp.md` and this English mirror together.

## 2. IR Layering Design (Recommended Industrial Standard)

Key principle: **IR must not "decide how Rust should be written"; it must only "describe what C is"**. Correctness comes from C oracle; IR is the intermediate representation that faithfully describes C semantics.

### Layer 1: Semantic IR (Most Important)

**Preserve C semantics. Do not do Rust inference. Do not produce candidates.**

This layer is the translator's core asset. It only answers: "What does this C code do in the C abstract machine?"

- Every C operation preserves its original semantics: integer promotion rules, usual arithmetic conversions, sequence points, lvalue conversions
- No premature judgment on "this pointer can become a slice" or "this struct can become a Rust struct"
- Preserve raw pointer arithmetic, implicit casts, truncation, and promotion information
- Array-to-pointer decay is part of C semantics and must be preserved in the IR
- UB markers (locations of undefined behavior) must also be recorded at this layer

**Current status**: Our typed IR mixes in some Rust inference (e.g., directly marking `const void *` as `&[u8]`). This is acceptable for P0 but should be separated into a dedicated Lowering layer long-term.

### Layer 2: Control IR

**if / loop / goto / switch, with explicit CFG.**

- Control flow transitions from AST to explicit basic blocks + CFG
- `if-else`, `while`, `for`, `do-while`, `switch-case`, `goto`/label all enter a unified CFG
- Each edge carries an explicit condition (or is unconditional)
- `break` and `continue` map to CFG edges; no ad-hoc handling needed
- Support relooper (recovering high-level structured control flow from arbitrary CFG), which is prerequisite for translating `goto` / `switch`

**Current status**: We have a basic `cfg.json` evidence template, but typed IR internally still uses AST-style control flow (`If`, `While`, `For`, `DoWhile`). `switch`, `goto`, and computed goto are completely unsupported.

### Layer 3: Typed Value IR

**integer / pointer / struct / array, explicit casts only.**

- All implicit type conversions (integer promotion, usual arithmetic conversion, array-to-pointer decay, function-to-pointer decay) become **explicit casts** at this layer
- Pointer arithmetic is decomposed into element access: `p + i` becomes `element_at(p, i)` or equivalent
- Struct field access is explicit offset-based or symbolic field access
- Array indexing is explicit base + offset
- The type system only describes C runtime behavior; no Rust type inference

**Current status**: Our typed IR has `Cast { implicit }` to distinguish explicit/implicit casts, integer types have signed/width information, and pointers have `Pointer { pointee }`. However, the clang frontend's handling of `ImplicitCastExpr` is incomplete (some transparently stripped, some preserved), and there is no unified principle of "all implicit casts become explicit."

### Lowering Layer (from Semantic IR to Rust candidate)

This layer converts "describing C" into "generating Rust". Key principles:

1. Do not modify the Semantic IR itself
2. Every lowering rule must be provable (supported by C oracle or typed evidence)
3. When lowering fails, preserve the complete fail-closed reason
4. No "guessing" allowed — if C semantics cannot be safely mapped to safe Rust, refuse translation

Typical lowering rules:
- `const T *p` + read-only access → `p: &[T]` (must prove: no writes, no escape, bounded lifetime)
- `T *out` + write-only access → `out: &mut [T]` (requires noalias proof)
- `uint32_t + uint8_t` → explicit `(byte as u32) + acc` (requires promotion proof)
- `while(size--)` → Rust `loop` + `wrapping_sub` (must preserve postfix side-effect semantics)

## 3. MVP Pipeline Roadmap

```
input.c  →  clang AST dump  →  Semantic IR  →  Lowering  →  Rust candidate
         \                    \              \            \
          source slice         typed IR       route decision  validation gates
          extraction           (current)      (current)       (current)
```

### Phase 1: Completed

- [x] Real clang AST dump JSON parsing (`clang -Xclang -ast-dump=json` → `clang_frontend.rs`)
- [x] typed IR data structures (`IrFunction` / `IrStmt` / `IrExpr` / `IrType`)
- [x] Generic typed IR emitter (scalar + control flow + pointer slice subset)
- [x] Readonly global const array support
- [x] Route decision and validation profile evidence binding
- [x] C oracle harness draft generation
- [x] Rust replay execution and diff gate
- [x] Legacy crc32 specialty code removed
- [x] FlashDB `real-fdb-calc-crc32` named slice passes accepted evidence semantic pass

### Phase 2: Near-term (complete IR layering)

- [ ] Separate Semantic IR from Lowering: IR describes C semantics only, not candidates
- [ ] All clang `ImplicitCastExpr` become explicit typed IR casts
- [ ] Array-to-pointer decay as explicit IR node
- [ ] `switch` / `goto` support (requires CFG + relooper)
- [ ] Compound literals, designated initializers
- [ ] Function pointers (at least direct calls and simple passing)
- [ ] `enum` types
- [ ] `union` types (at least tagged union pattern)

### Phase 3: Mid-term (expand real C project coverage)

- [ ] Push more FlashDB functions (`fdb_kv_set`, `fdb_tsl_iter`, etc.) to L3
- [ ] Support real function slices from libuv, zlib-ng, and other projects
- [ ] Select 5+ projects from `validation/projects.json`, pushing at least one named function slice per project: project-level L1 native baseline + slice-level L2/L3 evidence
- [ ] Govern catalogue L1 failures: every catalogue report must list success/fail/skipped ratios, top failure classes, fixable/non-fixable/missing-environment classes, exclusion rules, and next steps. L1 skipped/fail entries must not count as translation capability or L3 progress.
- [ ] Explicit model for usual arithmetic conversions
- [ ] Pointer/alias-sensitive struct field writes (with alias/noalias proof; simple readonly `const struct T *p` `p->scalar_field` reads, `p == NULL` / `p != NULL` presence checks to `Option<&T>`, flow-sensitive null-guarded `p->scalar_field` reads, direct mutable `struct T *p` `p->scalar_field = scalar`, simple standalone `p->scalar_field += scalar`, same-field `return p->scalar_field` after a definite write under the single-pointer-param gate, direct if-return branches where every fallthrough path writes that same field, standalone statement-position `p->scalar_field++` / `++p->scalar_field` / `p->scalar_field--` / `--p->scalar_field`, non-pointer simple by-value `p.x = value`, and standalone statement-position `p.x++` / `++p.x` / `p.x--` / `--p.x` are already in the typed IR candidate subset; multi-pointer aliasing, nullable mutable pointers, read-before-write, ordinary reads after maybe-writes, writes only on returning branches, loop/complex-path returns, complex RHS/targets, value-position field inc-dec, and other pointer field update/read forms still fail closed)
- [ ] Nested structs / anonymous structs
- [ ] Bitfields (at least common patterns)
- [ ] Macro expansion tracking

### Phase 4: Long-term (industrial-grade translator)

- [ ] Full C99/C11 subset coverage
- [ ] Multi-file translation unit support
- [ ] Incremental migration (change one function at a time without breaking the rest)
- [ ] Bidirectional evidence (C→Rust and Rust→C cross-validation)
- [ ] Performance regression gate
- [ ] Automatic fuzz harness generation
- [ ] Sanitizer / symbolic-execution / property-based exploration as enhanced oracle support for high-risk slices, not as replacements for the fixture contract and C/Rust diff
- [ ] MIRI validation (Rust UB detection, not as C UB proof)

## 4. P0/P1/P2 Backlog (Default Execution Order)

### P0: Make the current MVP a credible, maintainable translator core

- [ ] Keep converging `crates/c2r-translator/src/lib.rs`: the crate root is now a smaller public orchestration entrypoint, but CLI/manifest handling, legacy string translator responsibilities, typed IR routes, artifact writing, and unsafe/metadata accounting still need to continue moving into focused submodules. Public model schema extraction, the private artifact/IO leaf helper module extraction (`artifact_io.rs`: `write_json_file`, `write_text_file`, `translation_events_jsonl`), the core translation artifact writer helper extraction (`write_core_translation_artifacts`), the feature-gated clang dry-run artifact writer extraction (`write_clang_dry_run_artifact`), the clang lowering report artifact writer cluster extraction (`write_clang_lowering_report_artifact`, `typed_ir_candidate_evidence`, `readonly_global_summary`), the private clang-lowered translation/evidence module extraction (`clang_lowered_translation.rs`), the private legacy string translator module extraction (`legacy_translation.rs`), and the `write_translation_artifacts` public orchestration extraction are done with the crate root API preserved. CLI/manifest orchestration, generic typed IR routes, unsafe/metadata accounting, parser/evidence builder/emitter extraction still remain. Every split commit must keep existing tests passing.
- [ ] Split the large `typed_ir.rs` / `clang_frontend.rs` files: start with behavior-preserving splits that move IR data types, type/definite-assignment validation, emitter logic, side-effect helpers, clang AST skeletons, clang-to-IR lowering, and report/evidence builders into stable submodules. Every split must keep the feature matrix, public API, bounded tests, fixture replay, and `git diff --check` passing.
- [x] Normalize the clang frontend story: the active path is invoking `clang -Xclang -ast-dump=json -fsyntax-only` through `CLANG_PATH`; `--emit-clang-dry-run` artifacts now carry `artifact_kind=clang-dry-run`, `status=diagnostic_only`, `claim_boundary.role=diagnostic_only`, and `active_frontend.kind=clang_ast_dump_json`. `LIBCLANG_PATH` is only `ignored_env_for_ast_dump` / `observed_libclang_path` diagnostic metadata, does not participate in lowering, and must not imply that real libclang parsing is active.
- [x] Make the competition clang lane explicit: `config/competition-env/environment.json` now declares clang as an optional capability/optional lane; default build, test, and validation paths do not require clang. When the real clang AST dump typed-IR lane is needed, use `auto_migrate.py --competition-clang-lane`; that lane enables `clang-lowering-report`, requires `CLANG_PATH`, and fails clearly when it is missing. Passing only `--emit-clang-lowering-report` remains diagnostic opt-in and writes an unavailable report when clang is missing.
- [x] Define dependency and toolchain admission rules: keep `CLANG_PATH` + clang AST dump JSON as the current semantic frontend fact. Add dependencies such as libclang/bindgen/syn/quote/tracing/anyhow only when they remove a concrete semantic risk, generation-quality risk, or maintainability risk and fit `config/competition-env/environment.json`; do not add dependencies merely to make the project look like a compiler stack. `config/competition-env/environment.json` now contains `dependency_admission_policy`, admits only the current direct Rust dependencies `serde` / `serde_json`, marks libclang/bindgen/syn/quote/tracing/anyhow as not-approved candidates with before-use conditions, and `validation.tools.test_competition_environment_profile` scans current Rust manifests in core CI.
- [x] Add a no-clang typed-IR fixture replay CI lane: a reduced clang AST JSON replay fixture (`crates/c2r-translator/fixtures/clang_ast/add_one_ast.json`, used to regress AST shape handling rather than durable real-clang evidence) and replay API now let default CI run `AST JSON -> typed IR -> generic emitter -> rustc/check` without `CLANG_PATH`; the real clang lane remains responsible for frontend integration through `--competition-clang-lane`. Future coverage expansion should keep adding real AST JSON fixtures; handwritten IR unit tests are not a substitute for this regression path.
- [x] Commit durable real-clang lowering evidence: key real-source slices such as `real-fdb-calc-crc32` must include a real `clang-lowering-report` or equivalent artifact in committed evidence, recording `CLANG_PATH`/tool version/profile hash, typed IR hash, and Rust draft hash. If a run only has no-clang/compatibility-path evidence, public wording must be downgraded to "code path supported, current evidence does not include a real-clang lowering artifact." `auto_migrate.py --competition-clang-lane` now enriches the lowering report with Python sha256 values, and `validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-clang-lowering-report.json` is committed and bound from the evidence manifest, route decision, and validation profile. The artifact records `CLANG_PATH`, clang version, competition profile hash, typed IR sha256, and Rust draft sha256; final semantic pass still comes from accepted evidence binding and does not promote the generated draft to accepted.
- [x] Add core translator + validation CI: `.github/workflows/core-translator-validation-ci.yml` now covers `crates/c2r-translator` default and all-features tests, core validation unittests, the repo-level unsafe budget gate, and `git diff --check`. Trigger paths include translator code, validation tools/templates, `validation/l2_slices`, competition env, and the unsafe ledger, so this no longer relies only on `flashDB Rust CI`.
- [x] Add a translator coverage matrix instead of counting only test files or test cases: `validation/translator-coverage-matrix.json` now records representative coverage by IR construct, clang fixture replay, handwritten IR, negative cases, runtime emitted Rust, C/Rust diff, legacy fallback, and route evidence. `validation/tools/translator_coverage_matrix.py` and core CI reject matrix rows that lack positive cases, negative cases, fail-closed reasons, evidence for covered dimensions, or existing linked paths. This matrix is a coverage-claim gate, not a full C99/C11 support percentage or semantic acceptance proof.
- [ ] Split the large `bounded_translation.rs` test file: organize tests by capability area such as clang frontend, typed IR validation, emitter arithmetic, pointer/slice lowering, record/field lowering, route/provenance, negative/fail-closed behavior, and runtime emitted Rust. The split must preserve the coverage matrix and existing test meaning; a larger test-file count is not itself coverage improvement.
- [x] Fix unsigned integer modulo semantics before claiming checksum/hash translation breadth: typed IR now emits explicit `wrapping_add` / `wrapping_sub` / `wrapping_mul` for C unsigned `+`, `-`, and `*`, with debug/overflow-checks runtime RED tests covering `u32::MAX + 1`, `0u32 - 1`, and unsigned multiply. Signed overflow, division/modulo by zero, and invalid shift counts remain separate fail-closed/contract questions.
- [ ] Define the signed-overflow/division/modulo/shift UB contract: signed `+`/`-`/`*` may emit wrapping only when the slice contract or compiler flags explicitly declare a `-fwrapv`/two's-complement wrapping profile; otherwise it must fail closed or record a precondition. Division/modulo by zero, invalid shift counts, and implementation-defined signed shifts need negative tests, evidence fields, and refusal reasons instead of relying on Rust debug/release differences. Progress: literal `/ 0`, `% 0`, negative shift counts, `shift_count >= width`, and signed right shift without an explicit contract now fail closed in the typed IR emitter; signed `+`/`-`/`*` candidates now emit `checked_add` / `checked_sub` / `checked_mul` + `expect(...)`, encoding no signed overflow as a runtime precondition; non-literal division/modulo divisors and non-literal shift counts for supported shift operators are now encoded in emitted Rust as runtime preconditions (`divisor != 0`, `0 <= shift_count < type width`), avoiding Rust debug/release divergence; `clang-lowering-report` `typed_ir_candidate.runtime_preconditions` now records these candidate preconditions, binds them into `route_decision.candidate_generation.typed_ir` / `validation_profile.candidate_generation.typed_ir`, and the validator rejects route/profile/report drift. Additional progress: the slice spec schema/template now records `c_boundary.scalar_arithmetic_contract`, `fixture_contract.scalar_input_domain`, and the related cache invalidation keys; route/profile evidence now records `scalar_ub_contract`, `typed_ir_candidate.scalar_admission` binds runtime preconditions to the slice contract/input domain, the validator rejects admission drift, and unresolved admission prevents a 0-token scalar typed-IR candidate from being downgraded to L0; no-clang AST JSON replay fixtures now cover the positive scalar runtime-precondition path and fail-closed refusal paths for literal `/0`, `%0`, shift count out of range, and signed right shift without a contract. Still open: named-slice C/Rust diff plus positive/refusal evidence for explicit signed-right-shift contracts; signed right shift without an explicit contract must still fail closed.
  - Additional progress: the typed IR emitter now has a default fail-closed `EmitPolicy`; only an opt-in policy derived from `c_boundary.scalar_arithmetic_contract.signed_right_shift = "explicit_implementation_defined_contract"` may emit signed right shift. clang-lowering reports record a `signed_right_shift_implementation_defined` runtime precondition, and auto_migrate plus the validator require that contract and `fixture_contract.scalar_input_domain` to cover it. The remaining gap is named-slice C/Rust diff plus positive/refusal evidence artifacts for explicit signed-right-shift contracts.
- [x] Connect a minimal unsafe budget monitor to CI: `validation/tools/unsafe_budget.py` covers `crates/c2r-translator/src`, `flashDB_rust/src`, and `validation/l2_slices/src` by default, and reports scan scope, denominator line count, unsafe findings, ratio, registration status, and ledger reference. `validation/unsafe-budget-ledger.json` is the repo-level registration entrypoint, and core CI runs this gate with `--max-ratio 0.10`.
- [x] Clarify unsafe-claim boundaries: `<10%` or current zero findings must not be used to prove C ABI, FFI, flash hardware, volatile register, RTOS, or thread/interrupt semantics are solved. Before those capabilities are implemented, they need unsafe ledger spans, alternatives, tests/target evidence, and human review status. The root README and docs README now state this boundary so the unsafe budget is not misrepresented as platform-semantic proof.
- [x] Strengthen C oracle / UB / platform boundaries: every accepted slice must record observable outputs, fixture representativeness, compiler and flags, target ABI, endianness/word-size assumptions, sanitizer/diagnostic status, known UB or implementation-defined boundaries, and whether hardware/RTOS/volatile dependencies are modeled. If the evidence is insufficient, the run must remain candidate or blocked and must not be promoted to semantic pass. `auto_migrate.py` now emits `oracle_boundary_contract`, `validation-profile.schema.json` requires that contract for passed profiles, `validate_auto_translation_evidence.py --require-semantic-pass` checks profile/final contract agreement, non-unknown target values, non-unmodeled platform status, and `oracle_boundary_contract_identity` cache binding; the `real-fdb-calc-crc32` accepted evidence has been refreshed and passes this gate.
- [x] Strengthen unsafe ledger governance granularity: registration items should later include span, alternatives, coverage tests, source evidence, and review status instead of relying only on the minimal path+category key. `validation/unsafe-budget-ledger.json` now carries `repo_level_policy` with required fields, field/category/review-status contracts, and path/category compatibility constraints; `validation/tools/test_unsafe_budget.py` pins the contract with a unit test.
- [ ] Converge `CONTEXT.md` handoff: create a short current-state entrypoint, archive or split superseded long-history sections, and mark old sections as historical records that are not current capability facts. Release docs, README, and roadmap claims must not rely on old session sections in `CONTEXT.md` as capability proof.
- [x] Clean evidence portability: add a validator or report that catches local absolute paths, old WSL/Windows work directories, unreproducible temporary directories, and missing profile hashes. Historical evidence may remain but must be marked historical/diagnostic; new milestone evidence must be reproducible from the repo plus the competition profile. `validation/tools/evidence_governance.py` now provides a non-destructive portability report that distinguishes claim-anchor absolute paths, missing competition profile hashes, and diagnostic host metadata. It treats `translator.artifact_paths` and `source_boundary.files` as claim anchors while classifying skipped C2Rust `reference_tree`, clang path, lowering arguments, and historical L1 `worker_result_sources` as diagnostic context. The real-fdb-calc-crc32 accepted `source_boundary.files` now records `src/fdb_utils.c`, auto-translation manifest `translator.artifact_paths` are repo-relative, `write_translation_artifacts` normalizes newly generated manifest paths to repo-relative form, and skipped C oracle compilation records `compile_execution.toolchain_adapter = "not_executed"`. The current repository report finds 0 claim-anchor absolute-path issues, 0 profile-hash issues, and 1599 diagnostic host-path records under `validation/evidence`, so the hard portability gate now passes; diagnostic records remain historical/environment audit context and are not capability claim anchors.
- [ ] Add evidence cost and retention governance: distinguish committed release evidence, CI smoke evidence, diagnostic-only logs, and historical archives. Every evidence pipeline should report runtime, artifact count, total bytes, retention class, and compression/prune policy so 1000+ evidence files do not keep growing without bounds. Progress: `evidence_governance.py` now emits inventory and per-pipeline statistics; the current repository has 1033 files, about 2.66 MB, and 54 pipelines under `validation/evidence`, classified as committed_release / diagnostic_only / historical_archive. CI now runs the unit tests for this tool, but full-regression artifact integration, retention review, and historical evidence cleanup are still open.
- [ ] Govern OpenSpec/validation complexity: archive or close stale active changes, distinguish lightweight release gates, developer smoke gates, and full-regression gates. Default reading entrypoints should point to the current roadmap, quickstart, coverage/capability report, and milestone evidence instead of making 1000+ evidence files or long OpenSpec history the newcomer path.
- [x] Narrow public claims: README, roadmap, and evidence summaries must distinguish L1 native-build baseline, candidate generation, and accepted semantic pass; native-build catalogues must not be described as completed real-project Rust translation. The root README, roadmap, and routing/evidence docs now state that native-build catalogues are original-C build baselines, not automatic translation evidence.
- [x] Mark showcase boundaries: `flashDB_rust` is currently a handwritten safe implementation / validation baseline and must not be presented as automatic translation output. Public demonstrations must distinguish handwritten implementation, translator-generated candidate, accepted evidence, and semantic pass. The FlashDB skeleton/milestone docs and routing docs now carry this boundary.
- [ ] Land L0-L4 route governance: distinguish catalogue/native baseline, translation route signals, and semantic acceptance; L0 only means a deterministic 0-token candidate signal, L1 includes native C baseline and may also be used by current route policy for non-scalar typed IR candidate signals, L2 means candidate compilation plus unsafe/diff evidence, L3 is the first level that can claim named-slice semantic pass, and L4 is refusal or an accepted-evidence-authoritative boundary.
- [ ] Add a fail-closed repair playbook: every L4/refused or blocked slice must emit source span, IR feature gap, oracle/fixture gap, candidate routes worth trying (typed IR/C2Rust/LLM/manual), the smallest next test, and the human-intervention point. Without those fields, refusal must not be presented as "governed."
- [x] Stop silent fallback from clang-lowered typed IR to the legacy string translator: raw translator artifacts now write `translation_source`, fallback records `selected`, `fallback_from`, and `fallback_reason`, and JSONL appends `translation_fallback`; `auto_migrate.py` preserves that field after normalization and binds the primary candidate source into `route_decision.candidate_generation.primary_candidate`.
- [ ] Demote and retire the legacy string translator: mark it as a compatibility-only candidate source, count it separately in default route/metrics, and forbid describing it as a parser or typed-IR success. After no-clang fixture replay and the real clang lane cover the minimal slices, remove it from the primary candidate path and keep only diagnostic or historical-evidence compatibility entrypoints.
- [x] Make the minimal route candidate inventory real as provenance: `auto_migrate.py` now writes `selection_policy.stage=post_generation_provenance`, `selected_candidate_id`, and `candidate_set` into route/profile evidence, covering the primary Rust draft, typed-IR signal, and `c2rust-baseline` context. The validator rejects id drift, C2Rust baseline claims as a semantic source, and candidate `semantic_pass=true`.
- [ ] Upgrade route metadata into a real candidate-selection layer. Today's `candidate_set` is a post-generation inventory and `selection_policy.full_router=false`; future route governance still needs scores or hard gates, fallback-chain priority, refusal reasons, validation-gate summaries, and C2Rust/LLM candidate dispatch.
- [ ] Clarify out-pointer semantics: a safe API may map a single-value `out[0] = value` to return/report fields; typed IR generic candidates should prefer preserving it as `&mut [T]` writes; null, alias/noalias, multi-pointer, and inout-pointer cases must each have negative tests or fail-closed evidence.
- [ ] Tag the first externally assessable Milestone: once CI and documentation boundaries stabilize, create a tag/release whose notes list the commit, verification commands, evidence manifest hash, competition profile hash, supported subset, non-goals, and known refusals, without generalizing named-slice conclusions to project-level translation.
- [ ] Add a human/external review gate to milestones: before release, complete a reviewer checklist covering architecture layering, unsafe ledger, test coverage matrix, real-slice evidence, public-claim boundaries, and known refusals. Without review records, label the milestone as an internal preview only.

### P1: Expand syntax and memory-model coverage

- [ ] Keep expanding the generic typed IR emitter instead of restoring crc32/FlashDB special cases: initialized record local copy, by-value record dot-field compound assignment, statement-position by-value record dot-field inc/dec, whole-record return with unique named complete direct scalar field inventory, simple readonly `const struct T *p` `p->scalar_field` reads, readonly record pointer `p == NULL` / `p != NULL` presence checks, flow-sensitive null-guarded `p->scalar_field` reads, direct mutable `struct T *p` `p->scalar_field = scalar`, simple standalone `p->scalar_field += scalar`, same-field `p->scalar_field` reads after definite writes, direct if-return branch same-field reads when every fallthrough path writes, and statement-position `p->scalar_field++` / `--p->scalar_field` under the single-pointer-param gate are now in the candidate subset; next prioritize multi-pointer alias/noalias proof, value-position/complex-target field updates/inc-dec, deeper path-sensitive facts beyond direct if-return, and stronger layout/ABI evidence.
- [ ] Design compositional side-effect expression lowering: model sequence points, evaluation order, value-position/statement-position, `++`/`--`, and deref/index/member/call side effects as composable IR/emitter rules. Whole-statement-shape helpers are transitional only; every migration step needs red/green tests and a fail-closed reason.
- [ ] Design alias/noalias and pointer escape modeling: split readonly slices, mutable out slices, nullable pointers, unknown alias, and volatile/hardware registers into provable paths and L4 refusal paths.
- [ ] Finish integer conversion discipline: every clang `ImplicitCastExpr`, integer promotion, usual arithmetic conversion, and narrowing/truncation must become explicit in the IR.
- [ ] Expand control flow: send `switch`/`goto` through CFG evidence and a fail-closed classifier first, then consider relooper and Rust candidates.
- [ ] Expand the real-slice pool: choose more non-toy functions from FlashDB, libuv, zlib-ng, and similar projects. Each slice needs a C oracle, Rust replay, diff, and negative diff; FlashDB slices must bind a translator-generated candidate and cannot count the handwritten `flashDB_rust` skeleton as automatic translation evidence.
- [ ] Add a generated capability/refusal metrics artifact and report command: aggregate route/profile/final-verification evidence into counts by C construct, route level, candidate source, target, slice, generated/blocked/refused/accepted status, failure reason, human-intervention point, unsafe ratio, fixture case count, negative-diff coverage, and performance-smoke status. Publish this report with each externally assessable milestone and use it to constrain public claims; native-build catalogues alone are not translation evidence.
- [ ] Move performance smoke earlier for real-slice expansion: every new L3 named slice should either record a lightweight benchmark/performance-smoke or explicitly mark `performance_not_claimed`; the full performance regression gate remains Phase 4 work.
- [ ] Model embedded/platform dependency boundaries: FlashDB, RTOS, filesystem, flash power-loss recovery, volatile/hardware registers, and thread/interrupt interactions must be handled through mockable platform contracts, host simulation, target evidence, or L4 refusal, not assumed to be represented by ordinary host fixtures.
- [ ] Define the FlashDB FFI/C ABI/hardware route: `ffi.rs` must not remain a placeholder indefinitely. C ABI, on-disk layout, FAL/RTOS/Zephyr/hardware backends, error/logging interfaces, and sync/power-loss semantics each need an OpenSpec change, unsafe ledger entry, target evidence, or explicit deferred/L4 refusal; host skeleton tests must not substitute for target evidence.

### P2: Agent/LLM and long-term research tracks

- [ ] Use LLMs only as candidate sources, never fact sources: AI candidate manifests must record provider/model/version or equivalent labels, prompt scope, input artifact hashes, output hash, whether the candidate was applied, and accepting/rejecting gates.
- [ ] Add model-change impact evaluation: maintain a small golden slice regression set, record candidate differences across model/version changes for identical inputs, and let validation gates judge acceptance; provider/model/prompt/input hash changes may only invalidate AI candidates/cache, never change the C oracle ground truth.
- [ ] Keep and operationalize the C2Rust baseline/repair route: use it as an L2 candidate source and comparator, but force its output through the same validation path and fail-closed policy. The next stage should make at least one real slice produce C2Rust output, record output path/status/sha256, and keep it in the candidate set as `candidate_context_only` or with an explicit validation status instead of remaining skipped-only indefinitely.
- [ ] Build the multi-candidate router after P0 semantics are stable: route L0 deterministic recipes, L1 generic typed IR, L2 C2Rust baseline/repair, L3 LLM candidates, and L4 refusal through one auditable decision object with scores or hard gates. This is not a substitute for the C oracle and must not accept candidates without the common validation pipeline.
- [ ] Publish quantitative evaluations and case reports: every milestone should state the number of real projects/functions, accepted/refused/blocked ratios, dominant failure classes, average human-intervention points, performance-smoke results, unsafe statistics, reproducible commands, evidence hashes, community review status, and known non-goals. It must also include competitor/baseline comparisons across at least raw C2Rust, C2Rust+repair, the current typed-IR route, LLM candidates, and handwritten references for generation rate, compile rate, accepted rate, human-intervention points, unsafe, and performance boundaries. Without those data, describe the project only as a research prototype or bounded MVP.
- [ ] Build an open-source feedback loop: before externally assessable milestones, add `CONTRIBUTING`, issue templates, review checklists, or equivalent docs, and record review/PR/issue feedback entrypoints. Community metrics are not capability proof, but without public feedback records the release must not be described as a mature production tool.
- [ ] Reduce single-maintainer risk: before external milestones, add CODEOWNERS or equivalent ownership docs, reviewer rotation, issue triage rules, and a release checklist. Key validation commands, evidence generation, route decisions, and release procedures must not depend on one maintainer or one Codex session's memory.
- [ ] Add a newcomer quickstart: README or `docs/quickstart` must provide a 10-15 minute minimal reproduction path with environment prerequisites, competition Linux/CI commands, optional local PowerShell commands, the first verifiable slice, expected artifacts, common failures, and boundary notes. New users must not have to infer entrypoints from `CONTEXT.md` or historical evidence.
- [ ] Keep CFG/SSA/MIR/LLVM/self-hosting research in the long-term backlog; do not make it mainline before P0 CI, module split, and real-slice semantic pass rates are stable.

## 5. Current Core Principles

1. **C oracle is the sole ground truth**. typed IR, clang lowering, and Rust candidates are only descriptions and candidates.
2. **Fail-closed**. When uncertain, refuse translation, record reasons, never pretend success.
3. **Auditable evidence chain**. Every decision step has machine-readable evidence, cross-checked by the validator.
4. **Route only controls candidate path**. Semantic acceptance is decided by validation profile + gates.
5. **IR describes C, does not predict Rust**. Rust type inference and ownership inference are the lowering layer's responsibility.
6. **No restoration of specialty fallbacks**. Old crc32 templates and canned recognizers are deleted; project-specific code must not be reintroduced.
7. **Honest boundaries are more credible than exaggerated demos**. All documentation must honestly list "currently supported" and "explicitly unsupported".
