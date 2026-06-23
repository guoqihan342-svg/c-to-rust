# C2Rust Migration Agent

中文：这里是 `design-c2rust-migration-agent` 的可执行设计文档集合，供 OpenCode、Codex 或其他智能体按 OpenSpec 分阶段执行 C 到 Rust 迁移。

English: this folder contains the executable design contract for the OpenSpec-governed C-to-Rust migration Agent.

## Current Status

- OpenSpec change: `design-c2rust-migration-agent`
- First target: FlashDB
- Source clone: `sources/FlashDB`
- Source commit: `93d175549da579b8abac07bd175ce4c3f9dde829`
- Rust output project name: `flashDB_rust`
- C2Rust role: baseline/oracle only, not final deliverable
- Safety target: first-party non-test unsafe below 10%

## Document Map

- `baseline-record.json`: machine-readable version, hash, source, and tool availability record.
- `baseline-and-versioning.md`: version policy for Agent, schema, PatchPlan, and `flashDB_rust`.
- `build-and-c2rust-baseline.md`: FlashDB build capture, C2Rust baseline, and C oracle fallback.
- `agent-contract.md`: OpenCode/Codex runtime contract, phases, IO, subagents, AI policy, async/thread policy.
- `context-store-and-self-healing.md`: SQLite/JSONL schema, ContextPack, impact sets, rustc repair loop, PatchPlan.
- `flashdb-rust-skeleton-and-milestone.md`: `flashDB_rust` crate layout and first host-verifiable milestone.
- `testing-unsafe-cache-and-milestone.md`: tests, differential oracle, unsafe budget, cache policy, performance gates.

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

This host currently lacks native `c2rust`, `clang`, `cmake`, `bear`, `intercept-build`, `cargo-nextest`, `cargo-llvm-cov`, `cargo-fuzz`, and `cargo-geiger` on PATH. The design remains valid, but those gates need WSL/Linux or later tool installation before real migration verification can claim completion.
