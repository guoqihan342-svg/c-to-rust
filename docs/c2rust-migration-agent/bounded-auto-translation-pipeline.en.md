# Bounded Automatic Translation Pipeline Agent Guide

This guide is for OpenCode, Codex, and other executable agents working on OpenSpec change `add-bounded-auto-translation-pipeline`. The pipeline produces evidence-bound Rust draft candidates. It does not make an implementation accepted by default; acceptance still comes from the L1-L3 evidence gates.

## Entry Rules

- The project is no longer constrained to be "small and fine-grained" overall: it may grow into multiple crates, tools, batch jobs, and target validations. Each migration claim must still remain slice-level, evidence-bound, rollbackable, reproducible, and gated by L1-L3 evidence.
- Start from OpenSpec: read `openspec status --change "add-bounded-auto-translation-pipeline" --json` and `openspec instructions apply --change "add-bounded-auto-translation-pipeline" --json`.
- Start from a slice spec: automatic translation must not consume raw `c_source` alone. The input must include target id, slice id, source commit, C files, function signatures, L1 evidence, build profile, fixture contract, Rust output boundary, accepted metadata differences, and non-goals.
- Emit evidence before code: `context-pack`, `type-map`, `cfg`, and `pointer-graph` must be persisted before any Rust draft is accepted.
- Treat AI as candidate generation only: AI may propose a draft or PatchPlan, but AI output is never correctness evidence and cannot bypass local compile, C oracle, Rust replay, schema-aware diff, negative diff, unsafe scan, version/cache, or OpenSpec validation.
- Parallel agents may split read-only analysis or disjoint writes only. Slice specs, public APIs, fixtures, oracle contracts, unsafe ledgers, schemas, and files under active self-healing must not be edited concurrently.

## Workflow

1. Select a target and function slice with accepted L1 native validation.
2. Normalize the slice spec and build profile, recording include paths, defines, target triple/ABI, compiler command source, preprocessing mode, tool versions, and whether clang-backed type extraction is available.
3. Generate or refresh `l3-<slice>-context-pack.json`, `l3-<slice>-type-map.json`, `l3-<slice>-cfg.json`, and `l3-<slice>-pointer-graph.json`. Newly generated pointer graphs use `schema_version=2`; when a slice has both pointer reads and pointer writes and triggers the alias-sensitive gate, `effect_graph` must record read/write effects plus a `requires_noalias` or `may_alias` edge for each alias risk.
4. Generate a Rust draft only for the supported C subset, then write `l3-<slice>-auto-translation-plan.json` and `l3-<slice>-auto-translation-events.jsonl`.
5. Generate a C oracle harness draft and Rust replay test draft from the same fixture contract. If inputs or outputs cannot be mapped, mark the run blocked.
6. Run `cargo check --message-format=json`. On failure, write `l3-<slice>-rust-check.json`, generate a PatchPlan, and run at most five bounded repair rounds by default.
7. Run Rust replay, schema-aware diff, negative diff, unsafe scan, version/cache gates, and evidence manifest gates.
8. Promote the candidate to an accepted slice only when C oracle, Rust replay, diff, unsafe, version/cache, and OpenSpec validation pass for the same source commit, fixture hash, slice spec hash, and build profile hash.

## Supported C Subset

The MVP supports only bounded, evidence-backed function slices:

- Function signatures and primitive integer/boolean-like expressions.
- Primitive declarations, assignments, and returns.
- Simple calls whose callee facts are traceable in the context pack or direct caller/callee facts.
- Structured `if`, `while`, `for`, and `return`.
- Struct-by-name, without guessing unproven layout.
- Limited pointer patterns with fixture contracts: `const T*` input pointers, buffers with explicit length companions, and out-parameter struct/POD writes.
- Fixed-fixture C oracle and Rust replay.

## Blocked Or Downgraded Constructs

When these are found, the agent should write unsupported or blocked evidence instead of claiming success:

- Missing accepted L1 native evidence.
- Missing or insufficient build profile, especially unresolved typedefs, macros, integer widths, ABI, struct layout, enum values, implicit casts, or declaration disambiguation.
- `goto`, computed goto, `switch` fallthrough, `setjmp/longjmp`, inline assembly, or multi-entry unstructured CFG.
- VLA, complex typedef chains, union bitfields, unmodeled macro side effects, or cross-thread semantics.
- Unproven alias edges, escaping pointers, or returned raw pointers with unclear ownership.
- Fixture contracts that cannot map C inputs/outputs to Rust assertions.
- Any automatic repair that would edit oracle contracts, fixture expected behavior, accepted differences, public API boundaries, source slice boundaries, or the unsafe budget.

## API And Pointer Boundaries

The translator crate should expose a small slice-level API, such as `translate_c_slice(request) -> TranslationResult`. The request must include the slice spec, build profile, and evidence context. Do not treat `translate_c_to_rust(c_source: &str)` as the safe public entrypoint.

Rust-facing public APIs must not expose raw pointers by default. Low-level IR or draft code may keep raw pointers behind internal/FFI boundaries, but public APIs should use safe wrappers, validated buffers, newtypes, or explicitly isolated internal layers. A raw pointer may cross the public boundary only when the slice contract records a reviewed exception.

Safe promotion is an auditable optimization, not a guess. Every promotion from raw pointer to safe wrapper must be written to the pointer graph and unsafe ledger with read/write effects, alias assumptions, length companions, nullability, ownership/lifetime boundaries, and covering tests. Pointer graph v2 artifacts generated by `auto_migrate.py` include `effect_graph` in cache invalidation, and cache metadata must carry `effect_graph_identity` so changed effect or alias evidence cannot reuse an old candidate.

## Unsafe Ledger Rules

- First-party non-test unsafe ratio must remain below 10%.
- Every new unsafe use must be registered with file, span, category, reason, alternative considered, covering tests, and linked evidence.
- Unsafe scan and unsafe ledger are required even when the unsafe count is zero.
- Automatic repair must not expand the unsafe budget, bypass the safe public API, delete ledger entries, or weaken tests just to compile.

## Semantic Equivalence Limits

The pipeline supports only a limited semantic-equivalence claim: a named slice, pinned source commit, fixed fixture input domain, fixed build/config profile, and the behavior fields actually checked by schema-aware diff. It does not prove:

- Full project migration.
- Automatic translation for arbitrary C99/C11.
- That a compiling Rust draft is semantically equivalent.
- Byte-for-byte flash image layout, GC/clean, sector rollover, power-loss, capacity pressure, async/multithreading, performance preservation, or behavior outside the fixture.
- That the pointer graph is a whole-program alias proof. It is context and risk-boundary evidence only. The v2 `effect_graph` proves only that the current candidate recorded its effects and alias-risk edges; it does not replace the C oracle, Rust replay, unsafe ledger, or a full alias solver.

## External Proposal: Adopted, Corrected, Deferred

References:

- `F:\agent\codex\ctorustpaper\c-to-rust-翻译器嵌入方案.md`
- `F:\agent\codex\ctorustpaper\c-to-rust-slice-自动化翻译管线方案.md`

Adopted:

- Add an independent Rust translator crate or equivalent module.
- Keep the engineering split across types, expressions, statements, control flow, pointers, and emitter.
- Adopt the new pipeline role split: `context extractor -> candidate translator -> build healer -> semantic verifier -> evidence emitter`.
- Keep the batch migration idea of selecting slices from L1 accepted catalog targets using complexity signals.
- Default to raw pointers, then apply safe promotion only when evidence supports it.
- Integrate with C oracle, Rust replay, unsafe ledger, and L3 evidence manifest.
- Use rustc JSON error stacks, PatchPlan, repair, and rerun for compile self-healing.

Corrected:

- Do not keep "small and fine-grained project" as a current project constraint. The project may grow into multiple crates, tools, and targets; what remains bounded is each slice claim and evidence boundary.
- Do not use the stronger "fully automatic C -> Rust translation" claim. This change is a bounded automatic translation pipeline that generates evidence-bound candidates.
- Do not use `tree-sitter-only` as the semantic fact source. `tree-sitter-c` can help with fast indexing or slice location; types, macro expansion, ABI, struct layout, and implicit casts must come from the build profile, compile commands, `CLANG_PATH`-driven clang AST dump JSON, WSL/Linux/CI, or explicit unsupported evidence.
- Do not hard-depend on DeepSeek or any single model provider. The AI layer must be provider-agnostic, disableable, cacheable, and auditable; the default local pipeline must run without online AI.
- Do not implement the incorrect loop-label goto strategy in the MVP. The MVP supports structured control flow only; `goto` and unstructured CFG are blocked by default. Corrode-style CFG relooper is deferred.
- Do not expose raw pointer drafts as the default Rust public API. Raw pointers belong behind low-level draft/internal/FFI boundaries unless a reviewed exception is recorded.
- Do not treat Rust compilation, AI suggestions, or translator output as correctness proof.

Deferred:

- General C99/C11 coverage.
- Full Corrode-style CFG relooper.
- Macro solving, complex typedef chains, union bitfields, VLA, inline assembly, and `setjmp/longjmp`.
- Differential fuzzing expansion, synchronized code-test translation, and pass-rate targets for large-scale cross-project batch automation.
- Async or multithreaded runtime optimization.

## Operational Commands

Run these commands from repository root `C:\Users\Administrator\Documents\c-to-rust-flashdb`. Some commands are expected interfaces for this change; until schema, translator, and `auto_migrate` work lands, they define the agent contract rather than current availability.

### OpenSpec Status And Tasks

```powershell
openspec status --change "add-bounded-auto-translation-pipeline" --json
openspec instructions apply --change "add-bounded-auto-translation-pipeline" --json
openspec validate add-bounded-auto-translation-pipeline --strict
openspec validate --all
```

### L1 Input Selection

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\validate-c-project-catalog.ps1
Get-Content .\validation\evidence\l1-native-summary.json -Raw | ConvertFrom-Json
Get-Content .\validation\evidence\l1-low-cost-remediation-summary.json -Raw | ConvertFrom-Json
```

Agents may select only targets with accepted L1 native evidence. If accepted L1 evidence is missing, the run must write a blocked reason before generating Rust code.

### Auto Migration

Expected interface:

```powershell
python .\validation\tools\auto_migrate.py `
  --slice-spec .\validation\evidence\libuv\l3-ip4-addr-slice-spec.json `
  --evidence-root .\validation\evidence\libuv `
  --max-repair-rounds 3
```

This command should generate context pack, type map, CFG, pointer graph, Rust draft provenance, translation events, oracle/replay drafts, rust check, PatchPlan/blocked repairs, and evidence manifest inputs.

### C Oracle

The existing libuv L2 oracle generator must run under WSL/Linux because the script uses `/mnt/c` paths:

```bash
python3 validation/l2_slices/tools/generate_oracles.py
```

Expected slice-spec-driven oracle command:

```powershell
python .\validation\tools\auto_migrate.py `
  --slice-spec .\validation\evidence\libuv\l3-ip4-addr-slice-spec.json `
  --only oracle
```

A host without a C toolchain may record `SKIPPED_LOCAL_NO_C_TOOLCHAIN`, but that is not a semantic pass. Passing semantics requires `C_ORACLE_GENERATED` or equivalent CI/WSL/Linux evidence.

### Rust Replay And L2/L3 Reports

```powershell
Push-Location .\validation\l2_slices
cargo test
cargo run --bin emit_reports
Pop-Location
```

FlashDB CLI replay, unsafe scan, and evidence search:

```powershell
Push-Location .\flashDB_rust
cargo test
cargo run -- unsafe-scan
cargo run -- evidence-search --evidence-dir ..\validation\evidence --query "C_ORACLE_GENERATED" --limit 20 --report ..\validation\evidence\flashdb\evidence-search-report.json
Pop-Location
```

### Compile Self-Healing

Rust draft compile check:

```powershell
Push-Location .\flashDB_rust
cargo check --message-format=json *> ..\validation\evidence\flashdb\l3-<slice>-rust-check.raw.jsonl
Pop-Location
```

Existing FlashDB self-healing tool:

```powershell
python .\validation\tools\flashdb_l3_self_healing.py `
  --evidence-dir .\validation\evidence\flashdb `
  --slice-id <slice>
```

Expected auto-translation self-healing through `auto_migrate.py`:

```powershell
python .\validation\tools\auto_migrate.py `
  --slice-spec .\validation\evidence\libuv\l3-ip4-addr-slice-spec.json `
  --only self-heal `
  --max-repair-rounds 3
```

### Evidence Search

```powershell
Push-Location .\flashDB_rust
cargo run -- evidence-search --evidence-dir ..\validation\evidence --query "blocked" --limit 50
cargo run -- evidence-search --evidence-dir ..\validation\evidence --query "unsafe_ratio" --limit 50
cargo run -- evidence-search --evidence-dir ..\validation\evidence --query "l3-ip4-addr" --limit 50 --report ..\validation\evidence\flashdb\evidence-search-report.json
Pop-Location
```

### Final Verification

For a documentation or pipeline change, run at least:

```powershell
openspec validate add-bounded-auto-translation-pipeline --strict
openspec validate --all
git diff --check
```

After translator, `auto_migrate`, and MVP slices are implemented, also run:

```powershell
Push-Location .\crates\c2r-translator
cargo fmt -- --check
cargo test
Pop-Location

Push-Location .\validation\l2_slices
cargo fmt -- --check
cargo test
cargo run --bin emit_reports
Pop-Location

Push-Location .\flashDB_rust
cargo fmt -- --check
cargo test
cargo run -- unsafe-scan
Pop-Location
```

## Agent Completion Criteria

An agent may report an auto-translated slice complete only when all evidence is present and fresh:

- Slice spec, build profile, cache metadata, and version manifest bind to the same inputs.
- Validation profile binds the `profile_id`, path, and SHA256 of `config/competition-env/environment.json`, and cache metadata carries the same `competition_environment_identity`.
- Context pack, type map, CFG, and pointer graph were generated before the Rust draft.
- Unsupported constructs or blocked repairs are explicitly recorded.
- C oracle, Rust replay, schema-aware diff, negative diff, rust check, unsafe scan, unsafe ledger, and final verification are referenced from the L3 evidence manifest.
- OpenSpec change validation and `git diff --check` pass.
