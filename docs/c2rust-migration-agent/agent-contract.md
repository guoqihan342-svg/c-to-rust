英文镜像见 `agent-contract.en.md`。

# C2Rust Migration Agent Contract

中文说明：本文定义给 OpenCode、Codex 或其他智能体调用的迁移 Agent 契约。目标是少 token、安全、快、可追溯，并允许多个有边界的子智能体并行工作。

English summary: this is the runtime contract for OpenCode, Codex, or other agents to run the C-to-Rust migration workflow.

## Entrypoints

OpenCode entry:

```bash
c2rust-migrator --phase <phase> --change design-c2rust-migration-agent --input request.json
```

Codex or generic agent entry:

```bash
openspec status --change "design-c2rust-migration-agent" --json
openspec instructions apply --change "design-c2rust-migration-agent" --json
c2rust-migrator --phase <phase> --input request.json
```

Phases:

- `propose`: create or update OpenSpec proposal artifacts.
- `plan`: produce concrete task slices, owners, gates, and rollback points.
- `index`: build SQLite/JSONL context from C, Rust, build, test, and error facts.
- `skeleton`: create a compilable `flashDB_rust` crate before function-body migration.
- `migrate`: migrate one bounded slice with impact-set approval.
- `repair`: run compile/test self-healing through PatchPlan.
- `verify`: run compile, tests, differential checks, unsafe audit, cache gates, and performance smoke.
- `audit`: review evidence, unsafe ledger, cache correctness, version records, and traceability.
- `archive`: archive a completed OpenSpec change only after all gates pass.

Version manifest gate:

```bash
flashdb-rust version-manifest --report validation/evidence/flashdb/<slice>-version-manifest.json
```

The audit phase MUST compare this manifest with cache metadata before accepting cached ContextPacks, PatchPlans, C oracle reports, schema-aware diffs, or AI-generated candidate patches.

中文：每个 L3 切片在实现前必须生成 `version-manifest`，并把 manifest path/hash 放入最终证据。若版本 manifest 中的源码 commit、crate version、Cargo.lock hash、schema version、toolchain version 或 feature matrix 与缓存记录不一致，Agent 必须先失效缓存或重新生成证据。

## Runtime Input

```json
{
  "runtime": "codex",
  "phase": "migrate",
  "change": "design-c2rust-migration-agent",
  "target_repo": "sources/FlashDB",
  "output_crate": "flashDB_rust",
  "source_commit": "93d175549da579b8abac07bd175ce4c3f9dde829",
  "context_schema_version": "0.1.0",
  "allowed_paths": [
    "flashDB_rust",
    "docs/c2rust-migration-agent"
  ],
  "context_pack": {
    "target": "kvdb.set",
    "depth": 1,
    "max_tokens": 12000
  }
}
```

Required input fields: `runtime`, `phase`, `change`, `target_repo`, `output_crate`, `source_commit`, `context_schema_version`.

Optional fields: `allowed_paths`, `context_pack`, `feature_matrix`, `ai_policy`, `cache_policy`, `verification_profile`.

Version fields:

- `version_manifest_path`: path to the current per-slice version manifest generated before edits.
- `agent_contract_version`: current agent contract version; initial value `0.1.0`.
- `context_schema_version`: context store schema version; initial value `0.1.0`.
- `patch_plan_schema_version`: PatchPlan schema version; initial value `0.1.0`.
- `fixture_schema_version`: fixture schema version; initial value `1`.
- `evidence_schema_version`: evidence schema version; initial value `1`.

## Runtime Output

```json
{
  "status": "patched",
  "artifacts": [
    "flashDB_rust/src/kvdb.rs"
  ],
  "patch_plan": {
    "id": "patch-0007",
    "risk": "medium",
    "ai_used": false
  },
  "verification": {
    "cargo_check": "passed",
    "cargo_test": "passed",
    "differential": "passed"
  },
  "version_manifest": {
    "path": "validation/evidence/flashdb/<slice>-version-manifest.json",
    "hash": "<sha256-or-recorded-hash>",
    "agent_contract_version": "0.1.0",
    "context_schema_version": "0.1.0",
    "patch_plan_schema_version": "0.1.0"
  },
  "unsafe_budget": {
    "ratio": 0.04,
    "unregistered_unsafe": 0
  },
  "cache_keys": [
    "source:93d1755",
    "context-schema:0.1.0"
  ],
  "rollback_id": "good-0006",
  "next_phase": "verify"
}
```

## Subagent Policy

Parallelism is allowed by default for independent work:

- Read-only analysis can run in parallel: C2Rust baseline study, FlashDB scope inspection, paper/design review, test strategy, unsafe audit planning.
- Verification can run in parallel when it does not mutate shared files: formatting, tests, coverage, fuzz smoke, diff checks, artifact review.
- Disjoint-write implementation can run in parallel only when owner, allowed paths, rollback id, and merge order are explicit.

Parallel edits are forbidden for:

- shared public API files
- `Cargo.toml` and lockfiles
- context schema migrations
- unsafe ledger
- generated golden fixtures
- files currently under compile self-healing

The orchestrator merges subagent outputs. Subagents should return evidence, not directly rewrite shared design contracts unless ownership is assigned.

## AI Policy

The Agent uses deterministic rules first. AI is allowed only for low-certainty diagnosis or candidate generation, such as ownership/lifetime design, cross-module signature impact, or semantic-difference explanation.

AI calls must use a bounded `ContextPack`. The output is never evidence. It must pass PatchPlan review, compile gates, semantic gates, unsafe gates, and version/cache gates.

## Async and Multithreading Policy

Agent orchestration may use bounded concurrency to save time. Runtime async or multithreaded behavior inside `flashDB_rust` is not part of the first milestone unless the C oracle shows equivalent ordering, persistence, reopen, and failure behavior.

First milestone rule:

- Prefer synchronous, deterministic storage operations.
- Add async wrappers later only as adapters over proven synchronous semantics.
- Add multithreaded tests later for API safety, but do not change storage ordering without a separate OpenSpec change.

## Bilingual Documentation Rule

User-facing docs should include Chinese as the primary explanation and English labels where useful. OpenSpec parser anchors must remain in English, including `## ADDED Requirements`, `### Requirement:`, `#### Scenario:`, `WHEN`, and `THEN`.
