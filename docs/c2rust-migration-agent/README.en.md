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
- Core translation architecture and evidence status: see `core-translation-architecture.md` / `core-translation-architecture.en.md`; typed IR candidate generation is currently a `GenericTypedIr` / `Unsupported` two-route model, the generic emitter now covers local fixed-length integer array reads/writes plus narrow scalar integer binary `+`, `-`, `*`, `/`, `%`, `&`, `^`, `>>` and signed unary `-value` candidate generation, new evidence can bind `candidate_generation.typed_ir`, clang-lowered direct calls also flow into `call_expressions` / `direct_call_edges` evidence, external direct-callee call-site/signature/source binding now has default validator consistency checks, but this only proves evidence-chain consistency, not external-callee semantic acceptance; alias risk floors still override `GenericTypedIr` route signals, and semantic acceptance remains owned by validation gates.
- Core translation boundary: the signed unary minus support above is candidate generation only; unsigned/wrapping negation, floating-point negation, special literal/min-value edges, and full C unary semantics still fail closed.

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
