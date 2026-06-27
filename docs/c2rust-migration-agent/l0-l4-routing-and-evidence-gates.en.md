# L0-L4 Routing, Evidence Flow, and Validation Gates

This document explains the design rationale behind `validation/tools/auto_migrate.py`'s L0-L4 route decision, evidence flow topology, and validation gates. Chinese original: `l0-l4-routing-and-evidence-gates.md`.

## 1. Overview

The automatic translation pipeline starts from a real C source function, passes through slice extraction, clang AST lowering, typed IR construction, and Rust candidate generation, and is finally gated by multiple validation layers before acceptance.

The pipeline is built on two intersecting axes:

- **Route axis (route decision)**: decides candidate generation path and context budget (L0-L4).
- **Validation axis (validation profile + evidence gates)**: decides which validation gates must pass for this run, and whether semantic acceptance is achieved.

These two axes are **independent but bound together**: route decision records "how the candidate was produced"; validation profile answers "can the produced candidate be accepted".

## 2. L0-L4 Route Definitions

```
L0: Catalog validation                              (catalog layer)
     or typed IR deterministic zero-token scalar route (translation candidate layer)

L1: Native C build and test smoke                  (baseline layer)
L2: Bounded migration slice compile + safety       (compile layer + boundary proof)
L3: Behavioral equivalence evidence                (semantic layer)
L4: Explicit translation refusal / accepted evidence authoritative
```

### 2.1 Two Kinds of L0

| | Catalog L0 | Translation L0 |
|---|---|---|
| Source | `validate-c-project-catalog.ps1` | `auto_migrate.py` |
| Meaning | catalog schema valid, targets reachable | scalar-only `GenericTypedIr` + `token_cost=0`, no AI/token route needed |
| Proves | catalog metadata integrity | candidate generation path is deterministic zero-token |
| Proves semantic? | No | No |

Translation L0 only classifies the typed IR candidate generation path. True semantic equivalence is determined by C oracle, Rust replay, schema diff, negative diff, unsafe ledger, and final verification.

### 2.2 Layer Descriptions

**L0 (Catalog)**: `projects.json` is valid JSON, at least 12 targets, required fields present. Optional remote HEAD probe reachable.

**L0 (Translation)**: slice has no pointer surface (scalar-only), typed IR emitter successfully generated `GenericTypedIr` candidate with `token_cost=0`. This is a deterministic translation path requiring no AI or additional token budget.

**L1**: pinned C checkout builds and runs a simple smoke test in an external workspace. Environment profile, build commands, and tool versions are recorded. L1 pass only proves C baseline reproducibility, not any Rust translation success.

**L2**: `auto_migrate.py` produces a Rust candidate, which passes Rust compilation check (`rustc` or `cargo check`). Pointer graph records pointer dependencies and alias risks. Unsafe ledger counts first-party non-test unsafe. Negative diff proves the diff gate catches intentional mismatches.

**L3**: full semantic equivalence evidence chain. C oracle is ground truth (real C harness output, golden fixture, or accepted C oracle report). Rust replay executes the Rust candidate against the same inputs and compares outputs. Schema-aware diff compares C oracle against Rust replay. Negative diff intentionally mutates one expected value and confirms diff failure. Final verification aggregates all gate results. Validation profile requires no skipped gates.

**L4**: two forms:
1. **refused**: route decision is L4/refused. `translator.kind=refuse`. `candidate_generation_allowed=false`. Examples: function signature mismatch, unresolvable pointer graph, unsupported environment.
2. **accepted evidence authoritative**: slice spec explicitly declares `claim_boundary.accepted_evidence_authoritative=true`. Route remains L4/refused, but semantic pass is bound to external accepted C oracle / Rust report / diff / negative diff / unsafe evidence, not generated draft.

## 3. Route Decision Logic

`auto_migrate.py`'s `route_level()` function decides the route level in this order:

### 3.1 Hard Refuse Conditions (highest priority)

The following conditions directly return L4/refused:
- slice spec has no `c_boundary` or function signature
- `--accept-existing-evidence` finds no bindable accepted evidence
- `fixture_contract` requires accepted C oracle but none present

### 3.2 Typed IR Candidate Signal

If `clang-lowering-report.json` has `typed_ir_candidate`:

- `status=generated` + `route=GenericTypedIr` + `rust_draft_generated=true`:
  - scalar-only and `token_cost=0`: returns L0 (deterministic zero-token candidate route)
  - has pointer surface or token_cost≠0: returns L1
- `status=unsupported`: preserves `unsupported_reason`, returns L2

Typed IR signal does not override alias risk floor (see 3.3).

### 3.3 Alias/Risk Floor

Before typed IR candidate routing, the pointer graph's alias state is checked:

- `alias_contract.decision=blocked`: stays L3
- `requires_noalias_contract` or `unknown_alias`: stays L2
- pointer ownership role is `unknown`: stays L2

These floors take priority over typed IR signal, preventing `GenericTypedIr` from incorrectly lowering alias-unsafe pointer translations to L0/L1.

### 3.4 Legacy Scalar/Pointer Heuristic (fallback)

When no typed IR candidate exists, old heuristics based on pointer graph surface analysis determine L0/L1/L2/L3/L4.

### 3.5 Accepted Evidence Authoritative Override

When `--accept-existing-evidence` is used and the slice spec declares `accepted_evidence_authoritative=true`, even if typed IR or old heuristic gives L4/refused, route policy still writes:
- `accepted_evidence_authoritative=true`
- `generated_draft_semantic_pass=false`
- `verification_profile=L4-accepted-evidence`

Semantic pass follows external accepted evidence binding, not generated draft.

## 4. Validation Profile

Validation profile determines which gates must pass for this run. Key fields:

- `profile`: e.g. `L0-dev`, `L1-dev`, `L2-dev`, `L3-dev`, `L4-dev`, `L4-accepted-evidence`
- `status`: `passed`, `blocked`, `incomplete`
- `gates`: each gate's required / actual / skipped status
- `generated_draft_semantic_pass`: whether the generated draft itself passed semantics. It must remain `false`; even when `final_verification.semantic_pass=true`, the semantic source is the accepted/named-slice evidence bundle, not the generated draft itself.

### 4.1 Gate Inventory

| Gate | Description | Required condition |
|------|-------------|-------------------|
| `c_oracle` | C oracle present with status `C_ORACLE_GENERATED` | L3 |
| `rust_report` | Rust replay report status `passed` | L3 |
| `schema_diff` | Schema-aware C/Rust diff status `passed` | L3 |
| `negative_diff` | Negative diff mutation correctly detected | L2-L3 |
| `unsafe_scan` | First-party non-test unsafe count ≤ threshold | L2-L3 |
| `candidate_generation` | Candidate generation path (typed IR, string, C2Rust baseline) | L2-L3 |
| `competition_environment` | Competition environment profile binding | L1, L3 |

### 4.2 Semantic Pass Decision

`semantic_pass_for_run()` rules (simplified):

1. All required gates have `required_actual_status` matching `required_expected_status`
2. `skipped_gates` is empty (no skipped but required gates)
3. Top-level `status=passed`
4. L4/refused defaults to not-passed, unless slice spec declares `accepted_evidence_authoritative=true`
5. `generated_draft_semantic_pass` must be false (generated draft does not claim semantics directly)
6. When L4/refused passes through `accepted_evidence_authoritative=true`, reports must bind `accepted_evidence_binding` and keep `generated_draft_semantic_pass=false`.

### 4.3 Profile-Route Relationship

```
route_decision       →   answers "where did the candidate come from, what budget"
validation_profile   →   answers "what gates must pass, did they pass"
semantic_pass        →   determined by profile + gates, not by route alone
```

Route is recorded as an artifact in the evidence flow; the validator cross-checks route-profile consistency during semantic pass validation.

## 5. Evidence Flow Topology

A complete auto-translation evidence directory contains these files, forming a cross-reference chain:

```
validation/evidence/<target>/auto-translation/<slice>/
├── l3-<slice>-translator-input.json          # Translator input
├── l3-<slice>-translation-plan.json          # Translation plan (rules, call_expressions)
├── l3-<slice>-type-map.json                  # C→Rust type mappings
├── l3-<slice>-cfg.json                       # Control flow graph
├── l3-<slice>-pointer-graph.json             # Pointer dependency graph (v2 with effect_graph)
├── l3-<slice>-rust-draft.rs                  # Rust candidate draft
├── l3-<slice>-rust-check.json                # Rust compilation check result
├── l3-<slice>-test-translation-generated.json# Rust replay execution result
├── l3-<slice>-c-oracle-status.json           # C oracle status (harness draft/compile/execute)
├── l3-<slice>-c-oracle-harness-draft.c       # C oracle harness draft
├── l3-<slice>-rust-report.json               # Rust replay report
├── l3-<slice>-diff.json                      # Schema-aware diff
├── l3-<slice>-negative-diff.json             # Negative diff
├── l3-<slice>-c2rust-baseline-manifest.json   # C2Rust baseline
├── l3-<slice>-route-decision.json            # Route decision
├── l3-<slice>-validation-profile.json        # Validation profile
├── l3-<slice>-auto-translation-manifest.json  # Auto translation manifest
├── l3-<slice>-auto-cache-metadata.json        # Cache metadata
├── l3-<slice>-evidence-manifest.json          # L3 evidence manifest
├── l3-<slice>-final-verification.json         # Final verification
├── l3-<slice>-clang-dry-run.json              # Clang dry-run (optional)
└── l3-<slice>-clang-lowering-report.json      # Clang lowering report (optional)
```

### 5.1 Reference Chain Consistency

Each artifact's key fields (sha256, status, path) are cross-referenced by multiple other artifacts. The validator checks:

1. **Manifest refs consistent**: `schema_diff.sha256`, `negative_diff.sha256` in auto manifest, L3 evidence manifest, and final verification match actual files.
2. **Route↔Profile consistent**: `route_decision` route level matches `validation_profile` profile type; `candidate_generation` content is identical on both sides.
3. **Cache identity consistent**: `cache_metadata` identities (baseline, route, profile, effect_graph, competition_environment) match actual artifact hashes.
4. **C Oracle binding consistent**: `c-oracle-status.accepted_oracle.sha256` and `auto_manifest.accepted_evidence_binding.path_sha256.c_oracle` both match the actual root C oracle file hash.

### 5.2 Global Dependency Tracking

If the slice spec has `c_boundary.direct_dependencies` with `kind=global`:
- context-pack, type-map, pointer graph, C oracle status, and harness draft must all declare the dependency
- cache metadata must include `global_dependency_identity`
- validator checks canonical object (including source_span, sha256, definition_status, linkage_requirement, semantic_status), not just name matching

### 5.3 Effect Graph (v2)

After `pointer-graph.schema.json` v2 upgrade, alias-sensitive read/write pointer graphs must include:
- `effect_graph.effects[]`: read/write effects for each pointer node
- `effect_graph.edges[]`: `requires_noalias` or `may_alias` edges for each alias risk
- `effect_graph_identity` in cache metadata
- Validator requires each alias risk to have a corresponding edge in the effect graph

Legacy v1 pointer graphs may omit effect_graph to preserve historical evidence.

### 5.4 Competition Environment Binding

Newly generated evidence must bind the competition environment profile:
- `validation_profile.competition_environment` records `profile_id`, path, and SHA256
- `cache_metadata.competition_environment_identity` records the same information
- `cache_input_fields` must include `competition_environment_identity`
- Validator requires consistency between the two locations

### 5.5 External Direct Callee Binding

When the slice spec declares `external_direct_callees`:
- plan `translation_summary.call_expressions` must contain corresponding call sites
- context-pack `direct_call_edges` must have corresponding call edges
- each declared callee must have a `call_edge_to_callee_binding`
- signature binding, source hash, stub status, and semantics verified must all be consistent
- Both default validator and semantic-pass validator execute this check
- This is evidence integrity hardening, not proof that external callee semantics are verified

## 6. Candidate Route vs Evidence Route Decision

This is the most easily misunderstood aspect of the entire pipeline. Their relationship:

| | Candidate Route | Evidence Route Decision |
|---|---|---|
| Defined in | `crates/c2r-translator/src/translation_route.rs` | `validation/tools/auto_migrate.py` |
| Meaning | Which generator produced the typed IR candidate? | What is the migration path and budget for the whole slice? |
| Fields | `CandidateRoute::GenericTypedIr` / `Unsupported` | `route_decision.level: L0-L4` |
| Decides semantic acceptance? | No. Always `semantic_pass=false` | No. Acceptance is decided by validation profile + gates |
| Recorded in | `clang-lowering-report.typed_ir_candidate` | `route-decision.json` |

Key principles:
- Candidate route only selects the candidate generation implementation, not semantic acceptance.
- Evidence route decision incorporates candidate provenance into route rationale, but alias/pointer risk floors take priority.
- Only when validation profile + gates all pass + no skipped required gate can semantic pass be claimed.

## 7. Fail-Closed Design Principles

The entire pipeline follows fail-closed principles: when uncertain, refuse rather than pretend success.

### 7.1 Translation Layer Fail-Closed

- typed IR emitter returns `IrEmitError` for unsupported IR nodes, generating no Rust
- Old crc32 matcher and canned template are deleted; crc32 IR without globals fails closed
- clang frontend records `unsupported_clang_stmt/expr/type` for unsupported AST nodes
- Array initializer element count mismatch, type mismatch, call/inc/dec operands all rejected
- `const void *` only maps to `&[u8]` in proven byte cursor scenarios

### 7.2 Validation Layer Fail-Closed

- Schema requires all required properties present
- `candidate_generation` in route and profile must be exactly identical
- `semantic_pass=true` is rejected in any candidate/draft evidence
- L4/refused disallows residual `candidate_generated`, `accepted_after_gates` and similar statuses
- `--require-semantic-pass` strongly checks sha256/status for all manifest refs
- Accepted C oracle file's actual hash must match both `c-oracle-status.accepted_oracle.sha256` and `auto_manifest.accepted_evidence_binding.path_sha256.c_oracle`

### 7.3 Environment Layer Fail-Closed

- Competition environment profile path and SHA256 must be recomputable
- Cache metadata and validation profile environment identities must be consistent
- `--skip-c-oracle` writes `skipped_by_flag` for compile execution, never fakes `C_ORACLE_GENERATED`
- Missing compiler writes `compiler_not_found`, never enters subprocess

## 8. Full Validation Commands

```powershell
# Translator Rust tests
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report

# Python tool tests
python -m unittest validation.tools.test_auto_migrate validation.tools.test_validate_auto_translation_evidence

# Schema contract tests
python -m unittest validation.tools.test_template_schema_contracts

# OpenSpec full validation
openspec validate --all --strict

# FlashDB real-fdb-calc-crc32 evidence validation
python validation/tools/validate_auto_translation_evidence.py --target-id flashdb --slice-id real-fdb-calc-crc32 --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json

# FlashDB semantic pass validation
python validation/tools/validate_auto_translation_evidence.py --target-id flashdb --slice-id real-fdb-calc-crc32 --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --require-semantic-pass

# Full regression
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-full-regression.ps1 -Rounds 1 -SkipLongStress
```

## 9. Boundaries and Limitations

- L0-L4 routing only decides candidate generation path; "L3" does not equal "migration completed"
- Accepted evidence authoritative path is explicit opt-in and cannot bypass spec claim boundary
- FlashDB crc32 is the first case of real C source function going through typed IR → Rust draft → rustc smoke, but this does not mean all C subsets can be translated
- Pointer graph alias gate is a risk boundary, not a complete alias solver
- C2Rust baseline remains `candidate_context_only`, not a semantic equivalence proof
- `route_decision.level=L0` and catalog L0 are different evidence concepts and cannot substitute for each other
