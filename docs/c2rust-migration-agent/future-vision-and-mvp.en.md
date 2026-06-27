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
- [ ] Pointer/alias-sensitive struct field writes (with alias/noalias proof; non-pointer simple by-value `p.x = value` and standalone statement-position `p.x++` / `++p.x` / `p.x--` / `--p.x` are already in the typed IR candidate subset)
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

- [ ] Split `crates/c2r-translator/src/lib.rs`: it is currently about 4k lines. Do a behavior-preserving split first, moving CLI/manifest handling, legacy string translator, typed IR routes, artifact writing, and unsafe/metadata accounting into focused submodules. The split commit must keep existing tests passing.
- [ ] Normalize the clang frontend story: the active path is `clang -Xclang -ast-dump=json -fsyntax-only`; `LIBCLANG_PATH`/libclang dry-run skeleton may remain only as a diagnostic placeholder or be removed, but must not imply that real libclang parsing is active.
- [ ] Add core translator + validation CI: cover `crates/c2r-translator` unit tests, typed-ir/clang-frontend feature combinations, core validation tool tests, and `git diff --check`; do not rely only on `flashDB Rust CI`.
- [ ] Turn the unsafe budget into continuous monitoring: default coverage includes first-party non-test Rust crates (at least `crates/c2r-translator`, `flashDB_rust`, and `validation/l2_slices`), and the report must record scan scope, denominator, unsafe hits, ratio, and registration status; CI checks that the ratio stays below 10%, and every new unsafe use must register source, reason, and validation gates.
- [ ] Narrow public claims: README, roadmap, and evidence summaries must distinguish L1 native-build baseline, candidate generation, and accepted semantic pass; native-build catalogues must not be described as completed real-project Rust translation.
- [ ] Land L0-L4 route governance: distinguish catalogue/native baseline, translation route signals, and semantic acceptance; L0 only means a deterministic 0-token candidate signal, L1 includes native C baseline and may also be used by current route policy for non-scalar typed IR candidate signals, L2 means candidate compilation plus unsafe/diff evidence, L3 is the first level that can claim named-slice semantic pass, and L4 is refusal or an accepted-evidence-authoritative boundary.
- [ ] Clarify out-pointer semantics: a safe API may map a single-value `out[0] = value` to return/report fields; typed IR generic candidates should prefer preserving it as `&mut [T]` writes; null, alias/noalias, multi-pointer, and inout-pointer cases must each have negative tests or fail-closed evidence.
- [ ] Tag the first externally assessable Milestone: once CI and documentation boundaries stabilize, create a tag/release whose notes list the commit, verification commands, evidence manifest hash, competition profile hash, supported subset, non-goals, and known refusals, without generalizing named-slice conclusions to project-level translation.

### P1: Expand syntax and memory-model coverage

- [ ] Keep expanding the generic typed IR emitter instead of restoring crc32/FlashDB special cases: initialized record local copy, by-value record dot-field compound assignment, statement-position by-value record dot-field inc/dec, and whole-record return with unique named complete direct scalar field inventory are now in the candidate subset; next prioritize pointer-aware record access, value-position/complex-target/pointer-alias-sensitive update field writes, and stronger layout/ABI evidence.
- [ ] Design alias/noalias and pointer escape modeling: split readonly slices, mutable out slices, nullable pointers, unknown alias, and volatile/hardware registers into provable paths and L4 refusal paths.
- [ ] Finish integer conversion discipline: every clang `ImplicitCastExpr`, integer promotion, usual arithmetic conversion, and narrowing/truncation must become explicit in the IR.
- [ ] Expand control flow: send `switch`/`goto` through CFG evidence and a fail-closed classifier first, then consider relooper and Rust candidates.
- [ ] Expand the real-slice pool: choose more non-toy functions from FlashDB, libuv, zlib-ng, and similar projects. Each slice needs a C oracle, Rust replay, diff, and negative diff.

### P2: Agent/LLM and long-term research tracks

- [ ] Use LLMs only as candidate sources, never fact sources: AI candidate manifests must record provider/model/version or equivalent labels, prompt scope, input artifact hashes, output hash, whether the candidate was applied, and accepting/rejecting gates.
- [ ] Add model-change impact evaluation: maintain a small golden slice regression set, record candidate differences across model/version changes for identical inputs, and let validation gates judge acceptance; provider/model/prompt/input hash changes may only invalidate AI candidates/cache, never change the C oracle ground truth.
- [ ] Keep the C2Rust baseline/repair route: use it as an L2 candidate source and comparator, but force its output through the same validation path and fail-closed policy.
- [ ] Keep CFG/SSA/MIR/LLVM/self-hosting research in the long-term backlog; do not make it mainline before P0 CI, module split, and real-slice semantic pass rates are stable.

## 5. Current Core Principles

1. **C oracle is the sole ground truth**. typed IR, clang lowering, and Rust candidates are only descriptions and candidates.
2. **Fail-closed**. When uncertain, refuse translation, record reasons, never pretend success.
3. **Auditable evidence chain**. Every decision step has machine-readable evidence, cross-checked by the validator.
4. **Route only controls candidate path**. Semantic acceptance is decided by validation profile + gates.
5. **IR describes C, does not predict Rust**. Rust type inference and ownership inference are the lowering layer's responsibility.
6. **No restoration of specialty fallbacks**. Old crc32 templates and canned recognizers are deleted; project-specific code must not be reintroduced.
7. **Honest boundaries are more credible than exaggerated demos**. All documentation must honestly list "currently supported" and "explicitly unsupported".
