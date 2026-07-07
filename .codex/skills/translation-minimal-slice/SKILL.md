---
name: translation-minimal-slice
description: Use when Codex needs to plan, implement, or verify a smallest useful translator-layer slice in this repository, especially c2r-translator changes, bounded C-to-Rust translation gaps, typed-IR lowering, route/refusal behavior, translator coverage evidence, or auto-translation validation artifacts.
---

# Translation Minimal Slice

## Overview

Use this skill to keep translator work small, evidence-first, and reversible. A slice is acceptable only when its boundary, current failure, translator change, and verification evidence all describe the same behavior.

This skill is repo-local developer guidance. Do not copy API keys, provider credentials, competition host settings, or judge configuration into it or into outputs derived from it.

## Slice Boundary

Define the smallest unit that changes one translator behavior:

- One C construct, AST/typed-IR node, lowering rule, route decision, refusal reason, or compile blocker.
- One fixture or real slice that demonstrates that behavior.
- One expected evidence upgrade, such as gap to covered, refused to candidate, candidate to verified unsafe baseline, or verified unsafe baseline to semantic pass.

Reject a slice that requires multiple unrelated constructs, broad route-policy rewrites, fixture weakening, oracle weakening, or changing unrelated validation artifacts.

## Standard Workflow

1. Inspect current state before editing.
   Read the relevant translator module, existing bounded translation tests, coverage matrix entries, route decisions, and evidence artifacts. Identify the authoritative source of truth before choosing files to change.

2. Record the current failure.
   Add or identify the focused failing test, coverage gap, route refusal, compile error, oracle/diff failure, or validation-profile blocker. If the current system already passes, narrow the slice or choose the next missing behavior.

3. Change the translator minimally.
   Prefer the local translator pattern already used near the target code. Do not add a generic framework unless it removes real duplication in the changed path. Keep source edits, fixtures, and evidence updates scoped to the declared slice.

4. Verify at the narrowest useful level.
   Start with focused Rust tests for `crates/c2r-translator`, then run the coverage or evidence validators that cover the changed claim. Broaden validation only when shared route behavior, evidence schemas, or user-facing claims changed.

5. Classify the result honestly.
   Generated Rust is candidate context only until C oracle, Rust replay, schema-aware diff, negative diff, unsafe ledger, and validation profile prove the declared semantic boundary. Keep accepted evidence separate from generated-draft semantic pass.

6. Leave resumable evidence.
   Report the exact slice boundary, changed paths, commands run, artifact paths, current status, and the next smallest step when the slice is still blocked.

## Verification Ladder

Choose commands from this ladder based on what changed:

```bash
cargo test --manifest-path crates/c2r-translator/Cargo.toml
python3 -B validation/tools/translator_coverage_matrix.py --matrix validation/translator-coverage-matrix.json
python3 -B -m unittest validation.tools.test_validate_test_translation_coverage
python3 -B -m unittest validation.tools.test_validate_auto_translation_evidence
python3 -B validation/tools/validate_auto_translation_evidence.py --target-id <target> --slice-id <slice> --slice-spec <path> --evidence-root validation/evidence --require-semantic-pass
git diff --check
```

Use `python3 -B` for durable repo docs and judge-facing command examples. If the active shell is Windows and only `python` is available, run the equivalent local command but do not publish the fallback as the canonical reproduction command.

## Evidence Boundaries

Use these labels consistently:

| Label | Meaning |
| --- | --- |
| `candidate_context_only` | Generated or translated code exists, but semantic acceptance is not proven. |
| `verified_unsafe_baseline` | Candidate compiles and has bound oracle/replay/diff evidence, but unsafe remains the accepted baseline. |
| `semantic_pass` | The declared slice boundary is proven by current oracle, replay, diff, negative, unsafe-ledger, and validation-profile evidence. |
| `blocked` | Tooling, external callee context, missing fixture, compile failure, or evidence mismatch prevents acceptance. |

Never claim `semantic_pass` from translator output, compile success, green unit tests, or accepted historical evidence alone.

## Common Mistakes

- Expanding translator coverage without updating `validation/translator-coverage-matrix.json` or bound evidence refs.
- Treating accepted evidence as generated translator coverage.
- Weakening a refusal, fixture, oracle, diff, unsafe budget, or validation profile to make a slice pass.
- Mixing unrelated route-policy, typed-IR, and safety-refactor work in one patch.
- Reporting a broad capability claim when only one construct or fixture was verified.

