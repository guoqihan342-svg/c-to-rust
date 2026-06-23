## 1. Baseline and Version Locking

- [x] 1.1 Record the OpenSpec version, Agent draft version, context schema version, Rust toolchain, Git version, and test tool versions in a durable baseline file.
- [x] 1.2 Clone FlashDB with `git clone https://gitcode.com/xwxf/FlashDB.git` and record the exact source commit used for the migration run.
- [x] 1.3 Inspect `F:\agent\c2rust-master` and record C2Rust package version, toolchain file, critical file hashes, and execution environment assumptions.
- [x] 1.4 Define the version bump policy for Agent SemVer, context schema, PatchPlan contract, and `flashDB_rust` crate versions.

## 2. OpenCode/Codex Agent Contract

- [x] 2.1 Define the Agent entrypoints for propose, plan, index, skeleton, migrate, repair, verify, audit, and archive phases.
- [x] 2.2 Define the subagent policy for read-only analysis, disjoint-write implementation, verification, and review.
- [x] 2.3 Define the runtime input/output contract for OpenCode, Codex, and other agent runtimes.
- [x] 2.4 Add bilingual Chinese/English usage documentation while preserving OpenSpec parser anchors in English.

## 3. Build Capture and C2Rust Baseline

- [x] 3.1 Capture FlashDB build commands and produce or document the expected `compile_commands.json` workflow.
- [x] 3.2 Record the FlashDB macro and feature matrix, including KVDB, TSDB, file mode, and write granularity options.
- [x] 3.3 Generate a C2Rust baseline when the environment supports it, preferably in WSL/Linux if Windows is not reproducible.
- [x] 3.4 Store C2Rust output hashes, generation command, warnings, skipped functions, and fallback reason when generation fails.
- [x] 3.5 Define the C oracle fallback when C2Rust baseline generation is unavailable.

## 4. Cross-File Context Store

- [x] 4.1 Design the SQLite schema for files, symbols, call edges, type layouts, macro/cfg facts, pointer facts, Rust items, error events, patch events, test traces, and unsafe ledger entries.
- [x] 4.2 Design the JSONL append-only event format for operations, patches, tests, counterexamples, and unsafe audit records.
- [x] 4.3 Define the `ContextPack` structure with default 1-hop facts and controlled 2-hop expansion.
- [x] 4.4 Define evidence fields for every fact: source tool, source version, schema version, file hash, span, confidence, and source commit.
- [x] 4.5 Define the impact-set workflow for cross-module signature changes.

## 5. Skeleton-First `flashDB_rust`

- [x] 5.1 Define the `flashDB_rust` crate layout with `config`, `types`, `flash`, `port`, `format`, `kvdb`, `tsdb`, `ffi`, and `cli` modules.
- [x] 5.2 Define the Rust-native safe API surface and isolate any C ABI compatibility behind an explicit `ffi` layer.
- [x] 5.3 Define a CLI smoke executable for host validation, fixture replay, and C/Rust differential test execution.
- [x] 5.4 Define host memory and file-mode storage backends for the first milestone.
- [x] 5.5 Define deferred scope for FAL, RTOS, Zephyr, hardware ports, complete macro matrices, and full C ABI compatibility.

## 6. Compile Self-Healing

- [x] 6.1 Define the `cargo check --message-format=json` parser and structured rustc error-stack model.
- [x] 6.2 Define error classifiers for `E0308`, `E0499`, `E0502`, `E0382`, `E0277`, `E0599`, missing imports, cfg/feature errors, lifetime errors, unsafe/layout errors, and semantic test failures.
- [x] 6.3 Define the `PatchPlan` contract with files, spans, reason, expected error delta, risk, rollback id, and AI usage flag.
- [x] 6.4 Define deterministic repair rules that run before AI, including type mapping, borrow-scope narrowing, newtype/slice wrapping, feature cfg repair, and import repair.
- [x] 6.5 Define retry limits, rollback behavior, and debt records for failed self-healing attempts.

## 7. Semantic Equivalence and Test Generation

- [x] 7.1 Define C oracle and C2Rust baseline differential harness requirements.
- [x] 7.2 Define Rust unit tests for CRC, alignment, header/blob encoding, status tables, and address calculations.
- [x] 7.3 Define Rust integration tests for KVDB set/get/delete/iterate/gc/reopen and basic TSDB append/query/count/status.
- [x] 7.4 Define host file-mode persistence fixtures and golden flash image comparisons.
- [x] 7.5 Define `proptest` strategies for key/value sizes, capacity boundaries, write granularity, CRC errors, and corrupted images.
- [x] 7.6 Define `cargo-fuzz` targets for header/blob decoding and sector-state parsing.
- [x] 7.7 Define coverage and performance smoke gates using `cargo llvm-cov nextest` and Criterion or equivalent Rust benchmarks.

## 8. Cache Policy and Performance

- [x] 8.1 Define Agent-side cache keys for build traces, source facts, context packs, C2Rust artifacts, rustc classifications, test results, coverage results, fuzz metadata, and AI candidates.
- [x] 8.2 Define cache invalidation rules for source commit, file hash, macro/feature matrix, command arguments, tool versions, context schema version, and prompt/model metadata.
- [x] 8.3 Define the rule that cached AI output is only a candidate and must pass compile, test, equivalence, unsafe, and version gates.
- [x] 8.4 Define runtime cache boundaries for `flashDB_rust`: bounded, observable, disable-able, and semantically transparent.
- [x] 8.5 Define runtime cache invalidation on write, erase, format, GC, reopen, backend replacement, feature/config changes, and failed storage operations.
- [x] 8.6 Define cache performance gates: hit rate, invalidation count, memory budget, flash operation counts, scenario latency, and cache-enabled versus cache-disabled differential tests.

## 9. Unsafe Budget and Safe API Audit

- [x] 9.1 Define the unsafe budget numerator and denominator for first-party non-test Rust code.
- [x] 9.2 Define the unsafe whitelist for `ffi`, flash raw read/write, persistent layout conversion, required `#[repr(C)]` interop, and evidence-approved callback/union/allocator boundaries.
- [x] 9.3 Define unsafe ledger fields: file, span, category, reason, alternative considered, tests covering it, and source evidence.
- [x] 9.4 Define safe API checks that reject raw pointers in Rust-native public interfaces.
- [x] 9.5 Define failure behavior when a patch adds unregistered unsafe or increases unsafe above 10%.

## 10. First Milestone Scope

- [x] 10.1 Define the first implementation milestone around host-verifiable FlashDB behavior, not full project migration.
- [x] 10.2 Include memory backend for deterministic tests and file-mode backend for persistence smoke tests.
- [x] 10.3 Include KVDB string/blob set, get, delete, iterate, GC, and reopen behavior.
- [x] 10.4 Include basic TSDB append, query, count, and status behavior.
- [x] 10.5 Exclude hardware flash, FAL, RTOS/Zephyr ports, full C sample migration, and complete C ABI compatibility from the first milestone.

## 11. Validation

- [x] 11.1 Run `openspec status --change "design-c2rust-migration-agent"` and confirm proposal, design, specs, and tasks are complete.
- [x] 11.2 Run `openspec validate "design-c2rust-migration-agent" --strict` and fix all reported issues.
- [x] 11.3 Run `openspec list --json` and confirm the change is visible and not archived.
- [x] 11.4 Review generated artifacts for placeholders, contradictions, missing version records, missing scenarios, and non-bilingual user-facing content.
- [x] 11.5 Summarize the ready-to-apply change and list the created artifacts for the user.
