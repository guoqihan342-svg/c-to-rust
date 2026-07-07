---
name: translation-route-governance
description: Use when modifying or reviewing C-to-Rust route/profile/final-verification evidence, candidate_set, selection_policy, candidate source labels, refusal classifications, coverage numerator claims, route-governance metrics, capability ledgers, or public milestone claims.
---

# Translation Route Governance

## Overview

Use this skill to keep translator route metadata, coverage accounting, and public claims aligned with the actual evidence boundary. It complements `translation-minimal-slice` and `close-translator-slice`; it does not replace tests, validators, or C/Rust semantic evidence.

## Checklist

1. Classify candidate sources separately: typed IR, C2Rust, LLM/OpenCode, legacy fallback, handwritten/native baseline, and accepted historical evidence must not be merged.
2. Preserve semantic boundaries: generated Rust, rustc success, unit tests, fixture replay, and route decisions are not `semantic_pass`. Semantic acceptance requires the declared slice's C oracle, Rust replay, schema-aware diff, negative diff, unsafe ledger, and final verification.
3. Protect the coverage numerator: count only translator-generated named slices that pass the relevant acceptance gate. Do not count native-build catalogues, handwritten skeletons, local simulations, or accepted evidence reused as context.
4. Check route governance fields: route level/status, hard gate, fallback/refusal summary, source span, unsupported construct, IR/lowering gap, oracle/fixture gap, and smallest next test must match the current artifact state.
5. Reopen bound artifacts before trusting them: validate repo-relative paths, sha256/status bindings, and schema fields. Treat drift, stale artifacts, copied summaries, and validator-owned ref mismatch as blockers.
6. Treat LLM output as candidate input only: record provider/model/version or equivalent label, prompt scope, input/output artifact hashes, applied/refused gate, and never use chat text as semantic evidence.
7. Keep public claims machine-readable: milestone packets and release notes must expose blockers, publishability, proof class, semantic gate, and translation coverage numerator explicitly.

## Never Include

Do not write or echo API keys, provider credentials, tokens, shell history, private competition host details, local absolute host paths, raw OpenCode runtime caches, or `.codex/skills/*` as competition archive inputs.
