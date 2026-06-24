## 1. Evidence Contracts

- [x] 1.1 Define a reusable slice spec schema covering target id, slice id, L1 evidence, source commit, C files, signatures, build profile, fixture contract, Rust boundary, accepted metadata differences, and non-goals.
- [x] 1.2 Add `type-map` evidence schema and example for C-to-Rust primitive, struct, enum, pointer, integer-width, implicit-cast, and uncertainty mappings.
- [x] 1.3 Add `cfg` evidence schema and example for functions, basic blocks, edges, branches, returns, unsupported control-flow nodes, and source spans.
- [x] 1.4 Add auto-translation evidence conventions for `auto-translation-plan`, `auto-translation-events`, `ai-candidate-manifest`, `patch-events`, and `blocked-repairs`.
- [x] 1.5 Extend or wrap the existing L3 evidence manifest emitter so auto-translated slices reference context pack, type map, CFG, pointer graph, generated source provenance, oracle/replay/diff, unsafe, version, cache, and final verification artifacts.

## 2. Translator Core

- [x] 2.1 Create the bounded translator crate or module with a slice-level API driven by slice spec, build profile, and evidence context rather than raw `c_source` alone.
- [x] 2.2 Implement parsing/extraction for the MVP C subset: function signature, primitive declarations, assignments, returns, simple calls, if/while/for, and supported pointer input/output forms.
- [x] 2.3 Record clang/compile profile availability and treat unresolved typedef, macro, ABI, struct layout, implicit cast, or declaration ambiguity as unsupported evidence.
- [x] 2.4 Emit type-map, CFG, pointer graph decisions, unsupported node records, and translation rule ids before any Rust draft is accepted.
- [x] 2.5 Implement Rust draft generation for one pure-value function and one pointer-bearing out-parameter function while keeping public Rust boundaries safe by default.
- [x] 2.6 Add translator unit tests for supported expressions/statements, unsupported goto/switch behavior, type uncertainty, pointer graph emission, and unsafe budget accounting.

## 3. Oracle And Replay Generation

- [x] 3.1 Add `validation/tools/auto_migrate.py` or equivalent CLI that accepts `--slice-spec`, orchestrates translation, and writes all evidence under `validation/evidence/<target>/`.
- [x] 3.2 Generalize the existing libuv oracle generator pattern into a slice-spec-driven C oracle harness draft generator.
- [x] 3.3 Generate Rust replay test drafts from the same fixture contract and emit `test-translation` evidence linking C fixture cases to Rust assertions.
- [x] 3.4 Ensure local C oracle skips are recorded as `SKIPPED_LOCAL_NO_C_TOOLCHAIN` and are not counted as semantic pass.
- [x] 3.5 Add fixture-driven tests that prove the C oracle report and Rust replay report use the same fixture hash and source commit.

## 4. Compile Self-Healing

- [x] 4.1 Capture `cargo check --message-format=json` output for generated Rust drafts and normalize rustc errors into `rust-check` evidence.
- [x] 4.2 Implement PatchPlan generation with patch id, spans, files, reason, expected error delta, forbidden changes, rollback id, AI usage, and verification commands.
- [x] 4.3 Implement bounded automatic patch application for safe local syntax/type fixes with a default maximum of three repair rounds.
- [x] 4.4 Block and record repair candidates that edit oracle contracts, fixture expectations, accepted differences, public API outside the impact set, source slice boundaries, or unsafe budget policy.
- [x] 4.5 Add red/green tests for at least one compile failure that is self-healed and one forbidden repair that is blocked.

## 5. MVP Slice Validation

- [x] 5.1 Use the existing `libuv/ip4-addr` pointer-bearing slice as the first MVP target for auto-translation evidence, because it already exercises C string input, out parameter struct, pointer graph, oracle, replay, diff, and unsafe gates.
- [x] 5.2 Create a checked-in libuv slice spec and use it to regenerate context pack, type map, CFG, pointer graph, C oracle harness draft, Rust draft provenance, Rust replay test, and L3 evidence manifest.
- [x] 5.3 Add one pure-value regression slice such as `zlib/adler32` or `sqlite/varint` to ensure the translator path is not overfit to pointer-bearing code.
- [ ] 5.4 Run generated Rust replay tests, schema-aware diff, negative diff, unsafe scan, version manifest, cache metadata, and final verification for the MVP slices.
- [x] 5.5 Record known unsupported C constructs and non-goals in the slice summaries so the run does not overclaim C99 coverage.

## 6. AI Cache And Traceability

- [x] 6.1 Implement AI candidate manifest emission without requiring AI for the default local pipeline.
- [x] 6.2 Ensure prompts, when used, are bounded to slice spec, source spans, type/CFG/pointer excerpts, direct caller/callee facts, and current verification deltas.
- [x] 6.3 Add cache metadata keys for source commit, file hashes, slice spec hash, fixture hash, build profile hash, Cargo.lock hash, tool versions, schema versions, translator version, and command arguments.
- [x] 6.4 Add tests that cache drift invalidates context pack, type map, CFG, pointer graph, Rust draft, PatchPlan, oracle, diff, and summary reuse.

## 7. Documentation

- [x] 7.1 Document the bounded automatic translation workflow in Chinese and English for OpenCode/Codex/other agents.
- [x] 7.2 Document the supported C subset, blocked constructs, safe public API rule, raw pointer draft boundary, unsafe ledger rule, and semantic-equivalence limits.
- [x] 7.3 Document how the `F:\agent\codex\ctorustpaper\c-to-rust-翻译器嵌入方案.md` and `F:\agent\codex\ctorustpaper\c-to-rust-slice-自动化翻译管线方案.md` ideas were adopted, corrected, or deferred.
- [x] 7.4 Document operational commands for L1 input selection, auto migration, oracle generation, Rust replay, self-healing, evidence search, and final OpenSpec validation.

## 8. Verification

- [x] 8.1 Run translator crate formatting and unit tests.
- [x] 8.2 Run `cargo fmt -- --check`, targeted replay tests, `cargo test`, and `cargo run --bin emit_reports` for `validation/l2_slices`.
- [ ] 8.3 Generate or refresh accepted C oracle evidence for MVP slices in WSL/Linux/CI and prove `C_ORACLE_GENERATED` is present for semantic pass claims.
- [x] 8.4 Validate generated JSON evidence against all relevant schemas, including slice spec, type map, CFG, pointer graph, test translation, and L3 evidence manifest.
- [x] 8.5 Run `openspec validate add-bounded-auto-translation-pipeline --strict`.
- [x] 8.6 Run `openspec validate --all`.
- [x] 8.7 Run `git diff --check` and record any CRLF-only warnings separately from whitespace errors.
