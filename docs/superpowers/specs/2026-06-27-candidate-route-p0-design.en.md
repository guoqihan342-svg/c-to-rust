# Candidate Route P0 Design (Current Two-Route Revision)

This is the English mirror. The Chinese primary document is `2026-06-27-candidate-route-p0-design.md`.

## Current Conclusion

This file supersedes the earlier three-route P0 draft. The current typed IR candidate generation model has only two routes:

- `GenericTypedIr`: the generic typed IR emitter successfully generated a Rust candidate.
- `Unsupported`: the typed IR emitter failed closed, produced no Rust candidate, and preserved route metadata plus the fail-closed reason.

`DeprecatedLegacyCrc32`, the typed IR crc32 matcher, and the typed IR canned emitter have been removed from the current typed IR route model. The old string translator crc32 byte-cursor recognizer and canned Rust template have also been removed; raw string crc32 byte-cursor input now fails closed unless it first enters through clang-lowered typed IR + globals and reaches `GenericTypedIr`. The template must not be reintroduced as either a typed IR fallback or a legacy parser fallback.

## Goal

P0 makes typed IR candidate generation in `c2r-translator` return route metadata, and lets automatic-translation evidence bind that provenance through `route_decision.candidate_generation.typed_ir` and `validation_profile.candidate_generation`.

Successful state:

- Typed IR success records only `GenericTypedIr`.
- Unsupported typed IR records only `Unsupported` and does not generate a Rust draft.
- Candidate generation never sets semantic acceptance; `semantic_pass` must remain `false`.
- `generated_draft_semantic_pass` must remain `false` unless later independent validation gates explicitly promote that exact draft.

## Non-Goals

- Do not implement the full L0/L1/L2/L3/L4 evidence router.
- Do not let candidate route decide `validation_profile` or `semantic_pass`.
- Do not connect LLM candidate generation.
- Do not restore the old crc32 template as a typed IR fallback.
- Do not treat a generated Rust draft as semantic-pass evidence.
- Do not let `GenericTypedIr` override alias-risk floors already recorded in the pointer graph; P0 adds only the minimal route floor, not the full multi-route scheduler.

## Core Types

Current `translation_route.rs` contract:

```rust
pub enum CandidateRoute {
    GenericTypedIr,
    Unsupported,
}

pub enum CandidateGenerator {
    GenericTypedIrEmitter,
    None,
}

pub struct CandidateRouteDecision {
    pub route_id: String,
    pub route: CandidateRoute,
    pub candidate_generator: CandidateGenerator,
    pub reasons: Vec<CandidateRouteReason>,
    pub fallback: Option<CandidateRoute>,
    pub token_cost: u32,
    pub deprecated: bool,
    pub replacement: Option<CandidateRoute>,
    pub delete_when: Vec<String>,
    pub suggested_required_gates: Vec<String>,
}

pub struct EmittedRust {
    pub rust: String,
    pub route: CandidateRouteDecision,
}
```

`deprecated=false`, `replacement=None`, and `delete_when=[]` are the normal current state for the two-route model. The schema does not allow typed IR candidate routes to use `DeprecatedLegacyCrc32`.

## Route Rules

### GenericTypedIr

When the generic typed IR emitter succeeds:

- `route = GenericTypedIr`
- `candidate_generator = GenericTypedIrEmitter`
- `rust_draft_generated = true`
- `semantic_pass = false`
- `suggested_required_gates` may recommend `rustc_smoke` and `typed_ir_contract_tests`

### Unsupported

When the generic typed IR emitter fails closed:

- `route = Unsupported`
- `candidate_generator = None`
- `rust_draft_generated = false`
- `semantic_pass = false`
- `unsupported_reason` preserves the fail-closed detail
- `suggested_required_gates` may include `manual_review`

## candidate_generation Evidence

`route_decision.candidate_generation` and `validation_profile.candidate_generation` use the same typed IR binding. The object in the profile must equal the object in the route decision.

```json
{
  "typed_ir": {
    "status": "generated",
    "source_artifact": {
      "path": "validation/evidence/.../l3-<slice>-clang-lowering-report.json",
      "sha256": "<sha256>",
      "status": "lowered"
    },
    "candidate_route": {
      "route_id": "generic-typed-ir",
      "route": "GenericTypedIr",
      "candidate_generator": "GenericTypedIrEmitter",
      "token_cost": 0,
      "deprecated": false
    },
    "readonly_globals": [],
    "readonly_globals_identity": {
      "count": 0,
      "names": [],
      "sha256": "<sha256>"
    },
    "rust_draft_generated": true,
    "semantic_pass": false
  }
}
```

For unsupported typed IR, `typed_ir.status = "unsupported"`, `candidate_route.route = "Unsupported"`, `rust_draft_generated = false`, and `unsupported_reason` records the failure detail.

Schema compatibility rule: `candidate_generation` remains optional for legacy route/profile evidence; once present, it must satisfy the current two-route typed IR contract. This preserves older evidence tests while rejecting new typed IR candidate evidence that reintroduces `DeprecatedLegacyCrc32` or claims `semantic_pass=true`.

## Relationship To Evidence Route Decisions

Typed IR `CandidateRouteDecision` only answers:

```text
Which generator produced this typed IR Rust candidate, or why was no candidate produced?
```

The evidence route decision in `validation/tools/auto_migrate.py` still answers:

```text
What are this slice's candidate-generation path, validation profile, and evidence-binding state?
```

They must not be mixed:

- Candidate route does not set acceptance.
- Candidate route does not project L4/refuse semantics and does not override `alias_blocked`, `requires_noalias_contract`, or unknown pointer-ownership floors.
- Generated Rust draft is candidate evidence only.
- Semantic acceptance remains owned by C oracle, Rust replay, schema diff, negative diff, unsafe ledger, final verification, and related gates.

The current route-decision risk floor is intentionally small:

- A generated `GenericTypedIr` candidate still records `candidate_generation.typed_ir` and a rationale entry.
- If the pointer graph records `alias_contract.decision="blocked"`, the route stays L3 and is not downgraded to L1.
- If the pointer graph records `requires_noalias_contract` or an `unknown_alias` risk, the route stays L2 and is not downgraded to L1.
- If any pointer ownership role is still `unknown`, the route stays L2.

## Verification Strategy

Minimum verification:

1. `translation_route.rs` enum contains only `GenericTypedIr` and `Unsupported`.
2. `clang-lowering-report.typed_ir_candidate` records `semantic_pass=false`.
3. `route_decision.candidate_generation.typed_ir` matches the typed IR candidate in the clang-lowering-report.
4. `validation_profile.candidate_generation` exactly matches the route decision.
5. The schema accepts legacy route/profile evidence without `candidate_generation`, but rejects new typed IR candidate evidence containing `DeprecatedLegacyCrc32` or `semantic_pass=true`.
6. A `GenericTypedIr` candidate must not override alias route floors: `requires_noalias_contract` / `unknown_alias` routes to L2, and `alias_blocked` routes to L3.

Suggested verification commands:

```powershell
python validation/tools/validate_auto_translation_evidence.py --target-id demo --slice-id call-expression
python validation/tools/validate_auto_translation_evidence.py --target-id flashdb --slice-id real-fdb-calc-crc32
```

Rust route-contract tests may still be run from the existing `crates/c2r-translator` suite; the route-floor checks should also run the typed IR route-signal tests in `validation.tools.test_auto_migrate`.
