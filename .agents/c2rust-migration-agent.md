# c2rust-migration-agent

Purpose: generic Codex/OpenCode-compatible instructions for the C-to-Rust migration Agent.

中文说明：该 Agent 设计给 Codex、OpenCode 或其他智能体使用。执行前必须先读取 OpenSpec 当前 change，并把每一步变成可验证、可回滚的小切片。

## Change

`design-c2rust-migration-agent`

## Preflight

```bash
openspec status --change "design-c2rust-migration-agent" --json
openspec instructions apply --change "design-c2rust-migration-agent" --json
```

If artifacts or tasks are missing, stop and repair the OpenSpec change before implementation.

## Phase Workflow

1. `propose`: create or revise proposal/spec/design/tasks.
2. `plan`: split work by module, test gate, risk, and rollback point.
3. `index`: build SQLite/JSONL facts and ContextPack inputs.
4. `skeleton`: create compile-passing `flashDB_rust`.
5. `migrate`: migrate one approved slice.
6. `repair`: parse rustc JSON error stacks and apply PatchPlan.
7. `verify`: run compile, Rust tests, differential oracle checks, unsafe audit, cache gates, and performance smoke.
8. `audit`: review evidence and reject unproven changes.
9. `archive`: archive only after OpenSpec and verification evidence pass.

## Minimal Input

```json
{
  "runtime": "codex",
  "phase": "index",
  "change": "design-c2rust-migration-agent",
  "target_repo": "sources/FlashDB",
  "output_crate": "flashDB_rust",
  "source_commit": "93d175549da579b8abac07bd175ce4c3f9dde829",
  "context_schema_version": "0.1.0"
}
```

## Safety Rules

- OpenSpec is the source of workflow truth.
- C2Rust is baseline/oracle only.
- AI is allowed only when deterministic rules are insufficient.
- Cached AI is not evidence.
- Public Rust APIs must be safe and pointer-free.
- Unsafe must be registered and below 10%.
- Every cross-module signature change needs an impact set.
- Every repair needs a PatchPlan and rollback id.

## Parallel Work Rule

Open multiple agents for read-only analysis and verification whenever tasks are independent. Do not parallelize writes to shared APIs, Cargo metadata, context schema, unsafe ledger, or golden fixtures.
