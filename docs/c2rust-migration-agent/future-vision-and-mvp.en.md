# Future Vision and MVP Roadmap

Chinese original: `future-vision-and-mvp.md`.

## 1. Goal

Build an end-to-end MVP pipeline: `input.c` → `c2rust-migrator` → `output.rs`. Phase 1 proof is complete (the FlashDB `real-fdb-calc-crc32` named slice can generate a compilable Rust candidate through real clang AST dump lowering + typed IR + generic emitter, and bind it to semantic gates through accepted evidence), but significant gaps remain before reaching an industrial-grade C→Rust translator.

The boundary must stay explicit: `validation/evidence/*/l1-native-build.json` only proves the original C project builds or smoke-tests in a pinned environment. It does not prove Rust translation success. Current real auto-translation capability is still concentrated in curated function slices; the large-project evidence catalogue is an input pool and baseline, not proof that real large projects can already be translated.

## 1.1. Todo Execution Rules

From this document onward, core translation work defaults to the P0/P1/P2 backlog in this file. Unless a blocking bug appears, temporary demos or a single project should not reorder the main work.

- **Expand translation capability before expanding ceremony**: before adding a schema, manifest, or gate, explain which concrete translation risk, validation false positive, or reproducibility gap it solves.
- **FlashDB is only a use case**: FlashDB remains useful as a regression sample, but the project must not add FlashDB-specific recognizers, templates, or special-case routes.
- **Candidate generation is not semantic acceptance**: typed IR, C2Rust, LLMs, and handwritten rules are only candidate sources. Semantic pass is owned by the C oracle, Rust replay, diff, negative diff, unsafe ledger, and final verification.
- **C2Rust baseline must stay traceable**: the route/profile C2Rust candidate is only `candidate_context_only` and must bind the baseline manifest. When the baseline actually generates output, it must also bind output path/status/sha256, and the validator must reject drift.
- **Competition environment config is an adaptation reference and evidence profile**: `config/competition-env/environment.json` is the current default competition environment entrypoint. Development should follow its Ubuntu, Rust, Python, Node, gcc, mirror, and missing-tool constraints. The local machine does not need to replicate that environment exactly, but new default build, test, and validation paths must not violate it; `validation/environment-profiles/...` is compatibility-only.
- **Docs must stay bilingual**: update this file and `future-vision-and-mvp.md` together.

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
- [ ] MIRI validation (Rust UB detection, not as C UB proof)

## 4. P0/P1/P2 Backlog (Default Execution Order)

### P0: Make the current MVP a credible, maintainable translator core

- [ ] Split `crates/c2r-translator/src/lib.rs`: it is still about 69 lines. Do a behavior-preserving split first, moving CLI/manifest handling, legacy string translator, typed IR routes, artifact writing, and unsafe/metadata accounting into focused submodules. Public model schema extraction, artifact/IO leaf helper extraction (`write_json_file`, `write_text_file`, `translation_events_jsonl`), the core translation artifact writer helper extraction (`write_core_translation_artifacts`), the feature-gated clang dry-run artifact writer extraction (`write_clang_dry_run_artifact`), the clang lowering report artifact writer cluster extraction (`write_clang_lowering_report_artifact`, `typed_ir_candidate_evidence`, `readonly_global_summary`), the private clang-lowered translation/evidence module extraction (`clang_lowered_translation.rs`), the private legacy string translator module extraction (`legacy_translation.rs`), and the `write_translation_artifacts` public orchestration extraction are done with the crate root API preserved. CLI/manifest orchestration, generic typed IR routes, unsafe/metadata accounting, parser/evidence builder/emitter extraction still remain. Every split commit must keep existing tests passing.
- [x] Normalize the clang frontend story: the active path is invoking `clang -Xclang -ast-dump=json -fsyntax-only` through `CLANG_PATH`; `--emit-clang-dry-run` artifacts now carry `artifact_kind=clang-dry-run`, `status=diagnostic_only`, `claim_boundary.role=diagnostic_only`, and `active_frontend.kind=clang_ast_dump_json`. `LIBCLANG_PATH` is only `ignored_env_for_ast_dump` / `observed_libclang_path` diagnostic metadata, does not participate in lowering, and must not imply that real libclang parsing is active.
- [x] Make the competition clang lane explicit: `config/competition-env/environment.json` now declares clang as an optional capability/optional lane; default build, test, and validation paths do not require clang. When the real clang AST dump typed-IR lane is needed, use `auto_migrate.py --competition-clang-lane`; that lane enables `clang-lowering-report`, requires `CLANG_PATH`, and fails clearly when it is missing. Passing only `--emit-clang-lowering-report` remains diagnostic opt-in and writes an unavailable report when clang is missing.
- [x] Add core translator + validation CI: `.github/workflows/core-translator-validation-ci.yml` now covers `crates/c2r-translator` default and all-features tests, core validation unittests, the repo-level unsafe budget gate, and `git diff --check`. Trigger paths include translator code, validation tools/templates, `validation/l2_slices`, competition env, and the unsafe ledger, so this no longer relies only on `flashDB Rust CI`.
- [x] Fix unsigned integer modulo semantics before claiming checksum/hash translation breadth: typed IR now emits explicit `wrapping_add` / `wrapping_sub` / `wrapping_mul` for C unsigned `+`, `-`, and `*`, with debug/overflow-checks runtime RED tests covering `u32::MAX + 1`, `0u32 - 1`, and unsigned multiply. Signed overflow, division/modulo by zero, and invalid shift counts remain separate fail-closed/contract questions.
- [x] Connect a minimal unsafe budget monitor to CI: `validation/tools/unsafe_budget.py` covers `crates/c2r-translator/src`, `flashDB_rust/src`, and `validation/l2_slices/src` by default, and reports scan scope, denominator line count, unsafe findings, ratio, registration status, and ledger reference. `validation/unsafe-budget-ledger.json` is the repo-level registration entrypoint, and core CI runs this gate with `--max-ratio 0.10`.
- [ ] Strengthen unsafe ledger governance granularity: registration items should later include span, alternatives, coverage tests, source evidence, and review status instead of relying only on the minimal path+category key.
- [ ] Narrow public claims: README, roadmap, and evidence summaries must distinguish L1 native-build baseline, candidate generation, and accepted semantic pass; native-build catalogues must not be described as completed real-project Rust translation.
- [ ] Land L0-L4 route governance: distinguish catalogue/native baseline, translation route signals, and semantic acceptance; L0 only means a deterministic 0-token candidate signal, L1 includes native C baseline and may also be used by current route policy for non-scalar typed IR candidate signals, L2 means candidate compilation plus unsafe/diff evidence, L3 is the first level that can claim named-slice semantic pass, and L4 is refusal or an accepted-evidence-authoritative boundary.
- [x] Stop silent fallback from clang-lowered typed IR to the legacy string translator: raw translator artifacts now write `translation_source`, fallback records `selected`, `fallback_from`, and `fallback_reason`, and JSONL appends `translation_fallback`; `auto_migrate.py` preserves that field after normalization and binds the primary candidate source into `route_decision.candidate_generation.primary_candidate`.
- [x] Make the minimal route candidate inventory real as provenance: `auto_migrate.py` now writes `selection_policy.stage=post_generation_provenance`, `selected_candidate_id`, and `candidate_set` into route/profile evidence, covering the primary Rust draft, typed-IR signal, and `c2rust-baseline` context. The validator rejects id drift, C2Rust baseline claims as a semantic source, and candidate `semantic_pass=true`.
- [ ] Upgrade route metadata into a real candidate-selection layer. Today's `candidate_set` is a post-generation inventory and `selection_policy.full_router=false`; future route governance still needs scores or hard gates, fallback-chain priority, refusal reasons, validation-gate summaries, and C2Rust/LLM candidate dispatch.
- [ ] Clarify out-pointer semantics: a safe API may map a single-value `out[0] = value` to return/report fields; typed IR generic candidates should prefer preserving it as `&mut [T]` writes; null, alias/noalias, multi-pointer, and inout-pointer cases must each have negative tests or fail-closed evidence.
- [ ] Tag the first externally assessable Milestone: once CI and documentation boundaries stabilize, create a tag/release whose notes list the commit, verification commands, evidence manifest hash, competition profile hash, supported subset, non-goals, and known refusals, without generalizing named-slice conclusions to project-level translation.

### P1: Expand syntax and memory-model coverage

- [ ] Keep expanding the generic typed IR emitter instead of restoring crc32/FlashDB special cases: initialized record local copy, by-value record dot-field compound assignment, statement-position by-value record dot-field inc/dec, whole-record return with unique named complete direct scalar field inventory, simple readonly `const struct T *p` `p->scalar_field` reads, readonly record pointer `p == NULL` / `p != NULL` presence checks, flow-sensitive null-guarded `p->scalar_field` reads, direct mutable `struct T *p` `p->scalar_field = scalar`, simple standalone `p->scalar_field += scalar`, same-field `p->scalar_field` reads after definite writes, direct if-return branch same-field reads when every fallthrough path writes, and statement-position `p->scalar_field++` / `--p->scalar_field` under the single-pointer-param gate are now in the candidate subset; next prioritize multi-pointer alias/noalias proof, value-position/complex-target field updates/inc-dec, deeper path-sensitive facts beyond direct if-return, and stronger layout/ABI evidence.
- [ ] Design alias/noalias and pointer escape modeling: split readonly slices, mutable out slices, nullable pointers, unknown alias, and volatile/hardware registers into provable paths and L4 refusal paths.
- [ ] Finish integer conversion discipline: every clang `ImplicitCastExpr`, integer promotion, usual arithmetic conversion, and narrowing/truncation must become explicit in the IR.
- [ ] Expand control flow: send `switch`/`goto` through CFG evidence and a fail-closed classifier first, then consider relooper and Rust candidates.
- [ ] Expand the real-slice pool: choose more non-toy functions from FlashDB, libuv, zlib-ng, and similar projects. Each slice needs a C oracle, Rust replay, diff, and negative diff.

### P2: Agent/LLM and long-term research tracks

- [ ] Use LLMs only as candidate sources, never fact sources: AI candidate manifests must record provider/model/version or equivalent labels, prompt scope, input artifact hashes, output hash, whether the candidate was applied, and accepting/rejecting gates.
- [ ] Add model-change impact evaluation: maintain a small golden slice regression set, record candidate differences across model/version changes for identical inputs, and let validation gates judge acceptance; provider/model/prompt/input hash changes may only invalidate AI candidates/cache, never change the C oracle ground truth.
- [ ] Keep the C2Rust baseline/repair route: use it as an L2 candidate source and comparator, but force its output through the same validation path and fail-closed policy.
- [ ] Build the multi-candidate router after P0 semantics are stable: route L0 deterministic recipes, L1 generic typed IR, L2 C2Rust baseline/repair, L3 LLM candidates, and L4 refusal through one auditable decision object with scores or hard gates. This is not a substitute for the C oracle and must not accept candidates without the common validation pipeline.
- [ ] Keep CFG/SSA/MIR/LLVM/self-hosting research in the long-term backlog; do not make it mainline before P0 CI, module split, and real-slice semantic pass rates are stable.

## 5. Current Core Principles

1. **C oracle is the sole ground truth**. typed IR, clang lowering, and Rust candidates are only descriptions and candidates.
2. **Fail-closed**. When uncertain, refuse translation, record reasons, never pretend success.
3. **Auditable evidence chain**. Every decision step has machine-readable evidence, cross-checked by the validator.
4. **Route only controls candidate path**. Semantic acceptance is decided by validation profile + gates.
5. **IR describes C, does not predict Rust**. Rust type inference and ownership inference are the lowering layer's responsibility.
6. **No restoration of specialty fallbacks**. Old crc32 templates and canned recognizers are deleted; project-specific code must not be reintroduced.
7. **Honest boundaries are more credible than exaggerated demos**. All documentation must honestly list "currently supported" and "explicitly unsupported".
