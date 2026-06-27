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
- Core translation architecture and evidence status: see `core-translation-architecture.md` / `core-translation-architecture.en.md`; typed IR candidate generation is currently a `GenericTypedIr` / `Unsupported` two-route model, the generic emitter now covers local fixed-length integer array reads/writes, narrow scalar integer binary `+`, `-`, `*`, `/`, `%`, `&`, `|`, `^`, `<<`, `>>`, signed unary `-value`, clang-lowered simple scalar compound assignment family `+=`, `-=`, `*=`, `/=`, `%=`, `&=`, `|=`, `^=`, `<<=`, `>>=` desugaring, comparison expression candidate generation in conditions plus narrow value-position C `int` 0/1 result materialization, logical not `!expr` candidate generation in conditions plus narrow value-position C `int` 0/1 result materialization, short-circuit `&&` / `||` candidate generation in condition positions, readonly integer pointer-parameter null presence checks such as `values != NULL -> values: Option<&[i32]>` plus `.is_some()`, readonly direct deref reads such as `return *p -> return p[0usize]`, and bounded readonly pointer offset-deref reads such as `return *(p+i) -> return p[i as usize]`; new evidence can bind `candidate_generation.typed_ir`, clang-lowered direct calls also flow into `call_expressions` / `direct_call_edges` evidence; scalar-only `GenericTypedIr` candidates whose `candidate_route.token_cost=0` now act as an L0 route signal, non-scalar pointer surfaces remain at least L1, and alias risk floors still take priority. External direct-callee call-site/signature/source binding has default validator consistency checks, but this only proves evidence-chain consistency, not external-callee semantic acceptance; semantic acceptance remains owned by validation gates.
- Core translation boundary: the bitwise OR `|` / left shift `<<`, signed unary minus, simple scalar compound assignment family, comparison expression, logical-not, condition-position short-circuit `&&` / `||`, pointer-null presence, readonly direct deref read, and bounded readonly pointer offset-deref read support above are candidate generation only; bitwise OR `|` / left shift `<<` currently cover only narrow scalar-integer candidate generation and do not represent full C bitwise or shift semantics. Compound assignment currently accepts only simple scalar variable targets and requires clang `type`, `computeLHSType`, and `computeResultType` to match the target type before desugaring to `x = x op rhs`. Comparison currently covers conditions, narrow value-position C `int` 0/1 materialization such as `return x > 0`, assignment RHS, and declaration initializer, plus comparison operands with integral casts whose source and target are supported integer types and whose post-cast operand types match exactly, readonly direct deref read operands, and bounded readonly pointer offset-deref read operands. Pointer-null presence is limited to readonly integer pointer parameters used only in `== NULL` / `!= NULL` checks, emitted as `Option<&[T]>` plus `.is_none()` / `.is_some()`. Logical not covers integer zero checks, readonly direct deref read operands, bounded readonly pointer offset-deref read operands, and narrow value-position C `int` 0/1 materialization. Short-circuit support currently covers only `&&` / `||` in `if` / `while` conditions, with each operand recursively limited to the existing condition-expression subset. Arbitrary pointer arithmetic beyond the bounded readonly `*(p+i)` read, arbitrary pointer comparison, floating-point comparison, mixed-width/unsigned conversions that are not aligned by an explicit integer cast, non-simple-variable compound targets, promotion/truncation cases where compute types differ from the target type, call/inc/dec/side-effect operands, pointer truthiness, pointer null checks followed by pointer dereference/index use, floating-point truthiness, unsupported types, value-position short-circuit logic, full usual scalar conversions, invalid shift counts, signed shift/overflow UB parity, unsigned/wrapping negation, floating-point negation, special literal/min-value edges, and semantic acceptance still fail closed.

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
