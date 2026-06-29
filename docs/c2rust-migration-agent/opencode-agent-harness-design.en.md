# OpenCode Agent Harness Design

This document defines the competition-path OpenCode-only Agent Harness. It is not a new translator and not a general agent platform. It is the control layer between the existing `run_competition.py`, `auto_migrate.py`, evidence validators, and OpenCode multi-agent execution.

## Goal

P0 uses **SQLite as a scheduling-queue persistence layer**. SQLite records runs, agents, tasks, slices, artifacts, gates, events, leases, and merge plans. Long-term knowledge-base behavior is left as a future interface only.

Semantic acceptance is still decided only by on-disk evidence and validators:

- `validate_auto_translation_evidence.py --require-semantic-pass`
- `validate_competition_run_summary.py`
- `unsafe_budget.py`
- `openspec validate --all --strict`

Any `passed` field inside SQLite can only index validated evidence. It cannot replace evidence.

## Multi-Agent Roles

```mermaid
flowchart TD
    Lead["lead/orchestrator"] --> Router["router/planner"]
    Router --> WorkerA["slice worker A"]
    Router --> WorkerB["slice worker B"]
    WorkerA --> SummaryA["worker summary"]
    WorkerB --> SummaryB["worker summary"]
    SummaryA --> Validator["validator"]
    SummaryB --> Validator
    Validator --> Auditor["auditor"]
    Auditor --> Reporter["reporter"]
    Validator --> Evidence["on-disk evidence"]
    Evidence --> Final["final competition-run-summary.json"]
```

- `lead/orchestrator`: reads `CONTEXT.md`, the competition profile, and SQLite run state; creates runs, assignments, leases, and merge plans.
- `router/planner`: assigns only independent real C slices to workers; shared APIs, schemas, unsafe ledgers, golden fixtures, and Cargo metadata are not edited concurrently.
- `slice worker`: processes one or more independent slices and writes only under `target/competition-out/workers/<worker-id>/`.
- `validator`: reads worker summaries and aggregates them with `--worker-summary`; its final verdict is the only accepted run-level verdict.
- `auditor`: checks proof class, artifact roots, paths/hashes, refused/blocked/failed classification, and unsafe/cache/version boundaries.
- `reporter`: writes human-facing summaries without expanding capability claims.

## SQLite State Store

Default location:

```text
target/competition-out/state/opencode-agent-harness.sqlite3
```

Lifecycle:

- Runtime artifact, not committed by default.
- Schema/migration files and docs may be committed; `.sqlite3` files are not committed.
- For audits, export `target/competition-out/summary/harness-db-manifest.json` as a diagnostic artifact only.

Core tables:

| Table | Purpose |
|---|---|
| `runs` | Run id, out-root, proof class, profile hash, final gate, and summary hash. |
| `agents` | OpenCode lead/worker/validator roles and isolated output roots. |
| `agent_tasks` | Worker tasks, phase, attempt, status, allowed paths, and error keys. |
| `slices` | Target/slice/source/function/source commit/slice spec hash. |
| `candidates` | typed IR, C2Rust, legacy compatibility, and future candidates; candidates are not semantic acceptance. |
| `gates` | environment, auto_migrate, semantic validator, unsafe, OpenSpec, and summary-validator gates. |
| `artifacts` | Repo-relative artifact path, sha256, kind, and semantic role. |
| `artifact_links` | Manifest/cache/final-verification reference edges. |
| `events` | Mirror of `commands.jsonl`, auto-translation events, and harness events. |
| `leases` | Slice/out-root/shared-resource lease owner, heartbeat, and fencing token. |
| `context_packs` | ContextPack inputs, hashes, schema/profile/source commit bindings. |
| `repair_hints` | Diagnostic suggestions for blocked/refused slices; not evidence. |
| `metrics` | Recomputable statistics; not a fact source. |

## Directories And Isolation

```text
target/competition-out/
  state/opencode-agent-harness.sqlite3
  harness/
    assignments/<worker-id>.json
    assignments/<worker-id>-request.json
    merge-plan.json
  workers/<worker-id>/
    evidence/
    slice-specs/
    summary/competition-run-summary.json
    logs/commands.jsonl
  summary/competition-run-summary.json
  logs/commands.jsonl
```

Each worker must use a distinct `--out-root`. Final aggregation reads worker summaries only:

```bash
python validation/tools/run_competition.py \
  --worker-summary target/competition-out/workers/worker-a/summary/competition-run-summary.json \
  --worker-summary target/competition-out/workers/worker-b/summary/competition-run-summary.json \
  --out-root target/competition-out \
  --proof-class local-simulation
```

## OpenCode Entrypoint

OpenCode can invoke the repo-local wrapper directly:

```bash
python scripts/c2rust-migrator.py --phase migrate --input target/competition-out/harness/assignments/worker-a-request.json
```

`request.json` can contain direct slice input:

```json
{
  "source_repo_root": "external/demo",
  "source_file": "src/demo.c",
  "function": "add_one",
  "target_id": "demo",
  "slice_id": "demo-add-one",
  "source_commit": "abc123",
  "compiler_command_source": "compile_commands.json",
  "include_paths": ["include"],
  "defines": ["DEMO=1"],
  "proof_class": "local-simulation",
  "out_root": "target/competition-out/workers/worker-a",
  "run_id": "run-demo-worker-a"
}
```

It can also contain worker-summary aggregation input:

```json
{
  "worker_summaries": [
    "target/competition-out/workers/worker-a/summary/competition-run-summary.json",
    "target/competition-out/workers/worker-b/summary/competition-run-summary.json"
  ],
  "proof_class": "local-simulation",
  "out_root": "target/competition-out",
  "run_id": "run-demo"
}
```

## Invariants

- Input must come from real C source slices; hand-written `c_source` is forbidden.
- Worker claims are not evidence; only disk evidence and validators count.
- SQLite is a ledger/cache/index, not an evidence database.
- C2Rust baseline is candidate context; `skipped`/`blocked` does not count as generated, accepted, or semantic pass.
- LLM candidates are not part of the P0 default path. If added in P2, they must record provider/model/prompt/input/output hashes and pass the same validation.
- MCP, Cron, daemon workers, and general Harness framework work are not P0.
