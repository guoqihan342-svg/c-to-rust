## Why

需要设计一个可交给 OpenCode、Codex 或其他智能体执行的 C-to-Rust 迁移 Agent，用 OpenSpec 分阶段约束迁移过程，避免把整个 C 仓库一次性交给 LLM 导致 token 失控、跨文件关系断裂、语义等价不可验证。

We need a C-to-Rust migration Agent that can be used by OpenCode, Codex, or other agents. The process must be governed step by step with OpenSpec so translation, refactoring, repair, testing, and unsafe reduction remain traceable and reproducible.

FlashDB is the first target, but the design must generalize to larger C projects with deeper cross-file dependencies. The migrated output must use `flashDB_rust`, build as Rust code with a runnable binary, use Rust tests, keep first-party unsafe below 10%, and prove semantic equivalence with machine-verifiable evidence.

## What Changes

- Introduce a staged C-to-Rust migration Agent design for OpenCode/Codex-compatible execution.
- Define `flashDB_rust` as the first migrated Rust project output, with a library-first architecture plus CLI and optional FFI harness.
- Use C2Rust only as a baseline/oracle and reference implementation source, not as the final delivered Rust code.
- Add a local-first cross-file context model using SQLite/JSONL facts for symbols, calls, macros, type layouts, pointer facts, rustc errors, patches, tests, and unsafe ledger entries.
- Define a build-aware, skeleton-first workflow that creates a compilable Rust crate before function-body migration.
- Define a compile/self-healing loop driven by structured rustc error stacks and minimal patch plans.
- Define semantic equivalence gates based on C oracle/C2Rust baseline differential testing, golden flash images, Rust unit/integration tests, property tests, fuzzing, and regression counterexamples.
- Define unsafe budget accounting and safe API rules, with first-party unsafe kept below 10%.
- Define cache policy for Agent-side artifact caching and `flashDB_rust` runtime caching, including invalidation, determinism, and equivalence gates.
- Define versioning rules for the Agent, context schema, toolchain, FlashDB source baseline, generated artifacts, and output crate.
- Support multiple read-only or disjoint-write subagents for context gathering, migration, repair, verification, and review while avoiding shared mutable-state conflicts.

## Capabilities

### New Capabilities

- `agent-orchestration-interface`: Covers how OpenCode, Codex, and other agents invoke the migration workflow, spawn bounded subagents, and consume OpenSpec tasks.
- `build-and-version-baseline`: Covers cloning FlashDB, capturing exact source/toolchain versions, generating `compile_commands.json`, and producing C2Rust baseline/oracle artifacts.
- `cross-file-context-management`: Covers SQLite/JSONL context storage, 1-hop/2-hop context packs, symbol/call/type/macro/pointer facts, and token-bounded AI context.
- `skeleton-first-migration`: Covers generating the `flashDB_rust` crate skeleton, Rust-native safe API, CLI, FFI harness, module boundaries, and incremental migration order.
- `compile-self-healing`: Covers structured rustc error-stack parsing, error classification, minimal patch plans, retry limits, rollback records, and API update repair.
- `semantic-equivalence-verification`: Covers Rust tests, C/Rust differential tests, golden flash images, property/fuzz tests, performance smoke tests, and generated main-path coverage.
- `unsafe-budget-and-safe-api`: Covers unsafe accounting, whitelist policy, safe public API rules, unsafe reduction gates, and audit evidence.
- `cache-policy-and-performance`: Covers Agent-side artifact caching, runtime cache boundaries, cache invalidation, deterministic verification, memory budgets, and performance counters.

### Modified Capabilities

- None.

## Impact

- Adds OpenSpec change artifacts under `openspec/changes/design-c2rust-migration-agent/`.
- Establishes a bilingual Chinese/English design contract for future implementation.
- Affects future repository layout by reserving `flashDB_rust` as the migrated Rust output project name.
- Depends on local tools and references:
  - `F:\agent\c2rust-master` as the C2Rust reference tree.
  - OpenSpec CLI `1.4.1` for staged workflow.
  - Rust toolchain for generated Rust projects.
  - FlashDB source at `https://gitcode.com/xwxf/FlashDB`.
- Introduces version-sensitive records for source commit, Agent version, context schema version, Rust/C2Rust/OpenSpec toolchain versions, test seeds, and generated baseline artifacts.
- Future implementation will create Rust code, generated tests, local context databases, and verification reports, but this change is limited to designing the Agent and implementation plan.
