## Context

This change designs a C-to-Rust migration Agent for OpenCode, Codex, and other agent runtimes. The first target is FlashDB, cloned from `https://gitcode.com/xwxf/FlashDB.git`, with Rust output under `flashDB_rust`. The design must also generalize to larger C projects with deeper cross-file dependencies.

本设计的核心约束是：省 token、必要时才调用 AI、安全、速度快、小而精、OpenSpec 分阶段推进、Rust unsafe 低于 10%、Rust 测试覆盖主干路径、编译和语义验证都可复现。

Local references and verified baseline information:

- C2Rust reference tree: `F:\agent\c2rust-master`.
- C2Rust workspace package version observed locally: `0.22.1`.
- C2Rust toolchain file observed locally: `nightly-2022-11-03`.
- OpenSpec CLI version installed for this workspace: `1.4.1`.
- FlashDB GitCode HEAD observed on 2026-06-23: `93d175549da579b8abac07bd175ce4c3f9dde829`.

C2Rust is useful as a C99 migration starting point, ABI/layout reference, and oracle/cross-check source. It is not selected as the final output style because it intentionally produces Rust that closely mirrors C and uses unsafe extensively.

## Goals / Non-Goals

**Goals:**

- Define a bilingual Chinese/English OpenSpec-governed Agent design.
- Define an OpenCode/Codex-compatible orchestration model for multiple bounded agents.
- Define a versioned build baseline and C2Rust baseline/oracle workflow.
- Define a local-first cross-file context store that prevents module-call relationship breakage during single-point incremental refactors.
- Define a skeleton-first migration workflow that creates `flashDB_rust` as a Rust library crate with CLI and optional FFI harness.
- Define a rustc error-stack compile/self-healing loop with precise minimal patch plans.
- Define machine-verifiable semantic equivalence gates for FlashDB main paths.
- Define unsafe accounting and safe API gates with first-party unsafe below 10%.

**Non-Goals:**

- This change does not implement the migration Agent code yet.
- This change does not clone or migrate FlashDB yet.
- This change does not promise full automatic safe Rust conversion for arbitrary C projects.
- This change does not use raw C2Rust output as final deliverable.
- This change does not migrate full TSDB, hardware ports, or complex file backends in the first milestone.

## Decisions

### Decision 1: OpenSpec staged workflow

Use OpenSpec as the top-level governance mechanism. Each future migration step MUST be represented as proposal, specs, design, and tasks before implementation. This keeps the workflow auditable and avoids uncontrolled agent edits.

Alternative considered: implement directly from the chat request. Rejected because the target includes cross-file refactoring, automatic repair, semantic equivalence, version pinning, and safety gates that need durable contracts.

### Decision 2: C2Rust as baseline/oracle only

Use `F:\agent\c2rust-master` and generated C2Rust output to capture ABI, layouts, function boundaries, and executable oracle behavior. Do not ship the C2Rust output as the final `flashDB_rust` code.

Alternative considered: directly deliver C2Rust output and reduce unsafe later. Rejected because the requirement is safe, small, maintainable Rust with unsafe below 10% and Rust-native tests.

### Decision 3: Build-aware skeleton-first migration

Create a compilable Rust crate skeleton before translating function bodies. The skeleton reserves modules such as `config`, `types`, `flash`, `port`, `format`, `kvdb`, `tsdb`, `ffi`, and `cli`. Function bodies may start as placeholders during skeleton creation, but placeholders are not allowed in completed migration tasks.

Alternative considered: translate leaf functions first without a project skeleton. Rejected because cross-module API drift becomes difficult to control.

### Decision 4: SQLite/JSONL context store

Use SQLite plus JSONL for the cross-file context model. Store files, symbols, call edges, type layouts, macro/cfg facts, pointer facts, Rust items, error events, patch events, test traces, and unsafe ledger entries. Every fact records source, version, file hash, span, confidence, and source commit.

Alternative considered: use Neo4j or a vector database immediately. Rejected for the first milestone because FlashDB is small enough for SQLite/JSONL, and local structured facts are cheaper, faster, and easier to audit.

### Decision 5: Token-bounded context packs

Every AI call receives a minimal `ContextPack`: target item, owning module, direct callers/callees, public type definitions, macro/cfg facts, pointer facts, related tests, current diff, and structured rustc errors. Default depth is 1-hop. Expand to 2-hop only for trait, lifetime, or cross-module signature failures.

Alternative considered: include full files or full repository context. Rejected because it breaks the token budget and increases unrelated edits.

### Decision 6: rustc JSON error-stack self-healing

The compile loop is:

`cargo check --message-format=json -> error triage -> PatchPlan -> apply minimal patch -> rerun`

`CompileHealAgent` classifies errors such as `E0308`, `E0499`, `E0502`, `E0382`, `E0277`, `E0599`, missing imports, cfg/feature errors, and lifetime errors. It emits a minimal `PatchPlan` with affected files, spans, reason, expected error delta, and risk. Rules run before AI; AI is reserved for low-certainty ownership, lifetime, signature, and semantic-difference cases.

Alternative considered: ask AI to fix the whole build log. Rejected because it wastes tokens and tends to create broad, unsafe patches.

### Decision 7: Semantic equivalence by machine evidence

Semantic equivalence MUST be verified by C oracle or C2Rust baseline differential testing, golden flash images, Rust unit/integration tests, property tests, fuzz tests, and regression counterexamples. LLM judgment is not evidence.

Alternative considered: rely on translated tests and compiler success. Rejected because FlashDB is a persistent storage library where behavior includes flash image bytes, GC/reboot state, error codes, and recovery semantics.

### Decision 8: Unsafe budget and safe API

First-party non-test Rust unsafe MUST stay below 10%. Safe public Rust API MUST NOT expose raw pointers. Unsafe is only permitted in whitelisted zones: `ffi`, flash raw read/write, persistent layout conversion, required `#[repr(C)]` interop, and evidence-approved callback/union/allocator boundaries.

Alternative considered: count only `unsafe fn` or defer unsafe measurement. Rejected because unsafe may be hidden inside safe functions and must be tracked by behavior and location.

### Decision 9: First milestone scope

The first implementation milestone SHOULD target a host-verifiable FlashDB subset: `FlashDevice`, memory backend for deterministic tests, host file-mode backend for persistence smoke tests, `Error`, `Result<T>`, `FlashAddr`, `SectorOffset`, CRC/alignment/header/blob encoding, KVDB `init/set/get/delete/iterate/gc/reopen`, and basic TSDB `append/query/count/status`.

Alternative considered: migrate all FlashDB modules immediately. Rejected because FAL, hardware ports, RTOS/Zephyr integrations, and complete configuration matrices increase risk before the Agent framework is validated.

### Decision 10: Cache policy

Use caching at two different layers with different rules.

Agent-side engineering caches SHOULD be used aggressively for build traces, parsed AST summaries, context facts, C2Rust baseline artifacts, rustc error classification, test results, coverage results, fuzz corpus metadata, and AI response candidates. These caches MUST be content-addressed by source commit, file hash, feature matrix, tool version, context schema version, prompt/model metadata when AI is involved, and command arguments. Cached AI output is never a truth source; it is only a candidate that must pass the same compile and equivalence gates.

`flashDB_rust` runtime caches MUST be conservative, bounded, observable, and disable-able. In the first milestone, runtime caching MAY include read-through metadata/block caches for host memory/file backends, but write-back caching MUST NOT be introduced unless flush, sync, erase, reopen, and crash-recovery semantics are proven equivalent to the C oracle. Cache invalidation MUST occur on write, erase, GC, format, reopen, feature/config changes, and backend replacement.

Alternative considered: add async/multithreaded write-back caches early for performance. Rejected because FlashDB correctness depends on persistent state, write ordering, erased values, GC, and reopen behavior; premature caching makes equivalence and failure recovery harder to prove.

## Risks / Trade-offs

- [Risk] C2Rust baseline may not build on native Windows. → Mitigation: isolate C2Rust execution in WSL/Linux when needed and record environment versions.
- [Risk] SQLite/JSONL context may become insufficient for future huge projects. → Mitigation: version the context schema and allow later graph database adapters without changing the Agent contract.
- [Risk] Stale Agent caches may reuse facts from a different source commit, macro matrix, or toolchain. → Mitigation: content-address all caches and invalidate on commit, file hash, schema, feature, command, or tool-version changes.
- [Risk] Runtime caches may hide persistence bugs. → Mitigation: run cache-disabled and cache-enabled differential tests, compare flash image bytes, and require reopen/flush/GC tests.
- [Risk] AI may simplify code to pass tests while changing semantics. → Mitigation: require C/Rust differential testing, golden flash images, and regression counterexamples.
- [Risk] Borrow-checker repairs may reintroduce raw pointers. → Mitigation: forbid unregistered unsafe and require unsafe ledger entries with evidence.
- [Risk] Generated tests may cover only happy paths. → Mitigation: require boundary, error, GC, reopen, corrupted image, property, and fuzz cases.
- [Risk] Performance may degrade due to safe wrappers. → Mitigation: include Criterion smoke tests and scenario counters for flash read/write/erase operations.
- [Risk] Public API changes may cascade across modules. → Mitigation: freeze module boundaries, use adapters, and require `SignatureMigrationPlanner` impact sets for cross-module signature changes.

## Migration Plan

1. Create this design change and validate OpenSpec artifacts.
2. Implement a future `capture-build-and-scope` change to clone FlashDB, pin source commit, capture build commands, and record macro/feature matrix.
3. Implement a future `build-rust-skeleton` change to create `flashDB_rust` with library, CLI, and FFI harness.
4. Implement context indexing and context pack generation.
5. Implement C2Rust baseline/oracle generation and C/Rust differential harness.
6. Implement the host-verifiable FlashDB subset with memory backend, file-mode persistence smoke tests, KVDB core paths, and basic TSDB paths.
7. Add cache policy implementation for Agent artifact caches and optional runtime cache feature gates.
8. Add compile self-healing, unsafe ledger, generated Rust tests, property/fuzz hooks, and performance smoke gates.
9. Archive completed changes only after validation evidence is recorded.

Rollback strategy: each implementation task MUST keep a last-known-good checkpoint. Failed migration slices are rolled back to the previous compile-passing state and logged as unsafe or migration debt instead of allowing partial breakage to spread.

## Open Questions

- Whether the first implementation should build the Agent as a Rust CLI, a Codex/OpenCode skill pack, or both in one workspace.
- Whether C2Rust execution should be mandatory through WSL/Linux for this Windows host.
- Which exact coverage threshold should gate `flashDB_rust` before the first real migration task: 80% migrated-module coverage or stricter path-specific coverage.
