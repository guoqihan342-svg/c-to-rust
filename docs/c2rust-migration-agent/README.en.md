# C2Rust Migration Agent

This folder contains the executable design contract for the OpenSpec-governed C-to-Rust migration Agent. The Chinese mirror is `README.md`.

## Current Status

- OpenSpec change: `design-c2rust-migration-agent`
- First target: FlashDB
- Source clone: `sources/FlashDB`
- Source commit: `93d175549da579b8abac07bd175ce4c3f9dde829`
- Rust output project name: `flashDB_rust`
- C2Rust role: baseline/oracle only, not final deliverable
- Safety target: first-party non-test unsafe below 10%
- Fixed-width integer types: the clang frontend currently lowers `int8_t`, `int16_t`, `int32_t`, `int64_t`, `uint8_t`, `uint16_t`, `uint32_t`, and `uint64_t` into the corresponding typed IR integer types. This slice newly adds the signed fixed-width aliases plus `uint16_t` / `uint64_t`. Raw target-dependent spellings such as `signed char` / `short` / `long long`, plain `char`, plain `long`, complete usual scalar conversions, and semantic acceptance still fail closed.
- Multi-declaration expansion: `DeclStmt` nodes in ordinary compound bodies can now expand multiple simple `VarDecl` children into consecutive typed IR `Decl` statements in source order, for example `int a = 1, b = 2;`. Multi-declaration `ForStmt` init, unsupported types/initializers, VLAs, duplicate symbols, and semantic acceptance still fail closed.
- Uninitialized scalar local declarations: ordinary scalar locals such as `int tmp; tmp = 7; return tmp;` can now emit as `let mut tmp: i32; tmp = 7i32; return tmp;` through the typed IR emitter. Reads before assignment, first assignments that read the same variable, assignments only inside loops or one-sided branches, array/pointer/record/function declarations, and semantic acceptance still fail closed.
- Core translation architecture and evidence status: see `core-translation-architecture.md` / `core-translation-architecture.en.md`; typed IR candidate generation is currently a `GenericTypedIr` / `Unsupported` two-route model, the generic emitter now covers local fixed-length integer array reads/writes, narrow scalar integer binary `+`, `-`, `*`, `/`, `%`, `&`, `|`, `^`, `<<`, `>>`, signed unary `-value`, clang-lowered simple scalar compound assignment family `+=`, `-=`, `*=`, `/=`, `%=`, `&=`, `|=`, `^=`, `<<=`, `>>=` desugaring including narrow clang-proven integer promotion/truncation for simple scalar variable targets, clang-preserved value-position integer implicit casts in declaration initializers, assignment RHS, and return values, comparison expression candidate generation in conditions plus narrow value-position C `int` 0/1 result materialization, logical not `!expr` candidate generation in conditions plus narrow value-position C `int` 0/1 result materialization, short-circuit `&&` / `||` candidate generation in conditions plus narrow value-position C `int` 0/1 materialization, pure integer value-position `ConditionalOperator` / `?:` emission for return values, assignment RHS, and declaration initializers, narrow scoped `ForStmt` emission for simple scalar init/condition/step/body, readonly integer pointer-parameter null presence checks such as `values != NULL -> values: Option<&[i32]>` plus `.is_some()`, readonly direct deref reads such as `return *p -> return p[0usize]`, and bounded readonly pointer offset-deref reads such as `return *(p+i) -> return p[i as usize]`; new evidence can bind `candidate_generation.typed_ir`, clang-lowered direct calls also flow into `call_expressions` / `direct_call_edges` evidence; scalar-only `GenericTypedIr` candidates whose `candidate_route.token_cost=0` now act as an L0 route signal, non-scalar pointer surfaces remain at least L1, and alias risk floors still take priority. External direct-callee call-site/signature/source binding has default validator consistency checks, but this only proves evidence-chain consistency, not external-callee semantic acceptance; semantic acceptance remains owned by validation gates.
- Core translation boundary: the bitwise OR `|` / left shift `<<`, signed unary minus, simple scalar compound assignment family, value-position integer implicit cast preservation, comparison expression, logical-not, condition/value-position short-circuit `&&` / `||`, pure integer value-position `ConditionalOperator` / `?:`, narrow scoped `ForStmt`, pointer-null presence, readonly direct deref read, and bounded readonly pointer offset-deref read support above are candidate generation only; bitwise OR `|` / left shift `<<` currently cover only narrow scalar-integer candidate generation and do not represent full C bitwise or shift semantics. Compound assignment currently accepts only simple scalar variable targets; clang target/result types must match, compute lhs/result types must match, and all involved types must be supported integers. If the compute type differs from the target type, lowering emits explicit casts before assigning back to the target type. Value-position implicit cast preservation currently covers only clang `IntegralCast` / `IntegralPromotion` nodes in declaration initializers, assignment RHS, and return values when the typed IR emitter can prove supported integer source and target types; function-pointer decay, pointer/float casts, hidden side-effect conversions, and full usual scalar conversions remain outside this subset. Comparison currently covers conditions, narrow value-position C `int` 0/1 materialization such as `return x > 0`, assignment RHS, and declaration initializer, plus comparison operands with integral casts whose source and target are supported integer types and whose post-cast operand types match exactly, readonly direct deref read operands, and bounded readonly pointer offset-deref read operands. Pointer-null presence is limited to readonly integer pointer parameters used only in `== NULL` / `!= NULL` checks, emitted as `Option<&[T]>` plus `.is_none()` / `.is_some()`. Logical not covers integer zero checks, readonly direct deref read operands, bounded readonly offset-deref read operands, and narrow value-position C `int` 0/1 materialization. Short-circuit support covers `&&` / `||` in `if` / `while` conditions plus narrow value-position C `int` 0/1 materialization in return values, assignment RHS, and declaration initializers; each operand recursively uses the existing condition-expression subset and preserves Rust `&&` / `||` lazy evaluation. Conditional `?:` support currently covers only pure integer value positions and rejects condition-position `?:`, expression-statement `?:`, GNU omitted-middle `a ?: b`, branch side effects, pointer/floating/aggregate results, and unmodeled usual scalar conversions. Scoped `ForStmt` currently covers only simple scalar init, condition, assignment/compound-assignment/postfix inc-dec step, and the existing statement body subset, while rejecting `continue` / `break` / `goto` / `switch`, condition variable slots, empty condition/step, calls/inc/dec/side effects in the condition, complex init/step, and prefix inc-dec step. Arbitrary pointer arithmetic beyond the bounded readonly `*(p+i)` read, arbitrary pointer comparison, floating-point comparison, mixed-width/unsigned conversions that are not aligned by clang-preserved or explicit integer casts, non-simple-variable compound targets, promotion/truncation cases not proven by the compound-assignment guard above, call/inc/dec/side-effect operands, pointer truthiness, pointer null checks followed by pointer dereference/index use, floating-point truthiness, unsupported types, full usual scalar conversions, invalid shift counts, signed shift/overflow UB parity, unsigned/wrapping negation, floating-point negation, special literal/min-value edges, full C for-loop control-flow semantics, and semantic acceptance still fail closed.

## Bilingual Documentation Convention

- New user-facing or Agent-facing docs use a Chinese primary `.md` file and an English mirror `.en.md` by default.
- When an existing document receives more than a small edit, keep the matching English mirror synchronized.
- OpenSpec parser anchors must remain in English, including `## ADDED Requirements`, `### Requirement:`, `#### Scenario:`, `WHEN`, and `THEN`.
- Some older files in this directory still use a mixed "Chinese note + English summary" format. When touched, they should be split into full bilingual versions under this convention.

## Document Map

- `README.md` / `README.en.md`: directory index, current status, and bilingual documentation convention.
- `baseline-record.json`: machine-readable version, hash, source, and tool availability record.
- `baseline-and-versioning.md`: version policy for Agent, schema, PatchPlan, and `flashDB_rust`.
- `build-and-c2rust-baseline.md`: FlashDB build capture, C2Rust baseline, and C oracle fallback.
- `agent-contract.md`: OpenCode/Codex runtime contract, phases, IO, subagents, AI policy, async/thread policy.
- `context-store-and-self-healing.md`: SQLite/JSONL schema, ContextPack, impact sets, rustc repair loop, PatchPlan.
- `core-translation-architecture.md` / `core-translation-architecture.en.md`: current `clang_frontend -> typed IR + globals -> translation_route -> validation` architecture, core code map, two-route typed IR candidate model, candidate_generation evidence schema, clang-lowered direct-call evidence, external direct-callee binding validator, and typed IR legacy cleanup boundary.
- `flashdb-rust-skeleton-and-milestone.md`: `flashDB_rust` crate layout and first host-verifiable milestone.
- `testing-unsafe-cache-and-milestone.md`: tests, differential oracle, unsafe budget, cache policy, performance gates.
- `bounded-auto-translation-pipeline.md` / `bounded-auto-translation-pipeline.en.md`: bounded automatic translation pipeline Agent guide.

## Quick Use

```bash
openspec status --change "design-c2rust-migration-agent" --json
openspec instructions apply --change "design-c2rust-migration-agent" --json
```

Then run the Agent phase, for example:

```bash
c2rust-migrator --phase index --change design-c2rust-migration-agent --input request.json
```

## Operating Principles

- Use OpenSpec before implementation.
- Keep context local-first and token-bounded.
- Spawn multiple subagents for read-only or disjoint work.
- Use deterministic rules before AI.
- Treat AI output as a candidate, never as evidence.
- Keep C2Rust output as baseline/oracle only.
- Prefer small, compile-passing slices.
- Prove behavior with Rust tests and C/Rust differential evidence.
- Track unsafe and keep it below 10%.
- Add caching only with explicit invalidation and equivalence gates.

## Native Windows Tool Note

This host now has native LLVM `clang` at the default path `C:/Program Files/LLVM/bin/clang.exe`, and this slice uses it for real clang AST smoke tests. PATH may still lack native `c2rust`, `cmake`, `bear`, `intercept-build`, `cargo-nextest`, `cargo-llvm-cov`, `cargo-fuzz`, and `cargo-geiger`. The design remains valid, but those gates need WSL/Linux or later tool installation before full migration verification can claim completion.
