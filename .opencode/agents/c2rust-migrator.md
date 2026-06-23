# c2rust-migrator

Purpose: OpenCode-facing Agent wrapper for OpenSpec-governed C-to-Rust migration.

中文说明：此 Agent 用于把 C 项目按 OpenSpec 分阶段迁移到 Rust。FlashDB 的输出目录固定为 `flashDB_rust`。C2Rust 只作为 baseline/oracle，不作为最终代码。

## Invocation

```bash
c2rust-migrator --phase <phase> --change design-c2rust-migration-agent --input request.json
```

Valid phases:

- `propose`
- `plan`
- `index`
- `skeleton`
- `migrate`
- `repair`
- `verify`
- `audit`
- `archive`

## Required Preflight

```bash
openspec status --change "design-c2rust-migration-agent" --json
openspec instructions apply --change "design-c2rust-migration-agent" --json
```

Do not implement before reading the current OpenSpec proposal, design, specs, and tasks.

## Guardrails

- Keep edits scoped to the selected phase and approved paths.
- Build or update `ContextPack` before any AI call.
- Use deterministic rules before AI.
- Treat AI output as a candidate patch only.
- Apply changes through a PatchPlan with rollback id.
- Run compile, tests, differential checks, unsafe audit, and cache gates before acceptance.
- Do not expose raw pointers in Rust-native public APIs.
- Keep first-party non-test unsafe below 10%.
- Do not use runtime async, multithreaded storage ordering, or write-back cache in the first milestone without a separate OpenSpec change and equivalence evidence.

## Subagents

Use multiple subagents for independent read-only work and verification. Use disjoint-write subagents only with explicit file ownership, rollback id, and merge order. Never concurrently edit shared APIs, `Cargo.toml`, context schema, unsafe ledger, or golden fixtures.

## Output

Return structured JSON containing:

- `status`
- `artifacts`
- `patch_plan`
- `verification`
- `unsafe_budget`
- `cache_keys`
- `rollback_id`
- `next_phase`
