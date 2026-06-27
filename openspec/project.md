# Project Context

## Purpose

This repository is an agent-facing C-to-Rust migration pipeline. It combines candidate generation with fail-closed validation so that Rust translation candidates are accepted only when evidence ties them back to the original C behavior.

Correctness comes from the C oracle, Rust replay, schema-aware diff, negative diff, unsafe ledger, version/config binding, and final verification evidence. Typed IR, C2Rust, LLM output, handwritten recipes, and generated Rust drafts are candidate sources only; they are not correctness sources.

## OpenSpec Workflow

1. Create a unique verb-led change ID under `openspec/changes/`.
2. Draft `proposal.md` for why the change exists, what is in scope, and expected impact.
3. Draft behavior-first delta specs under `openspec/changes/<change-id>/specs/<capability>/spec.md`.
4. Draft `design.md` for architecture decisions and implementation sequencing.
5. Draft `tasks.md` as the step-by-step checklist.
6. Validate the change with `openspec validate <change-id> --strict` when the OpenSpec CLI is available.
7. Do not implement product code until the proposal is reviewed and approved.

## Conventions

- Specs describe externally visible behavior with MUST/SHALL language and concrete scenarios.
- Preserve OpenSpec parser anchors such as `## Purpose`, `## Requirements`, `### Requirement:`, `#### Scenario:`, `WHEN`, `THEN`, and `AND`.
- Keep implementation details in `design.md` and delivery steps in `tasks.md`.
- Prefer small, reviewable stages with clear acceptance criteria.
- Every public claim must state whether it is L1 native baseline, candidate generation, L2 compile/safety evidence, L3 named-slice semantic evidence, or L4 refusal/accepted-evidence-authoritative binding.
- `config/competition-env/environment.json` is the default competition environment profile. New validation evidence generated for that profile must record the profile id and environment hash.
- Go and CMake are not default competition-environment dependencies. Gates that require missing tools must be optional, skipped with explicit evidence, or run in a declared compatible environment.

## Non-Goals

- Do not describe native C build success as Rust translation success.
- Do not let `route_decision.level=L0` imply semantic equivalence.
- Do not treat AI, C2Rust, typed IR, or string recipes as correctness evidence.
- Do not claim full FlashDB or real-project migration from curated named-slice evidence.
