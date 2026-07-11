# c2rust-migration-agent

Purpose: generic Codex/OpenCode-compatible instructions for the C-to-Rust migration harness.

中文说明：该 Agent 设计给 Codex、OpenCode 或其他智能体使用。开发前读取 `docs/superpowers/specs/` 中相关设计、`docs/superpowers/plans/` 中相关计划，以及 canonical backlog `docs/c2rust-migration-agent/future-vision-and-mvp.md`。

## Preflight

1. 确认当前 source pin、slice boundary 和 competition proof class。
2. 读取相关 Superpowers spec/plan；没有可执行计划时先补最小计划。
3. 为每个改动定义正例、最近邻负例、回滚点和验证命令。
4. OpenCode competition worker 启动前必须通过 repo-owned preflight。

## Phase Workflow

1. `plan`: split work by module, test gate, risk, and rollback point.
2. `index`: build SQLite/JSONL facts and ContextPack inputs.
3. `skeleton`: create or preserve a compile-passing Rust boundary.
4. `migrate`: translate one approved real-source slice.
5. `repair`: parse concrete compiler/oracle failures and apply one bounded patch.
6. `verify`: run compile, Rust tests, C oracle, replay, diff, negative diff, unsafe, and profile gates.
7. `audit`: reject unproven claims and bind machine-readable evidence.
8. `report`: publish the accepted boundary, blockers, metrics, and next smallest step.

## Minimal Input

```json
{
  "runtime": "codex",
  "phase": "index",
  "target_repo": "sources/FlashDB",
  "output_crate": "flashDB_rust",
  "source_commit": "f9d0421315c564fb890a1b14eee77b290e0d7bbe",
  "context_schema_version": "0.1.0"
}
```

## Safety Rules

- Superpowers specs/plans and the canonical backlog define developer workflow.
- C2Rust, typed IR, and AI are candidate sources only.
- Cached AI output and chat text are not semantic evidence.
- Public Rust APIs stay safe and pointer-free unless a reviewed FFI boundary proves otherwise.
- Every unsafe site must be registered and verified.
- Every cross-module signature change needs an impact set.
- Every repair needs a bounded PatchPlan, rollback id, and revalidation.

## Parallel Work Rule

Open multiple agents for independent read-only analysis and isolated writes. Do not parallelize writes to shared APIs, Cargo metadata, context schema, unsafe ledger, or golden fixtures.
